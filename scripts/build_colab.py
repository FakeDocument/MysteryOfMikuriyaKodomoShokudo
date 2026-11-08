"""既存の全章JSONから、固定コミットの教材を取得するColabノートブックを生成する。"""

from __future__ import annotations

import argparse
import base64
import builtins
import hashlib
import io
import json
import keyword
import re
import subprocess
import textwrap
import unicodedata
import zipfile
from pathlib import Path
from typing import Any

import colab_assets

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "experiments/colab/MysteryOfMikuriyaKodomoShokudo-Colab.ipynb"
REPOSITORY = "FakeDocument/MysteryOfMikuriyaKodomoShokudo"
# 準備セルとフォームが使う名前は、回答欄の変数名にしない。
RESERVED_NAMES = frozenset(
    {"lab", "files", "json", "sys", "importlib", "ROOT", "_", "合言葉"}
)


def load_lesson() -> dict[str, Any]:
    return colab_assets.load_lesson(ROOT)


def head_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def source_commit() -> str:
    """配布版の取得先。セルと取得する教材の版を揃えるため、未コミット変更を拒否する。"""
    commit = head_commit()
    if has_source_changes(commit):
        raise ValueError(
            "教材・実行用ソースを先にコミットしてからNotebookを生成してください。"
        )
    return commit


def has_source_changes(commit: str) -> bool:
    changed = subprocess.run(
        [
            "git",
            "diff",
            "--quiet",
            commit,
            "--",
            *colab_assets.SOURCE_FILES,
            *colab_assets.SOURCE_DIRS,
        ],
        cwd=ROOT,
        check=False,
    )
    untracked = subprocess.check_output(
        [
            "git",
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            *colab_assets.SOURCE_FILES,
            *colab_assets.SOURCE_DIRS,
        ],
        cwd=ROOT,
        text=True,
    )
    return bool(changed.returncode or untracked.strip())


def cell(kind: str, identifier: str, source: str, form: bool = False) -> dict[str, Any]:
    if len(identifier) > 64:
        digest = hashlib.sha256(identifier.encode()).hexdigest()[:12]
        identifier = identifier[:51] + "-" + digest
    result = {
        "cell_type": kind,
        "id": identifier,
        "metadata": {"id": identifier, **({"cellView": "form"} if form else {})},
        "source": source.splitlines(keepends=True),
    }
    if kind == "code":
        result.update(execution_count=None, outputs=[])
    return result


def field_variable(label: str, index: int, used: set[str]) -> str:
    """Colabフォームの欄名として表示される変数名を、回答欄のラベルから決める。"""
    # Pythonは識別子をNFKC正規化するため、生成側でも揃えて実行時の名前と一致させる。
    name = re.sub(r"\W+", "_", unicodedata.normalize("NFKC", label)).strip("_")
    usable = (
        name.isidentifier()
        and not keyword.iskeyword(name)
        and not hasattr(builtins, name)
        and name not in RESERVED_NAMES
        and name not in used
    )
    return name if usable else f"answer_{index + 1}"


def block_cells(block: dict[str, Any], chapter_id: str) -> list[dict[str, Any]]:
    kind = block["type"]
    if kind not in {"dialogue", "document", "evidence_note", "questions", "report"}:
        raise ValueError(f"未対応のブロック種別です: {kind}")
    # Colabではノートブック自体に記録できるため、調査メモの欄は設けない。
    if kind == "evidence_note":
        return []
    identifier = f"{chapter_id}-{block['id']}"
    title = block.get("heading", {}).get("title", kind).replace("\n", " ")
    if kind != "questions":
        return [
            cell(
                "code",
                identifier,
                f"# @title {title}\nlab.show_block({chapter_id!r}, {block['id']!r})\n",
                form=True,
            )
        ]
    # 設問群の見出しは題名へ含め、設問の表示から回答までを1セルで行う。
    return [
        question_cell(question, f"{identifier}-{question['id']}", title)
        for question in block["items"]
    ]


