#!/usr/bin/env python3
"""O'zingiz suratga olgan videoga avtomatik subtitr (+ musiqa, + format o'zgartirish).

Misollar:
  python add_captions.py mening_videom.mp4                       # subtitr qo'shish
  python add_captions.py video.mp4 --format reels --fit blur     # 16:9 -> 9:16 (xira fon bilan)
  python add_captions.py video.mp4 --music generate --mood lofi  # fon musiqasi bilan
  python add_captions.py video.mp4 --srt-only                    # faqat .srt yasash (tahrirlash uchun)
  python add_captions.py video.mp4 --srt tuzatilgan.srt          # tahrirlangan matn bilan

Whisper o'zbekcha so'zlarni ba'zan xato yozadi. Yaxshi natija uchun: avval --srt-only bilan
.srt oling, xatolarni tuzating, keyin --srt bilan qayta ishga tushiring.
"""
import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from studio import captions as cap
from studio import music as mus
from studio.audio import build_mix
from studio.config import CACHE_DIR, FONTS_DIR, FORMATS, OUTPUT_DIR, export_args
from studio.tts import duration


def probe_size(path: Path) -> tuple[int, int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:stream_side_data=rotation", "-of", "csv=p=0",
                          str(path)], capture_output=True, text=True).stdout.split()
    w, h = [int(x) for x in out[0].split(",")[:2]]
    rot = next((abs(int(float(x))) for x in out[1:] if x.strip("-").replace(".", "").isdigit()), 0)
    return (h, w) if rot in (90, 270) else (w, h)


def main():
    ap = argparse.ArgumentParser(description="Videoga avtomatik subtitr")
    ap.add_argument("video", type=Path)
    ap.add_argument("--lang", default="uz", help="uz, ru, en ... (auto uchun: auto)")
    ap.add_argument("--model", default="small", help="whisper modeli: base | small | medium | large-v3")
    ap.add_argument("--format", "-f", choices=list(FORMATS), help="chiqish formati (bermasangiz - asl o'lcham)")
    ap.add_argument("--fit", choices=["cover", "blur"], default="cover",
                    help="format o'zgarganda: cover - qirqish, blur - to'liq + xira fon")
    ap.add_argument("--srt", type=Path, help="tayyor/tahrirlangan .srt fayldan foydalanish")
    ap.add_argument("--srt-only", action="store_true", help="faqat .srt yaratish")
    ap.add_argument("--position", default="bottom", choices=["bottom", "center", "top"])
    ap.add_argument("--font", default="Montserrat-ExtraBold")
    ap.add_argument("--highlight", default="#FFD400")
    ap.add_argument("--no-upper", action="store_true", help="katta harflarsiz")
    ap.add_argument("--music", help="musiqa fayli yoki 'generate'")
    ap.add_argument("--mood", default="lofi")
    ap.add_argument("--music-volume", type=float, default=0.12)
    ap.add_argument("--out", "-o", type=Path)
    a = ap.parse_args()

    src = a.video.resolve()
    out = (a.out or OUTPUT_DIR / f"{src.stem}_subtitr{'_' + a.format if a.format else ''}.mp4").resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="cap_", dir=CACHE_DIR))
    try:
        total = duration(src)
        if a.srt:
            words = cap.read_srt(a.srt)
        else:
            print(f"1. Nutq aniqlanmoqda (whisper {a.model})...")
            wav = tmp / "a.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
                            str(wav)], check=True)
            words = cap.transcribe(wav, None if a.lang == "auto" else a.lang, a.model)
            print(f"   {len(words)} ta so'z topildi")
        srt_path = out.with_suffix(".srt")
        cap.write_srt(words, srt_path)
        print(f"   SRT: {srt_path}")
        if a.srt_only:
            return

        if a.format:
            W, H = FORMATS[a.format]
        else:
            W, H = probe_size(src)
        style = {"font": a.font, "highlight": a.highlight, "position": a.position,
                 "uppercase": not a.no_upper}
        (tmp / "c.ass").write_text(cap.build_ass(words, W, H, style), encoding="utf-8")

        print("2. Audio...")
        music = None
        if a.music == "generate":
            music = mus.generate_file(tmp / "m.wav", total + 1, a.mood)
        elif a.music:
            music = Path(a.music).resolve()
        mix = build_mix(total, [(0.0, src, 1.0)], tmp / "mix.wav", music, a.music_volume)

        print("3. Video kodlanmoqda...")
        fonts_rel = os.path.relpath(FONTS_DIR, tmp).replace("\\", "/")
        if a.format and a.fit == "blur":
            chain = (f"[0:v]split[a][b];[a]scale={W//4}:{H//4}:force_original_aspect_ratio=increase,"
                     f"crop={W//4}:{H//4},gblur=sigma=12,scale={W}:{H},eq=brightness=-0.12[bg];"
                     f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
                     f"[bg][fg]overlay=(W-w)/2:(H-h)/2,")
        elif a.format:
            chain = f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
        else:
            chain = "[0:v]"
        fc = f"{chain}setsar=1,ass=c.ass:fontsdir={fonts_rel}[v]"
        cmd = ["ffmpeg", "-v", "error", "-stats", "-y", "-i", str(src), "-i", str(mix), "-filter_complex", fc,
               "-map", "[v]", "-map", "1:a"] + export_args() + ["-shortest", str(out)]
        subprocess.run(cmd, check=True, cwd=tmp)
        print(f"✔ Tayyor: {out}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
