"""ブラウザの枠（タブとアドレスバー）を描き、その中に実際に描画したページを置く。

ページの画像は capture_pages.py で撮ったもので、加工しない。枠の高さは80px、ページは1920x1000。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from pixel import OUT_H, OUT_W

PAGES = Path(__file__).resolve().parent / "assets/pages"
GOTHIC = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"
GOTHIC_BOLD = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"

CHROME_H = OUT_H - 1000
TAB_H = 36
TAB_BAR = (232, 232, 237)
TOOLBAR = (249, 249, 251)
URL_BG = (240, 240, 244)
INK = (21, 20, 26)
MUTED = (91, 91, 102)
LINE = (207, 207, 216)


@lru_cache(maxsize=None)
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(GOTHIC_BOLD if bold else GOTHIC, size)


@lru_cache(maxsize=None)
def page_image(name: str) -> Image.Image:
    return Image.open(PAGES / name).convert("RGB")


@lru_cache(maxsize=None)
def page_info(name: str) -> dict:
    return json.loads((PAGES / name).read_text(encoding="utf-8"))


def _chrome(draw: ImageDraw.ImageDraw, url: str, title: str) -> None:
    draw.rectangle((0, 0, OUT_W, TAB_H + 4), fill=TAB_BAR)
    # 開いているタブ
    draw.rounded_rectangle((12, 4, 420, TAB_H + 8), radius=6, fill=TOOLBAR)
    draw.text((32, 4 + TAB_H / 2), title, font=_font(17), fill=INK, anchor="lm")
    draw.text((400, 4 + TAB_H / 2), "×", font=_font(18), fill=MUTED, anchor="mm")
    draw.text((448, 4 + TAB_H / 2), "+", font=_font(22), fill=MUTED, anchor="mm")
    # 戻る・進む・再読み込みとアドレスバー
    draw.rectangle((0, TAB_H + 4, OUT_W, CHROME_H), fill=TOOLBAR)
    mid = (TAB_H + 4 + CHROME_H) / 2
    for i, mark in enumerate(("←", "→", "↻")):
        draw.text((32 + i * 44, mid), mark, font=_font(22), fill=MUTED, anchor="mm")
    draw.rounded_rectangle((170, mid - 16, OUT_W - 170, mid + 16), radius=6, fill=URL_BG)
    scheme, _, rest = url.partition("://")
    x = 192
    draw.text((x, mid), f"{scheme}://", font=_font(18), fill=MUTED, anchor="lm")
    x += _font(18).getlength(f"{scheme}://")
    draw.text((x, mid), rest, font=_font(18), fill=INK, anchor="lm")
    draw.line((0, CHROME_H - 1, OUT_W, CHROME_H - 1), fill=LINE)


def render(page: Image.Image, url: str, title: str) -> Image.Image:
    """page は1920x1000に切り出したページ。"""
    img = Image.new("RGB", (OUT_W, OUT_H), TOOLBAR)
    _chrome(ImageDraw.Draw(img), url, title)
    img.paste(page, (0, CHROME_H))
    return img
