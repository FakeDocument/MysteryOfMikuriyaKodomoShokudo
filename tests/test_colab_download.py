"""固定コミットからの教材取得と、既存データの保持を検証する。"""

import base64
import importlib.util
import io
import json
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
COMMIT = "a" * 40


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ColabDownloadTests(unittest.TestCase):
    def assets(self):
        path = ROOT / "scripts/colab_assets.py"
        self.assertTrue(
            path.is_file(), "固定コミットから教材を準備する処理が必要です。"
        )
        return load("download_assets", path)

    def test_ブランチ名の指定は固定コミットとして受け付けない(self) -> None:
        assets = self.assets()
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(assets, "urlopen") as request,
        ):
            with self.assertRaises(ValueError):
                assets.bootstrap_runtime(
                    Path(temp), "FakeDocument/MysteryOfMikuriyaKodomoShokudo", "main"
                )
            request.assert_not_called()

    def test_教材の未コミット変更があると版不一致のNotebookを生成しない(self) -> None:
        builder = load("revision_builder", ROOT / "scripts/build_colab.py")
        for changed, untracked in ((1, ""), (0, "docker/sushi/site/new.html\n")):
            with (
                self.subTest(changed=changed, untracked=bool(untracked)),
                patch.object(
                    builder.subprocess,
                    "check_output",
                    side_effect=[COMMIT + "\n", untracked],
                ),
                patch.object(
                    builder.subprocess,
                    "run",
                    return_value=SimpleNamespace(returncode=changed),
                ),
                self.assertRaises(ValueError),
            ):
                builder.source_commit()

    def test_固定コミットから必要ファイルを準備し既存進捗を保持する(self) -> None:
        assets = self.assets()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in assets.source_files(ROOT):
                archive.writestr(
                    "snapshot/" + path.as_posix(), (ROOT / path).read_bytes()
                )
            archive.writestr("snapshot/unrelated.txt", "対象外")
            unrelated_link = zipfile.ZipInfo("snapshot/.agents/shared")
            unrelated_link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(unrelated_link, "../../shared-settings")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            progress = b'{"version":1,"answers":{},"note":"saved"}'
            (root / "progress.json").write_bytes(progress)
            with patch.object(
                assets, "urlopen", return_value=io.BytesIO(buffer.getvalue())
            ) as request:
                assets.bootstrap_runtime(
                    root, "FakeDocument/MysteryOfMikuriyaKodomoShokudo", COMMIT
                )
            self.assertIn(COMMIT, request.call_args.args[0])
            self.assertTrue((root / "colab_lab.py").is_file())
            self.assertTrue((root / "colab_render.py").is_file())
            self.assertTrue((root / "site/index.html").is_file())
            self.assertTrue((root / "smb.conf.in").is_file())
            lesson = json.loads((root / "lesson.json").read_text())
            self.assertTrue(lesson["chapters"])
            self.assertTrue(lesson["questions"])
            self.assertEqual((root / "progress.json").read_bytes(), progress)
            self.assertFalse((root / "unrelated.txt").exists())

    def test_教材で削除された旧ファイルを残さず進捗を保持する(self) -> None:
        assets = self.assets()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("site", "share", "images"):
                (root / name).mkdir()
                (root / name / "retired.txt").write_text("old")
            (root / "progress.json").write_text("saved")
            assets.prepare_from_source(ROOT, root)
            for name in ("site", "share", "images"):
                self.assertFalse((root / name / "retired.txt").exists())
            self.assertEqual((root / "progress.json").read_text(), "saved")

    def test_取得失敗時は既存教材と進捗を変更しない(self) -> None:
        assets = self.assets()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "lesson.json").write_text("existing")
            with (
                patch.object(assets, "urlopen", side_effect=URLError("offline")),
                self.assertRaises(RuntimeError),
            ):
                assets.bootstrap_runtime(
                    root, "FakeDocument/MysteryOfMikuriyaKodomoShokudo", COMMIT
                )
            self.assertEqual((root / "lesson.json").read_text(), "existing")

    def test_破損ZIPとパストラバーサルを拒否する(self) -> None:
        assets = self.assets()
        malicious = io.BytesIO()
        with zipfile.ZipFile(malicious, "w") as archive:
            archive.writestr("snapshot/../../outside.txt", "bad")
        for data in (b"not-a-zip", malicious.getvalue()):
            with self.subTest(data=data[:10]), tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / "runtime"
                root.mkdir()
                with (
                    patch.object(assets, "urlopen", return_value=io.BytesIO(data)),
                    self.assertRaises((ValueError, zipfile.BadZipFile)),
                ):
                    assets.bootstrap_runtime(
                        root, "FakeDocument/MysteryOfMikuriyaKodomoShokudo", COMMIT
                    )
                self.assertFalse((root.parent / "outside.txt").exists())


