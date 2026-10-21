"""ローカル案内サイトを生成・配信し、編集時にブラウザーを更新する。"""

from pathlib import Path
import subprocess
import sys

from livereload import Server

ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "scripts" / "build_site.py"


def build_site() -> None:
    subprocess.run([sys.executable, str(BUILD_SCRIPT)], cwd=ROOT, check=True)


build_site()
server = Server()
for source in (ROOT / "README.md", ROOT / "site" / "style.css", ROOT / "docs/mac-setup/*.png", BUILD_SCRIPT):
    server.watch(str(source), build_site, delay=0.5)

server.serve(root=str(ROOT / "_site"), host="127.0.0.1", port=8000)
