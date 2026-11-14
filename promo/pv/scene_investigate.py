"""0:22〜0:33 ゲーム紹介：本物のKaliを操作し、実際に動くサーバーを調べることを見せる。

1カット目は、noVNCで開いたKaliのデスクトップの実画面（capture_screens.py）で、本物であることを見せる。
2カット目からは1920x1080で描く。端末は実際のコマンドの出力（capture_transcripts.py）を、
ブラウザは標的サイトを実際に描画したページ（capture_pages.py）を使い、枠だけを描く。ドット化はしない。
ここだけアップテンポな曲（audio.drive_theme）に乗せ、1小節ごとにカットを切り替える。
各カットは1小節かけて、一定の速さでゆっくり寄る。
この場面に限り、機能を短く伝える見出しを入れる（台本で決めた例外）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import browser_view
import term_view
from pixel import OUT_H, OUT_W

SCREENS = Path(__file__).resolve().parent / "assets/screens"
GOTHIC = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"

BARS = 6
DURATION = 11.0
BEAT = DURATION / (BARS * 4)
BPM = 60.0 / BEAT  # 約131。6小節がちょうど場面の長さになるテンポ
BAR = BEAT * 4

Camera = tuple[float, float, float]  # 倍率, 中心x, 中心y（その画の座標）


@dataclass(frozen=True)
class Cut:
    draw: Callable[[float], Image.Image]  # カットの中の時刻 → 画
    zoom_from: Camera
    zoom_to: Camera


HEADINGS = (
    (0, "ブラウザから、本物のKali Linuxを操作する"),
    (3, "調べる相手は、実際に動いているサーバー"),
)  # （最初のカット番号, 見出し）


@lru_cache(maxsize=None)
def _screen(name: str) -> Image.Image:
    path = SCREENS / name
    if not path.exists():
        raise FileNotFoundError(f"{path} がありません。uv run promo/pv/capture_screens.py で撮ってください")
    return Image.open(path).convert("RGB")


def _terminal(name: str, timing: term_view.Timing) -> Callable[[float], Image.Image]:
    lines = term_view.lay_out(name, timing)
    title = term_view.title_for(name)
    return lambda t: term_view.render(lines, t, title)


def _shop(t: float) -> Image.Image:
    """寿司屋HPを上からゆっくりスクロールする。"""
    page = browser_view.page_image("shop.jpg")
    info = browser_view.page_info("shop.json")
    y = int(_ease(t / BAR) * SHOP_SCROLL)
    return browser_view.render(page.crop((0, y, OUT_W, y + 1000)), info["url"], info["title"])


def _webmail(first: int, last: int) -> Callable[[float], Image.Image]:
    """社内Webメールの画面を、撮った順に1小節の中で送る。"""
    frames = browser_view.page_info("webmail.json")["frames"][first : last + 1]

    def draw(t: float) -> Image.Image:
        i = min(int(t / (BAR * 0.85) * len(frames)), len(frames) - 1)
        f = frames[i]
        return browser_view.render(browser_view.page_image(f["file"]), f["url"], f["title"])

    return draw


SHOP_SCROLL = 700
LOGIN_FRAMES = (0, 16)  # ログイン画面で、メールアドレスとパスワードを入れていく途中まで
INBOX_FRAME = 17

CUTS = (
    Cut(lambda _t: _screen("kali_terminal_nmap.png"), (1.15, 420, 230), (1.32, 380, 220)),
    Cut(_terminal("dirb", term_view.Timing(cps=95, lps=60)), (1.00, 960, 540), (1.10, 760, 640)),
    Cut(_terminal("smbclient", term_view.Timing(cps=80, lps=40)), (1.00, 960, 540), (1.10, 820, 420)),
    Cut(_shop, (1.00, 960, 540), (1.06, 900, 560)),
    # アドレスバーが画面に残る倍率までにとどめ、ブラウザで開いていることとURLを見せる
    Cut(_webmail(*LOGIN_FRAMES), (1.30, 960, 0), (1.42, 960, 0)),
    Cut(_webmail(INBOX_FRAME, INBOX_FRAME), (1.30, 960, 0), (1.42, 900, 0)),
)
assert len(CUTS) == BARS

HEADING_SLIDE = 0.28
END_FADE = 0.35


@lru_cache(maxsize=None)
def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(GOTHIC, size)


def _ease(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    return p * p * (3 - 2 * p)


def _ease_out(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    return 1 - (1 - p) ** 3


def _frame(cut: Cut, local: float) -> Image.Image:
    img = cut.draw(local)
    w, h = img.size
    p = local / BAR
    # 1小節かけて一定の速さで寄る。速さが途中で変わると、30fpsではカクついて見える
    zoom, cx, cy = (a + (b - a) * p for a, b in zip(cut.zoom_from, cut.zoom_to))
    cw = w / zoom
    ch = cw * OUT_H / OUT_W
    if ch > h:
        ch, cw = h, h * OUT_W / OUT_H
    x0 = min(max(cx - cw / 2, 0), w - cw)
    y0 = min(max(cy - ch / 2, 0), h - ch)
    return img.resize((OUT_W, OUT_H), Image.Resampling.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))


def _heading_at(index: int) -> tuple[str, float]:
    """カット番号に対する見出しと、その見出しが出始めた時刻。"""
    text, start = HEADINGS[0][1], 0.0
    for first, heading in HEADINGS:
        if index >= first:
            text, start = heading, first * BAR
    return text, start


def _draw_heading(img: Image.Image, text: str, since: float) -> Image.Image:
    """画面下に、半透明の帯と白い見出しを重ねる。左から滑り込ませる。"""
    p = _ease_out(since / HEADING_SLIDE)
    if p <= 0:
        return img
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    band_top, band_bottom = OUT_H - 220, OUT_H - 80
    band_right = int(OUT_W * p)
    draw.rectangle((0, band_top, band_right, band_bottom), fill=(10, 18, 16, 185))
    # 帯の先端に細い朱の線を付け、動きを見せる
    draw.rectangle((band_right - 8, band_top, band_right, band_bottom), fill=(201, 72, 56, 255))
    offset = int((1 - p) * -120)
    draw.text(
        (OUT_W / 2 + offset, (band_top + band_bottom) / 2),
        text,
        font=_font(60),
        fill=(255, 255, 255, int(255 * p)),
        anchor="mm",
    )
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def render(t: float) -> np.ndarray:
    index = min(int(t / BAR), len(CUTS) - 1)
    local = t - index * BAR
    frame = _frame(CUTS[index], local)
    text, since = _heading_at(index)
    frame = _draw_heading(frame, text, t - since - 0.05)
    arr = np.asarray(frame, dtype=np.float32)
    # 前の場面からは拍の頭で切り替え、最後だけ黒へ落とす
    arr *= _ease((DURATION - t) / END_FADE)
    return arr.astype(np.uint8)
