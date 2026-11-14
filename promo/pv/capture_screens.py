# /// script
# requires-python = ">=3.12"
# dependencies = ["playwright"]
# ///
"""PVのゲーム紹介の1カット目に使う、Kaliのデスクトップの実画面を撮る。

ローカルの調査環境（docker compose）を起動した状態で実行する。

    uv run promo/pv/capture_screens.py

ホストのブラウザで開いたnoVNCの画面（Kaliのデスクトップ）をそのまま撮り、
promo/pv/assets/screens/ へPNGで保存する。画面は加工しない。
Kali側で開く端末には撮影専用の名前を付け、終わったらそれだけを閉じる。
撮影用の端末は時計を作中の日時に合わせて開く（story_clock.py）。
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

import story_clock

OUT_DIR = Path(__file__).resolve().parent / "assets/screens"
KALI = story_clock.KALI
NOVNC = "http://127.0.0.1:6901/vnc.html?autoconnect=true&password=99&resize=scale"
# Kaliのデスクトップと同じ大きさで撮り、拡大縮小でぼかさない
VIEWPORT = {"width": 1280, "height": 800}

TERM_TITLE = "pv-capture"


def kali(command: str, detach: bool = False) -> None:
    args = ["docker", "exec", "--user", "player", "-e", "DISPLAY=:1"]
    if detach:
        args.append("-d")
    subprocess.run([*args, KALI, "bash", "-lc", command], check=True)


def close_capture_windows() -> None:
    # 先頭の1文字を [ ] で囲み、このコマンド自身のコマンドラインに一致しないようにする
    kali(f"pkill -f -- '[-]-title={TERM_TITLE}' ; true")
    time.sleep(1.0)


def open_novnc(page: Page) -> None:
    page.goto(NOVNC)
    page.wait_for_selector("#noVNC_canvas, canvas", state="visible", timeout=20000)
    time.sleep(2.0)


def shot(page: Page, name: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUT_DIR / name))
    print(f"保存: {OUT_DIR / name}")


def capture_terminal(page: Page, inputs: tuple[tuple[str, float], ...], name: str, clock: str) -> None:
    """端末で実際にコマンドを打ち込み、結果が出た画面を撮る。

    inputs は（打ち込む文字列, Enterのあと待つ秒数）の並び。
    端末は作中の時刻 clock から時計が進む状態で開く。
    """
    kali(
        f"{story_clock.exports(clock)} cd ~ && xfce4-terminal --disable-server --title={TERM_TITLE} "
        "--geometry=104x30+90+60 --hide-menubar",
        detach=True,
    )
    time.sleep(2.5)
    page.mouse.click(640, 300)  # 端末にフォーカスを移す
    for text, wait in inputs:
        page.keyboard.type(text, delay=50)
        page.keyboard.press("Enter")
        time.sleep(wait)
    shot(page, name)
    close_capture_windows()


def main() -> None:
    story_clock.ensure_faketime()
    close_capture_windows()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT)
        open_novnc(page)
        capture_terminal(page, (("nmap -sV www.mikuriya-suisan.local", 12.0),), "kali_terminal_nmap.png", "13:00:00")
        browser.close()


if __name__ == "__main__":
    main()
