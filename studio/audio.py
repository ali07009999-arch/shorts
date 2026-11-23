"""Ovozlarni yig'ish: diktor ovozi + fon musiqasi (ovoz paytida avtomatik pasayadi) + video ovozi.
Oxirida ovoz balandligi Instagram/YouTube standartiga (-14 LUFS) moslanadi."""
import subprocess
from pathlib import Path

import numpy as np

from .tts import SR, load_audio, save_wav


def _smooth(x: np.ndarray, k: int) -> np.ndarray:
    """Tez sirpanuvchi o'rtacha (markazlashgan)."""
    k = max(1, k)
    c = np.concatenate([[0.0], np.cumsum(x, dtype=np.float64)])
    half = k // 2
    idx = np.arange(len(x))
    lo = np.clip(idx - half, 0, len(x))
    hi = np.clip(idx + half + 1, 0, len(x))
    return ((c[hi] - c[lo]) / (hi - lo)).astype(np.float32)


def build_mix(total: float, voices: list[tuple[float, Path, float]], out_wav: Path,
              music: Path | None = None, music_volume: float = 0.15, duck: float = 0.35,
              extra: list[tuple[float, Path, float, float]] | None = None,
              fade_out: float = 1.5, loudness: float = -14.0) -> Path:
    """voices: [(boshlanish_vaqti, fayl, balandlik)]; extra: [(boshlanish, fayl, balandlik, max_uzunlik)]"""
    n = int(total * SR) + 1
    voice = np.zeros(n, np.float32)
    for start, path, vol in voices:
        a = load_audio(path) * vol
        i = int(start * SR)
        j = min(n, i + len(a))
        if j > i:
            voice[i:j] += a[: j - i]

    mix = np.repeat(voice[:, None], 2, axis=1)

    for start, path, vol, max_len in extra or []:
        try:
            a = load_audio(path, mono=False) * vol
        except subprocess.CalledProcessError:
            continue  # videoda ovoz yo'q
        a = a[: int(max_len * SR)]
        i = int(start * SR)
        j = min(n, i + len(a))
        if j > i:
            f = min(j - i, int(0.15 * SR))
            a = a.copy()
            a[:f] *= np.linspace(0, 1, f)[:, None]
            a[j - i - f:j - i] *= np.linspace(1, 0, f)[:, None]
            mix[i:j] += a[: j - i]

    if music:
        m = load_audio(music, mono=False)
        if len(m) == 0:
            m = np.zeros((n, 2), np.float32)
        reps = int(np.ceil(n / len(m)))
        m = np.tile(m, (reps, 1))[:n] * music_volume
        # ducking: ovoz bor joyda musiqa pasayadi
        env = _smooth(np.abs(voice), int(0.05 * SR))
        active = (env > 0.01).astype(np.float32)
        # attack/release yumshatish
        active = np.clip(_smooth(active, int(0.35 * SR)) * 1.6, 0, 1)
        gain = 1 - (1 - duck) * active
        m *= gain[:, None]
        fi = min(n, int(1.0 * SR))
        m[:fi] *= np.linspace(0, 1, fi)[:, None]
        fo = min(n, int(fade_out * SR))
        m[n - fo:] *= np.linspace(1, 0, fo)[:, None]
        mix += m

    raw = out_wav.with_suffix(".raw.wav")
    save_wav(raw, mix / max(1.0, float(np.abs(mix).max())))
    # Ovoz balandligini normallashtirish (YouTube/Instagram ~ -14 LUFS)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af",
                    f"loudnorm=I={loudness}:TP=-1.5:LRA=11", "-ar", str(SR), "-ac", "2",
                    str(out_wav)], check=True)
    raw.unlink(missing_ok=True)
    return out_wav
