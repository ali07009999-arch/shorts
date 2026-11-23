"""Matnni ovozga aylantirish (TTS).

Dvigatellar:
  mms   - Meta MMS, oflayn ishlaydi, o'zbek tili bor (sifati o'rtacha). Standart.
  edge  - Microsoft Edge ovozlari (uz-UZ-SardorNeural / MadinaNeural). Eng tabiiy ovoz,
          lekin internet (WebSocket) kerak - o'z kompyuteringizda ishlaydi.
  gtts  - Google Translate ovozi (ru, en, tr...). O'zbek tili yo'q.
Har bir natija .cache/tts ichida saqlanadi, qayta yasashda vaqt ketmaydi.
"""
import hashlib
import os
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from .config import CACHE_DIR
from . import uzbek

SR = 48000
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

MMS_MODELS = {
    "uz": "facebook/mms-tts-uzb-script_cyrillic",
    "ru": "facebook/mms-tts-rus",
    "en": "facebook/mms-tts-eng",
    "tr": "facebook/mms-tts-tur",
    "kk": "facebook/mms-tts-kaz",
    "tg": "facebook/mms-tts-tgk",
}

EDGE_VOICES = {
    ("uz", "male"): "uz-UZ-SardorNeural",
    ("uz", "female"): "uz-UZ-MadinaNeural",
    ("ru", "male"): "ru-RU-DmitryNeural",
    ("ru", "female"): "ru-RU-SvetlanaNeural",
    ("en", "male"): "en-US-AndrewNeural",
    ("en", "female"): "en-US-AvaNeural",
    ("tr", "male"): "tr-TR-AhmetNeural",
    ("tr", "female"): "tr-TR-EmelNeural",
}

_mms_cache = {}


def load_audio(path, sr=SR, mono=True) -> np.ndarray:
    """Istalgan audio/video fayldan float32 massiv o'qiydi (ffmpeg orqali)."""
    ch = 1 if mono else 2
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", str(ch), "-ar", str(sr),
           "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    a = np.frombuffer(raw, dtype=np.float32)
    return a if mono else a.reshape(-1, 2)


def save_wav(path, audio: np.ndarray, sr=SR):
    import scipy.io.wavfile as wavfile
    wavfile.write(str(path), sr, np.clip(audio, -1, 1).astype(np.float32))


def _trim(a: np.ndarray, thr=0.01, keep=0.04) -> np.ndarray:
    idx = np.where(np.abs(a) > thr)[0]
    if len(idx) == 0:
        return a
    k = int(keep * SR)
    return a[max(0, idx[0] - k): min(len(a), idx[-1] + k)]


def _split_phrases(text: str):
    """Matnni gaplarga bo'lib, har biridan keyingi pauza uzunligini qaytaradi."""
    parts = re.split(r"([.!?…]+|[,;:—–]+)", text)
    out = []
    for i in range(0, len(parts), 2):
        chunk = parts[i].strip()
        punct = parts[i + 1] if i + 1 < len(parts) else ""
        if not chunk:
            continue
        pause = 0.45 if re.search(r"[.!?…]", punct) else (0.22 if punct else 0.0)
        out.append((chunk, pause))
    return out


def _resample(a: np.ndarray, src_sr: int) -> np.ndarray:
    if src_sr == SR:
        return a
    from scipy.signal import resample_poly
    from math import gcd
    g = gcd(SR, src_sr)
    return resample_poly(a, SR // g, src_sr // g).astype(np.float32)


def _mms(text: str, lang: str, speed: float, seed: int = 7) -> np.ndarray:
    import torch
    from transformers import AutoTokenizer, VitsModel

    model_id = MMS_MODELS.get(lang, f"facebook/mms-tts-{lang}")
    if model_id not in _mms_cache:
        tok = AutoTokenizer.from_pretrained(model_id)
        model = VitsModel.from_pretrained(model_id).eval()
        _mms_cache[model_id] = (tok, model)
    tok, model = _mms_cache[model_id]
    model.speaking_rate = speed
    model.noise_scale = 0.6

    if lang == "uz":
        text = uzbek.prepare_for_tts(text)
    pieces = []
    for chunk, pause in _split_phrases(text):
        clean = re.sub(r"[^\w\s\-ʻ']", " ", chunk).strip()
        if not clean:
            continue
        inputs = tok(clean, return_tensors="pt")
        if inputs["input_ids"].shape[-1] == 0:
            continue
        torch.manual_seed(seed)
        with torch.no_grad():
            wav = model(**inputs).waveform[0].numpy().astype(np.float32)
        wav = _trim(_resample(wav, model.config.sampling_rate))
        pieces.append(wav)
        pieces.append(np.zeros(int(pause * SR), dtype=np.float32))
    if not pieces:
        return np.zeros(int(0.5 * SR), dtype=np.float32)
    a = np.concatenate(pieces)
    peak = np.abs(a).max() or 1.0
    return (a / peak * 0.9).astype(np.float32)


def _edge(text: str, lang: str, gender: str, voice: str | None, speed: float, out_mp3: Path):
    import asyncio
    import edge_tts

    voice = voice or EDGE_VOICES.get((lang, gender)) or EDGE_VOICES[("en", gender)]
    rate = f"{int(round((speed - 1) * 100)):+d}%"

    async def run():
        await edge_tts.Communicate(text, voice, rate=rate).save(str(out_mp3))

    asyncio.run(run())


def _gtts(text: str, lang: str, out_mp3: Path):
    from gtts import gTTS
    gTTS(text, lang=lang).save(str(out_mp3))


def synthesize(text: str, engine: str = "mms", lang: str = "uz", gender: str = "male",
               voice: str | None = None, speed: float = 1.0) -> Path:
    """Matndan WAV (48 kHz mono) yasaydi va fayl yo'lini qaytaradi. Natija keshlanadi."""
    key = hashlib.sha1(f"{engine}|{lang}|{gender}|{voice}|{speed}|{text}".encode()).hexdigest()[:16]
    out = CACHE_DIR / "tts" / f"{key}.wav"
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)

    if engine == "edge":
        try:
            with tempfile.TemporaryDirectory() as td:
                mp3 = Path(td) / "v.mp3"
                _edge(text, lang, gender, voice, speed, mp3)
                if not mp3.exists() or mp3.stat().st_size == 0:
                    raise RuntimeError("edge-tts bo'sh fayl qaytardi")
                save_wav(out, _trim(load_audio(mp3)))
            return out
        except Exception as e:  # internet yo'q bo'lsa MMS ga o'tamiz
            print(f"  ! edge-tts ishlamadi ({type(e).__name__}); MMS oflayn ovozga o'tilyapti")
            engine = "mms"
    if engine == "gtts":
        with tempfile.TemporaryDirectory() as td:
            mp3 = Path(td) / "v.mp3"
            _gtts(text, lang, mp3)
            a = _trim(load_audio(mp3))
            if speed != 1.0:
                tmp = Path(td) / "a.wav"
                save_wav(tmp, a)
                a = load_audio_filtered(tmp, f"atempo={speed}")
            save_wav(out, a)
        return out
    if engine == "mms":
        save_wav(out, _mms(text, lang, speed))
        return out
    raise ValueError(f"Noma'lum TTS dvigatel: {engine}")


def load_audio_filtered(path, af: str) -> np.ndarray:
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-af", af, "-ac", "1", "-ar", str(SR),
           "-f", "f32le", "-"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, np.float32)


def duration(path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return float(out.strip())
