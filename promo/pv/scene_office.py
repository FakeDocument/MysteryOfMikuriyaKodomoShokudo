"""0:12〜0:19 事務所：調査ノートの会話欄で、主人公と所長が掛け合う。

台詞・話者名・表情は章JSONと話者定義から読み込み、作中の会話と食い違わないようにする。
吹き出しの色と配置は調査ノート（notebook.css の .dialogue-*）に合わせる。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from pixel import WORLD_H, WORLD_W, FontSpec, bayer_threshold, dither_fade, dither_mix, glyph_mask
from wrap_ja import wrap

APP = Path(__file__).resolve().parents[2] / "docker/notebook/app"
CHAPTER_1 = APP / "data/chapters/chapter-1.json"
SPEAKERS = APP / "data/dialogue-speakers.json"
AVATAR_DIR = APP / "static/images"

DURATION = 7.0
W, H = WORLD_W, WORLD_H

FONT_TEXT: FontSpec = (os.path.expanduser("~/Library/Fonts/JF-Dot-ShinonomeMin16.ttf"), 16)
FONT_NAME: FontSpec = (os.path.expanduser("~/Library/Fonts/JF-Dot-ShinonomeMin12.ttf"), 12)
CHAR_W = 16
LINE_H = 22
PAD_X, PAD_Y = 12, 10
AVATAR = 128

# notebook.css の色を、紙の上に重ねた結果の色として持つ
DESK = (16, 42, 37)
DESK_LIGHT = (29, 64, 55)
PAPER = (255, 253, 246)
RULE = (217, 228, 231)
INK = (22, 40, 35)
AVATAR_BG = (239, 232, 211)
AVATAR_EDGE = (190, 186, 170)
NAME_COLOR = {"player": (46, 88, 111), "director": (168, 59, 50)}
BUBBLE = {
    "player": ((238, 244, 245), (173, 191, 199)),
    "director": ((255, 255, 255), (185, 192, 190)),
}

TYPE_CPS = 18
APPEAR_SEC = 0.25
PAGE_X0, PAGE_X1 = 56, 584


@dataclass(frozen=True)
class Line:
    speaker: str
    expression: str
    text: str
    appear: float  # 吹き出しが出る時刻


SCRIPT = (
    ("ハッキング……って、それ、犯罪じゃないですか！？", 0.3),
    ("おやおや。子どもの命がかかっているかもしれないというのに、ずいぶん細かいことを気にしますね。", 2.6),
)


def _find_message(text: str) -> dict:
    data = json.loads(CHAPTER_1.read_text(encoding="utf-8"))

    def walk(node: object) -> dict | None:
        if isinstance(node, dict):
            if node.get("text") == text and "speaker" in node:
                return node
            for v in node.values():
                if (hit := walk(v)) is not None:
                    return hit
        if isinstance(node, list):
            for v in node:
                if (hit := walk(v)) is not None:
                    return hit
        return None

    hit = walk(data)
    if hit is None:
        raise KeyError(f"第1章に台詞「{text}」が見つかりません")
    return hit


def _lines() -> tuple[Line, ...]:
    out = []
    for text, appear in SCRIPT:
        msg = _find_message(text)
        out.append(Line(msg["speaker"], msg.get("expression", "normal"), text, appear))
    return tuple(out)


LINES = _lines()
SPEAKER_DEF = json.loads(SPEAKERS.read_text(encoding="utf-8"))["speakers"]


def _avatar(speaker: str, expression: str) -> np.ndarray:
    spec = SPEAKER_DEF[speaker]
    name = spec["avatars"].get(expression, spec["avatars"][spec["defaultExpression"]])
    img = Image.open(AVATAR_DIR / name).convert("RGBA")
    if img.size != (AVATAR, AVATAR):
        raise ValueError(f"立ち絵は{AVATAR}x{AVATAR}を想定しています: {name}")
    bg = Image.new("RGBA", img.size, AVATAR_BG + (255,))
    return np.array(Image.alpha_composite(bg, img).convert("RGB"))


@dataclass(frozen=True)
class Row:
    line: Line
    avatar_xy: tuple[int, int]
    bubble: tuple[int, int, int, int]  # x0, y0, x1, y1
    text_lines: tuple[str, ...]
    is_player: bool


def _row(line: Line, top: int, max_chars: int) -> Row:
    is_player = line.speaker == "player"
    text_lines = tuple(wrap(line.text, max_chars))
    bw = max(len(t) for t in text_lines) * CHAR_W + PAD_X * 2
    bh = len(text_lines) * LINE_H + PAD_Y * 2 - (LINE_H - CHAR_W)
    by = top + 17
    if is_player:
        ax = PAGE_X1 - 20 - AVATAR
        bx1 = ax - 14
        bubble = (bx1 - bw, by, bx1, by + bh)
    else:
        ax = PAGE_X0 + 20
        bx0 = ax + AVATAR + 14
        bubble = (bx0, by, bx0 + bw, by + bh)
    return Row(line, (ax, top), bubble, text_lines, is_player)


ROWS = (_row(LINES[0], 30, 17), _row(LINES[1], 196, 19))


def _background() -> np.ndarray:
    yy, xx = np.mgrid[0:H, 0:W]
    light = np.clip(1 - np.hypot((xx - W / 2) / (W * 0.6), (yy - H / 2) / (H * 0.8)), 0, 1)
    bg = dither_mix(
        np.broadcast_to(np.array(DESK, np.uint8), (H, W, 3)),
        np.broadcast_to(np.array(DESK_LIGHT, np.uint8), (H, W, 3)),
        light,
    ).copy()
    bg[:, PAGE_X0 + 3 : PAGE_X1 + 3] = (8, 22, 19)  # 紙の影
    bg[:, PAGE_X0:PAGE_X1] = PAPER
    for y in range(14, H, 24):
        bg[y, PAGE_X0 + 6 : PAGE_X1 - 6] = RULE
    return bg


def _round_rect(img: np.ndarray, box: tuple[int, int, int, int], fill: tuple[int, int, int],
                edge: tuple[int, int, int], sharp_corner: str) -> None:
    """角を丸めた枠を描く。吹き出しの尻尾側の上の角だけ角張らせる（notebook.css と同じ）。"""
    x0, y0, x1, y1 = box
    img[y0:y1, x0:x1] = edge
    img[y0 + 1 : y1 - 1, x0 + 1 : x1 - 1] = fill
    corners = {"tl": (x0, y0, 1, 1), "tr": (x1 - 1, y0, -1, 1), "bl": (x0, y1 - 1, 1, -1),
               "br": (x1 - 1, y1 - 1, -1, -1)}
    for key, (cx, cy, sx, sy) in corners.items():
        if key == sharp_corner:
            continue
        # 半径3の角：外側の画素を紙の色に戻し、内側に縁の色を置く
        for dx, dy in ((0, 0), (1, 0), (0, 1)):
            img[cy + dy * sy, cx + dx * sx] = PAPER
        img[cy + 1 * sy, cx + 1 * sx] = edge
        img[cy + 0 * sy, cx + 2 * sx] = edge
        img[cy + 2 * sy, cx + 0 * sx] = edge


def _draw_tail(img: np.ndarray, row: Row, fill: tuple[int, int, int], edge: tuple[int, int, int]) -> None:
    x0, y0, x1, _ = row.bubble
    ty = y0 + 13
    for i in range(6):
        if row.is_player:
            img[ty - 5 + i, x1 - 1 + (5 - abs(i - 5))] = edge
            img[ty - 5 + i, x1 - 1 : x1 - 1 + (5 - abs(i - 5))] = fill
        else:
            img[ty - 5 + i, x0 - (5 - abs(i - 5))] = edge
            img[ty - 5 + i, x0 - (5 - abs(i - 5)) + 1 : x0 + 1] = fill
    for i in range(6, 11):
        k = 10 - i
        if row.is_player:
            img[ty - 5 + i, x1 - 1 + k] = edge
            img[ty - 5 + i, x1 - 1 : x1 - 1 + k] = fill
        else:
            img[ty - 5 + i, x0 - k] = edge
            img[ty - 5 + i, x0 - k + 1 : x0 + 1] = fill


def _text(img: np.ndarray, text: str, x: int, y: int, spec: FontSpec, color: tuple[int, int, int],
          advance: int) -> None:
    size = spec[1]
    for ch in text:
        ys, xs = np.nonzero(glyph_mask(ch, spec))
        img[ys + y - size // 2, xs + x - size // 2] = color
        x += advance


def _draw_row(img: np.ndarray, row: Row, chars_shown: int) -> None:
    ax, ay = row.avatar_xy
    img[ay - 1 : ay + AVATAR + 1, ax - 1 : ax + AVATAR + 1] = AVATAR_EDGE
    img[ay : ay + AVATAR, ax : ax + AVATAR] = _avatar(row.line.speaker, row.line.expression)

    fill, edge = BUBBLE[row.line.speaker]
    _round_rect(img, row.bubble, fill, edge, "tr" if row.is_player else "tl")
    _draw_tail(img, row, fill, edge)

    name = SPEAKER_DEF[row.line.speaker]["name"]
    x0, y0, x1, _ = row.bubble
    name_x = x1 - 8 - len(name) * 12 if row.is_player else x0 + 8
    _text(img, name, name_x, y0 - 16, FONT_NAME, NAME_COLOR[row.line.speaker], 12)

    remaining = chars_shown
    for i, line in enumerate(row.text_lines):
        if remaining <= 0:
            break
        part = line[:remaining]
        remaining -= len(line)
        _text(img, part, x0 + PAD_X, y0 + PAD_Y + i * LINE_H, FONT_TEXT, INK, CHAR_W)


BACKGROUND = _background()


def type_start(row: Row) -> float:
    return row.line.appear + APPEAR_SEC * 0.6


def typed_chars(row: Row, t: float) -> int:
    return max(0, int((t - type_start(row)) * TYPE_CPS))


def render(t: float) -> np.ndarray:
    frame = BACKGROUND.copy()
    for row in ROWS:
        if t < row.line.appear:
            continue
        layer = BACKGROUND.copy()
        _draw_row(layer, row, typed_chars(row, t))
        # 調査ノートの ink-appear と同じく、少し下から浮かび上がるように網点で出す
        p = min((t - row.line.appear) / APPEAR_SEC, 1.0)
        rise = int(round((1 - p) * 4))
        if rise:
            layer = np.roll(layer, rise, axis=0)
        changed = np.any(layer != BACKGROUND, axis=2)
        show = changed & (p > bayer_threshold(H, W))
        frame[show] = layer[show]
    if t < 0.25:
        frame = dither_fade(frame, 1 - t / 0.25)
    return frame


def audio_events() -> list[tuple[float, str]]:
    """（時刻, 種類）の一覧。種類は 'pop'（吹き出しが出る）か 'blip:<話者>'（1文字表示）。"""
    events: list[tuple[float, str]] = []
    for row in ROWS:
        events.append((row.line.appear, "pop"))
        total = sum(len(t) for t in row.text_lines)
        for i in range(total):
            ch = "".join(row.text_lines)[i]
            if ch in "、。…！？ 　":
                continue
            events.append((type_start(row) + (i + 1) / TYPE_CPS, f"blip:{row.line.speaker}"))
    return events
