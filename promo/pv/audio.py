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


def triangle_note(freq: float, dur: float, volume: float = 0.14) -> np.ndarray:
    n = int(SR * dur)
    phase = (np.arange(n) * freq / SR) % 1.0
    wave_ = 4 * np.abs(phase - 0.5) - 1
    # ファミコン風に16段階へ量子化する
    wave_ = np.round(wave_ * 7.5) / 7.5
    return (wave_ * _env(n) * volume).astype(np.float32)


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


def static_burst(duration: float, rng: np.random.Generator, volume: float = 0.10) -> np.ndarray:
    """テープの割り込みのノイズ：ざらついた雑音に、低い唸りを混ぜる。"""
    n = int(SR * duration)
    t = np.arange(n) / SR
    noise = rng.normal(0, 1, n) * (0.6 + 0.4 * np.sign(np.sin(2 * np.pi * 31 * t)))
    hum = np.sin(2 * np.pi * 60 * t) * 0.6
    env = np.clip(np.minimum(t / 0.01, (duration - t) / 0.03), 0, 1)
    return ((noise + hum) * env * volume).astype(np.float32)


# ---- ゲーム紹介のアップテンポな曲 -------------------------------------------

# 1小節ごとの（ベースの音, 和音）。短調で緊張感を保つ：Am → F → G → Am → F → E
DRIVE_CHORDS: tuple[tuple[int, tuple[int, int, int]], ...] = (
    (45, (69, 72, 76)), (41, (65, 69, 72)), (43, (67, 71, 74)),
    (45, (69, 72, 76)), (41, (65, 69, 72)), (40, (68, 71, 76)),
)


def kick(volume: float = 0.42) -> np.ndarray:
    """キック：高めから一気に下がるサイン波。"""
    t = np.arange(int(SR * 0.24)) / SR
    freq = 45 + 95 * np.exp(-t / 0.03)
    phase = np.cumsum(2 * np.pi * freq / SR)
    return (np.sin(phase) * np.exp(-t / 0.11) * volume).astype(np.float32)


def snare(rng: np.random.Generator, volume: float = 0.20) -> np.ndarray:
    t = np.arange(int(SR * 0.18)) / SR
    noise = np.diff(rng.normal(0, 1, t.size), prepend=0.0) * np.exp(-t / 0.05)
    body = np.sin(2 * np.pi * 185 * t) * np.exp(-t / 0.04)
    return ((noise * 0.7 + body * 0.6) * volume).astype(np.float32)


def hat(rng: np.random.Generator, volume: float = 0.05, decay: float = 0.012) -> np.ndarray:
    t = np.arange(int(SR * 0.06)) / SR
    noise = np.diff(np.diff(rng.normal(0, 1, t.size), prepend=0.0), prepend=0.0)
    return (noise * np.exp(-t / decay) * volume).astype(np.float32)


def saw_note(freq: float, dur: float, volume: float, taps: int = 8) -> np.ndarray:
    """のこぎり波の音を、低域通過で少し丸めて鳴らす。ベースとアルペジオに使う。"""
    n = int(SR * dur)
    phase = (np.arange(n) * freq / SR) % 1.0
    wave_ = lowpass((2 * phase - 1).astype(np.float32), taps)
    return (wave_ * _env(n, 0.003, 0.02) * volume).astype(np.float32)


def reverse_swell(duration: float, rng: np.random.Generator, volume: float = 0.12) -> np.ndarray:
    """逆再生のシンバルのように、だんだん大きくなって最後に途切れる上昇音。"""
    n = int(SR * duration)
    t = np.arange(n) / SR
    noise = np.diff(rng.normal(0, 1, n), prepend=0.0)
    return (noise * (t / duration) ** 3 * volume).astype(np.float32)


