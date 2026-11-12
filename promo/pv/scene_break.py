"""0:10〜0:12 CMが壊れる：テープが止まり、エンドカードがブロック状に崩れて暗く沈む。"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from PIL import Image

import scene_cm
from pixel import OUT_H, OUT_W, WORLD_H, WORLD_W, dither_fade, upscale

DURATION = 2.0
COLLAPSE_SEC = 0.9  # 崩れきるまで
TAPE_STOP_SEC = 0.8
MAX_BLOCK = 24  # 崩れきる直前のブロックの大きさ（出力画素）


@lru_cache(maxsize=1)
def _last_frame() -> Image.Image:
    return Image.fromarray(scene_cm.render(scene_cm.DURATION - 1e-3))


@lru_cache(maxsize=1)
def _remnant() -> np.ndarray:
    """崩れたあとに残る、暗く沈んだドット（ワールド解像度）。"""
    small = _last_frame().resize((WORLD_W, WORLD_H), Image.Resampling.BOX)
    quant = small.quantize(colors=12, dither=Image.Dither.NONE).convert("RGB")
    return dither_fade(np.asarray(quant), 0.9)


def render(t: float) -> np.ndarray:
    if t >= COLLAPSE_SEC:
        # 沈んだ残骸も、最後は黒へ落としてフックの場面へ渡す
        fade = min(max((t - COLLAPSE_SEC) / (DURATION - COLLAPSE_SEC), 0), 1)
        return upscale(dither_fade(_remnant(), 0.9 + 0.1 * fade))
    p = t / COLLAPSE_SEC
    block = max(1, int(round(1 + (MAX_BLOCK - 1) * p**1.5)))
    small = _last_frame().resize((max(1, OUT_W // block), max(1, OUT_H // block)), Image.Resampling.BOX)
    mosaic = np.asarray(small.resize((OUT_W, OUT_H), Image.Resampling.NEAREST)).astype(np.float32)
    return (mosaic * (1 - 0.7 * p)).astype(np.uint8)


def vhs_boost(t: float) -> float:
    """崩れる間にテープの乱れを最大まで強め、そのあと静かに戻す。"""
    if t < COLLAPSE_SEC:
        return 0.5 + 0.5 * (t / COLLAPSE_SEC) ** 0.7
    return max(0.0, 1 - (t - COLLAPSE_SEC) / 0.5) * 0.6
