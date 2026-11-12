"""PV用のドット描画ユーティリティ。

すべての絵は低解像度の「ワールド座標」で描き、最後に最近傍補間で拡大する。
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUT_W, OUT_H = 1920, 1080
FPS = 30
# 基本のワールド解像度（3倍で1920x1080）。立ち絵の128x128と同じくらいの細かさにする
WORLD_W, WORLD_H = 640, 360


def _find_klee() -> str:
    """macOS付属の手書き風書体Klee。オンデマンド資産なので場所が固定されていない。"""
    hits = sorted(glob.glob("/System/Library/AssetsV2/com_apple_MobileAsset_Font*/*/AssetData/Klee.ttc"))
    if not hits:
        raise FileNotFoundError(
            "Klee書体が見つかりません。Font Book で「Klee」をダウンロードしてください"
        )
    return hits[0]


FontSpec = tuple[str, int]

KLEE = _find_klee()
FONT_HOOK: FontSpec = (KLEE, 40)
FONT_LETTER: FontSpec = (KLEE, 16)
FONT_SIGNATURE: FontSpec = (KLEE, 22)
FONT_STAMP: FontSpec = (os.path.expanduser("~/Library/Fonts/JF-Dot-Shinonome12.ttf"), 12)

RGB = tuple[int, int, int]

# 4x4のベイヤー行列（0〜1に正規化）。グラデーションをドットの網で表すために使う
BAYER4 = (
    np.array(
        [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]],
        dtype=np.float32,
    )
    + 0.5
) / 16.0

PAPER = (239, 230, 207)
PAPER_SHADE = (222, 210, 182)
PAPER_RULE = (196, 205, 214)
GRAPHITE = (58, 58, 66)
GRAPHITE_LIGHT = (112, 110, 118)
STAMP_RED = (196, 52, 44)
BLACK = (0, 0, 0)


@lru_cache(maxsize=None)
def load_font(spec: FontSpec) -> ImageFont.FreeTypeFont:
    path, size = spec
    return ImageFont.truetype(path, size, index=0)


def glyph_mask(ch: str, spec: FontSpec) -> np.ndarray:
    """1文字を1bitのマスクとして描く。アンチエイリアスはかけない。"""
    font = load_font(spec)
    size = spec[1]
    canvas = Image.new("1", (size * 2, size * 2), 0)
    draw = ImageDraw.Draw(canvas)
    draw.fontmode = "1"
    draw.text((size // 2, size // 2), ch, font=font, fill=1)
    return np.array(canvas, dtype=bool)


@dataclass(frozen=True)
class Glyph:
    """書き順付きで配置された1文字分の画素。"""

    xs: np.ndarray
    ys: np.ndarray
    colors: np.ndarray  # (N, 3) uint8

    @property
    def count(self) -> int:
        return int(self.xs.size)


def child_glyph(
    ch: str,
    spec: FontSpec,
    origin: tuple[int, int],
    rng: np.random.Generator,
    max_angle: float = 6.0,
) -> Glyph:
    """子どもの鉛筆書き風に、傾き・大きさの揺れ・ずれ・かすれを加えた文字を作る。

    大きな字（フック用）は、線を太らせて字の大きさも1文字ずつ変える。
    """
    is_large = spec[1] >= 30
    if is_large:
        spec = (spec[0], spec[1] + int(rng.integers(-5, 4)))
    mask = glyph_mask(ch, spec)
    # 画数の多い漢字は小さいと回転でつぶれるので、傾きを控えめにする
    is_kana = "぀" <= ch <= "ヿ"
    limit = max_angle if is_kana or is_large else min(max_angle, 2.0)
    angle = float(rng.uniform(-limit, limit))
    rotated = Image.fromarray(mask.astype(np.uint8) * 255).rotate(
        angle, resample=Image.Resampling.NEAREST
    )
    arr = np.array(rotated) > 127
    if is_large:
        arr = bold(arr)
    ys, xs = np.nonzero(arr)
    if xs.size == 0:
        return Glyph(np.empty(0, int), np.empty(0, int), np.empty((0, 3), np.uint8))

    # glyph_mask は文字を枠の中央（size, size）付近に描くので、origin が文字の中心になるようずらす
    size = spec[1]
    wobble = max(1, size // 10)
    dx = origin[0] - size + int(rng.integers(-wobble, wobble + 1))
    dy = origin[1] - size + int(rng.integers(-wobble, wobble + 1))

    # 左上から右下へ、少し揺らぎを入れて「書いていく」順に並べる
    order = np.argsort(xs * 1.0 + ys * 0.35 + rng.normal(0, 1.2, xs.size))
    xs, ys = xs[order] + dx, ys[order] + dy

    # 鉛筆のかすれ：一部を薄く、ごく一部を抜く
    roll = rng.random(xs.size)
    keep = roll > 0.04
    colors = np.where(
        (roll < 0.20)[:, None], np.array(GRAPHITE_LIGHT), np.array(GRAPHITE)
    ).astype(np.uint8)
    return Glyph(xs[keep], ys[keep], colors[keep])


def paint_glyph(frame: np.ndarray, glyph: Glyph, progress: float) -> None:
    """書き順に沿って progress (0〜1) の割合だけ画素を置く。"""
    n = int(round(glyph.count * min(max(progress, 0.0), 1.0)))
    if n == 0:
        return
    xs, ys, cs = glyph.xs[:n], glyph.ys[:n], glyph.colors[:n]
    h, w = frame.shape[:2]
    inside = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
    frame[ys[inside], xs[inside]] = cs[inside]


def bayer_threshold(h: int, w: int, offset: tuple[int, int] = (0, 0)) -> np.ndarray:
    oy, ox = offset
    ty = np.tile(BAYER4, (h // 4 + 2, w // 4 + 2))
    return ty[oy % 4 : oy % 4 + h, ox % 4 : ox % 4 + w]


def dither_mix(a: np.ndarray, b: np.ndarray, t: np.ndarray) -> np.ndarray:
    """t (0〜1) に応じて a と b をベイヤー網点で切り替える。"""
    h, w = t.shape
    pick_b = t > bayer_threshold(h, w)
    return np.where(pick_b[..., None], b, a)


def dither_fade(frame: np.ndarray, darkness: float | np.ndarray) -> np.ndarray:
    """黒への網点フェード。darkness=1で真っ黒。"""
    h, w = frame.shape[:2]
    t = np.broadcast_to(np.asarray(darkness, dtype=np.float32), (h, w))
    return dither_mix(frame, np.zeros_like(frame), t)


def spotlight(frame: np.ndarray, focus: np.ndarray, amount: float) -> np.ndarray:
    """focus の外側を網点で暗くして、読ませたい所へ視線を集める。

    amount=0で効果なし、1で外側が最も暗くなる。
    """
    if amount <= 0:
        return frame
    amount = min(amount, 1.0)
    shadow = (frame.astype(np.float32) * 0.42).astype(np.uint8)
    h, w = focus.shape
    # 影の縁だけを網点でぼかす。影の中は単色にして、紙のざらつきが目立たないようにする
    edge = _dilate(focus, 3) & ~focus
    t = np.where(focus, 0.0, np.where(edge, 0.5 * amount, amount)).astype(np.float32)
    pick = t > bayer_threshold(h, w)
    return np.where(pick[..., None], shadow, frame)


def _dilate(mask: np.ndarray, r: int) -> np.ndarray:
    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out |= np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
    return out


def bold(mask: np.ndarray) -> np.ndarray:
    """鉛筆の線を1画素ぶん太らせる（右と下へ広げる）。"""
    return mask | np.roll(mask, 1, axis=1) | np.roll(mask, 1, axis=0)


def upscale(frame: np.ndarray) -> bytes:
    """ワールド画素を最近傍補間で出力解像度まで拡大し、生のRGBバイト列にする。"""
    h, w = frame.shape[:2]
    sx, sy = OUT_W // w, OUT_H // h
    if sx != sy or sx * w != OUT_W or sy * h != OUT_H:
        raise ValueError(f"整数倍で拡大できない大きさです: {w}x{h}")
    big = frame.repeat(sy, axis=0).repeat(sx, axis=1)
    return big.astype(np.uint8).tobytes()


def ease_out(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3