def drive_theme(bpm: float, bars: int, rng: np.random.Generator) -> np.ndarray:
    """ゲーム紹介の曲：四つ打ちのキック、2・4拍のスネア、裏拍のハイハット、
    8分で跳ねるベース、16分のアルペジオ。最後の拍は余韻を残して止める。"""
    beat = 60.0 / bpm
    out = silence(bars * 4 * beat + 0.6)
    for bar in range(bars):
        root, chord = DRIVE_CHORDS[bar % len(DRIVE_CHORDS)]
        t0 = bar * 4 * beat
        for k in range(4):
            place(out, kick(), t0 + k * beat)
        for k in (1, 3):
            place(out, snare(rng), t0 + k * beat)
        for k in range(16):
            # 裏拍の8分を強く、残りの16分は小さく刻む
            is_offbeat = k % 4 == 2
            place(out, hat(rng, 0.06 if is_offbeat else 0.025, 0.02 if is_offbeat else 0.008), t0 + k * beat / 4)
        for k in range(8):
            note = root + (12 if k % 2 else 0)
            place(out, saw_note(midi_hz(note), beat / 2 * 0.85, 0.11, taps=14), t0 + k * beat / 2)
        pattern = (0, 1, 2, 1, 0, 1, 2, 0)
        for k in range(16):
            note = chord[pattern[k % 8]] + (12 if k >= 8 else 0)
            place(out, saw_note(midi_hz(note), beat / 4 * 0.7, 0.035, taps=4), t0 + k * beat / 4)
    # 最後の小節の終わりに、キックとシンバルを一発鳴らして締める
    end = bars * 4 * beat
    place(out, kick(0.5), end - 0.02)
    place(out, hat(rng, 0.10, 0.25), end - 0.02)
    fade = np.clip((out.size - np.arange(out.size)) / (SR * 0.5), 0, 1).astype(np.float32)
    return out * fade


OMINOUS_BPM = 66.0
# 短調で下がっていく、間の多い旋律（拍・長さ・音）
OMINOUS_LEAD: tuple[Note, ...] = (
    (0, 2, 69), (2, 2, 64), (4, 2, 65), (6, 2, 64),
    (8, 2, 69), (10, 2, 64), (12, 2, 72), (14, 2, 71),
    (16, 2, 69), (18, 2, 64), (20, 2, 65), (22, 2, 63),
)


def ominous_theme(duration: float) -> np.ndarray:
    """不穏な曲：オルゴールの短調の旋律に低い唸りを重ねる。CMのあとの紹介PVなので揺れは控えめ。"""
    beat = 60.0 / OMINOUS_BPM
    out = silence(duration)
    loop = 24 * beat
    k = 0
    while k * loop < duration:
        for start, _, note in OMINOUS_LEAD:
            place(out, music_box_note(midi_hz(note), 1.2, volume=0.07), k * loop + start * beat)
        k += 1
    out = lowpass(wow_flutter(out, wow_depth=0.0015, flutter_depth=0.0004), 6)
    fade_in = np.clip(np.arange(out.size) / (SR * 1.5), 0, 1).astype(np.float32)
    return out * fade_in + drone(duration, volume=0.05)


def tape_stop(x: np.ndarray, duration: float) -> np.ndarray:
    """テープが止まるときのように、再生速度を0まで落として音程を下げる。"""
    n = int(SR * duration)
    rate = np.linspace(1.0, 0.0, n) ** 1.6
    idx = np.cumsum(rate)
    out = np.interp(idx, np.arange(x.size), x).astype(np.float32)
    return lowpass(out * np.linspace(1.0, 0.3, n).astype(np.float32), 8)


def drone(duration: float, volume: float = 0.07) -> np.ndarray:
    """不穏な低い唸り。わずかにずれた2つの低音のうなりに、ゆっくりした膨らみをつける。"""
    n = int(SR * duration)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * 55.0 * t) + np.sin(2 * np.pi * 58.3 * t) + 0.3 * np.sin(2 * np.pi * 110.4 * t)
    swell = np.clip(t / (duration * 0.6), 0, 1) * np.clip((duration - t) / 0.3, 0, 1)
    return (tone * swell * volume).astype(np.float32)


# ---- 和風のCM曲（仮。音源はあとで差し替える） ---------------------------------

CM_BPM = 120.0
CM_BARS = 4
# ヨナ抜き音階（D・E・G・A・B）の元気な旋律。最後の小節は駆け上がって、次の場面で途切れる
CM_LEAD: tuple[Note, ...] = (
    (0, .5, 69), (.5, .5, 69), (1, .5, 71), (1.5, .5, 74), (2, 1, 76), (3, 1, 74),
    (4, .5, 76), (4.5, .5, 79), (5, .5, 81), (5.5, .5, 79), (6, .5, 76), (6.5, .5, 74), (7, 1, 71),
    (8, .5, 69), (8.5, .5, 71), (9, .5, 74), (9.5, .5, 76), (10, 1, 79), (11, 1, 76),
    (12, .5, 74), (12.5, .5, 76), (13, .5, 79), (13.5, .5, 81), (14, 1, 86), (15, 1, 86),
)
# 低い三味線で、各拍の頭に根音と5度を交互に弾く
CM_BASS: tuple[Note, ...] = tuple((b, 0.5, 50 if b % 2 == 0 else 57) for b in range(CM_BARS * 4))
# 太鼓：「ドン」を1拍目と3拍目、「カッ」を2拍目と4拍目の裏に置く
CM_DON = tuple(float(b) for b in range(CM_BARS * 4) if b % 2 == 0)
CM_KA = tuple(b + 0.5 for b in range(CM_BARS * 4) if b % 2 == 1)

