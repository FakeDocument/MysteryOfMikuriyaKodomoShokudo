"""0:37〜0:42 締め：タイトルロゴと、配布ページへのQRコード、右下に小さく注釈を出す。

証拠の場面が黒へ落ちたあと、タイトルを黒からゆっくり浮かび上がらせ、少し遅れてQRコードと注釈を出す。
QRコードは読み取りやすいよう、白地に黒のモジュールで描く。
1920x1080で描き、ドット化はしない。
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import segno
from PIL import Image, ImageDraw, ImageFont

from pixel import OUT_H, OUT_W, find_system_font

DURATION = 5.0

TITLE = "御厨こども食堂の謎"
SITE_URL = "https://fakedocument.github.io/MysteryOfMikuriyaKodomoShokudo/"
SITE_LABEL = "fakedocument.github.io/MysteryOfMikuriyaKodomoShokudo"
# READMEの注意書きと、作中の団体・人物・事件がフィクションであることを縮めて示す
NOTES = (
    "本作のハッキング演習は、同梱されたローカルのCTF環境だけを対象にしてください。",
    "作中の団体・人物・事件はすべてフィクションです。",
)

MINCHO = find_system_font("YuMincho.ttc", "游明朝")
GOTHIC = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"
EXTRABOLD = 2

INK = (236, 232, 224)
SUB_INK = (150, 146, 140)
TITLE_SIZE = 116
TITLE_CENTER = (680, 500)
QR_SIZE = 330  # 静かな余白を含めたQRコードの一辺
QR_CENTER = (1500, 500)
LABEL_SIZE = 24
NOTE_SIZE = 22
NOTE_MARGIN = 48  # 注釈の、画面の右端と下端からの余白
NOTE_LINE_GAP = 10

TITLE_FADE = (0.15, 1.2)
QR_FADE = (1.0, 1.7)


@lru_cache(maxsize=None)
def _font(path: str, size: int, index: int = 0) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size, index=index)


def _qr_image() -> Image.Image:
    """白地に黒のQRコードを、余白込みで QR_SIZE 四方に描く。拡大は最近傍補間でモジュールの縁を保つ。"""
    qr = segno.make(SITE_URL, error="m")
    width = qr.symbol_size(scale=1, border=4)[0]
    img = Image.new("L", (width, width), 255)
    pixels = img.load()
    for y, row in enumerate(qr.matrix_iter(scale=1, border=4)):
        for x, is_dark in enumerate(row):
            if is_dark:
                pixels[x, y] = 0
    scale = QR_SIZE // width
    return img.resize((width * scale, width * scale), Image.Resampling.NEAREST).convert("RGB")


def _layer_title() -> Image.Image:
    img = Image.new("RGB", (OUT_W, OUT_H), (0, 0, 0))
    ImageDraw.Draw(img).text(
        TITLE_CENTER, TITLE, font=_font(MINCHO, TITLE_SIZE, EXTRABOLD), fill=INK, anchor="mm"
    )
    return img


def _layer_qr() -> Image.Image:
    img = Image.new("RGB", (OUT_W, OUT_H), (0, 0, 0))
    qr = _qr_image()
    x0 = QR_CENTER[0] - qr.width // 2
    y0 = QR_CENTER[1] - qr.height // 2
    img.paste(qr, (x0, y0))
    draw = ImageDraw.Draw(img)
    draw.text(
        (QR_CENTER[0], y0 + qr.height + 20),
        SITE_LABEL,
        font=_font(GOTHIC, LABEL_SIZE),
        fill=SUB_INK,
        anchor="mt",
    )
    # 注釈は右下に小さく、右揃えで置く
    font = _font(GOTHIC, NOTE_SIZE)
    y = OUT_H - NOTE_MARGIN
    for line in reversed(NOTES):
        draw.text((OUT_W - NOTE_MARGIN, y), line, font=font, fill=SUB_INK, anchor="rd")
        y -= NOTE_SIZE + NOTE_LINE_GAP
    return img


TITLE_LAYER = np.asarray(_layer_title(), np.float32)
QR_LAYER = np.asarray(_layer_qr(), np.float32)


def _ramp(t: float, span: tuple[float, float]) -> float:
    p = min(max((t - span[0]) / (span[1] - span[0]), 0.0), 1.0)
    return p * p * (3 - 2 * p)


def render(t: float) -> np.ndarray:
    frame = TITLE_LAYER * _ramp(t, TITLE_FADE) + QR_LAYER * _ramp(t, QR_FADE)
    return np.clip(frame, 0, 255).astype(np.uint8)
