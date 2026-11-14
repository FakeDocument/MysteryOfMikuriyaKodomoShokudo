"""PVのブラウザのカットに使う、標的サイトの実際のページを1920幅で描画して保存する。

ローカルの調査環境（docker compose）を起動した状態で実行する。

    uv run python promo/pv/capture_pages.py

標的サイトは隔離ネットワーク（target-net）の中にしかないので、Playwrightのコンテナを一時的に起こし、
日本語フォントを入れてから target-net へつなぎ、そこからページを開いて撮る。終わったらコンテナを消す。
ページは加工しない。ブラウザの枠（タブとアドレスバー）はPV側で描く。

保存先：promo/pv/assets/pages/
- shop.jpg            寿司屋HPのトップ（ページ全体）
- webmail/NNN.png     社内Webメールに神崎でログインしていく途中の画面と、ログイン後の受信箱
- shop.json           寿司屋HPのURLとタイトル
- webmail.json        各画面のURLとタイトル
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / "assets/pages"
IMAGE = "mcr.microsoft.com/playwright/python:v1.65.1-noble"
NAME = "pv-capture-pages"
NETWORK = "sushictf_target-net"
HOSTS = ("www.mikuriya-suisan.local:172.30.0.10", "mail.mikuriya-suisan.local:172.30.0.10")

# コンテナの中で動かす撮影処理
INNER = r'''
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("/out")
VIEW = {"width": 1920, "height": 1000}  # 1080からブラウザの枠の分を引いた高さ
EMAIL = "hitomi.kanzaki@mikuriya-suisan.local"
PASSWORD = "Kanzaki2018"  # 第1章で導く神崎の初期パスワード（画面では伏せ字になる）
STEP = 3  # 何文字ごとに撮るか

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport=VIEW)
    page.goto("http://www.mikuriya-suisan.local/")
    page.wait_for_load_state("networkidle")
    page.screenshot(path=str(OUT / "shop.jpg"), full_page=True, type="jpeg", quality=92)
    (OUT / "shop.json").write_text(json.dumps({"url": page.url, "title": page.title()}, ensure_ascii=False) + "\n")

    frames = []
    shots = OUT / "webmail"
    shots.mkdir(exist_ok=True)

    def shot():
        name = f"{len(frames):03d}.png"
        page.screenshot(path=str(shots / name))
        frames.append({"file": f"webmail/{name}", "url": page.url, "title": page.title()})

    page.goto("http://mail.mikuriya-suisan.local/")
    page.wait_for_load_state("networkidle")
    shot()
    for field, text in (("#email", EMAIL), ("#password", PASSWORD)):
        page.click(field)
        for i in range(0, len(text), STEP):
            page.keyboard.type(text[i : i + STEP])
            shot()
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    shot()
    (OUT / "webmail.json").write_text(json.dumps({"frames": frames}, ensure_ascii=False, indent=2) + "\n")
    browser.close()
'''


def docker(*args: str, quiet: bool = True) -> None:
    subprocess.run(["docker", *args], check=True, stdout=subprocess.DEVNULL if quiet else None)


def main() -> None:
    subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)
    host_args = [arg for h in HOSTS for arg in ("--add-host", h)]
    # 日本語フォントを入れるまでは通常のネットワークにつなぎ、入れてから target-net へ移す
    docker("run", "-d", "--name", NAME, *host_args, IMAGE, "sleep", "infinity")
    try:
        docker(
            "exec", NAME, "bash", "-c",
            "apt-get update -qq && apt-get install -y -qq fonts-noto-cjk"
            f" && pip install -q --break-system-packages playwright=={IMAGE.split(':v')[1].split('-')[0]}",
        )
        docker("network", "disconnect", "bridge", NAME)
        docker("network", "connect", NETWORK, NAME)
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "inner.py"
            script.write_text(INNER, encoding="utf-8")
            docker("cp", str(script), f"{NAME}:/inner.py")
            docker("exec", NAME, "mkdir", "-p", "/out")
            docker("exec", NAME, "python", "/inner.py", quiet=False)
            if OUT_DIR.exists():
                shutil.rmtree(OUT_DIR)
            docker("cp", f"{NAME}:/out", str(OUT_DIR))
        print(f"保存: {OUT_DIR}")
    finally:
        subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)


if __name__ == "__main__":
    main()
