"""0:05〜0:09 依頼書：机の上の依頼書を、接写から段階的に引いて見せる。

本文は調査ノートの序章JSONから読み込み、作中の依頼書と食い違わないようにする。
カットごとに読ませる一文を決め、それ以外を網点の影で落として視線を誘導する。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pixel import (
    FONT_LETTER,
    FONT_SIGNATURE,
    FONT_STAMP,
    OUT_H,
    OUT_W,
    PAPER,
    PAPER_RULE,
    PAPER_SHADE,
    STAMP_RED,
    FontSpec,
    Glyph,
    child_glyph,
    dither_fade,
    dither_mix,
    glyph_mask,
    paint_glyph,
    spotlight,
)
from wrap_ja import wrap

PROLOGUE = (
    Path(__file__).resolve().parents[2]
    / "docker/notebook/app/data/chapters/prologue.json"
)

DURATION = 7.0

CHARS_PER_LINE = 14
CHAR_STEP = 18
LINE_H = 25
PAPER_MARGIN = 18
PAPER_W = CHARS_PER_LINE * CHAR_STEP + PAPER_MARGIN * 2
PAPER_X = 200
PAPER_Y = 30
WORLD_W = PAPER_X * 2 + PAPER_W

FULLWIDTH_DIGITS = str.maketrans("0123456789", "０１２３４５６７８９")

WOOD_DARK = (58, 36, 26)
WOOD = (92, 58, 38)
WOOD_LIGHT = (128, 84, 52)
WOOD_SEAM = (40, 24, 18)

SPOT_DELAY = 0.12
SPOT_RAMP = 0.35
SNAP_SEC = 0.05


@dataclass(frozen=True)
class Shot:
    start: float
    scale: int  # ワールド1画素を出力の何pxにするか（1920と1080を割り切れる値）
    focus: tuple[str, ...]  # 読ませたい文。これ以外を影で落とす
    drift_x: float = 0.0  # 1秒あたりの横移動量（ワールド画素）
    offset_x: int = 0


SHOTS = (
    Shot(0.0, 6, ("食堂へ来たあとから、いなくなりました。",), drift_x=4.0),
    Shot(2.3, 4, ("「家出かもしれない」って、さがしてくれません。",), drift_x=3.0),
    Shot(4.6, 3, ("「エマちゃんは、そろそろころあいね」",)),
)


def _load_letter() -> dict:
    data = json.loads(PROLOGUE.read_text(encoding="utf-8"))
    for block in data["chapter"]["blocks"]:
        if block.get("id") == "request-letter":
            return block["content"]
    raise KeyError("序章JSONに依頼書（request-letter）が見つかりません")


@dataclass(frozen=True)
class CharPos:
    block: int  # 何番目の文のまとまりか（宛名・本文の段落・日付・署名）
    offset: int  # まとまりの中で何文字目か
    x: int
    y: int


@dataclass(frozen=True)
class LetterLayout:
    glyphs: tuple[Glyph, ...]
    blocks: tuple[str, ...]
    chars: tuple[CharPos, ...]
    rule_ys: tuple[int, ...]
    paper_h: int


def _layout(seed: int = 11) -> LetterLayout:
    letter = _load_letter()
    rng = np.random.default_rng(seed)
    glyphs: list[Glyph] = []
    blocks: list[str] = []
    chars: list[CharPos] = []
    rule_ys: list[int] = []
    left = PAPER_X + PAPER_MARGIN + CHAR_STEP // 2
    y = PAPER_Y + PAPER_MARGIN + LINE_H // 2

    def put_block(text: str, x0: int | None, spec: FontSpec = FONT_LETTER) -> None:
        nonlocal y
        grow = spec[1] - FONT_LETTER[1]
        step = CHAR_STEP + grow
        block = len(blocks)
        blocks.append(text)
        offset = 0
        lines = wrap(text, CHARS_PER_LINE) if x0 is None else [text]
        for line in lines:
            x = left if x0 is None else x0
            # 手書きでは数字も漢字と同じ幅で書くので、全角に揃えて描く
            for ch in line.translate(FULLWIDTH_DIGITS):
                if ch not in " 　":
                    glyphs.append(child_glyph(ch, spec, (x, y), rng, 4.0))
                chars.append(CharPos(block, offset, x, y))
                offset += 1
                x += step + int(rng.integers(0, 2))
            rule_ys.append(y + LINE_H // 2 - 1)
            y += LINE_H + grow

    put_block(letter["title"], None)
    y += LINE_H // 2
    for para in letter["body"]:
        put_block("　" + para, None)
        y += LINE_H // 3
    y += LINE_H // 2
    right = PAPER_X + PAPER_W - PAPER_MARGIN
    for text, spec in ((letter["date"], FONT_LETTER), (letter["signature"], FONT_SIGNATURE)):
        step = CHAR_STEP + spec[1] - FONT_LETTER[1]
        put_block(text, right - step * len(text) + step // 2, spec)
    return LetterLayout(tuple(glyphs), tuple(blocks), tuple(chars), tuple(rule_ys),
                        y - PAPER_Y + PAPER_MARGIN // 2)


LAYOUT = _layout()
WORLD_H = PAPER_Y + LAYOUT.paper_h + 90


def _phrase_chars(phrase: str) -> list[CharPos]:
    """文を含むまとまりを探す。署名のように完全一致するものを優先する。"""
    exact = [i for i, b in enumerate(LAYOUT.blocks) if b == phrase]
    partial = [i for i, b in enumerate(LAYOUT.blocks) if phrase in b]
    candidates = exact or partial
    if not candidates:
        raise KeyError(f"依頼書に「{phrase}」が見つかりません")
    block = candidates[0]
    start = LAYOUT.blocks[block].index(phrase)
    span = range(start, start + len(phrase))
    return [c for c in LAYOUT.chars if c.block == block and c.offset in span]


def _focus_mask(phrases: tuple[str, ...]) -> np.ndarray:
    """読ませたい文を、行ごとに1本の帯として囲む。"""
    mask = np.zeros((WORLD_H, WORLD_W), dtype=bool)
    pad_x, half_h = CHAR_STEP // 2 + 3, LINE_H // 2 - 1
    for phrase in phrases:
        rows: dict[int, list[int]] = {}
        for c in _phrase_chars(phrase):
            rows.setdefault(c.y, []).append(c.x)
        for y, xs in rows.items():
            mask[y - half_h : y + half_h + 1, min(xs) - pad_x : max(xs) + pad_x + 1] = True
    # 帯が便箋の外（机）へはみ出さないようにする
    paper = np.zeros_like(mask)
    paper[PAPER_Y : PAPER_Y + LAYOUT.paper_h, PAPER_X + 2 : PAPER_X + PAPER_W - 2] = True
    return mask & paper


def _focus_center(phrases: tuple[str, ...]) -> tuple[float, float]:
    pts = [c for p in phrases for c in _phrase_chars(p)]
    xs, ys = [c.x for c in pts], [c.y for c in pts]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def _desk(rng: np.random.Generator) -> np.ndarray:
    yy, xx = np.mgrid[0:WORLD_H, 0:WORLD_W]
    # 卓上ライトの当たり方を、3段階の木目色の網点で表す。光は最後の引きの画面の中央付近に置く
    light = 1 - np.hypot(
        (xx - (PAPER_X + PAPER_W / 2)) / 420, (yy - (PAPER_Y + LAYOUT.paper_h - 150)) / 330
    )
    light = np.clip(light, 0, 1) * 2
    dark, mid, bright = (np.broadcast_to(np.array(c, np.uint8), (WORLD_H, WORLD_W, 3))
                         for c in (WOOD_DARK, WOOD, WOOD_LIGHT))
    low = dither_mix(dark, mid, np.clip(light, 0, 1))
    desk = np.where((light > 1)[..., None], dither_mix(mid, bright, light - 1), low)
    # 板の継ぎ目と木目
    desk[(yy % 92) == 0] = WOOD_SEAM
    desk[(yy % 92) == 1] = WOOD_DARK
    for _ in range(700):
        gy, gx = int(rng.integers(0, WORLD_H)), int(rng.integers(0, WORLD_W - 60))
        desk[gy, gx : gx + int(rng.integers(10, 60))] = WOOD_DARK
    return desk


def _stamp(img: np.ndarray, cx: int, cy: int) -> None:
    yy, xx = np.mgrid[0 : img.shape[0], 0 : img.shape[1]]
    d = np.hypot(xx - cx, yy - cy)
    img[(d <= 23) & (d > 20.5)] = STAMP_RED
    img[cy, cx - 18 : cx + 19] = STAMP_RED
    size = FONT_STAMP[1]
    for text, top in (("受付", cy - 16), ("9.10", cy + 3)):
        x = cx - (len(text) * (size if text == "受付" else size // 2)) // 2
        for ch in text:
            ys, xs = np.nonzero(glyph_mask(ch, FONT_STAMP))
            img[ys + top - size // 2, xs + x - size // 2] = STAMP_RED
            x += size if text == "受付" else size // 2


def _world() -> np.ndarray:
    rng = np.random.default_rng(5)
    img = _desk(rng)
    ph = LAYOUT.paper_h
    img[PAPER_Y + 4 : PAPER_Y + ph + 4, PAPER_X + 4 : PAPER_X + PAPER_W + 4] = WOOD_SEAM
    paper = img[PAPER_Y : PAPER_Y + ph, PAPER_X : PAPER_X + PAPER_W]
    paper[:] = PAPER
    paper[rng.random(paper.shape[:2]) < 0.05] = PAPER_SHADE
    for ry in LAYOUT.rule_ys:
        img[ry, PAPER_X + 8 : PAPER_X + PAPER_W - 8] = PAPER_RULE
    for g in LAYOUT.glyphs:
        paint_glyph(img, g, 1.0)
    # 受付印は、本文の最後の行の右にある余白へ押す
    last = [c for c in LAYOUT.chars if c.block == len(LAYOUT.blocks) - 3][-1]
    _stamp(img, PAPER_X + PAPER_W - 40, last.y + 8)
    return img


WORLD = _world()
FOCUS = tuple(_focus_mask(s.focus) for s in SHOTS)


def _shot_at(t: float) -> int:
    index = 0
    for i, shot in enumerate(SHOTS):
        if t >= shot.start:
            index = i
    return index


def render(t: float) -> np.ndarray:
    i = _shot_at(t)
    shot, local = SHOTS[i], t - SHOTS[i].start
    w, h = OUT_W // shot.scale, OUT_H // shot.scale
    fx, fy = _focus_center(shot.focus)
    x0 = int(np.clip(fx - w / 2 + shot.offset_x + local * shot.drift_x, 0, WORLD_W - w))
    y0 = int(np.clip(fy - h / 2, 0, WORLD_H - h))
    frame = WORLD[y0 : y0 + h, x0 : x0 + w].copy()
    amount = (local - SPOT_DELAY) / SPOT_RAMP
    frame = spotlight(frame, FOCUS[i][y0 : y0 + h, x0 : x0 + w], amount)
    if shot.start > 0 and local < SNAP_SEC:
        frame = dither_fade(frame, 0.5)
    return frame
