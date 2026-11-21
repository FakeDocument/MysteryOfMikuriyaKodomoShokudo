# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "numpy",
#     "pillow",
#     "budoux",
#     "segno>=1.6.6",
# ]
# ///
"""動画サムネイルを作る。エマのいない集合写真を古い録画の一場面のように加工し、タイトルを重ねる。

写真は16:9に切り出して1920x1080へ拡大し、目線の黒線を重ねる。色を抜いて緑がかった暗い色調に沈め、
VHSの劣化（vhs.apply）と、まばらなノイズの横線・色の縦すじを足す。
タイトルは最後に白い明朝で、画面の幅いっぱいに置く。

    uv run promo/pv/thumbnail.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import vhs
from pixel import OUT_H, OUT_W, find_system_font
from scene_cm import _with_eye_bars

HERE = Path(__file__).parent
PHOTO = HERE / "assets" / "group_without_ema.png"
OUT = HERE / "build" / "thumbnail.png"

SUBTITLE = "子供の消える寿司屋"  # 上の段（中くらい）
TITLE = "御厨水産の謎"  # 下の段（大きく）
MINCHO = find_system_font("YuMincho.ttc", "游明朝")
EXTRABOLD = 2
TITLE_WIDTH = 0.8  # 画面の幅に対する下の段の幅
SUBTITLE_SCALE = 0.42  # 下の段に対する上の段の文字の大きさ
LINE_GAP = 40  # 2段の間の余白
TITLE_CENTER_Y = OUT_H // 2  # 2段をまとめた塊の縦の中心
TITLE_INK = (246, 244, 238)
SHADOW_BLUR = 10
SHADOW_ALPHA = 0.7

CROP_TOP = 80  # 1536x1024 から 16:9 を切り出すときの上端
SATURATION = 0.35  # 元の彩度をどれだけ残すか
TINT = np.array([0.94, 1.0, 0.92], dtype=np.float32)  # 緑がかった色かぶり（R, G, B の倍率）
BRIGHTNESS = 0.72
BLACK_LIFT = 0.06
VHS_TIME = 7.4  # ノイズと横揺れの模様を決める時刻
GLITCH_LINES = 28  # ノイズの横線の本数
COLOR_STREAKS = 3  # 色の縦すじの本数
STREAK_STRENGTH = 0.07
SEED = 7


def _crop_16x9(img: Image.Image) -> Image.Image:
    w = img.width
    h = w * 9 // 16
    return img.crop((0, CROP_TOP, w, CROP_TOP + h)).resize((OUT_W, OUT_H), Image.Resampling.LANCZOS)


def _grade(img: Image.Image) -> np.ndarray:
    """色を抜き、緑がかった暗い色調にする。0〜1の浮動小数で返す。"""
    f = np.asarray(img, np.float32) / 255
    gray = f @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    f = gray[..., None] + (f - gray[..., None]) * SATURATION
    return np.clip(f * TINT * BRIGHTNESS + BLACK_LIFT, 0, 1)


def _glitches(f: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """まばらな白いノイズの横線と、うっすらとした色の縦すじを足す。"""
    out = f.copy()
    h, w = out.shape[:2]
    for _ in range(GLITCH_LINES):
        y = int(rng.integers(0, h - 2))
        x0 = int(rng.integers(0, w))
        length = int(rng.integers(20, 160))
        out[y : y + 2, x0 : x0 + length] += rng.uniform(0.15, 0.45)
    # 色の縦すじは、横に赤・緑・青を少しずつずらしたぼかしの帯にする
    xs = np.arange(w, dtype=np.float32)
    ys = np.arange(h, dtype=np.float32)
    for _ in range(COLOR_STREAKS):
        cx = float(rng.integers(w // 8, w * 7 // 8))
        cy = float(rng.integers(h // 4, h * 3 // 4))
        width, height = float(rng.integers(14, 28)), float(rng.integers(h // 6, h // 3))
        fade_y = np.exp(-(((ys - cy) / height) ** 2))[:, None]
        for channel, dx in enumerate((-width, 0.0, width)):
            fade_x = np.exp(-(((xs - cx - dx) / width) ** 2))[None, :]
            out[..., channel] += STREAK_STRENGTH * fade_y * fade_x
    return np.clip(out, 0, 1)


def _title_size() -> int:
    """下の段が画面の幅の TITLE_WIDTH 倍に収まる文字の大きさを返す。"""
    probe = ImageFont.truetype(MINCHO, 100, index=EXTRABOLD)
    return int(100 * OUT_W * TITLE_WIDTH / probe.getlength(TITLE))


def _title_lines() -> list[tuple[str, ImageFont.FreeTypeFont, tuple[int, int]]]:
    """上の段と下の段の、文字・書体・中心位置を返す。2段の塊が TITLE_CENTER_Y を中心にくるよう並べる。"""
    size = _title_size()
    sub_font = ImageFont.truetype(MINCHO, int(size * SUBTITLE_SCALE), index=EXTRABOLD)
    main_font = ImageFont.truetype(MINCHO, size, index=EXTRABOLD)
    sub_h, main_h = int(sub_font.size), int(main_font.size)
    top = TITLE_CENTER_Y - (sub_h + LINE_GAP + main_h) // 2
    return [
        (SUBTITLE, sub_font, (OUT_W // 2, top + sub_h // 2)),
        (TITLE, main_font, (OUT_W // 2, top + sub_h + LINE_GAP + main_h // 2)),
    ]


def _draw_title(img: Image.Image) -> Image.Image:
    """白い明朝に、ぼかした黒い影だけを添える。"""
    lines = _title_lines()
    shadow = Image.new("L", img.size, 0)
    shadow_draw = ImageDraw.Draw(shadow)
    for text, font, center in lines:
        shadow_draw.text(center, text, font=font, fill=255, anchor="mm")
    shadow = shadow.filter(ImageFilter.GaussianBlur(SHADOW_BLUR))
    out = Image.composite(
        Image.new("RGB", img.size), img, shadow.point(lambda v: v * SHADOW_ALPHA)
    )
    draw = ImageDraw.Draw(out)
    for text, font, center in lines:
        draw.text(center, text, font=font, fill=TITLE_INK, anchor="mm")
    return out


def build() -> Path:
    rng = np.random.default_rng(SEED)
    photo = _with_eye_bars(Image.open(PHOTO).convert("RGB"), PHOTO.name)
    graded = (_grade(_crop_16x9(photo)) * 255).astype(np.uint8)
    worn = vhs.apply(graded, VHS_TIME, show_osd=False, seed=SEED)
    worn = _glitches(worn.astype(np.float32) / 255, rng)
    out = _draw_title(Image.fromarray((worn * 255).astype(np.uint8)))
    OUT.parent.mkdir(exist_ok=True)
    out.save(OUT)
    out.resize((1280, 720), Image.Resampling.LANCZOS).save(OUT.with_name("thumbnail_1280.png"))
    return OUT


if __name__ == "__main__":
    print(build())
