"""VHSテープの劣化表現。書き出す直前の1920x1080のフレームにかける。

色のにじみ、走査線、ノイズ、行ごとの横揺れ、画面下端のヘッド切り替えノイズ、
録画機の日時表示（OSD）を重ねる。光過敏に配慮し、全面の明滅は入れない。
"""

from __future__ import annotations

import os
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from pixel import OUT_H, OUT_W

H, W = OUT_H, OUT_W
OSD_FONT = (os.path.expanduser("~/Library/Fonts/JF-Dot-K14.ttf"), 14)
OSD_SCALE = 4
# 物語の起点（序章）：2026年9月10日 13時00分
OSD_DATE = "SEP.10 2026"
OSD_START_SEC = 13 * 3600

CHROMA_SHIFT = 5
CHROMA_BLUR = 13
HEAD_SWITCH_ROWS = 14

_YY, _XX = np.mgrid[0:H, 0:W]


def _box_blur_x(a: np.ndarray, k: int) -> np.ndarray:
    pad = k // 2
    padded = np.pad(a, ((0, 0), (pad + 1, pad)), mode="edge")
    c = np.cumsum(padded, axis=1)
    return (c[:, k:] - c[:, :-k]) / k


@lru_cache(maxsize=1)
def _vignette() -> np.ndarray:
    r = np.hypot((_XX - W / 2) / (W * 0.62), (_YY - H / 2) / (H * 0.62))
    return np.clip(1.08 - r**2 * 0.45, 0.55, 1.0).astype(np.float32)


@lru_cache(maxsize=1)
def _scanlines() -> np.ndarray:
    lines = np.ones(H, dtype=np.float32)
    lines[2::4] = 0.86
    lines[3::4] = 0.80
    return lines[:, None]


def _row_offsets(t: float, rng: np.random.Generator, boost: float) -> np.ndarray:
    """行ごとの横ずれ（画素）。ゆるい波と、下端のヘッド切り替えノイズ。

    boost（0〜1）が大きいほど揺れが強まり、太いトラッキングの乱れが常に出る。
    """
    y = np.arange(H, dtype=np.float32)
    amp = 1 + boost * 9
    dx = amp * (1.4 * np.sin(y * 0.021 + t * 2.3) + 0.8 * np.sin(y * 0.11 - t * 7.0))
    if boost > 0:
        band_y = int(H * ((t * 1.7) % 1.0))
        band = np.abs(y - band_y) < 20 + boost * 120
        dx[band] += rng.normal(boost * 60, boost * 25, int(band.sum()))
    tail = slice(H - HEAD_SWITCH_ROWS, H)
    dx[tail] += 18 + rng.normal(0, 6, HEAD_SWITCH_ROWS)
    # ときどき細いトラッキングの乱れが画面を流れる（数秒に一度、0.5秒ほど）
    phase = (t * 0.35) % 1.0
    if phase < 0.15:
        band_y = int(H * (1.0 - phase / 0.15))
        band = (y > band_y - 10) & (y < band_y + 10)
        dx[band] += rng.normal(10, 4, int(band.sum()))
    return dx.round().astype(np.int32)


def _osd(t: float) -> np.ndarray:
    """録画機の画面表示。白い文字に黒い影。"""
    small = Image.new("L", (W // OSD_SCALE, H // OSD_SCALE), 0)
    shadow = Image.new("L", small.size, 0)
    font = ImageFont.truetype(*OSD_FONT)
    secs = OSD_START_SEC + int(t)
    hh, mm, ss = secs // 3600, secs // 60 % 60, secs % 60
    ampm = "PM" if hh >= 12 else "AM"
    texts = (
        ((14, 10), "PLAY ▶"),
        ((14, small.height - 42), OSD_DATE),
        ((14, small.height - 26), f"{ampm} {hh % 12 or 12}:{mm:02d}:{ss:02d}"),
    )
    for img, off in ((shadow, 1), (small, 0)):
        d = ImageDraw.Draw(img)
        d.fontmode = "1"
        for (x, y), text in texts:
            d.text((x + off, y + off), text, font=font, fill=255)
    return np.stack([_enlarge_mask(small), _enlarge_mask(shadow)])


def _enlarge_mask(img: Image.Image) -> np.ndarray:
    return np.asarray(img.resize((W, H), Image.Resampling.NEAREST)) > 0


def apply(frame: np.ndarray, t: float, boost: float = 0.0, strength: float = 1.0,
          seed: int = 0) -> np.ndarray:
    """劣化をかける。strength（0〜1）は元の映像との混ぜ具合で、0なら何もしない。"""
    if strength <= 0:
        return frame
    rng = np.random.default_rng(seed + int(t * 1000))
    f = frame.astype(np.float32) / 255.0

    osd_text, osd_shadow = _osd(t)
    f[osd_shadow & ~osd_text] *= 0.15
    f[osd_text] = 0.95

    dx = _row_offsets(t, rng, boost)
    f = f[_YY, np.clip(_XX - dx[:, None], 0, W - 1)]

    # 輝度と色差に分け、色差だけ横に大きくにじませてずらす
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    i = 0.596 * r - 0.274 * g - 0.322 * b
    q = 0.211 * r - 0.523 * g + 0.312 * b
    shift = CHROMA_SHIFT + int(boost * 14)
    i = np.roll(_box_blur_x(i, CHROMA_BLUR), shift, axis=1) * 0.85
    q = np.roll(_box_blur_x(q, CHROMA_BLUR), shift, axis=1) * 0.85
    y = _box_blur_x(y, 3)
    out = np.stack(
        [y + 0.956 * i + 0.621 * q, y - 0.272 * i - 0.647 * q, y - 1.106 * i + 1.703 * q], axis=-1
    )

    # 黒浮き・ノイズ・走査線・周辺減光
    out = out * 0.88 + 0.05
    grain = rng.normal(0, 0.035 + boost * 0.06, (H // 2, W // 2)).astype(np.float32)
    out += grain.repeat(2, 0).repeat(2, 1)[..., None]
    tail = slice(H - HEAD_SWITCH_ROWS, H)
    out[tail] += rng.normal(0, 0.12, (HEAD_SWITCH_ROWS, W, 1)).astype(np.float32)
    out *= _scanlines()[..., None] * _vignette()[..., None]
    out = np.clip(out, 0, 1) * 255
    if strength < 1:
        out = frame.astype(np.float32) * (1 - strength) + out * strength
    return out.astype(np.uint8)
