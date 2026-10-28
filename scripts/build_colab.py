"""既存の第1章データから単独配布用のColab試作を生成する。"""

from __future__ import annotations

import argparse
import base64
import io
import json
import textwrap
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "experiments/colab/MysteryOfMikuriyaKodomoShokudo-Colab.ipynb"


def load_lesson() -> dict[str, Any]:
    data = ROOT / "docker/notebook/app/data"
    chapter = json.loads((data / "chapters/chapter-1.json").read_text())["chapter"]
    answers = json.loads((data / "answers.json").read_text())["answers"]
    speakers = json.loads((data / "dialogue-speakers.json").read_text())["speakers"]
    questions = next(
        block for block in chapter["blocks"] if block["id"] == "port-scan"
    )["items"]
    return {
        "title": chapter["title"],
        "speakers": speakers,
        "questions": [
            {**question, **answers[question["id"]]} for question in questions
        ],
    }


def build_payload(lesson: dict[str, Any]) -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "colab_lab.py", (ROOT / "experiments/colab/colab_lab.py").read_bytes()
        )
        archive.writestr("lesson.json", json.dumps(lesson, ensure_ascii=False))
        archive.writestr(
            "smb.conf.in", (ROOT / "docker/sushi/samba/smb.conf").read_bytes()
        )
        answers = json.loads(
            (ROOT / "docker/notebook/app/data/answers.json").read_text()
        )["answers"]
        username, password = answers["ch1_samba_credentials"]["accepted"][0].split("\t")
        archive.writestr(
            "account.json", json.dumps({"username": username, "password": password})
        )
        for source, destination in (
            (ROOT / "docker/sushi/site", "site"),
            (ROOT / "docker/sushi/samba/share", "share"),
        ):
            for file in sorted(source.rglob("*")):
                if file.is_file():
                    archive.writestr(
                        str(Path(destination) / file.relative_to(source)),
                        file.read_bytes(),
                    )
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def cell(kind: str, identifier: str, source: str, form: bool = False) -> dict[str, Any]:
    result = {
        "cell_type": kind,
        "id": identifier,
        "metadata": {"id": identifier, **({"cellView": "form"} if form else {})},
        "source": source.splitlines(keepends=True),
    }
    if kind == "code":
        result.update(execution_count=None, outputs=[])
    return result


def build_notebook() -> dict[str, Any]:
    lesson = load_lesson()
    payload = build_payload(lesson)
    setup = textwrap.dedent("""\
        # @title 1. 調査環境を準備する
        import base64, importlib, io, sys, zipfile
        from pathlib import Path
        if "lab" in globals():
            lab.stop()
        ROOT = Path("/content/mikuriya-colab")
        ROOT.mkdir(parents=True, exist_ok=True)
        """)
    setup += 'PAYLOAD = """\n' + "\n".join(textwrap.wrap(payload, 1024)) + '\n"""\n'
    setup += textwrap.dedent("""\
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(PAYLOAD))) as archive:
            archive.extractall(ROOT)
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
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

第1章のポート調査を、このノートブックだけで試せます。

1. Googleアカウントでログインし、ランタイムは **CPU** を選びます。
2. 「調査環境を準備する」の左にある ▶ を押し、準備完了まで待ちます。
3. 下のコマンドセルを実行し、Nmapの結果を回答欄へ記録します。

環境と教材はこのファイルに同梱されています。初回は必要なツールを取得します。
進捗はランタイム内へ保存します。終了後も残したい場合は、末尾のセルから進捗ファイルをダウンロードしてください。
""",
        ),
        cell("code", "setup", setup, form=True),
        cell(
            "markdown",
            "scan-instructions",
            """## サーバーの入口を調べる

調査対象のドメイン名は `www.mikuriya-suisan.local` です。
次のセルの ▶ を押すと、Nmapを実行できます。コマンドの先頭の `!` は、Colabからコマンドを実行するための記号です。

結果の `PORT`・`STATE`・`SERVICE` の表で、`open` の行を読みます。
`-sV` は、サービスの種類やバージョンも調べる指定です。
""",
        ),
        cell("code", "scan", "!nmap -sV www.mikuriya-suisan.local\n"),
    ]
    for index, question in enumerate(lesson["questions"]):
        cells.append(
            cell(
                "markdown",
                f"question-{index}",
                f"## {question['label']}\n\n{question['prompt']}\n",
            )
        )
        fields = question["answer_fields"]
        assignments = "\n".join(
            f'{field["label"]} = "" # @param {{type:"string"}}' for field in fields
        )
        values = ", ".join(f"{field['id']!r}: {field['label']}" for field in fields)
        source = f"# @title 回答を記録する\n{assignments}\n_ = lab.answer({question['id']!r}, {{{values}}})\n"
        cells.append(cell("code", f"answer-{index}", source, form=True))
    cells.extend(
        [
            cell(
                "markdown",
                "finish",
                """## 調査の中断・再開

ここまでが今回の試作です。同じランタイムなら、準備セルを再実行しても保存済みの正解を引き継げます。
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
        json.dumps(build_notebook(), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"ノートブックを生成しました: {arguments.output}")


if __name__ == "__main__":
    main()
