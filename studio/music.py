"""Oddiy fon musiqasi generatori (mualliflik huquqi muammosiz, o'zimiz sintez qilamiz).

Bu - vaqtinchalik yechim. Haqiqiy videolar uchun assets/music/ papkasiga
YouTube Audio Library yoki boshqa litsenziyali musiqani qo'yish tavsiya etiladi.
"""
import numpy as np
from scipy.signal import butter, lfilter

from .tts import SR, save_wav

NOTE = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}

MOODS = {
    # bpm, akkordlar (ildiz, minor?), baraban, arpejio
    "calm": dict(bpm=78, chords=[("A", 1), ("F", 0), ("C", 0), ("G", 0)], kick=[0, 2.5], snare=[], arp=False),
    "lofi": dict(bpm=84, chords=[("D", 1), ("G", 0), ("C", 0), ("A", 1)], kick=[0, 2.5], snare=[1, 3], arp=False),
    "upbeat": dict(bpm=112, chords=[("C", 0), ("G", 0), ("A", 1), ("F", 0)], kick=[0, 1, 2, 3], snare=[1, 3], arp=True),
    "epic": dict(bpm=96, chords=[("A", 1), ("F", 0), ("C", 0), ("G", 0)], kick=[0, 1.5, 2, 3.5], snare=[1, 3], arp=True),
}


def _freq(semitone_from_a4: float) -> float:
    return 440.0 * 2 ** (semitone_from_a4 / 12)


def _chord_notes(root: str, minor: int, octave: int = 3):
    base = NOTE[root] - 9 + 12 * (octave - 4)  # A4 ga nisbatan
    third = 3 if minor else 4
    return [base, base + third, base + 7, base + 12]


def _env(n: int, attack: float, release: float) -> np.ndarray:
    e = np.ones(n, np.float32)
    a, r = int(attack * SR), int(release * SR)
    if a:
        e[:min(a, n)] = np.linspace(0, 1, min(a, n))
    if r:
        e[max(0, n - r):] *= np.linspace(1, 0, n - max(0, n - r))
    return e


def _lowpass(x, cutoff, order=2):
    b, a = butter(order, cutoff / (SR / 2), btype="low")
    return lfilter(b, a, x, axis=0).astype(np.float32)


def _highpass(x, cutoff, order=2):
    b, a = butter(order, cutoff / (SR / 2), btype="high")
    return lfilter(b, a, x, axis=0).astype(np.float32)


def generate(duration: float, mood: str = "calm", seed: int = 1) -> np.ndarray:
    cfg = MOODS.get(mood, MOODS["calm"])
    rng = np.random.default_rng(seed)
    beat = 60.0 / cfg["bpm"]
    bar = beat * 4
    bars = int(np.ceil(duration / bar)) + 1
    n = int(bars * bar * SR)
    out = np.zeros((n, 2), np.float32)
    t_bar = np.arange(int(bar * SR) + int(1.2 * SR)) / SR

    for b in range(bars):
        root, minor = cfg["chords"][b % len(cfg["chords"])]
        notes = _chord_notes(root, minor)
        i0 = int(b * bar * SR)
        seg = np.zeros((len(t_bar), 2), np.float32)
        # pad (ikki kanal biroz farqli - kenglik hissi)
        for k, semi in enumerate(notes):
            f = _freq(semi)
            for ch, det in ((0, 0.9985), (1, 1.0015)):
                ff = f * det
                tone = (np.sin(2 * np.pi * ff * t_bar) + 0.35 * np.sin(4 * np.pi * ff * t_bar)
                        + 0.12 * np.sin(6 * np.pi * ff * t_bar))
                seg[:, ch] += tone * 0.09
        # bass
        fb = _freq(notes[0] - 12)
        bass = np.sin(2 * np.pi * fb * t_bar) * 0.22
        seg += bass[:, None]
        seg *= _env(len(t_bar), 0.25, 1.2)[:, None]
        # arpejio
        if cfg["arp"]:
            step = beat / 2
            for s in range(8):
                semi = notes[[0, 1, 2, 3, 2, 1, 2, 3][s]] + 12
                f = _freq(semi)
                j0 = int(s * step * SR)
                L = int(step * 1.8 * SR)
                tt = np.arange(L) / SR
                pl = np.sin(2 * np.pi * f * tt) * np.exp(-tt * 9) * 0.10
                j1 = min(len(seg), j0 + L)
                seg[j0:j1, 0] += pl[: j1 - j0] * (0.8 if s % 2 else 1.0)
                seg[j0:j1, 1] += pl[: j1 - j0] * (1.0 if s % 2 else 0.8)
        j1 = min(n, i0 + len(seg))
        out[i0:j1] += seg[: j1 - i0]

    out = _lowpass(out, 2600 if cfg["arp"] else 1800)

    # barabanlar
    drums = np.zeros(n, np.float32)
    kl = int(0.35 * SR)
    tk = np.arange(kl) / SR
    kick = np.sin(2 * np.pi * (45 * tk + 75 / 18 * (1 - np.exp(-18 * tk)))) * np.exp(-tk * 9) * 0.6
    sl = int(0.2 * SR)
    snare_base = _highpass(rng.standard_normal(sl).astype(np.float32), 1200) * np.exp(-np.arange(sl) / SR * 22) * 0.18
    hl = int(0.05 * SR)
    hat_base = _highpass(rng.standard_normal(hl).astype(np.float32), 7000) * np.exp(-np.arange(hl) / SR * 80) * 0.06
    for b in range(bars):
        for pos in cfg["kick"]:
            i = int((b * bar + pos * beat) * SR)
            j = min(n, i + kl)
            drums[i:j] += kick[: j - i]
        for pos in cfg["snare"]:
            i = int((b * bar + pos * beat) * SR)
            j = min(n, i + sl)
            drums[i:j] += snare_base[: j - i]
        for h in range(8):
            i = int((b * bar + h * beat / 2 + (0.02 if h % 2 else 0)) * SR)
            j = min(n, i + hl)
            drums[i:j] += hat_base[: j - i] * (1.0 if h % 2 else 0.6)
    out += drums[:, None]

    out = out[: int(duration * SR)]
    peak = float(np.abs(out).max()) or 1.0
    return out / peak * 0.8


def generate_file(path, duration: float, mood: str = "calm"):
    save_wav(path, generate(duration, mood))
    return path
