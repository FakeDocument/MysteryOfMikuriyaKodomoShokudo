"""固定したGitHubコミット、またはNotebookに埋め込んだZIPからColabの教材・実行用ファイルを準備する。"""

from __future__ import annotations

import base64
import io
import importlib.util
import json
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

SOURCE_FILES = (
    "docker/notebook/app/block_variants.py",
    "colab/colab_lab.py",
    "colab/colab_render.py",
    "colab/colab_web.py",
    "colab/checkpoints.json",
    "docker/sushi/samba/smb.conf",
)
SOURCE_DIRS = (
    "docker/notebook/app/data",
    "docker/notebook/app/static/images",
    "docker/sushi/site",
    "docker/sushi/samba/share",
)


def source_files(source: Path) -> list[Path]:
    return [Path(name) for name in SOURCE_FILES] + [
        file.relative_to(source)
        for directory in SOURCE_DIRS
        for file in sorted((source / directory).rglob("*"))
        if file.is_file()
    ]


def load_lesson(source: Path) -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location(
        "block_variants", source / "docker/notebook/app/block_variants.py"
    )
    if spec is None or spec.loader is None:
        raise ValueError("ブロックの環境差分処理を読み込めません。")
    variants = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(variants)
    data = source / "docker/notebook/app/data"
    manifest = json.loads((data / "chapters/manifest.json").read_text(encoding="utf-8"))
    chapters = [
        json.loads((data / "chapters" / filename).read_text(encoding="utf-8"))[
            "chapter"
        ]
        for filename in manifest["chapter_files"]
    ]
    chapters = variants.resolve_environment(chapters, "$colab")
    answers = json.loads((data / "answers.json").read_text(encoding="utf-8"))["answers"]
    speakers = json.loads(
        (data / "dialogue-speakers.json").read_text(encoding="utf-8")
    )["speakers"]
    # 合言葉の区切りはColab版だけで使うため、章JSONとは別に管理する。
    checkpoints = json.loads(
        (source / "colab/checkpoints.json").read_text(encoding="utf-8")
    )["checkpoints"]
    return {
        "title": "御厨こども食堂の謎",
        "chapters": chapters,
        "speakers": speakers,
        "checkpoints": checkpoints,
        "questions": [
            {**question, **answers[question["id"]]}
            for chapter in chapters
            for block in chapter["blocks"]
            if block["type"] == "questions"
            for question in block["items"]
        ],
    }


def prepare_from_source(source: Path, root: Path) -> None:
    lesson = load_lesson(source)
    credential = next(
        question
        for question in lesson["questions"]
        if question["id"] == "ch1_samba_credentials"
    )
    username, password = credential["accepted"][0].split("\t")
    # 必要ファイルがそろうまで、使用中の教材と進捗には触れない。
    with tempfile.TemporaryDirectory() as temporary:
        staging = Path(temporary)
        (staging / "lesson.json").write_text(
            json.dumps(lesson, ensure_ascii=False), encoding="utf-8"
        )
        (staging / "account.json").write_text(
            json.dumps({"username": username, "password": password}), encoding="utf-8"
        )
        for name in ("colab_lab.py", "colab_render.py", "colab_web.py"):
            shutil.copyfile(source / "colab" / name, staging / name)
        shutil.copyfile(source / "docker/sushi/samba/smb.conf", staging / "smb.conf.in")
        for directory, destination in (
            ("docker/sushi/site", "site"),
            ("docker/sushi/samba/share", "share"),
            ("docker/notebook/app/static/images", "images"),
        ):
            shutil.copytree(source / directory, staging / destination)
        root.mkdir(parents=True, exist_ok=True)
        for asset in staging.iterdir():
            destination = root / asset.name
            if destination.is_symlink() or destination.is_file():
                destination.unlink()
            elif destination.is_dir():
                shutil.rmtree(destination)
            shutil.move(str(asset), str(destination))


def fetch_archive(repository: str, commit: str) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("取得先は40桁のコミットSHAで固定してください。")
    if not re.fullmatch(
        r"[A-Za-z0-9_-][A-Za-z0-9_.-]*/[A-Za-z0-9_-][A-Za-z0-9_.-]*", repository
    ):
        raise ValueError("GitHubリポジトリの指定が不正です。")
    url = f"https://codeload.github.com/{repository}/zip/{commit}"
    try:
        with urlopen(url, timeout=45) as response:
            return response.read()
    except (URLError, TimeoutError) as error:
        raise RuntimeError(
            "GitHubから教材を取得できませんでした。接続を確認し、準備セルを再実行してください。"
        ) from error


def install_archive(root: Path, data: bytes) -> None:
    """先頭に1階層を持つ教材ZIPから、取得対象だけを検証して配置する。"""
    with (
        tempfile.TemporaryDirectory() as temporary,
        zipfile.ZipFile(io.BytesIO(data)) as archive,
    ):
        source = Path(temporary)
        for member in archive.infolist():
            path = PurePosixPath(member.filename)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("教材ZIPに不正なパスが含まれています。")
            if member.is_dir():
                continue
            relative = PurePosixPath(*path.parts[1:])
            name = relative.as_posix()
            if name not in SOURCE_FILES and not any(
                name.startswith(directory + "/") for directory in SOURCE_DIRS
            ):
                continue
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError(
                    "教材ZIPの展開対象にシンボリックリンクが含まれています。"
                )
            destination = source / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(member))
        prepare_from_source(source, root)


def bootstrap_runtime(root: Path, repository: str, commit: str) -> None:
    install_archive(root, fetch_archive(repository, commit))


def bootstrap_embedded(root: Path, encoded: str) -> None:
    """Notebookに埋め込んだ教材ZIPから、通信せずに準備する。"""
    install_archive(root, base64.b64decode(encoded, validate=True))
