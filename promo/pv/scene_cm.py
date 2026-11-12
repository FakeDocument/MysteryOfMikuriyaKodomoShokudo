"""0:00〜0:10 寿司屋のCM：明るい店の紹介に、依頼書の断片が短く割り込む。

写真と紹介文は御厨水産の公開サイトのものだけを使い、新しい宣伝文は書かない。
この場面の写真は、ドット化せずに1920x1080で描く。割り込みはワールド解像度のドット絵。
光過敏に配慮し、割り込みは1秒に3回を超えない間隔にする。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import scene_letter
from pixel import OUT_H, OUT_W, find_system_font, upscale

ASSETS = Path(__file__).resolve().parents[2] / "docker/sushi/site/assets"
# PVのために作る写真（集合写真）の置き場所
PV_ASSETS = Path(__file__).resolve().parent / "assets"
BEAT = 0.5  # テンポ120
BAR = BEAT * 4
DURATION = BAR * 4

# style.css の色
RED = (201, 72, 56)
INK = (23, 54, 47)
PAPER = (255, 253, 247)
MINCHO = find_system_font("YuMincho.ttc", "游明朝")


@dataclass(frozen=True)
class Cut:
    start: float
    photo: str | None  # None はエンドカード
    focus_y: float = 0.5  # 16:9に切り抜くときの縦位置（0=上端、1=下端）
    zoom: tuple[float, float] = (1.0, 1.06)
    copy: str = ""  # 公開サイトの文面
    # 寄り・紹介文の時間の起点。前のカットと同じ構図を続けるとき、そのカットの開始時刻を指定する
    anchor: float | None = None


GROUP_WITH_EMA = "pv:group_with_ema.png"
GROUP_WITHOUT_EMA = "pv:group_without_ema.png"
GROUP_COPY = "「ただいま」と言えるような場所に。"

CUTS = (
    Cut(0.0, "mikuriya-sushi-hero.jpg", 0.75, (1.00, 1.06), "旬をにぎり、笑顔をむすぶ。"),
    Cut(BAR, "mikuriya-blog-kodomo-shokudo.jpg", 0.45, (1.00, 1.04),
        "一人でごはんを食べる子を、一人でも減らしたい。"),
    Cut(BAR * 2, GROUP_WITH_EMA, 0.5, (1.00, 1.03), GROUP_COPY),
    # 2回目の割り込みのあと、同じ構図のままエマのいた場所だけが空いている
    Cut(BAR * 2 + 1.6, GROUP_WITHOUT_EMA, 0.5, (1.00, 1.03), GROUP_COPY, anchor=BAR * 2),
    Cut(BAR * 3, None),
)
SIGN_CUT = 1  # 子ども食堂の看板を出すカット
SIGN_POP = 0.28
END_CARD_LINES = ("千葉県沖津市沖津町3-14", "昼 11:00–14:30／夜 17:00–22:00（火曜定休）")


@dataclass(frozen=True)
class CutIn:
    start: float
    length: float
    phrase: str  # 依頼書のこの語句を接写で見せる


# 回を追うごとに長く、言葉も不穏にしていく
# 子ども食堂のカットから狂い始める
CUT_INS = (
    CutIn(BAR * 1 + 1.0, 0.40, "いなくなりました。"),
    CutIn(BAR * 2 + 1.0, 0.60, "そろそろころあいね"),
)
END_DECAY_START = BAR * 3.5  # ここから乱れが強まり、次の場面で壊れる


@lru_cache(maxsize=None)
def _photo(name: str) -> Image.Image:
    if not name.startswith("pv:"):
        return Image.open(ASSETS / name).convert("RGB")
    path = PV_ASSETS / name.removeprefix("pv:")
    if not path.exists():
        return _placeholder(path.name)
    return _with_eye_bars(Image.open(path).convert("RGB"), path.name)


def _with_eye_bars(img: Image.Image, filename: str) -> Image.Image:
    """集合写真の顔に、目線の黒線を重ねる。

    位置は assets/eye_bars.json に、写真の画素座標で書く（2枚の集合写真で共通）。
    [{"x": 中心x, "y": 中心y, "w": 幅, "h": 太さ, "angle": 傾き（度）, "only": ファイル名}, ...]
    "only" を書いた線は、そのファイルにだけ重ねる（片方にしか写っていない人のため）。
    """
    spec = PV_ASSETS / "eye_bars.json"
    if not spec.exists():
        return img
    out = img.copy()
    for bar in json.loads(spec.read_text(encoding="utf-8")):
        if bar.get("only", filename) != filename:
            continue
        w, h = int(bar["w"]), int(bar["h"])
        rect = Image.new("RGBA", (w, h), (8, 8, 8, 255)).rotate(
            float(bar.get("angle", 0.0)), expand=True, resample=Image.Resampling.BICUBIC
        )
        out.paste(rect, (int(bar["x"] - rect.width / 2), int(bar["y"] - rect.height / 2)), rect)
    return out


def _placeholder(label: str) -> Image.Image:
    """PV用の写真がまだないときの仮の画。尺と流れを確かめるためだけに使う。"""
    img = Image.new("RGB", (1536, 1024), (120, 112, 100))
    d = ImageDraw.Draw(img)
    d.rectangle((40, 40, 1496, 984), outline=(230, 224, 210), width=6)
    d.text((768, 512), f"仮：{label}", font=_font(64, 0), fill=(240, 236, 226), anchor="mm")
    return img


@lru_cache(maxsize=None)
def _font(size: int, index: int = 1) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(MINCHO, size, index=index)


def _frame_photo(cut: Cut, local: float) -> Image.Image:
    assert cut.photo is not None
    img = _photo(cut.photo)
    w, h = img.size
    p = local / BAR
    zoom = cut.zoom[0] + (cut.zoom[1] - cut.zoom[0]) * p
    cw = w / zoom
    ch = cw * OUT_H / OUT_W
    if ch > h:
        ch, cw = h, h * OUT_W / OUT_H
    x0 = (w - cw) / 2
    y0 = (h - ch) * cut.focus_y
    return img.resize((OUT_W, OUT_H), Image.Resampling.BICUBIC, box=(x0, y0, x0 + cw, y0 + ch))


def _draw_spaced(d: ImageDraw.ImageDraw, xy: tuple[float, float], text: str,
                 font: ImageFont.FreeTypeFont, fill: tuple[int, ...], spacing: float) -> None:
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill)
        x += d.textlength(ch, font=font) + spacing


def _spaced_width(d: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, spacing: float) -> float:
    return d.textlength(text, font=font) + spacing * (len(text) - 1)


def _copy(img: Image.Image, text: str, local: float) -> None:
    """地方局のCMのような、下寄せの白い明朝。影を付けて写真の上でも読めるようにする。"""
    d = ImageDraw.Draw(img, "RGBA")
    font = _font(60)
    alpha = int(255 * min(max((local - 0.15) / 0.3, 0), 1))
    tw = _spaced_width(d, text, font, 6)
    x, y = (OUT_W - tw) / 2, OUT_H - 300  # 左下の録画日時の表示と重ならない高さ
    for dx, dy in ((3, 3), (0, 3), (3, 0), (-2, 2)):
        _draw_spaced(d, (x + dx, y + dy), text, font, (10, 20, 18, alpha * 3 // 4), 6)
    _draw_spaced(d, (x, y), text, font, PAPER + (alpha,), 6)


@lru_cache(maxsize=1)
def _sign() -> Image.Image:
    """公開サイトの .community-stamp を借りた、朱色のスタンプ風の看板。"""
    size = 420
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c, r = size // 2, 170
    for i in range(48):
        a0 = i * 7.5
        d.arc((c - r - 22, c - r - 22, c + r + 22, c + r + 22), a0, a0 + 4.2, fill=RED + (255,), width=4)
    d.ellipse((c - r, c - r + 4, c + r, c + r - 2), fill=(255, 255, 255, 150))
    d.ellipse((c - r + 22, c - r + 24, c + r - 20, c + r - 22), fill=RED + (255,))
    font = _font(46)
    for i, line in enumerate(("みくりや", "子ども食堂")):
        _draw_spaced(d, (c - _spaced_width(d, line, font, 6) / 2, c - 58 + i * 64), line, font,
                     PAPER + (255,), 6)
    return img.rotate(4, resample=Image.Resampling.BICUBIC)


def _ease_out_back(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    k = 1.7
    return 1 + (k + 1) * (p - 1) ** 3 + k * (p - 1) ** 2


def _paste_sign(img: Image.Image, local: float) -> None:
    p = local / SIGN_POP
    scale = 1.35 - 0.35 * _ease_out_back(p)
    sign = _sign()
    sz = int(sign.width * scale)
    s = sign.resize((sz, sz), Image.Resampling.BICUBIC)
    if p < 1:
        s.putalpha(s.getchannel("A").point(lambda a: int(a * min(p * 2.5, 1.0))))
    cx, cy = int(OUT_W * 0.80), int(OUT_H * 0.42)
    img.paste(s, (cx - sz // 2, cy - sz // 2), s)


@lru_cache(maxsize=1)
def _end_card() -> Image.Image:
    """公開サイトのフッターと同じ並び：鮨の印、店名、読み、所在地、営業時間。"""
    img = Image.new("RGB", (OUT_W, OUT_H), PAPER)
    d = ImageDraw.Draw(img)
    cx, cy = OUT_W // 2, OUT_H // 2 - 90
    d.ellipse((cx - 300 - 70, cy - 70, cx - 300 + 70, cy + 70), fill=RED)
    d.text((cx - 300, cy), "鮨", font=_font(88), fill=PAPER, anchor="mm")
    _draw_spaced(d, (cx - 190, cy - 78), "御厨水産", _font(120), INK, 22)
    _draw_spaced(d, (cx - 182, cy + 66), "みくりやすいさん", _font(34, 0), (72, 99, 92), 10)
    for i, line in enumerate(END_CARD_LINES):
        font = _font(38, 0)
        d.text((cx, cy + 250 + i * 62), line, font=font, fill=INK, anchor="mm")
    return img


def _cut_at(t: float) -> Cut:
    current = CUTS[0]
    for c in CUTS:
        if t >= c.start:
            current = c
    return current


def _active_cut_in(t: float) -> CutIn | None:
    for c in CUT_INS:
        if c.start <= t < c.start + c.length:
            return c
    return None


@lru_cache(maxsize=None)
def _cut_in_frame(cut_in: CutIn) -> np.ndarray:
    return upscale(scene_letter.closeup(cut_in.phrase))


def render(t: float) -> np.ndarray:
    if (cut_in := _active_cut_in(t)) is not None:
        return _cut_in_frame(cut_in)
    cut = _cut_at(t)
    local = t - (cut.start if cut.anchor is None else cut.anchor)
    if cut.photo is None:
        return np.asarray(_end_card())
    img = _frame_photo(cut, local)
    if CUTS.index(cut) == SIGN_CUT:
        _paste_sign(img, local)
    if cut.copy:
        _copy(img, cut.copy, local)
    return np.asarray(img)


def vhs_boost(t: float) -> float:
    """割り込みの瞬間とその前後だけテープを乱し、CMの終わりにかけて乱れを強めていく。"""
    for c in CUT_INS:
        if c.start - 0.08 <= t < c.start + c.length + 0.12:
            return 0.75
    if t >= END_DECAY_START:
        return (t - END_DECAY_START) / (DURATION - END_DECAY_START) * 0.5
    return 0.0


def vhs_strength(t: float) -> float:
    """最初はきれいな放送のまま。割り込みを受けるたびにテープの劣化が表に出てくる。"""
    first, second = CUT_INS[0].start - 0.08, CUT_INS[1].start - 0.08
    if t < first:
        return 0.0
    if t < second:
        return 0.55
    return 1.0


def audio_cues() -> dict[str, object]:
    return {"sign": CUTS[SIGN_CUT].start, "cut_ins": [(c.start, c.length) for c in CUT_INS]}
