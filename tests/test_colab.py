"""Colab試作の回答判定・進捗復元・配布ノートブックを検証する。"""

import ast
import base64
import importlib.util
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "colab"))
sys.path.insert(0, str(ROOT / "scripts"))

import colab_assets
from build_colab import build_notebook

spec = importlib.util.spec_from_file_location(
    "colab_lab", ROOT / "colab/colab_lab.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Lesson = module.Lesson


class DialogueParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[dict[str, str]] = []
        self.tags: list[str] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        if tag == "img":
            self.images.append(dict(attrs))

    def handle_data(self, data: str) -> None:
        self.text.append(data)


class ColabDialogueTests(unittest.TestCase):
    def test_話者の既定表情と台詞指定の表情を画像として埋め込む(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "normal.png").write_bytes(b"normal-image")
            (root / "surprised.png").write_bytes(b"surprised-image")
            speakers = {
                "guide": {
                    "name": "案内役",
                    "defaultExpression": "normal",
                    "avatars": {"normal": "normal.png", "surprised": "surprised.png"},
                }
            }
            html = module.dialogue_html(
                [
                    {"speaker": "guide", "text": "確認中"},
                    {"speaker": "guide", "expression": "surprised", "text": "発見"},
                ],
                speakers,
                root,
            )
        parser = DialogueParser()
        parser.feed(html)
        images = [
            base64.b64decode(image["src"].split(",", 1)[1]) for image in parser.images
        ]
        self.assertEqual(images, [b"normal-image", b"surprised-image"])
        self.assertTrue(all(image.get("alt") for image in parser.images))

    def test_話者名と台詞をHTMLとして実行せず簡単な書式は保持する(self) -> None:
        speakers = {"guide": {"name": '<img src=x onerror="bad()">'}}
        html = module.dialogue_html(
            [
                {
                    "speaker": "guide",
                    "text": "<script>bad()</script>\n`open` と **強調**",
                },
            ],
            speakers,
            Path("/unused"),
        )
        parser = DialogueParser()
        parser.feed(html)
        self.assertNotIn("script", parser.tags)
        self.assertFalse(parser.images)
        self.assertIn("code", parser.tags)
        self.assertIn("strong", parser.tags)
        self.assertIn("<script>bad()</script>", "".join(parser.text))
        self.assertIn(speakers["guide"]["name"], "".join(parser.text))


class ColabLessonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = {
            "speakers": {"guide": {"name": "案内役"}},
            "questions": [
                {
                    "id": "sample",
                    "answer_fields": [{"id": "port"}, {"id": "service"}],
                    "accepted": ["123 sample-service", "123/tcp sample-service"],
                    "blocks": [
                        {
                            "type": "dialogue",
                            "messages": [
                                {"speaker": "guide", "text": "確認できました。"}
                            ],
                        }
                    ],
                },
                {"id": "middle", "blocks": [], "accepted": ["middle"]},
                {"id": "later", "blocks": [], "accepted": ["later"]},
            ],
            "checkpoints": [
                {"after": "middle", "passphrase": "はじめ"},
                {"after": "later", "passphrase": "つづき"},
            ],
        }
        self.lesson = Lesson(self.data, self.root / "progress.json")

    def solve(self, question_id: str) -> None:
        values = (
            {"port": "123", "service": "sample-service"}
            if question_id == "sample"
            else {"answer": question_id}
        )
        self.assertTrue(self.lesson.submit(question_id, values))

    def test_表記揺れを許容して正解を保存し再開できる(self) -> None:
        self.assertTrue(
            self.lesson.submit(
                "sample", {"port": "１２３/tcp", "service": " SAMPLE-SERVICE "}
            )
        )
        restored = Lesson(self.data, self.root / "progress.json")
        self.assertTrue(restored.is_solved("sample"))

    def test_不正解は会話を解放せず進捗を変えない(self) -> None:
        self.assertFalse(
            self.lesson.submit("sample", {"port": "124", "service": "sample-service"})
        )
        self.assertFalse(self.lesson.is_solved("sample"))
        self.assertEqual(self.lesson.follow_up("sample"), "")

    def test_正解後だけ会話を取得でき再回答しても進捗が重複しない(self) -> None:
        values = {"port": "123", "service": "sample-service"}
        self.lesson.submit("sample", values)
        self.assertTrue(self.lesson.follow_up("sample"))
        self.assertTrue(self.lesson.submit("sample", values))
        self.assertTrue(
            Lesson(self.data, self.root / "progress.json").is_solved("sample")
        )

    def test_不足した入力欄や未知の設問を拒否する(self) -> None:
        with self.assertRaises(ValueError):
            self.lesson.submit("sample", {"port": "123 sample-service"})
        with self.assertRaises(ValueError):
            self.lesson.submit("unknown", {"port": "123", "service": "sample-service"})

    def test_区切りまでの設問をすべて正解するとその地点の合言葉を得られる(self) -> None:
        self.assertIsNone(self.lesson.passphrase())
        self.solve("middle")
        # 区切りより前の設問が残っていれば、その地点には到達していない。
        self.assertIsNone(self.lesson.passphrase())
        self.solve("sample")
        self.assertEqual(self.lesson.passphrase(), "はじめ")
        self.solve("later")
        self.assertEqual(self.lesson.passphrase(), "つづき")

    def test_正解した設問が属する区間の合言葉だけをその設問で示す(self) -> None:
        self.solve("sample")
        self.assertIsNone(self.lesson.segment_passphrase("sample"))
        self.solve("middle")
        self.assertEqual(self.lesson.segment_passphrase("sample"), "はじめ")
        self.assertEqual(self.lesson.segment_passphrase("middle"), "はじめ")
        self.assertIsNone(self.lesson.segment_passphrase("later"))
        self.solve("later")
        self.assertEqual(self.lesson.segment_passphrase("sample"), "はじめ")
        self.assertEqual(self.lesson.segment_passphrase("later"), "つづき")

    def test_合言葉で区切りまでを正解済みにし再起動後も保持する(self) -> None:
        self.assertTrue(self.lesson.resume(" はじめ　"))
        self.assertTrue(self.lesson.is_solved("sample"))
        self.assertTrue(self.lesson.is_solved("middle"))
        self.assertFalse(self.lesson.is_solved("later"))
        restored = Lesson(self.data, self.root / "progress.json")
        self.assertTrue(restored.is_solved("middle"))
        self.assertEqual(restored.passphrase(), "はじめ")

    def test_合言葉で戻っても先に正解した設問は残る(self) -> None:
        self.solve("later")
        self.assertTrue(self.lesson.resume("はじめ"))
        self.assertTrue(self.lesson.is_solved("later"))
        self.assertEqual(self.lesson.passphrase(), "つづき")

    def test_誤った合言葉や空の入力は進捗を変えない(self) -> None:
        self.solve("sample")
        before = (self.root / "progress.json").read_bytes()
        self.assertFalse(self.lesson.resume("ちがう"))
        self.assertFalse(self.lesson.resume("  "))
        self.assertEqual((self.root / "progress.json").read_bytes(), before)
        self.assertFalse(self.lesson.is_solved("middle"))

    def test_形式が壊れた進捗ファイルは読み込み時に拒否する(self) -> None:
        path = self.root / "progress.json"
        path.write_text('{"solved": "sample"}', encoding="utf-8")
        with self.assertRaises(ValueError):
            Lesson(self.data, path)

    def test_未知の設問を指す区切りは読み込み時に拒否する(self) -> None:
        broken = {
            **self.data,
            "checkpoints": [{"after": "unknown", "passphrase": "なぞ"}],
        }
        with self.assertRaises(ValueError):
            Lesson(broken, self.root / "other.json")

    def test_重複した合言葉は読み込み時に拒否する(self) -> None:
        broken = {
            **self.data,
            "checkpoints": [
                {"after": "middle", "passphrase": "おなじ"},
                {"after": "later", "passphrase": "おなじ"},
            ],
        }
        with self.assertRaises(ValueError):
            Lesson(broken, self.root / "other.json")


class ColabNotebookTests(unittest.TestCase):
    def test_固定コミットから教材を取得するノートブックを生成できる(self) -> None:
        source_commit = "a" * 40
        notebook = build_notebook(source_commit)
        self.assertEqual(notebook["nbformat"], 4)
        ids = [cell["id"] for cell in notebook["cells"]]
        self.assertEqual(len(ids), len(set(ids)))
        code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
        self.assertTrue(code_cells)
        for cell in code_cells:
            source = "".join(cell["source"])
            if not source.lstrip().startswith("!"):
                compile(source, cell["id"], "exec")
            self.assertEqual(cell["outputs"], [])
            self.assertIsNone(cell["execution_count"])
        setup = "".join(code_cells[0]["source"])
        # 準備セルを実行せず、固定コミットと初期出力だけを検証する。
        tree = ast.parse(setup)
        commit = next(
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "SOURCE_COMMIT"
                for target in node.targets
            )
        )
        self.assertEqual(commit, source_commit)

    def test_各章のセルは章見出しのセクションにまとまる(self) -> None:
        notebook = build_notebook("a" * 40)
        lesson = colab_assets.load_lesson(ROOT)
        cells = notebook["cells"]

        def heading_level(cell: dict) -> int | None:
            if cell["cell_type"] != "markdown":
                return None
            first = "".join(cell["source"]).lstrip().splitlines()[0]
            marks = len(first) - len(first.lstrip("#"))
            return marks or None

        for chapter in lesson["chapters"]:
            # Colabは見出しセルから次の同階層以上の見出しまでを1セクションとして折りたたむ。
            start = next(
                index
                for index, cell in enumerate(cells)
                if heading_level(cell) == 2
                and chapter["nav_title"] in "".join(cell["source"])
            )
            end = next(
                (
                    index
                    for index in range(start + 1, len(cells))
                    if (level := heading_level(cells[index])) is not None
                    and level <= 2
                ),
                len(cells),
            )
            owned = [
                index
                for index, cell in enumerate(cells)
                if cell["cell_type"] == "code"
                and cell["id"].startswith(chapter["id"] + "-")
            ]
            self.assertTrue(owned)
            self.assertTrue(all(start < index < end for index in owned))


if __name__ == "__main__":
    unittest.main()
