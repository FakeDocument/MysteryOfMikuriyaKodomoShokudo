"""PVの効果音とチップチューンをコードで合成する。"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100


def silence(duration: float) -> np.ndarray:
    return np.zeros(int(SR * duration), dtype=np.float32)


def place(track: np.ndarray, clip: np.ndarray, at: float) -> None:
    i = int(at * SR)
    end = min(i + clip.size, track.size)
    if i < end:
        track[i:end] += clip[: end - i]


def pencil_scratch(duration: float, rng: np.random.Generator) -> np.ndarray:
    """鉛筆で紙をこする音：高域寄りのノイズを、筆圧の揺れで細かく区切る。"""
    n = int(SR * duration)
    noise = rng.normal(0, 1, n).astype(np.float32)
    hiss = np.diff(noise, prepend=0.0)  # 低域を削る
    hiss = np.convolve(hiss, np.ones(3) / 3, mode="same")  # 耳に痛い最高域を少し丸める
    t = np.arange(n) / SR
    strokes = 0.55 + 0.45 * np.sign(np.sin(2 * np.pi * rng.uniform(11, 17) * t + rng.uniform(0, 6)))
    env = np.minimum(1.0, np.minimum(t / 0.015, (duration - t) / 0.03))
    return (hiss * strokes * np.clip(env, 0, 1) * 0.16).astype(np.float32)


def square_blip(freqs: tuple[float, ...], step: float, volume: float = 0.12) -> np.ndarray:
    """矩形波の短いアルペジオ。カット切り替えの合図に使う。"""
    parts = []
    for f in freqs:
        n = int(SR * step)
        t = np.arange(n) / SR
        wave_ = np.sign(np.sin(2 * np.pi * f * t))
        env = np.exp(-t / (step * 0.6))
        parts.append(wave_ * env * volume)
    return np.concatenate(parts).astype(np.float32)


def room_tone(duration: float, rng: np.random.Generator, volume: float = 0.012) -> np.ndarray:
    n = int(SR * duration)
    noise = rng.normal(0, 1, n)
    kernel = np.ones(200) / 200
    return (np.convolve(noise, kernel, mode="same") * volume * 14).astype(np.float32)


def write_wav(path: Path, track: np.ndarray) -> None:
    peak = float(np.max(np.abs(track))) or 1.0
    data = (np.clip(track / max(peak, 1.0), -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())





# ---- チップチューン ----------------------------------------------------------

Note = tuple[float, float, int]  # 開始拍・長さ（拍）・MIDIノート番号


def midi_hz(note: int) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)


def _env(n: int, attack: float = 0.004, release: float = 0.03) -> np.ndarray:
    t = np.arange(n) / SR
    dur = n / SR
    return np.clip(np.minimum(t / attack, (dur - t) / release), 0, 1).astype(np.float32)


def square_note(freq: float, dur: float, duty: float = 0.25, volume: float = 0.08) -> np.ndarray:
    n = int(SR * dur)
    phase = (np.arange(n) * freq / SR) % 1.0
    wave_ = np.where(phase < duty, 1.0, -1.0)
    return (wave_ * _env(n) * volume).astype(np.float32)


def triangle_note(freq: float, dur: float, volume: float = 0.14) -> np.ndarray:
    n = int(SR * dur)
    phase = (np.arange(n) * freq / SR) % 1.0
    wave_ = 4 * np.abs(phase - 0.5) - 1
    # ファミコン風に16段階へ量子化する
    wave_ = np.round(wave_ * 7.5) / 7.5
    return (wave_ * _env(n) * volume).astype(np.float32)


def noise_hit(dur: float, rng: np.random.Generator, volume: float = 0.05) -> np.ndarray:
    n = int(SR * dur)
    t = np.arange(n) / SR
    return (rng.choice([-1.0, 1.0], n) * np.exp(-t / (dur * 0.25)) * volume).astype(np.float32)


def sequence(track_len: float, bpm: float, notes: tuple[Note, ...],
             voice: str, rng: np.random.Generator | None = None) -> np.ndarray:
    beat = 60.0 / bpm
    out = silence(track_len)
    for start, length, note in notes:
        dur = length * beat * 0.92
        if voice == "lead":
            clip = square_note(midi_hz(note), dur)
        elif voice == "bass":
            clip = triangle_note(midi_hz(note), dur)
        else:
            assert rng is not None
            clip = noise_hit(min(dur, 0.06), rng)
        place(out, clip, start * beat)
    return out


FRONT_BPM = 120.0
# 「表の顔」の明るい曲。3小節目は解決させず、次の場面で途切れる前提にする
FRONT_LEAD: tuple[Note, ...] = (
    (0, .5, 76), (.5, .5, 79), (1, 1, 84), (2, .5, 83), (2.5, .5, 81), (3, 1, 79),
    (4, .5, 81), (4.5, .5, 84), (5, .5, 81), (5.5, .5, 77), (6, 1, 79), (7, 1, 76),
    (8, .5, 74), (8.5, .5, 76), (9, .5, 79), (9.5, .5, 81), (10, .5, 84), (10.5, .5, 86),
    (11, 1, 88),
)
FRONT_BASS: tuple[Note, ...] = tuple(
    (b + h * 0.5, 0.5, root + (7 if h else 0))
    for b, root in ((0, 48), (1, 48), (2, 48), (3, 48), (4, 53), (5, 53), (6, 55), (7, 55),
                    (8, 48), (9, 48), (10, 45), (11, 45))
    for h in (0, 1)
)
FRONT_HATS: tuple[Note, ...] = tuple((i * 0.5, 0.25, 0) for i in range(24))


def front_theme(rng: np.random.Generator) -> np.ndarray:
    length = 12 * 60.0 / FRONT_BPM
    return (
        sequence(length, FRONT_BPM, FRONT_LEAD, "lead")
        + sequence(length, FRONT_BPM, FRONT_BASS, "bass")
        + sequence(length, FRONT_BPM, FRONT_HATS, "hat", rng)
    )


# ---- テープの質感 ------------------------------------------------------------


def music_box_note(freq: float, dur: float, volume: float = 0.10) -> np.ndarray:
    """オルゴール風の音：減衰の速い正弦波に、少しずれた倍音と打鍵の雑音を重ねる。"""
    n = int(SR * max(dur, 0.6))
    t = np.arange(n) / SR
    tone = (np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * freq * 2.01 * t) * np.exp(-t / 0.15)
            + 0.12 * np.sin(2 * np.pi * freq * 3.98 * t) * np.exp(-t / 0.06))
    env = np.exp(-t / 0.55) * np.clip(t / 0.002, 0, 1)
    return (tone * env * volume).astype(np.float32)


def wow_flutter(x: np.ndarray, wow_depth: float = 0.0045, flutter_depth: float = 0.0009) -> np.ndarray:
    """テープの回転むら。ゆっくりした音程の揺れ（ワウ）と細かい揺れ（フラッター）を加える。"""
    n = x.size
    t = np.arange(n) / SR
    drift = (wow_depth * SR) * np.sin(2 * np.pi * 0.55 * t) + (flutter_depth * SR) * np.sin(2 * np.pi * 7.3 * t)
    idx = np.clip(np.arange(n) + drift, 0, n - 1)
    return np.interp(idx, np.arange(n), x).astype(np.float32)


def lowpass(x: np.ndarray, taps: int = 6) -> np.ndarray:
    return np.convolve(x, np.ones(taps) / taps, mode="same").astype(np.float32)


def tape_hiss(duration: float, rng: np.random.Generator, volume: float = 0.006) -> np.ndarray:
    noise = rng.normal(0, 1, int(SR * duration))
    return (np.diff(noise, prepend=0.0) * volume).astype(np.float32)


def front_theme_tape(rng: np.random.Generator) -> np.ndarray:
    """「表の顔」の曲をオルゴールで鳴らし、古いテープで再生したように揺らして丸める。"""
    length = 12 * 60.0 / FRONT_BPM
    beat = 60.0 / FRONT_BPM
    out = silence(length)
    for start, _, note in FRONT_LEAD:
        place(out, music_box_note(midi_hz(note + 12), 0.6), start * beat)
    for start, length_beats, note in FRONT_BASS[::2]:
        place(out, triangle_note(midi_hz(note), length_beats * 2 * beat * 0.9, volume=0.05), start * beat)
    return lowpass(wow_flutter(out))