def question_cell(
    question: dict[str, Any], identifier: str, title: str
) -> dict[str, Any]:
    for child in question["blocks"]:
        if child["type"] not in {"hints", "dialogue"}:
            raise ValueError(f"未対応の設問内ブロックです: {child['type']}")
    fields = question.get(
        "answer_fields",
        [
            {
                "id": "answer",
                "label": "回答",
                "input_mode": question.get("input_mode", "text"),
                "placeholder": question.get("placeholder", ""),
            }
        ],
    )
    label = question["label"].replace("\n", " ")
    lines = [f"# @title {title}（{label}）"]
    # フォームでは @markdown 行が入力欄の上に出るため、何を答えるかを先に示す。
    lines.extend(f"# @markdown {line}" for line in question["prompt"].splitlines())
    values = []
    used: set[str] = set()
    for index, field in enumerate(fields):
        parameter = (
            json.dumps(["", *field["options"]], ensure_ascii=False)
            if field.get("input_mode") == "select"
            else '{type:"string"}'
        )
        field_label = field["label"].replace("\n", " ")
        description = field_label
        if field.get("input_mode") == "datetime":
            # Colabのフォームに日時の選択欄はないため、入力形式を示す。
            description += "（YYYY-MM-DDTHH:MM）"
        elif field.get("placeholder") not in {None, "", field["label"]}:
            description += f"（{field['placeholder']}）"
        variable = field_variable(field["label"], index, used)
        used.add(variable)
        # 変数名だけで欄名と入力形式が伝わる場合は、説明行を省く。
        if variable != description:
            lines.append(f"# @markdown {description}")
        lines.append(f'{variable} = "" # @param {parameter}')
        values.append(f"{field['id']!r}: {variable}")
    lines.append(f"_ = lab.ask({question['id']!r}, {{{', '.join(values)}}})")
    return cell("code", identifier, "\n".join(lines) + "\n", form=True)


