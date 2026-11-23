"""Umumiy sozlamalar: papkalar, formatlar, shriftlar, eksport parametrlari."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = ROOT / "assets" / "fonts"
OUTPUT_DIR = ROOT / "output"
CACHE_DIR = ROOT / ".cache"

# Platforma formatlari (kenglik x balandlik)
FORMATS = {
    "reels": (1080, 1920),    # Instagram Reels, 9:16
    "shorts": (1080, 1920),   # YouTube Shorts, 9:16
    "tiktok": (1080, 1920),
    "youtube": (1920, 1080),  # Oddiy YouTube video, 16:9
    "square": (1080, 1080),   # 1:1
    "post": (1080, 1350),     # Instagram feed, 4:5
}

# Shrift nomi -> fayl. ASS (subtitr) uchun oila nomi ham kerak.
FONTS = {
    "Montserrat-SemiBold": ("Montserrat-SemiBold.ttf", "Montserrat SemiBold"),
    "Montserrat-Bold": ("Montserrat-Bold.ttf", "Montserrat"),
    "Montserrat-ExtraBold": ("Montserrat-ExtraBold.ttf", "Montserrat ExtraBold"),
    "Montserrat-Black": ("Montserrat-Black.ttf", "Montserrat Black"),
    "Oswald-Bold": ("Oswald-Bold.ttf", "Oswald"),
    "NotoSans-Regular": ("NotoSans-Regular.ttf", "Noto Sans"),
    "NotoSans-Bold": ("NotoSans-Bold.ttf", "Noto Sans"),
    "Anton": ("Anton-Regular.ttf", "Anton"),  # faqat lotin (kirill yo'q)
}
DEFAULT_FONT = "Montserrat-ExtraBold"


def font_path(name: str) -> Path:
    if name in FONTS:
        return FONTS_DIR / FONTS[name][0]
    p = Path(name)
    if p.exists():
        return p
    cand = FONTS_DIR / name
    if cand.exists():
        return cand
    raise FileNotFoundError(f"Shrift topilmadi: {name}. Mavjudlari: {', '.join(FONTS)}")


def font_family(name: str) -> tuple[str, bool]:
    """ASS uchun (oila nomi, bold) qaytaradi."""
    if name in FONTS:
        fam = FONTS[name][1]
        bold = name.endswith("-Bold") and fam in ("Montserrat", "Noto Sans", "Oswald")
        return fam, bold
    return name, False


# Eksport: H.264 + AAC, Instagram va YouTube tavsiyalariga mos
def export_args(preview: bool = False) -> list[str]:
    if preview:
        v = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "26"]
    else:
        v = ["-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-maxrate", "20M", "-bufsize", "40M", "-profile:v", "high", "-level", "4.2"]
    return v + ["-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-movflags", "+faststart"]
