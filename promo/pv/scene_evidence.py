"""0:33〜0:37 証拠：黒地に、作中の台詞と調査記録の語句が次々に現れては消えていく。

語句は読ませるためではなく、量と気配で見せる。位置・大きさ・明るさを乱数で決めて無秩序に重ね、
それぞれ現れてすぐにフェードアウトさせる。出る間隔はだんだん詰める。縦書きも混ぜる。
新しい語句は、十分に暗くなった語句とだけ重なる位置に置く。
「肉付き: 極上」は流れの最後の1語として中央に現れる。大きさとフェードはほかの語句と同じにする。
ほかの語句は場面の終わりまでに消えきるよう寿命を詰めてあるので、最後に出たこの語句だけが、
周りが消えていく結果として自然に残って見える。
語句はすべて作中の文面から抜き出す。書き出し時に、元のファイルにそのまま含まれるかを確かめる。
1920x1080で描き、ドット化はしない。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from pixel import OUT_H, OUT_W, find_system_font

REPO = Path(__file__).resolve().parents[2]
PROLOGUE = "docker/notebook/app/data/chapters/prologue.json"
CHAPTER_1 = "docker/notebook/app/data/chapters/chapter-1.json"
EMA_RECORD = "docker/sushi/samba/share/01_child_records/sasaki_ema.txt"

MINCHO = find_system_font("YuMincho.ttc", "游明朝")
DEMIBOLD, EXTRABOLD = 1, 2

DURATION = 4.0
INK = np.array((236, 232, 224), np.float32)


@dataclass(frozen=True)
class Phrase:
    text: str
    source: str  # 文面の出どころ（リポジトリからの相対パス）


POOL = (
    Phrase("善意に満ちた、よくできた看板ですね。", CHAPTER_1),
    Phrase("嘘は、事実に混ぜたほうが長持ちしますから。", CHAPTER_1),
    Phrase("子どもの命がかかっているかもしれない", CHAPTER_1),
    Phrase("えまちゃんを、さがしてください。", PROLOGUE),
    Phrase("家に居場所がない様子。", EMA_RECORD),
    Phrase("一人で過ごしていることが多い。", EMA_RECORD),
    Phrase("唯一、遠藤美咲とは関係良好な様子。", EMA_RECORD),
    Phrase("年齢: 12歳", EMA_RECORD),
    Phrase("わずかにリスクはあるが", EMA_RECORD),
    Phrase("2026年9月に提供予定。", EMA_RECORD),
    Phrase("氏名: 佐々木 笑真", EMA_RECORD),
)
FINAL_PHRASE = Phrase("肉付き: 極上", EMA_RECORD)


@dataclass(frozen=True)
class Spawn:
    """画面に1回現れる語句。"""

    text: str
    start: float
    size: int
    center: tuple[int, int]
    weight: int
    vertical: bool
    peak: float  # 最も明るいときの明るさ（0〜1）
    life: float  # 現れてから消えきるまでの時間


FIRST_AT = 0.15
LAST_AT = 2.75  # 語句が出続ける最後の時刻。この直後に「肉付き: 極上」が出て、流れが止まる
GAP_FROM, GAP_TO = 0.18, 0.05  # 出る間隔を、この幅からこの幅までだんだん詰める
FADE_IN = 0.05
SIZE_RANGE = (40, 200)
LIFE_RANGE = (1.6, 2.8)
SETTLE_AT = 3.75  # ほかの語句は、この時刻までに消えきる
FINAL_SIZE = 120  # ほかの語句の大きさの範囲に収まる、中くらいの大きさ
END_FADE = (3.6, 4.0)
VERTICAL_RATE = 0.4  # 縦書きにする割合（縦書きにできる語句のうち）
# 新しい語句は、この明るさより暗くなった語句とだけ重なってよい
OVERLAP_OK = 0.25
BOX_PAD = 10  # 重なりを調べるときに、語句の外枠に足す余白
PLACE_TRIES = 80
SHRINK = 0.85  # 置き場所が見つからないとき、語句を小さくする割合
MIN_SIZE = SIZE_RANGE[0]

Box = tuple[int, int, int, int]


def _can_be_vertical(text: str) -> bool:
    """半角の数字や記号は縦に並べると崩れるので、全角の文字だけの語句を縦書きにする。"""
    return all(ord(ch) >= 0x80 for ch in text)


def _box(spawn: Spawn) -> Box:
    mask = _mask(spawn.text, spawn.size, spawn.weight, spawn.vertical)
    x0 = spawn.center[0] - mask.width // 2 - BOX_PAD
    y0 = spawn.center[1] - mask.height // 2 - BOX_PAD
    return (x0, y0, x0 + mask.width + BOX_PAD * 2, y0 + mask.height + BOX_PAD * 2)


def _bright_until(spawn: Spawn) -> float:
    """明るさが OVERLAP_OK 以下に落ちる時刻。それまでは、ほかの語句と重ならせない。"""
    if spawn.peak <= OVERLAP_OK:
        return spawn.start
    rest = (1.0 - OVERLAP_OK / spawn.peak) ** 0.5
    return spawn.start + FADE_IN + rest * (spawn.life - FADE_IN)


def _conflicts(spawn: Spawn, others: list[Spawn]) -> bool:
    ax0, ay0, ax1, ay1 = _box(spawn)
    a_end = _bright_until(spawn)
    for other in others:
        # 両方が明るい時間が重ならなければ、位置が重なってもよい
        if other.start >= a_end or spawn.start >= _bright_until(other):
            continue
        bx0, by0, bx1, by1 = _box(other)
        if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
            return True
    return False


def _place(base: Spawn, placed: list[Spawn], rng: np.random.Generator) -> Spawn | None:
    """明るい語句と重ならない位置を探す。見つからなければ小さくして探し直し、それでもなければ出さない。"""
    size = base.size
    while size >= MIN_SIZE:
        for _ in range(PLACE_TRIES):
            center = (int(rng.uniform(0.05, 0.95) * OUT_W), int(rng.uniform(0.05, 0.95) * OUT_H))
            candidate = replace(base, size=size, center=center)
            if not _conflicts(candidate, placed):
                return candidate
        size = int(size * SHRINK)
    return None


def _schedule(seed: int = 11) -> tuple[Spawn, ...]:
    rng = np.random.default_rng(seed)
    final_at = _final_start()
    # 「肉付き: 極上」は中央に置く。先に置いておき、ほかの語句がその場所を明るいまま覆わないようにする
    final = Spawn(FINAL_PHRASE.text, final_at, FINAL_SIZE, (OUT_W // 2, OUT_H // 2), EXTRABOLD, False, 1.0, LIFE_RANGE[1])
    placed: list[Spawn] = [final]
    order: list[Phrase] = []
    for t in _spawn_times():
        if not order:
            # 同じ語句が続かないよう、語句の束を混ぜてから順に使う
            order = [POOL[i] for i in rng.permutation(len(POOL))]
        phrase = order.pop()
        base = Spawn(
            text=phrase.text,
            start=t,
            # 大きい語句は少なめにする
            size=int(SIZE_RANGE[0] + (SIZE_RANGE[1] - SIZE_RANGE[0]) * rng.random() ** 2),
            center=(0, 0),
            weight=EXTRABOLD if rng.random() < 0.5 else DEMIBOLD,
            vertical=_can_be_vertical(phrase.text) and rng.random() < VERTICAL_RATE,
            peak=float(rng.uniform(0.45, 1.0)),
            life=min(float(rng.uniform(*LIFE_RANGE)), SETTLE_AT - t),
        )
        spawn = _place(base, placed, rng)
        if spawn is not None:
            placed.append(spawn)
    # 描く順は出た順にする（最後の語句が最後）
    return (*sorted(placed[1:], key=lambda s: s.start), final)


def _spawn_times() -> tuple[float, ...]:
    times: list[float] = []
    t = FIRST_AT
    while t <= LAST_AT:
        times.append(t)
        p = (t - FIRST_AT) / (LAST_AT - FIRST_AT)
        t += GAP_FROM + (GAP_TO - GAP_FROM) * p
    return tuple(times)


def _final_start() -> float:
    """流れの次の1語が出るはずの時刻に「肉付き: 極上」を出す。"""
    times = _spawn_times()
    return times[-1] + GAP_TO


def verify_sources() -> None:
    """語句が作中の文面からそのまま抜き出したものかを確かめる。"""
    for phrase in (*POOL, FINAL_PHRASE):
        body = (REPO / phrase.source).read_text(encoding="utf-8")
        if phrase.text not in body:
            raise ValueError(f"「{phrase.text}」が {phrase.source} にありません")


@lru_cache(maxsize=None)
def _font(size: int, weight: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(MINCHO, size, index=weight)


@lru_cache(maxsize=None)
def _mask(text: str, size: int, weight: int, vertical: bool = False) -> Image.Image:
    """語句の形を、余白なしの濃淡マスクとして描く。"""
    font = _font(size, weight)
    if vertical:
        return _vertical_mask(text, font, size)
    left, top, right, bottom = font.getbbox(text)
    img = Image.new("L", (right - left, bottom - top), 0)
    ImageDraw.Draw(img).text((-left, -top), text, font=font, fill=255)
    return img


# 縦書きでは、句読点を字の枠の右上へ寄せる
VERTICAL_PUNCT_SHIFT = 0.6


def _vertical_mask(text: str, font: ImageFont.FreeTypeFont, size: int) -> Image.Image:
    """全角の文字を、1文字ずつ縦に並べて描く（PillowのFreeType描画には縦組みがないため）。"""
    img = Image.new("L", (size * 2, size * (len(text) + 1)), 0)
    draw = ImageDraw.Draw(img)
    for i, ch in enumerate(text):
        x, y = size // 2, size // 2 + i * size
        if ch in "、。":
            x += int(size * VERTICAL_PUNCT_SHIFT)
            y -= int(size * VERTICAL_PUNCT_SHIFT)
        draw.text((x, y), ch, font=font, fill=255)
    bbox = img.getbbox()
    return img.crop(bbox) if bbox else img


def _stamp(canvas: np.ndarray, spawn: Spawn, brightness: float) -> None:
    """語句を中心に合わせて置く。重なった所は明るいほうを残す。"""
    mask = _mask(spawn.text, spawn.size, spawn.weight, spawn.vertical)
    alpha = np.asarray(mask, np.float32) / 255.0 * brightness
    x0 = spawn.center[0] - mask.width // 2
    y0 = spawn.center[1] - mask.height // 2
    # 画面からはみ出す部分を切り落とす
    sx0, sy0 = max(0, -x0), max(0, -y0)
    dx0, dy0 = max(0, x0), max(0, y0)
    dx1, dy1 = min(OUT_W, x0 + mask.width), min(OUT_H, y0 + mask.height)
    if dx0 >= dx1 or dy0 >= dy1:
        return
    region = alpha[sy0 : sy0 + dy1 - dy0, sx0 : sx0 + dx1 - dx0]
    np.maximum(canvas[dy0:dy1, dx0:dx1], region, out=canvas[dy0:dy1, dx0:dx1])


def _brightness(spawn: Spawn, since: float) -> float:
    """すぐに現れ、しばらく明るさを保ってから、だんだん速く消えていく。"""
    if since < FADE_IN:
        return spawn.peak * since / FADE_IN
    rest = (since - FADE_IN) / (spawn.life - FADE_IN)
    return spawn.peak * (1.0 - rest**2) if rest < 1.0 else 0.0


def render(t: float) -> np.ndarray:
    canvas = np.zeros((OUT_H, OUT_W), np.float32)
    for spawn in SPAWNS:
        since = t - spawn.start
        if since < 0:
            continue
        brightness = _brightness(spawn, since)
        if brightness <= 0:
            continue
        _stamp(canvas, spawn, brightness)
    fade = 1.0 - min(max((t - END_FADE[0]) / (END_FADE[1] - END_FADE[0]), 0.0), 1.0)
    return (canvas[..., None] * INK * fade).astype(np.uint8)


SPAWNS = _schedule()
