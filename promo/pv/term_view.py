"""Kaliの端末（xfce4-terminal）を1920x1080で描く。

文字は capture_transcripts.py で記録した実際の出力をそのまま使う。配色はKaliの実画面から取った。
書体はKaliのNoto Sans Mono CJK JPに近いmacOS付属のMenloを使い、Menloにない文字だけヒラギノで補う。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from pixel import OUT_H, OUT_W

TRANSCRIPTS = Path(__file__).resolve().parent / "assets/terminal"
MENLO = "/System/Library/Fonts/Menlo.ttc"
# ㉿（U+327F）はヒラギノにもないので、字形のある韓国語フォントで補う
FALLBACK = "/System/Library/Fonts/AppleSDGothicNeo.ttc"

RGB = tuple[int, int, int]
BG: RGB = (0, 0, 0)
FG: RGB = (255, 255, 255)
GREEN: RGB = (0, 170, 0)
BLUE: RGB = (85, 85, 255)
TITLE_BG: RGB = (217, 213, 210)
TITLE_FG: RGB = (40, 40, 40)

FONT_SIZE = 30
LINE_H = 40
TITLE_H = 46
PAD_X, PAD_Y = 22, 14
ROWS = (OUT_H - TITLE_H - PAD_Y * 2) // LINE_H


@lru_cache(maxsize=None)
def _font(bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(MENLO, FONT_SIZE, index=1 if bold else 0)


@lru_cache(maxsize=None)
def _fallback() -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FALLBACK, FONT_SIZE - 4)


CHAR_W = _font().getlength("M")
# Menloに字形がない文字（Kaliのプロンプトの ㉿ など）
_MISSING = frozenset("㉿")

Span = tuple[str, RGB, bool]  # 文字列・色・太字


@dataclass(frozen=True)
class Line:
    spans: tuple[Span, ...]
    start: float  # この行が出る時刻
    typed: str = ""  # 打ち込む文字列（spans の後ろに1文字ずつ出す）
    cps: float = 0.0

    def typing_end(self) -> float:
        return self.start + (len(self.typed) / self.cps if self.typed else 0.0)


def _prompt(host: str) -> tuple[tuple[Span, ...], tuple[Span, ...]]:
    """Kaliの2行のプロンプト。"""
    first = (("┌──(", GREEN, False), (f"player㉿{host}", BLUE, True), (")-[", GREEN, False),
             ("~", FG, True), ("]", GREEN, False))
    second = (("└─", GREEN, False), ("$ ", BLUE, True))
    return first, second


@dataclass(frozen=True)
class Timing:
    """記録を時間に並べるときの速さ。PVの1小節に収めるため、待ち時間だけ詰める。"""

    start: float = 0.08
    cps: float = 60.0
    enter_pause: float = 0.12
    lps: float = 50.0  # 出力の1秒あたりの行数
    output_wait: float = 0.1  # コマンドを打ってから出力が出始めるまで


def lay_out(name: str, timing: Timing) -> tuple[Line, ...]:
    data = json.loads((TRANSCRIPTS / f"{name}.json").read_text(encoding="utf-8"))
    first, second = _prompt(data["host"])
    lines: list[Line] = []
    t = timing.start
    for item in data["items"]:
        if "shell" in item or "input" in item:
            if "shell" in item:
                lines.append(Line(first, t))
                spans, typed = second, item["shell"]
            else:
                spans, typed = ((item["prompt"], FG, False),), item["input"]
            line = Line(spans, t, typed, timing.cps)
            lines.append(line)
            t = line.typing_end() + timing.enter_pause + timing.output_wait
        else:
            for text in item["output"]:
                # 端末と同じく、タブは8桁ごとの位置まで空白で埋める
                lines.append(Line(((text.expandtabs(8), FG, False),), t))
                t += 1 / timing.lps
    return tuple(lines)


def _draw_spans(draw: ImageDraw.ImageDraw, spans: tuple[Span, ...], x: float, y: float) -> float:
    for text, color, bold in spans:
        for ch in text:
            if ch in _MISSING:
                draw.text((x + CHAR_W, y + LINE_H / 2), ch, font=_fallback(), fill=color, anchor="mm")
                x += CHAR_W * 2
                continue
            draw.text((x, y), ch, font=_font(bold), fill=color)
            x += CHAR_W
    return x


def render(lines: tuple[Line, ...], t: float, title: str) -> Image.Image:
    img = Image.new("RGB", (OUT_W, OUT_H), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, OUT_W, TITLE_H), fill=TITLE_BG)
    draw.text((OUT_W / 2, TITLE_H / 2), title, font=_font(True), fill=TITLE_FG, anchor="mm")
    for i, mark in enumerate(("✕", "□", "–")):
        draw.text((OUT_W - 40 - i * 44, TITLE_H / 2), mark, font=_fallback(), fill=TITLE_FG, anchor="mm")

    shown = [line for line in lines if line.start <= t][-ROWS:]
    for row, line in enumerate(shown):
        y = TITLE_H + PAD_Y + row * LINE_H + (LINE_H - FONT_SIZE) / 2
        x = _draw_spans(draw, line.spans, PAD_X, y)
        if line.typed:
            n = max(0, int((t - line.start) * line.cps))
            x = _draw_spans(draw, ((line.typed[:n], FG, False),), x, y)
            is_last = line is shown[-1]
            if is_last and int(t * 4) % 2 == 0:
                draw.rectangle((x, y - 2, x + CHAR_W, y + FONT_SIZE + 4), fill=FG)
    return img


def title_for(name: str) -> str:
    data = json.loads((TRANSCRIPTS / f"{name}.json").read_text(encoding="utf-8"))
    return f"player@{data['host']}: ~"
