"""0:19〜0:25 表の顔：御厨水産の公開サイトの写真を、明るい曲に合わせて切り替える。

この場面だけはドット化せず、写真の質感を残して1920x1080で描く。
看板は公開サイトの子ども食堂ページにある朱色のスタンプ（.community-stamp）の意匠を借りる。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from pixel import OUT_H, OUT_W, find_system_font

ASSETS = Path(__file__).resolve().parents[2] / "docker/sushi/site/assets"
BEAT = 0.5  # テンポ120
BAR = BEAT * 4
DURATION = BAR * 3

# style.css の --red と --paper
RED = (201, 72, 56)
PAPER = (255, 253, 247)
MINCHO = find_system_font("YuMincho.ttc", "游明朝")
SIGN_LINES = ("みくりや", "子ども食堂")


@dataclass(frozen=True)
class Cut:
    start: float
    photo: str
    focus_y: float  # 16:9に切り抜くときの縦位置（0=上端、1=下端）
    zoom: tuple[float, float]  # カットの頭と終わりの拡大率


CUTS = (
    Cut(0.0, "mikuriya-sushi-hero.jpg", 0.75, (1.00, 1.06)),
    Cut(BAR, "mikuriya-blog-kodomo-shokudo.jpg", 0.45, (1.04, 1.00)),
    Cut(BAR * 2, "mikuriya-blog-autumn.jpg", 0.55, (1.00, 1.06)),
)
SIGN_IN = BAR  # 子ども食堂の写真と同時に看板を出す
SIGN_POP = 0.28


@lru_cache(maxsize=None)
def _photo(name: str) -> Image.Image:
    return Image.open(ASSETS / name).convert("RGB")


def _frame_photo(cut: Cut, local: float) -> Image.Image:
    img = _photo(cut.photo)
    w, h = img.size
    p = local / BAR
    zoom = cut.zoom[0] + (cut.zoom[1] - cut.zoom[0]) * p
    cw = w / zoom
    ch = cw * OUT_H / OUT_W
    if ch > h:
        ch, cw = h, h * OUT_W / OUT_H
    x0 = (w - cw) / 2
    y0 = (h - ch) * cut.focus_y
    return img.resize((OUT_W, OUT_H), Image.Resampling.BICUBIC, box=(x0, y0, x0 + cw, y0 + ch))


@lru_cache(maxsize=1)
def _sign() -> Image.Image:
    """朱色のスタンプ風の看板。いびつな丸、白い縁、外側の破線、白抜きの明朝。"""
    size = 420
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = size // 2
    r = 170
    # 外側の破線（outline: 2px dashed、outline-offset: 8px）
    for i in range(48):
        a0, a1 = i * 7.5, i * 7.5 + 4.2
        d.arc((c - r - 22, c - r - 22, c + r + 22, c + r + 22), a0, a1, fill=RED + (255,), width=4)
    d.ellipse((c - r, c - r + 4, c + r, c + r - 2), fill=(255, 255, 255, 150))  # 白い縁
    d.ellipse((c - r + 22, c - r + 24, c + r - 20, c + r - 22), fill=RED + (255,))
    font = ImageFont.truetype(MINCHO, 46, index=1)
    for i, line in enumerate(SIGN_LINES):
        tw = d.textlength(line, font=font) + 6 * (len(line) - 1)
        x, y = c - tw / 2, c - 58 + i * 64
        for ch in line:
            d.text((x, y), ch, font=font, fill=PAPER + (255,))
            x += d.textlength(ch, font=font) + 6
    return img.rotate(4, resample=Image.Resampling.BICUBIC)


def _ease_out_back(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    k = 1.7
    return 1 + (k + 1) * (p - 1) ** 3 + k * (p - 1) ** 2


def render(t: float) -> np.ndarray:
    cut = CUTS[0]
    for c in CUTS:
        if t >= c.start:
            cut = c
    frame = _frame_photo(cut, t - cut.start)
    if t >= SIGN_IN:
        p = (t - SIGN_IN) / SIGN_POP
        scale = 1.35 - 0.35 * _ease_out_back(p)
        sign = _sign()
        sz = int(sign.width * scale)
        s = sign.resize((sz, sz), Image.Resampling.BICUBIC)
        if p < 1:
            alpha = s.getchannel("A").point(lambda a: int(a * min(p * 2.5, 1.0)))
            s.putalpha(alpha)
        cx, cy = int(OUT_W * 0.80), int(OUT_H * 0.62)
        frame.paste(s, (cx - sz // 2, cy - sz // 2), s)
    return np.asarray(frame)


def audio_cues() -> dict[str, float]:
    """曲の頭と、看板が出る時刻。"""
    return {"theme": 0.0, "sign": SIGN_IN}
