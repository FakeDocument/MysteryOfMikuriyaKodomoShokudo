"""章JSONからのセル生成と、生成セルの表示・入力の振る舞いを検証する。"""

import ast
import base64
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
import zipfile
from copy import deepcopy
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments/colab"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_module("colab_builder", ROOT / "scripts/build_colab.py")
runtime = load_module("colab_runtime", ROOT / "experiments/colab/colab_lab.py")


class Markup(HTMLParser):
    def __init__(self, value: str) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict]] = []
        self.text: list[str] = []
        self.feed(value)

    def handle_starttag(self, tag, attrs) -> None:
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, value) -> None:
        self.text.append(value)


class ColabConversionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "images").mkdir()
        (self.root / "images/face.png").write_bytes(b"portrait")
        (self.root / "images/diagram.png").write_bytes(b"diagram")
        self.question = {
            "type": "question",
            "id": "sample",
            "label": "確認",
            "prompt": "調査した値は？",
            "placeholder": "値を入力",
            "input_mode": "text",
            "blocks": [],
            "accepted": ["result"],
        }
        self.chapter = {
            "id": "sample-chapter",
            "title": "調査",
            "lead": "調査の説明",
            "objective": "調査の目的",
            "date": "調査日時",
            "blocks": [],
        }
        self.data = {
            "chapters": [self.chapter],
            "questions": [self.question],
            "speakers": {
                "player": {
                    "name": "調査員",
                    "defaultExpression": "normal",
                    "avatars": {"normal": "face.png"},
                }
            },
        }

    def generate(self, block: dict) -> list[dict]:
        self.assertTrue(
            callable(getattr(builder, "block_cells", None)),
            "章JSONのブロックを変換する入口が必要です。",
        )
        self.chapter["blocks"] = [block]
        if block["type"] == "questions":
            self.data["questions"] = [
                {**question, "accepted": ["result"]} for question in block["items"]
            ]
        (self.root / "lesson.json").write_text(json.dumps(self.data))
        self.lab = runtime.Lab(self.root)
        return builder.block_cells(block, self.chapter["id"])

    def execute(self, cells: list[dict]) -> tuple[str, dict]:
        output = []
        scope = {"lab": self.lab}
        display = SimpleNamespace(
            HTML=str, display=lambda value: output.append(str(value))
        )
        with (
            patch.dict(sys.modules, {"IPython.display": display}),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            for cell in cells:
                self.assertEqual(cell["cell_type"], "code")
                # 生成したローカル教材セルを実際に実行して表示結果を検証する。
                exec("".join(cell["source"]), scope)  # noqa: S102
        return "\n".join(output), scope

    def test_会話ブロックから顔と話者名と本文を表示できる(self) -> None:
        cells = self.generate(
            {
                "type": "dialogue",
                "id": "conversation",
                "messages": [{"speaker": "player", "text": "調査しました。"}],
            }
        )
        output, _ = self.execute(cells)
        markup = Markup(output)
        self.assertIn("調査しました。", "".join(markup.text))
        self.assertIn("調査員", "".join(markup.text))
        self.assertTrue(any(tag == "img" for tag, _ in markup.tags))

    def test_地の文は顔や人物名を付けずに表示できる(self) -> None:
        cells = self.generate(
            {
                "type": "dialogue",
                "id": "narration",
                "messages": [{"speaker": "narrator", "text": "調査が始まった。"}],
            }
        )
        output, _ = self.execute(cells)
        markup = Markup(output)
        self.assertIn("調査が始まった。", "".join(markup.text))
        self.assertFalse(any(tag == "img" for tag, _ in markup.tags))

    def test_会話に付いたリンクと説明画像を保持する(self) -> None:
        cells = self.generate(
            {
                "type": "dialogue",
                "id": "guide",
                "messages": [
                    {
                        "speaker": "player",
                        "text": "手順を確認。",
                        "link": {"label": "参照先", "href": "https://example.com/help"},
                        "image": {
                            "src": "/static/images/diagram.png",
                            "alt": "操作図",
                            "caption": "補足",
                        },
                    }
                ],
            }
        )
        output, _ = self.execute(cells)
        markup = Markup(output)
        self.assertTrue(
            any(
                tag == "a" and attrs.get("href") == "https://example.com/help"
                for tag, attrs in markup.tags
            )
        )
        self.assertTrue(
            any(
                tag == "img"
                and attrs.get("alt") == "操作図"
                and attrs.get("src", "").startswith("data:image/")
                for tag, attrs in markup.tags
            )
        )
        self.assertIn("補足", "".join(markup.text))

    def test_ローカル端末へのリンクはColabのコードセル案内として表示する(self) -> None:
        cells = self.generate(
            {
                "type": "dialogue",
                "id": "terminal",
                "messages": [
                    {
                        "speaker": "player",
                        "text": "端末を準備。",
                        "link": {
                            "label": "端末",
                            "href": "http://127.0.0.1:6901/vnc.html",
                        },
                    }
                ],
            }
        )
        output, _ = self.execute(cells)
        markup = Markup(output)
        self.assertFalse(
            any(
                tag == "a" and "6901" in attrs.get("href", "")
                for tag, attrs in markup.tags
            )
        )
        self.assertTrue(any(tag == "aside" for tag, _ in markup.tags))

    def test_複数欄のラベルがColabフォームに表示される(self) -> None:
        question = {
            key: value
            for key, value in self.question.items()
            if key not in {"input_mode", "placeholder"}
        }
        question["answer_fields"] = [
            {"id": "when", "label": "日時", "input_mode": "datetime"},
            {"id": "place", "label": "場所", "input_mode": "text"},
        ]
        cells = self.generate(
            {"type": "questions", "id": "questions", "items": [question]}
        )
        source = "\n".join("".join(cell["source"]) for cell in cells)
        for field in question["answer_fields"]:
            self.assertIn("# @markdown " + field["label"], source)

    def test_文書の本文と署名や受付情報を表示できる(self) -> None:
        content = {
            "kicker": "原本",
            "title": "依頼",
            "body": ["本文一", "本文二"],
            "signature": "差出人",
            "date": "記入日",
            "received_stamp": "受付",
        }
        output, _ = self.execute(
            self.generate({"type": "document", "id": "letter", "content": content})
        )
        text = "".join(Markup(output).text)
        for value in ["原本", "依頼", "本文一", "本文二", "差出人", "記入日", "受付"]:
            self.assertIn(value, text)

    def test_証拠メモの入力セルを生成し保存して再開できる(self) -> None:
        cells = self.generate(
            {
                "type": "evidence_note",
                "id": "memo",
                "label": "調査メモ",
                "placeholder": "記録",
                "action_label": "保存",
            }
        )
        _, scope = self.execute(cells)
        assignments = [
            node
            for cell in cells
            for node in ast.parse("".join(cell["source"])).body
            if isinstance(node, ast.Assign)
        ]
        self.assertTrue(assignments)
        self.lab.lesson.save_note("見つけた事実")
        restored = runtime.Lab(self.root)
        self.assertEqual(restored.lesson.note, "見つけた事実")
        self.assertTrue(
            any(
                isinstance(value, str)
                for key, value in scope.items()
                if key != "__builtins__"
            )
        )

    def test_設問の説明と回答フォームを生成し単一欄を判定できる(self) -> None:
        output, scope = self.execute(
            self.generate(
                {"type": "questions", "id": "questions", "items": [self.question]}
            )
        )
        self.assertIn(self.question["prompt"], "".join(Markup(output).text))
        self.assertTrue(any(key.startswith("answer_") for key in scope))
        self.assertTrue(self.lab.lesson.submit("sample", {"answer": "result"}))

    def test_複数回答欄の入力セルを生成し順序を保って判定する(self) -> None:
        question = {
            key: value
            for key, value in self.question.items()
            if key not in {"input_mode", "placeholder"}
        }
        question["answer_fields"] = [
            {"id": "first", "label": "値一", "input_mode": "text"},
            {"id": "second", "label": "値二", "input_mode": "text"},
        ]
        cells = self.generate(
            {"type": "questions", "id": "questions", "items": [question]}
        )
        _, scope = self.execute(cells)
        self.assertGreaterEqual(
            len([key for key in scope if key.startswith("answer_")]), 2
        )
        self.lab.lesson.questions["sample"]["accepted"] = ["alpha\tbeta"]
        self.assertTrue(
            self.lab.lesson.submit("sample", {"first": "alpha", "second": "beta"})
        )

    def test_選択式と日時の回答欄も生成できる(self) -> None:
        question = {
            key: value
            for key, value in self.question.items()
            if key not in {"input_mode", "placeholder"}
        }
        question["answer_fields"] = [
            {
                "id": "choice",
                "label": "選択",
                "input_mode": "select",
                "options": ["候補A", "候補B"],
            },
            {"id": "when", "label": "日時", "input_mode": "datetime"},
        ]
        cells = self.generate(
            {"type": "questions", "id": "questions", "items": [question]}
        )
        source = "\n".join("".join(cell["source"]) for cell in cells)
        self.assertIn('"候補A"', source)
        self.assertIn('"候補B"', source)
        self.assertIn("日時", source)
        self.execute(cells)

    def test_設問内のヒントは折りたたんで表示できる(self) -> None:
        question = deepcopy(self.question)
        question["blocks"] = [{"type": "hints", "id": "help", "items": ["手掛かり"]}]
        output, _ = self.execute(
            self.generate({"type": "questions", "id": "questions", "items": [question]})
        )
        markup = Markup(output)
        self.assertIn("手掛かり", "".join(markup.text))
        self.assertTrue(
            any(tag == "details" and "open" not in attrs for tag, attrs in markup.tags)
        )

    def test_設問内の正解後会話は解答まで伏せる(self) -> None:
        question = deepcopy(self.question)
        question["blocks"] = [
            {
                "type": "dialogue",
                "id": "follow-up",
                "visible_when": {"event": "question_solved"},
                "messages": [{"speaker": "narrator", "text": "解放された会話"}],
            }
        ]
        cells = self.generate(
            {"type": "questions", "id": "questions", "items": [question]}
        )
        output, _ = self.execute(cells)
        self.assertNotIn("解放された会話", output)
        self.lab.lesson.submit("sample", {"answer": "result"})
        output, _ = self.execute(cells)
        self.assertIn("解放された会話", output)

    def test_報告書の件名と項目と結論を表示できる(self) -> None:
        output, _ = self.execute(
            self.generate(
                {
                    "type": "report",
                    "id": "report",
                    "subject": "対象事案",
                    "items": [{"label": "確認事項", "value": "調査結果"}],
                    "conclusion": "調査の結論",
                }
            )
        )
        text = "".join(Markup(output).text)
        for value in ["対象事案", "確認事項", "調査結果", "調査の結論"]:
            self.assertIn(value, text)

    def test_条件付きブロックは必要な設問に正解してから表示する(self) -> None:
        cells = self.generate(
            {
                "type": "document",
                "id": "locked",
                "content": {"title": "解放文書", "body": []},
                "visible_when": {
                    "event": "questions_solved",
                    "question_ids": ["sample"],
                },
            }
        )
        output, _ = self.execute(cells)
        self.assertNotIn("解放文書", output)
        self.lab.lesson.submit("sample", {"answer": "result"})
        output, _ = self.execute(cells)
        self.assertIn("解放文書", output)

    def test_シェルのコード例だけに感嘆符を付け出力例とPythonは保持する(self) -> None:
        cells = self.generate(
            {
                "type": "dialogue",
                "id": "commands",
                "messages": [
                    {
                        "speaker": "narrator",
                        "text": "```sh\necho hello\n!pwd\n```\n```text\ncommand output\n```\n```python\nprint(1)\n```",
                    }
                ],
            }
        )
        output, _ = self.execute(cells)
        text = "".join(Markup(output).text)
        self.assertIn("!echo hello", text)
        self.assertIn("!pwd", text)
        self.assertNotIn("!!pwd", text)
        self.assertIn("command output", text)
        self.assertNotIn("!command output", text)
        self.assertIn("print(1)", text)
        self.assertNotIn("!print(1)", text)

    def test_ブロック見出しと本文のHTMLは文字列として扱う(self) -> None:
        output, _ = self.execute(
            self.generate(
                {
                    "type": "document",
                    "id": "escaped",
                    "heading": {"title": "<script>heading()</script>"},
                    "content": {"title": "文書", "body": ["<script>body()</script>"]},
                }
            )
        )
        markup = Markup(output)
        self.assertFalse(any(tag == "script" for tag, _ in markup.tags))
        self.assertIn("<script>heading()</script>", "".join(markup.text))

    def test_未知のブロックを黙って欠落させずエラーにする(self) -> None:
        self.assertTrue(callable(getattr(builder, "block_cells", None)))
        with self.assertRaises(ValueError):
            builder.block_cells({"type": "unsupported", "id": "unknown"}, "chapter")

    def test_全章と全設問をマニフェストから読み込む(self) -> None:
        lesson = builder.load_lesson()
        self.assertIn("chapters", lesson)
        data_root = ROOT / "docker/notebook/app/data"
        manifest = json.loads((data_root / "chapters/manifest.json").read_text())
        expected = [
            json.loads((data_root / "chapters" / name).read_text())["chapter"]
            for name in manifest["chapter_files"]
        ]
        self.assertEqual(
            {chapter["id"] for chapter in lesson["chapters"]},
            {chapter["id"] for chapter in expected},
        )
        self.assertEqual(
            {question["id"] for question in lesson["questions"]},
            {
                question["id"]
                for chapter in expected
                for block in chapter["blocks"]
                if block["type"] == "questions"
                for question in block["items"]
            },
        )

    def test_生成ノートブックのセルを構文検証でき出力が空でIDが重複しない(self) -> None:
        lesson = builder.load_lesson()
        self.assertIn("chapters", lesson)
        notebook = builder.build_notebook()
        self.assertEqual(
            len({cell["id"] for cell in notebook["cells"]}), len(notebook["cells"])
        )
        for cell in notebook["cells"]:
            self.assertRegex(cell["id"], r"\A[a-zA-Z0-9_-]{1,64}\Z")
            if cell["cell_type"] == "code":
                compile("".join(cell["source"]), cell["id"], "exec")
                self.assertEqual(cell["outputs"], [])
                self.assertIsNone(cell["execution_count"])

    def test_同梱データだけで全章の全表示セルを実行できる(self) -> None:
        lesson = builder.load_lesson()
        self.assertIn("chapters", lesson)
        with zipfile.ZipFile(
            io.BytesIO(base64.b64decode(builder.build_payload(lesson)))
        ) as archive:
            archive.extractall(self.root)
        self.lab = runtime.Lab(self.root)
        for question in lesson["questions"]:
            fields = runtime.answer_fields(question)
            if question.get("validation") == "contains_all":
                parts = [
                    " ".join(question["required_terms"]),
                    *[""] * (len(fields) - 1),
                ]
            else:
                value = question["accepted"][0]
                parts = (
                    value.split("\t")
                    if "\t" in value
                    else value.split(maxsplit=len(fields) - 1)
                )
            self.assertTrue(
                self.lab.lesson.submit(
                    question["id"], dict(zip([field["id"] for field in fields], parts))
                )
            )
        for chapter in lesson["chapters"]:
            for block in chapter["blocks"]:
                with self.subTest(chapter=chapter["id"], block=block["id"]):
                    output, _ = self.execute(builder.block_cells(block, chapter["id"]))
                    self.assertTrue(output)

    def test_前の章の完了まで次章の本文と回答を開かない(self) -> None:
        self.generate(
            {"type": "questions", "id": "questions", "items": [self.question]}
        )
        self.lab.lesson.data["chapters"].append({"id": "next", "blocks": []})
        self.assertFalse(self.lab.lesson.chapter_open("next"))
        self.lab.lesson.submit("sample", {"answer": "result"})
        self.assertTrue(self.lab.lesson.chapter_open("next"))

    def test_完全一致と必須語判定を既存JSONの方式どおりに扱う(self) -> None:
        self.generate({"type": "dialogue", "id": "empty", "messages": []})
        question = self.lab.lesson.questions["sample"]
        question.update(validation="exact", accepted=["CaseSensitive"])
        self.assertFalse(self.lab.lesson.submit("sample", {"answer": "casesensitive"}))
        self.assertTrue(self.lab.lesson.submit("sample", {"answer": "CaseSensitive"}))
        question.update(validation="contains_all", required_terms=["alpha", "beta"])
        self.assertFalse(self.lab.lesson.submit("sample", {"answer": "alpha"}))
        self.assertTrue(self.lab.lesson.submit("sample", {"answer": "BETA と ALPHA"}))
