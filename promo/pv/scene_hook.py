"""0:00〜0:05 フック：便箋の接写に「ささき えまちゃんを さがしてください」を書いていく。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pixel import (
    FONT_HOOK,
    WORLD_H,
    WORLD_W,
    PAPER,
    PAPER_RULE,
    PAPER_SHADE,
    Glyph,
    child_glyph,
    dither_fade,
    paint_glyph,
)

W, H = WORLD_W, WORLD_H
DURATION = 5.0

LINES = ("ささき えまちゃんを", "さがしてください")
LINE_Y = (146, 226)
CHAR_STEP = 46

FADE_IN = (0.0, 0.6)
WRITE_START = 0.7
CHAR_TIME = 0.19
SPACE_TIME = 0.12
LINE_PAUSE = 0.35
FADE_OUT = (4.75, 5.0)


@dataclass(frozen=True)
class TimedGlyph:
    glyph: Glyph
    start: float
    end: float


def _layout(seed: int = 7) -> tuple[TimedGlyph, ...]:
    rng = np.random.default_rng(seed)
    timed: list[TimedGlyph] = []
    t = WRITE_START
    for line, y in zip(LINES, LINE_Y):
        line_w = sum(CHAR_STEP // 2 if ch == " " else CHAR_STEP for ch in line)
        x = (W - line_w) // 2 + CHAR_STEP // 2
        for ch in line:
            if ch == " ":
                x += CHAR_STEP // 2
                t += SPACE_TIME
                continue
            glyph = child_glyph(ch, FONT_HOOK, (x, y), rng, max_angle=9.0)
            timed.append(TimedGlyph(glyph, t, t + CHAR_TIME))
            x += CHAR_STEP + int(rng.integers(-3, 4))
            t += CHAR_TIME
        t += LINE_PAUSE
    return tuple(timed)


GLYPHS = _layout()


def writing_spans() -> tuple[tuple[float, float], ...]:
    """効果音の同期に使う、各文字を書いている区間。"""
    return tuple((g.start, g.end) for g in GLYPHS)


def _paper(seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = np.broadcast_to(np.array(PAPER, np.uint8), (H, W, 3)).copy()
    grain = rng.random((H, W)) < 0.05
    base[grain] = PAPER_SHADE
    # 子ども用便箋の罫線
    for y in (LINE_Y[0] + 26, LINE_Y[1] + 26):
        base[y, 24 : W - 24] = PAPER_RULE
    # 周辺を網点で暗くし、手元だけ照らされているように見せる
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.hypot((xx - W / 2) / (W * 0.7), (yy - H / 2) / (H * 0.9))
    shade = np.clip((r - 0.55) / 0.3, 0, 1)
    return dither_fade(base, shade)


PAPER_FRAME = _paper()


def render(t: float) -> np.ndarray:
    frame = PAPER_FRAME.copy()
    for g in GLYPHS:
        if t >= g.start:
            paint_glyph(frame, g.glyph, (t - g.start) / (g.end - g.start))

    if t < FADE_IN[1]:
        darkness = 1 - (t - FADE_IN[0]) / (FADE_IN[1] - FADE_IN[0])
        frame = dither_fade(frame, darkness)
    elif t > FADE_OUT[0]:
        darkness = (t - FADE_OUT[0]) / (FADE_OUT[1] - FADE_OUT[0])
        frame = dither_fade(frame, min(darkness, 1.0))
    return frame