def embedded_archive(source: Path = ROOT) -> bytes:
    """作業ツリーの取得対象を、GitHubのZIPと同じ1階層付きでZIP化する。

    セルも作業ツリーから生成するため、未コミット変更を含めても両者の版は揃う。
    .gitignore の対象は含めない。
    """
    listed = subprocess.check_output(
        [
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            *colab_assets.SOURCE_FILES,
            *colab_assets.SOURCE_DIRS,
        ],
        cwd=source,
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(set(listed.decode().split("\0")) - {""}):
            path = source / name
            # 展開側でも拒否されるため、生成時点で止めて原因を示す。
            if path.is_symlink():
                raise ValueError(f"取得対象にシンボリックリンクがあります: {name}")
            # 削除済みでまだコミットしていないファイルは含めない。
            if path.is_file():
                archive.write(path, "snapshot/" + name)
    return buffer.getvalue()


def embedded_state(commit: str, changed: bool, data: bytes) -> str:
    """埋め込み版で試している教材の生成元を、後から照合できる形で示す。"""
    revision = "未コミット変更あり" if changed else "未コミット変更なし"
    digest = hashlib.sha256(data).hexdigest()[:12]
    return f"HEAD {commit[:12]}・{revision}・ZIP sha256 {digest}"


def build_notebook(
    commit: str, embedded: str | None = None, state: str | None = None
) -> dict[str, Any]:
    """embedded にbase64の教材ZIPを渡すと、GitHubへ通信しない準備セルにする。"""
    lesson = load_lesson()
    setup = "# @title 調査環境を準備する\n"
    setup += Path(colab_assets.__file__).read_text(encoding="utf-8")
    setup += f"\nSOURCE_COMMIT = {commit!r}\nREPOSITORY = {REPOSITORY!r}\n"
    if embedded is None:
        bootstrap = "bootstrap_runtime(ROOT, REPOSITORY, SOURCE_COMMIT)"
    else:
        setup += f"EMBEDDED_ARCHIVE = {embedded!r}\n"
        if state is not None:
            setup += (
                f"EMBEDDED_STATE = {state!r}\nprint('埋め込み教材:', EMBEDDED_STATE)\n"
            )
        bootstrap = "bootstrap_embedded(ROOT, EMBEDDED_ARCHIVE)"
    setup += textwrap.dedent("""\
        import importlib, sys
        ROOT = Path("/content/mikuriya-colab")
        BOOTSTRAP
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import colab_web
        importlib.reload(colab_web)
        import colab_render
        importlib.reload(colab_render)
        import colab_lab
        importlib.reload(colab_lab)
        lab = colab_lab.Lab(ROOT)
        lab.install_tools()
        lab.start()
        """).replace("BOOTSTRAP", bootstrap)
    origin = (
        "固定した版の教材をGitHubから取得し"
        if embedded is None
        else "ノートブックに同梱した教材を展開し"
    )
    cells = [
        cell(
            "markdown",
            "introduction",
            f"""# 御厨こども食堂の謎：Colab試作

1. Googleアカウントでログインし、ランタイムは **CPU** を選びます。
2. 「調査環境を準備する」の左にある ▶ を押し、準備完了まで待ちます。
3. 上から順にセルを実行し、会話と設問を読み進めます。
4. 設問のセルでは、回答欄の上に問われている内容が表示されます。実行するとヒントを表示し、回答欄に入力してから実行すると判定します。
5. 調査には「＋コード」でセルを追加し、自分でコマンドを入力します。シェルコマンドの先頭には `!` を付けます。
6. 正解すると続くセルを読めるようになります。先に実行して表示されなかったセルは、正解後に再実行してください。

標的環境は寿司屋のWeb・Sambaを起動する試作です。後続章のWebメールや政府側サービスのColab対応は準備中です。

準備セルで、{origin}、必要なツールを導入します。
""",
        ),
        cell("code", "setup", setup, form=True),
        cell(
            "markdown",
            "resume-guide",
            """## 調査の中断・再開

章の区切りまで進むと合言葉が表示されます。
同じランタイムなら、準備セルを再実行しても正解済みの設問を引き継げます。
ランタイムが削除されたときは、準備セルを実行してから、次のセルに合言葉を入力して実行します。
合言葉を忘れたときは、空欄のまま実行すると、いまの進捗の合言葉を確認できます。
""",
        ),
        cell(
            "code",
            "resume-progress",
            '# @title 合言葉で再開する\n# @markdown 区切りで表示された合言葉をひらがなで入力します。\n合言葉 = "" # @param {type:"string"}\n_ = lab.resume(合言葉)\n',
            form=True,
        ),
    ]
    for chapter in lesson["chapters"]:
        chapter_id = chapter["id"]
        title = chapter["nav_title"].replace("\n", " ")
        # 見出しセルでColabの目次と折りたたみの単位を章ごとにする。
        cells.append(cell("markdown", chapter_id + "-section", f"## {title}\n"))
        for block in chapter["blocks"]:
            cells.extend(block_cells(block, chapter_id))
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "colab": {"name": DEFAULT_OUTPUT.name, "provenance": []},
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "cells": cells,
    }


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--embed",
        action="store_true",
        help="作業ツリーの教材をZIPで埋め込み、GitHubへ通信しない検証用Notebookを生成する",
    )
    arguments = parser.parse_args(argv)
    if not arguments.embed:
        arguments.output = arguments.output or DEFAULT_OUTPUT
        return arguments
    # 検証用の埋め込み版で、配布用Notebookを上書きしない。
    if arguments.output is None:
        parser.error("--embed には --output で配布用以外の出力先を指定してください。")
    if arguments.output.resolve() == DEFAULT_OUTPUT.resolve():
        parser.error("--embed の出力先に配布用Notebookは指定できません。")
    return arguments


def main() -> None:
    arguments = parse_arguments()
    embedded = state = None
    if arguments.embed:
        commit = head_commit()
        data = embedded_archive()
        embedded = base64.b64encode(data).decode("ascii")
        state = embedded_state(commit, has_source_changes(commit), data)
    else:
        commit = source_commit()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(
            build_notebook(commit, embedded, state), ensure_ascii=False, indent=1
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"ノートブックを生成しました: {arguments.output}")


if __name__ == "__main__":
    main()
