"""既存の全章JSONから単独配布用のColabノートブックを生成する。"""

from __future__ import annotations

import argparse
import base64
import hashlib
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
    manifest = json.loads((data / "chapters/manifest.json").read_text())
    chapters = [
        json.loads((data / "chapters" / filename).read_text())["chapter"]
        for filename in manifest["chapter_files"]
    ]
    answers = json.loads((data / "answers.json").read_text())["answers"]
    speakers = json.loads((data / "dialogue-speakers.json").read_text())["speakers"]
    questions = [
        question
        for chapter in chapters
        for block in chapter["blocks"]
        if block["type"] == "questions"
        for question in block["items"]
    ]
    return {
        "title": "御厨こども食堂の謎",
        "chapters": chapters,
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
        archive.writestr(
            "colab_render.py", (ROOT / "experiments/colab/colab_render.py").read_bytes()
        )
        archive.writestr("lesson.json", json.dumps(lesson, ensure_ascii=False))
        images = {
            image
            for speaker in lesson["speakers"].values()
            for image in speaker["avatars"].values()
        }

        def find_images(value: Any) -> None:
            if isinstance(value, dict):
                if isinstance(value.get("image"), dict):
                    images.add(Path(value["image"]["src"]).name)
                for item in value.values():
                    find_images(item)
            elif isinstance(value, list):
                for item in value:
                    find_images(item)

        find_images(lesson.get("chapters", []))
        for image in sorted(images):
            archive.writestr(
                f"images/{image}",
                (ROOT / "docker/notebook/app/static/images" / image).read_bytes(),
            )
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

環境と教材はこのファイルに同梱されています。初回は必要なツールを取得します。
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
        json.dumps(build_notebook(), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"ノートブックを生成しました: {arguments.output}")


if __name__ == "__main__":
    main()