# 割り込みを1回受けるごとの崩れ方：音程のぶれ（セント）、半音ずれた音の割合、テープの揺れ
SOUR_LEVELS = ((0.0, 0.0, 0.0), (35.0, 0.2, 0.6), (65.0, 0.45, 1.0))


def pluck(freq: float, dur: float, brightness: float = 0.5, volume: float = 0.16) -> np.ndarray:
    """三味線風の撥弦（Karplus-Strong）。周期ごとに平均をとって減衰させ、少しだけ歪ませて弦のさわりを出す。"""
    n = int(SR * dur)
    period = max(2, int(round(SR / freq)))
    rng = np.random.default_rng(int(freq * 1000) % 2**32)
    buf = rng.uniform(-1, 1, period).astype(np.float32)
    out = np.empty(n, dtype=np.float32)
    decay = 0.996 - (1 - brightness) * 0.01
    for i in range(0, n, period):
        k = min(period, n - i)
        out[i : i + k] = buf[:k]
        buf = (decay * 0.5 * (buf + np.roll(buf, -1))).astype(np.float32)
    out = np.tanh(out * 1.8) / np.tanh(1.8)
    return (out * _env(n, attack=0.001, release=0.02) * volume).astype(np.float32)


def taiko(dur: float = 0.35, volume: float = 0.35) -> np.ndarray:
    """太鼓の「ドン」：音程が急に下がる低い正弦波。"""
    n = int(SR * dur)
    t = np.arange(n) / SR
    freq = 70 + 90 * np.exp(-t / 0.03)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    return (np.sin(phase) * np.exp(-t / 0.12) * volume).astype(np.float32)


def rim(rng: np.random.Generator, volume: float = 0.10) -> np.ndarray:
    """太鼓の縁打ちの「カッ」：ごく短い明るい雑音。"""
    n = int(SR * 0.04)
    t = np.arange(n) / SR
    click = np.diff(rng.normal(0, 1, n + 1)) * np.exp(-t / 0.008)
    return (click * volume).astype(np.float32)


def cm_theme(sour_points: tuple[float, ...] = (), tail: float = 0.0, seed: int = 7) -> np.ndarray:
    """和風で元気なCM曲。最初は素直に鳴らし、sour_points（秒）を過ぎるたびに音を外していく。

    tail 秒だけ長く合成し、最後の音の余韻を残す（テープ停止に使う）。
    """
    rng = np.random.default_rng(seed)
    beat = 60.0 / CM_BPM
    out = silence(CM_BARS * 4 * beat + tail)

    def level(at: float) -> int:
        return min(sum(at >= p for p in sour_points), len(SOUR_LEVELS) - 1)

    def sour(note: int, at: float) -> float:
        cents, wrong_rate, _ = SOUR_LEVELS[level(at)]
        shift = rng.normal(0, cents) / 100 if cents else 0.0
        if rng.random() < wrong_rate:
            shift += rng.choice([-1.0, 1.0])
        return midi_hz(note) * 2 ** (shift / 12)

    for start, length, note in CM_LEAD:
        at = start * beat
        place(out, pluck(sour(note, at), max(length * beat, 0.45), brightness=0.8), at)
    for start, length, note in CM_BASS:
        at = start * beat
        place(out, pluck(sour(note, at), 0.45, brightness=0.3, volume=0.10), at)
    for b in CM_DON:
        place(out, taiko(), b * beat)
    for b in CM_KA:
        place(out, rim(rng), b * beat)

    # テープの揺れは、揺れのない版と強い版を、崩れ具合に応じて混ぜて強めていく
    warped = wow_flutter(out, wow_depth=0.010, flutter_depth=0.0018)
    t = np.arange(out.size) / SR
    coarse = t[:: SR // 100]
    mix = np.interp(t, coarse, [SOUR_LEVELS[level(x)][2] for x in coarse]).astype(np.float32)
    return out * (1 - mix) + warped * mix
