# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy", "pillow", "imageio-ffmpeg", "budoux"]
# ///
"""PVの試作を書き出す。

    uv run promo/pv/build.py            # 動画を書き出す
    uv run promo/pv/build.py --stills   # 確認用の静止画だけ書き出す
"""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image

import audio
import scene_break
import scene_cm
import scene_hook
import scene_office
import vhs
from pixel import FPS, OUT_H, OUT_W, upscale

OUT_DIR = Path(__file__).resolve().parent / "build"


@dataclass(frozen=True)
class Scene:
    name: str
    duration: float
    render: Callable[[float], np.ndarray]
    vhs_boost: Callable[[float], float] | None = None  # 場面がテープの乱れを強めたいとき
    # VHSの劣化をどれだけかけるか（0〜1）。指定しない場面は劣化なしの「ふつうの紹介PV」
    vhs_strength: Callable[[float], float] | None = None


SCENES = (
    Scene("cm", scene_cm.DURATION, scene_cm.render, scene_cm.vhs_boost, scene_cm.vhs_strength),
    Scene("break", scene_break.DURATION, scene_break.render, scene_break.vhs_boost, lambda _t: 1.0),
    Scene("hook", scene_hook.DURATION, scene_hook.render),
    Scene("office", scene_office.DURATION, scene_office.render),
)


def scene_start(name: str) -> float:
    start = 0.0
    for scene in SCENES:
        if scene.name == name:
            return start
        start += scene.duration
    raise KeyError(name)


def scene_at(t: float) -> tuple[Scene, float, float]:
    start = 0.0
    for scene in SCENES:
        if t < start + scene.duration:
            return scene, t - start, start
        start += scene.duration
    last = SCENES[-1]
    return last, last.duration - 1e-6, start - last.duration


def total_duration() -> float:
    return sum(s.duration for s in SCENES)


def _cm_audio(track: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """CMの曲。割り込みの間は曲を切ってノイズを鳴らす。返り値は余韻（テープ停止に使う）。"""
    cues = scene_cm.audio_cues()
    theme = audio.cm_theme(tuple(start for start, _ in cues["cut_ins"]), tail=1.0)
    cut = int(scene_cm.DURATION * audio.SR)
    body = theme[:cut].copy()
    for start, length in cues["cut_ins"]:
        body[int(start * audio.SR) : int((start + length) * audio.SR)] = 0.0
        audio.place(track, audio.static_burst(length, rng), scene_start("cm") + start)
    audio.place(track, body, scene_start("cm"))
    audio.place(track, audio.square_blip((784.0, 1046.5), 0.05, volume=0.09), scene_start("cm") + cues["sign"])
    return theme[cut:]


def build_audio(path: Path) -> None:
    rng = np.random.default_rng(1)
    total = total_duration()
    track = audio.silence(total)
    audio.place(track, audio.tape_hiss(total, rng), 0.0)

    tail = _cm_audio(track, rng)
    audio.place(track, audio.tape_stop(tail, scene_break.TAPE_STOP_SEC), scene_start("break"))

    # フックから先は不穏な曲を敷く
    hook = scene_start("hook")
    audio.place(track, audio.ominous_theme(total - hook), hook)
    for start, end in scene_hook.writing_spans():
        audio.place(track, audio.pencil_scratch(end - start, rng), hook + start)

    # 吹き出しの文字送り音。話者ごとに高さを変える（主人公は高め、所長は低め）
    clips = {
        "pop": audio.square_blip((392.0, 587.3), 0.04, volume=0.10),
        "blip:player": audio.square_blip((880.0,), 0.022, volume=0.05),
        "blip:director": audio.square_blip((587.3,), 0.022, volume=0.05),
    }
    for t, kind in scene_office.audio_events():
        audio.place(track, clips[kind], scene_start("office") + t)
    audio.write_wav(path, track)


def final_frame(t: float, use_vhs: bool) -> np.ndarray:
    """場面を描いて出力解像度へ拡大し、必要ならVHSの劣化表現をかける。"""
    scene, local, _ = scene_at(t)
    frame = upscale(scene.render(local))
    if not use_vhs:
        return frame
    strength = scene.vhs_strength(local) if scene.vhs_strength else 0.0
    boost = scene.vhs_boost(local) if scene.vhs_boost else 0.0
    return vhs.apply(frame, t, boost, strength)


def write_stills(times: tuple[float, ...], use_vhs: bool) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    for t in times:
        img = Image.fromarray(final_frame(t, use_vhs))
        img.resize((OUT_W // 2, OUT_H // 2), Image.Resampling.NEAREST).save(
            OUT_DIR / f"still_{t:05.2f}.png"
        )


def write_video(path: Path, use_vhs: bool) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    wav = OUT_DIR / "audio.wav"
    build_audio(wav)
    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OUT_W}x{OUT_H}", "-r", str(FPS), "-i", "-",
        "-i", str(wav),
        "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
        str(path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    frames = int(round(total_duration() * FPS))
    for i in range(frames):
        proc.stdin.write(final_frame(i / FPS, use_vhs).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpegでの書き出しに失敗しました")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stills", action="store_true")
    parser.add_argument("--no-vhs", action="store_true", help="VHSの劣化表現をかけずに書き出す")
    args = parser.parse_args()
    use_vhs = not args.no_vhs
    if args.stills:
        write_stills((0.8, 2.8, 4.6, 5.2, 6.6, 7.2, 7.8, 9.0), use_vhs)
        return
    write_video(OUT_DIR / "pv_intro_draft.mp4", use_vhs)


if __name__ == "__main__":
    main()
