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



