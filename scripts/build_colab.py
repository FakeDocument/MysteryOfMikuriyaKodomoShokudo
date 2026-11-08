"""既存の全章JSONから、固定コミットの教材を取得するColabノートブックを生成する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import textwrap
from pathlib import Path
from typing import Any

import colab_assets

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "experiments/colab/MysteryOfMikuriyaKodomoShokudo-Colab.ipynb"
REPOSITORY = "FakeDocument/MysteryOfMikuriyaKodomoShokudo"


def load_lesson() -> dict[str, Any]:
    return colab_assets.load_lesson(ROOT)


def source_commit() -> str:
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
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
    if changed.returncode or untracked.strip():
        raise ValueError(
            "教材・実行用ソースを先にコミットしてからNotebookを生成してください。"
        )
    return commit


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


def block_cells(block: dict[str, Any], chapter_id: str) -> list[dict[str, Any]]:
    kind = block["type"]
    if kind not in {"dialogue", "document", "evidence_note", "questions", "report"}:
        raise ValueError(f"未対応のブロック種別です: {kind}")
    identifier = f"{chapter_id}-{block['id']}"
    title = block.get("heading", {}).get("title", kind).replace("\n", " ")
    cells = [
        cell(
            "code",
            identifier,
            f"# @title {title}\nlab.show_block({chapter_id!r}, {block['id']!r})\n",
            form=True,
        )
    ]
    if kind == "evidence_note":
        source = (
            "# @title 調査メモを保存する\n"
            'evidence_note = lab.lesson.note # @param {type:"string"}\n'
            f"lab.save_note({chapter_id!r}, evidence_note)\n"
        )
        cells.append(cell("code", identifier + "-input", source, form=True))
    if kind == "questions":
        for question in block["items"]:
            for child in question["blocks"]:
                if child["type"] not in {"hints", "dialogue"}:
                    raise ValueError(f"未対応の設問内ブロックです: {child['type']}")
            question_id = question["id"]
            cells.append(
                cell(
                    "code",
                    identifier + "-" + question_id,
                    f"# @title 設問とヒントを表示する\nlab.show_question({question_id!r})\n",
                    form=True,
                )
            )
            fields = question.get(
                "answer_fields",
                [
                    {
                        "id": "answer",
                        "label": "回答",
                        "input_mode": question.get("input_mode", "text"),
                    }
                ],
            )
            lines = ["# @title 回答を記録する"]
            values = []
            for index, field in enumerate(fields):
                parameter = (
                    json.dumps(["", *field["options"]], ensure_ascii=False)
                    if field.get("input_mode") == "select"
                    else '{type:"string"}'
                )
                label = field["label"].replace("\n", " ")
                if field.get("input_mode") == "datetime":
                    label += "（YYYY-MM-DDTHH:MM）"
                lines.extend(
                    [
                        f"# @markdown {label}",
                        f'answer_{index} = "" # @param {parameter}',
                    ]
                )
                values.append(f"{field['id']!r}: answer_{index}")
            lines.append(f"_ = lab.answer({question_id!r}, {{{', '.join(values)}}})")
            cells.append(
                cell(
                    "code",
                    identifier + "-" + question_id + "-answer",
                    "\n".join(lines) + "\n",
                    form=True,
                )
            )
    return cells


def build_notebook(commit: str) -> dict[str, Any]:
    lesson = load_lesson()
    setup = "# @title 1. 調査環境を準備する\n"
    setup += Path(colab_assets.__file__).read_text(encoding="utf-8")
    setup += f"\nSOURCE_COMMIT = {commit!r}\nREPOSITORY = {REPOSITORY!r}\n"
    setup += textwrap.dedent("""\
        import importlib, sys
        if "lab" in globals():
            lab.stop()
        ROOT = Path("/content/mikuriya-colab")
        bootstrap_runtime(ROOT, REPOSITORY, SOURCE_COMMIT)
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import colab_render
        importlib.reload(colab_render)
        import colab_lab
        importlib.reload(colab_lab)
        lab = colab_lab.Lab(ROOT)
        lab.install_tools()
        lab.start()
        """)
    cells = [
        cell(
            "markdown",
            "introduction",
            """# 御厨こども食堂の謎：Colab試作

既存の章JSONから、序章から終章までの教材を生成したノートブックです。

1. Googleアカウントでログインし、ランタイムは **CPU** を選びます。
2. 「調査環境を準備する」の左にある ▶ を押し、準備完了まで待ちます。
3. 上から表示セルを実行し、会話と設問を読み進めます。
4. 調査には「＋コード」でセルを追加し、自分でコマンドを入力します。シェルコマンドの先頭には `!` を付けます。
5. 正解後は続く表示セルを実行します。条件付きのセルを先に実行した場合は、正解後に再実行してください。

標的環境は寿司屋のWeb・Sambaを起動する試作です。後続章のWebメールや政府側サービスのColab対応は準備中です。

準備セルで、固定した版の教材をGitHubから取得し、必要なツールを導入します。
進捗はランタイム内へ保存します。終了後も残したい場合は、末尾のセルから進捗ファイルをダウンロードしてください。
""",
        ),
        cell("code", "setup", setup, form=True),
    ]
    for chapter in lesson["chapters"]:
        chapter_id = chapter["id"]
        cells.append(
            cell(
                "code",
                chapter_id + "-heading",
                f"# @title {chapter['nav_title']}\nlab.show_chapter({chapter_id!r})\n",
                form=True,
            )
        )
        for block in chapter["blocks"]:
            cells.extend(block_cells(block, chapter_id))
    cells.extend(
        [
            cell(
                "markdown",
                "finish",
                """## 調査の中断・再開

同じランタイムなら、準備セルを再実行しても保存済みの正解と調査メモを引き継げます。
Colabのランタイムが削除されると保存ファイルも消えるため、残したい進捗をダウンロードしてください。
再開時は準備セルを実行し、次の「進捗を読み込む」からファイルを選びます。
""",
            ),
            cell(
                "code",
                "download-progress",
                "# @title 進捗をダウンロードする\nfrom google.colab import files\nif lab.lesson.progress_path.exists():\n    files.download(str(lab.lesson.progress_path))\nelse:\n    print('まだ保存された回答がありません。')\n",
                form=True,
            ),
            cell(
                "code",
                "restore-progress",
                "# @title 進捗を読み込む（再開時のみ）\nimport json\nfrom google.colab import files\nuploaded = files.upload()\nif len(uploaded) == 1:\n    lab.lesson.restore(json.loads(next(iter(uploaded.values()))))\n    print('進捗を復元しました。正解済み:', len(lab.lesson.answers))\nelse:\n    print('進捗ファイルを1つ選んでください。')\n",
                form=True,
            ),
            cell(
                "code",
                "stop",
                "# @title 調査環境を停止する\nlab.stop()\nprint('調査環境を停止しました。')\n",
                form=True,
            ),
        ]
    )
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(build_notebook(source_commit()), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"ノートブックを生成しました: {arguments.output}")


if __name__ == "__main__":
    main()
