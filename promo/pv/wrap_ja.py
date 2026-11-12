"""日本語の文を文節の境目で折り返す。依頼書と吹き出しで共通に使う。"""

from __future__ import annotations

import itertools
import re
from functools import lru_cache

import budoux

# BudouXが途中で区切ってしまう語。PVで読ませる文の中にあるものを指定する
KEEP_TOGETHER = ("ころあい", "佐々木笑真", "遠藤美咲", "ハッキング")
# 1行に収まらない長い文節を分けてよい位置（この文字の直後）
SOFT_BREAK_AFTER = "」、。！？…"


@lru_cache(maxsize=1)
def _parser() -> budoux.Parser:
    return budoux.load_default_japanese_parser()


def segments(text: str) -> list[str]:
    """BudouXで文節に分け、KEEP_TOGETHER の語の途中にある区切りは取り除く。"""
    parts = _parser().parse(text)
    cuts = set(itertools.accumulate(len(p) for p in parts[:-1]))
    for word in KEEP_TOGETHER:
        for m in re.finditer(re.escape(word), text):
            cuts -= set(range(m.start() + 1, m.end()))
    bounds = [0, *sorted(cuts), len(text)]
    return [text[a:b] for a, b in itertools.pairwise(bounds)]


def _split_long(seg: str, width: int) -> list[str]:
    """1行に収まらない文節を、括弧や読点の直後で分ける。分けられなければ文字単位で切る。"""
    if len(seg) <= width:
        return [seg]
    soft = [i + 1 for i, ch in enumerate(seg[:width]) if ch in SOFT_BREAK_AFTER]
    cut = soft[-1] if soft else width
    return [seg[:cut], *_split_long(seg[cut:], width)]


def wrap(text: str, width: int) -> list[str]:
    """文節の境目で折り返す。1文節が1行に収まらないときだけ文節の中で切る。"""
    lines: list[str] = []
    current = ""
    for seg in segments(text):
        for piece in _split_long(seg, width):
            if current and len(current) + len(piece) > width:
                lines.append(current)
                current = ""
            current += piece
    if current:
        lines.append(current)
    return lines
