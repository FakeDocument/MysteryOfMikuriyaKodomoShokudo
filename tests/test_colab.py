"""Colab試作の回答判定・進捗復元・配布ノートブックを検証する。"""

import ast
import base64
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "colab_lab", ROOT / "experiments/colab/colab_lab.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Lesson = module.Lesson


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
                }
            ],
        }
        self.lesson = Lesson(self.data, self.root / "progress.json")

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
        self.lesson.submit("sample", values)
        self.assertEqual(
            len(json.loads((self.root / "progress.json").read_text())["answers"]), 1
        )

    def test_不足した入力欄や未知の設問を拒否する(self) -> None:
        with self.assertRaises(ValueError):
            self.lesson.submit("sample", {"port": "123 sample-service"})
        with self.assertRaises(ValueError):
            self.lesson.submit("unknown", {"port": "123", "service": "sample-service"})

    def test_不正な進捗ファイルは既存の正解を上書きしない(self) -> None:
        self.lesson.submit("sample", {"port": "123", "service": "sample-service"})
        before = (self.root / "progress.json").read_bytes()
        with self.assertRaises(ValueError):
            self.lesson.restore(
                {"answers": {"sample": {"port": "124", "service": "sample-service"}}}
            )
        self.assertEqual((self.root / "progress.json").read_bytes(), before)


class ColabNotebookTests(unittest.TestCase):
    def test_単独配布できるノートブックを生成できる(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "experiment.ipynb"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/build_colab.py"),
                    "--output",
                    str(output),
                ],
                check=True,
                capture_output=True,
            )
            notebook = json.loads(output.read_text())
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
        # 準備セルを実行せず、埋め込まれた配布データだけを検証する。
        tree = ast.parse(setup)
        payload = next(
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "PAYLOAD"
                for target in node.targets
            )
        )
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(payload))) as archive:
            self.assertIn("colab_lab.py", archive.namelist())
            lesson = json.loads(archive.read("lesson.json"))
            question_ids = {question["id"] for question in lesson["questions"]}
            self.assertTrue(question_ids)
            self.assertTrue(
                all(question.get("accepted") for question in lesson["questions"])
            )
            self.assertTrue(
                any(name.startswith("site/") for name in archive.namelist())
            )
            self.assertTrue(
                all(
                    not Path(name).is_absolute() and ".." not in Path(name).parts
                    for name in archive.namelist()
                )
            )


if __name__ == "__main__":
    unittest.main()
