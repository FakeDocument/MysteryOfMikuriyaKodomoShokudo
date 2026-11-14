"""GarageBandに付属する和楽器（箏・太鼓）の録音を、単音として取り出す。

音源はリポジトリに含めない。Appleの使用許諾は、音源を曲の中で使うことは認めるが、
素材を単体で配布することは認めていないため。書き出し時に、このMacへインストール
されたGarageBandの音源から読む（PVの書き出しは、もともとmacOS専用）。

音源は2つのファイルからなる。
- .exs：ゾーン（どの録音を、どの鍵盤・強さで鳴らすか）の一覧
- *_consolidated.caf：全ゾーンの録音を1本にまとめたAAC。macOS付属のafconvertで展開する
"""

from __future__ import annotations

import re
import struct
import subprocess
import wave
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import numpy as np

SR = 44100
LIBRARY = Path("/Library/Application Support/Logic")
INSTRUMENTS = LIBRARY / "Sampler Instruments" / "Japanese Traditional"
SAMPLES = LIBRARY / "EXS Factory Samples" / "Japanese Traditional"
CACHE = Path(__file__).parent / "build" / "garageband"

# .exs の塊：先頭84バイトが見出し（種類・大きさ・名前）、その後ろが本体
CHUNK_HEADER = 84
CHUNK_ZONE = 1
# 録音の頭の無音を飛ばすときの基準（最大振幅に対する割合）と、立ち上がりの前に残す長さ
ONSET_RATIO = 0.08
PRE_ROLL = 64
FADE = 0.03
# 録音どうしの間は無音で区切られている。20ミリ秒の窓の最大振幅がこれを下回ったら、録音の終わりとみなす
GAP_WINDOW = 0.02
GAP_LEVEL = 0.0003
MAX_SECONDS = 4.0


class MissingLibraryError(RuntimeError):
    """GarageBandの和楽器の音源が見つからない。"""


@dataclass(frozen=True)
class Zone:
    name: str
    root: float  # 録音の音程（MIDIノート番号。微調整を含む）
    velocity: int  # 名前の末尾にある強さ
    start: int  # まとめた録音の中での開始フレーム


def parse_zones(data: bytes) -> list[tuple[str, float, int]]:
    """.exs の中身から、ゾーンの (名前, 音程, 開始フレーム) を並び順に返す。"""
    zones = []
    off = 0
    while off + CHUNK_HEADER <= len(data):
        sig, size = struct.unpack_from("<II", data, off)
        body = data[off + CHUNK_HEADER : off + CHUNK_HEADER + size]
        if (sig >> 24) & 0x0F == CHUNK_ZONE:
            name = data[off + 20 : off + CHUNK_HEADER].split(b"\0")[0].decode("latin-1")
            fine = struct.unpack_from("<b", body, 2)[0]
            start = struct.unpack_from("<I", body, 12)[0]
            zones.append((name, body[1] + fine / 100, start))
        off += CHUNK_HEADER + size
    return zones


def _velocity(name: str) -> int:
    m = re.search(r" - (\d+)$", name)
    return int(m.group(1)) if m else 127


@cache
def _zones(instrument: str) -> tuple[Zone, ...]:
    exs = INSTRUMENTS / f"{instrument}.exs"
    if not exs.exists():
        raise MissingLibraryError(f"{exs} がありません。GarageBandの追加音源（和楽器）をダウンロードしてください")
    return tuple(Zone(name, root, _velocity(name), start) for name, root, start in parse_zones(exs.read_bytes()))


@cache
def _audio(instrument: str) -> np.ndarray:
    """まとめた録音をモノラルのfloatで返す。展開したWAVは build/ に置いて使い回す。"""
    caf = SAMPLES / f"{instrument}_consolidated.caf"
    wav = CACHE / f"{instrument}.wav"
    if not wav.exists():
        if not caf.exists():
            raise MissingLibraryError(f"{caf} がありません")
        CACHE.mkdir(parents=True, exist_ok=True)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16", str(caf), str(wav)], check=True)
    with wave.open(str(wav)) as w:
        if w.getframerate() != SR:
            raise ValueError(f"{wav} の標本化周波数が {w.getframerate()} Hz です")
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").reshape(-1, w.getnchannels())
    return (pcm.mean(axis=1) / 32768).astype(np.float32)


def _segment(instrument: str, zone: Zone) -> np.ndarray:
    """ゾーンの録音を、頭の無音を除き、次の録音との間の無音までで切り出す。"""
    seg = _audio(instrument)[zone.start : zone.start + int(SR * MAX_SECONDS)]
    loud = np.flatnonzero(np.abs(seg) > np.abs(seg).max() * ONSET_RATIO)
    head = max(int(loud[0]) - PRE_ROLL, 0) if loud.size else 0
    seg = seg[head:]
    win = int(SR * GAP_WINDOW)
    frames = np.abs(seg[: seg.size // win * win]).reshape(-1, win).max(axis=1)
    quiet = np.flatnonzero(frames[1:] < GAP_LEVEL)
    return seg[: (int(quiet[0]) + 1) * win] if quiet.size else seg


def _pick(instrument: str, prefix: str) -> list[Zone]:
    found = [z for z in _zones(instrument) if z.name.startswith(prefix)]
    if not found:
        raise ValueError(f"{instrument} に「{prefix}」で始まるゾーンがありません")
    return found


def _closest(zones: list[Zone], distance: Callable[[Zone], float]) -> list[Zone]:
    best = min(distance(z) for z in zones)
    return [z for z in zones if distance(z) == best]


def _shape(x: np.ndarray, dur: float, volume: float) -> np.ndarray:
    n = min(x.size, int(SR * dur))
    out = x[:n].copy()
    fade = min(int(SR * FADE), n)
    out[n - fade :] *= np.linspace(1, 0, fade, dtype=np.float32)
    return (out * volume).astype(np.float32)


def hit(instrument: str, prefix: str, dur: float, volume: float, take: int = 0, velocity: int = 100) -> np.ndarray:
    """打楽器の1打。同じ打ち方の録音が複数あれば、take で順に使い分ける。"""
    zones = _closest(_pick(instrument, prefix), lambda z: abs(z.velocity - velocity))
    return _shape(_segment(instrument, zones[take % len(zones)]), dur, volume)


def note(instrument: str, prefix: str, pitch: float, dur: float, volume: float, take: int = 0, velocity: int = 100) -> np.ndarray:
    """音程のある楽器の1音。pitch（MIDIノート番号。小数で半端な音程も可）に最も近い録音を移調して使う。"""
    # 移調は少ないほど自然なので、音程の近さを先に、強さの近さを後に見る
    zones = _closest(_pick(instrument, prefix), lambda z: abs(z.root - pitch))
    zones = _closest(zones, lambda z: abs(z.velocity - velocity))
    zone = zones[take % len(zones)]
    src = _segment(instrument, zone)
    ratio = 2 ** ((pitch - zone.root) / 12)
    n = min(int(SR * dur), int((src.size - 1) / ratio))
    shifted = np.interp(np.arange(n) * ratio, np.arange(src.size), src).astype(np.float32)
    return _shape(shifted, dur, volume)