def snapshot_zip(paths: list[Path], extra: dict[str, bytes] | None = None) -> bytes:
    """git archive と同じく先頭に1階層を持つ教材ZIPを作る。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.writestr("snapshot/" + path.as_posix(), (ROOT / path).read_bytes())
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return buffer.getvalue()


class ColabEmbeddedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assets = load("embedded_assets", ROOT / "scripts/colab_assets.py")

    def test_埋め込み版の準備はネットワークを使わずに必要ファイルを配置し進捗を保持する(
        self,
    ) -> None:
        encoded = base64.b64encode(
            snapshot_zip(
                self.assets.source_files(ROOT),
                {"snapshot/unrelated.txt": "対象外".encode()},
            )
        ).decode()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            progress = b'{"version":1,"answers":{},"note":"saved"}'
            (root / "progress.json").write_bytes(progress)
            with patch.object(
                self.assets, "urlopen", side_effect=AssertionError("通信しない")
            ) as request:
                self.assets.bootstrap_embedded(root, encoded)
            request.assert_not_called()
            self.assertTrue((root / "colab_lab.py").is_file())
            self.assertTrue((root / "site/index.html").is_file())
            self.assertTrue((root / "smb.conf.in").is_file())
            lesson = json.loads((root / "lesson.json").read_text())
            self.assertTrue(lesson["chapters"])
            self.assertEqual((root / "progress.json").read_bytes(), progress)
            self.assertFalse((root / "unrelated.txt").exists())

    def test_埋め込み版は不正なZIPを拒否し既存教材を変更しない(self) -> None:
        traversal = io.BytesIO()
        with zipfile.ZipFile(traversal, "w") as archive:
            archive.writestr("snapshot/../../outside.txt", "bad")
        link = io.BytesIO()
        with zipfile.ZipFile(link, "w") as archive:
            member = zipfile.ZipInfo("snapshot/docker/sushi/site/index.html")
            member.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(member, "/etc/passwd")
        cases = {
            "base64でない": "@@@",
            "ZIPでない": base64.b64encode(b"not-a-zip").decode(),
            "パストラバーサル": base64.b64encode(traversal.getvalue()).decode(),
            "シンボリックリンク": base64.b64encode(link.getvalue()).decode(),
        }
        for label, encoded in cases.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / "runtime"
                root.mkdir()
                (root / "lesson.json").write_text("existing")
                with self.assertRaises((ValueError, zipfile.BadZipFile)):
                    self.assets.bootstrap_embedded(root, encoded)
                self.assertEqual((root / "lesson.json").read_text(), "existing")
                self.assertFalse((root.parent / "outside.txt").exists())

    def test_HEADの教材ZIPを埋め込み版の準備に使える(self) -> None:
        builder = load("embed_builder", ROOT / "scripts/build_colab.py")
        commit = builder.subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        data = builder.embedded_archive(commit)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = {PurePosixPath(*PurePosixPath(n).parts[1:]).as_posix()
                     for n in archive.namelist()}
        for name in self.assets.SOURCE_FILES:
            self.assertIn(name, names)
        self.assertNotIn("README.md", names)
        with tempfile.TemporaryDirectory() as temp:
            self.assets.bootstrap_embedded(
                Path(temp), base64.b64encode(data).decode()
            )
            self.assertTrue((Path(temp) / "lesson.json").is_file())

    def test_埋め込みなしの生成は固定コミットから取得し埋め込み版とは準備部分だけが異なる(
        self,
    ) -> None:
        builder = load("default_builder", ROOT / "scripts/build_colab.py")
        default = builder.build_notebook(COMMIT)
        embedded = builder.build_notebook(COMMIT, embedded="QUJD")
        self.assertEqual(default, builder.build_notebook(COMMIT, embedded=None))
        default_setup = "".join(default["cells"][1]["source"])
        embedded_setup = "".join(embedded["cells"][1]["source"])
        self.assertIn("bootstrap_runtime(ROOT, REPOSITORY, SOURCE_COMMIT)", default_setup)
        self.assertNotIn("EMBEDDED_ARCHIVE", default_setup)
        self.assertIn("bootstrap_embedded(ROOT, EMBEDDED_ARCHIVE)", embedded_setup)
        self.assertIn("'QUJD'", embedded_setup)
        compile(embedded_setup, "setup", "exec")
        self.assertEqual(default["metadata"], embedded["metadata"])
        self.assertEqual(default["cells"][2:], embedded["cells"][2:])

    def test_埋め込み版は出力先の指定が必要で配布用ノートブックを上書きしない(
        self,
    ) -> None:
        builder = load("cli_builder", ROOT / "scripts/build_colab.py")
        for argv in (["--embed"], ["--embed", "--output", str(builder.DEFAULT_OUTPUT)]):
            with (
                self.subTest(argv=argv),
                patch.object(sys, "stderr", io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                builder.parse_arguments(argv)
        arguments = builder.parse_arguments([])
        self.assertFalse(arguments.embed)
        self.assertEqual(arguments.output, builder.DEFAULT_OUTPUT)
