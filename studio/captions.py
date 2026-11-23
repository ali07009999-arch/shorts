"""Subtitrlar: Whisper bilan nutqni aniqlash, so'zlarni vaqtga bog'lash va
"har bir so'z yonib chiqadigan" (Reels/Shorts uslubi) ASS subtitr yasash."""
import re
from dataclasses import dataclass
from pathlib import Path

from .config import font_family


@dataclass
class Word:
    text: str
    start: float
    end: float


_whisper_cache = {}


def transcribe(audio_path, lang: str | None = "uz", model_size: str = "small") -> list[Word]:
    """faster-whisper bilan so'zma-so'z vaqt belgilari."""
    from faster_whisper import WhisperModel

    if model_size not in _whisper_cache:
        _whisper_cache[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
    model = _whisper_cache[model_size]
    segments, _ = model.transcribe(str(audio_path), language=lang, word_timestamps=True,
                                   vad_filter=True)
    words = []
    for seg in segments:
        for w in seg.words or []:
            t = w.word.strip()
            if t:
                words.append(Word(t, float(w.start), float(w.end)))
    return words


def align_script(script: str, heard: list[Word], total: float) -> list[Word]:
    """Asl matn so'zlarini Whisper eshitgan vaqtlarga moslaydi.

    Whisper o'zbekcha so'zlarni xato yozishi mumkin, shuning uchun ekranda ASL matnni
    ko'rsatamiz, faqat vaqtini Whisperdan olamiz (harflar ulushi bo'yicha interpolyatsiya).
    """
    words = script.split()
    if not words:
        return []
    lens = [len(re.sub(r"\W", "", w)) or 1 for w in words]
    total_chars = sum(lens)

    if heard:
        hl = [len(re.sub(r"\W", "", w.text)) or 1 for w in heard]
        ht = sum(hl)
        xs, ts_start, ts_end = [], [], []
        acc = 0
        for w, l in zip(heard, hl):
            xs.append(acc / ht)
            ts_start.append(w.start)
            acc += l
            ts_end.append(w.end)
        xs.append(1.0)
        ts_start.append(heard[-1].end)

        def t_at(frac):
            for i in range(len(xs) - 1):
                if frac <= xs[i + 1]:
                    span = xs[i + 1] - xs[i] or 1e-9
                    k = (frac - xs[i]) / span
                    a, b = ts_start[i], (ts_end[i] if i < len(ts_end) else ts_start[i + 1])
                    return a + (b - a) * k
            return ts_start[-1]
    else:
        def t_at(frac):
            return frac * total

    out = []
    acc = 0
    for w, l in zip(words, lens):
        s = t_at(acc / total_chars)
        acc += l
        e = t_at(acc / total_chars)
        out.append(Word(w, s, max(e, s + 0.08)))
    return out


def distribute(text: str, start: float, end: float) -> list[Word]:
    """Matnni berilgan oraliqqa harflar soniga qarab tekis taqsimlaydi."""
    ws = align_script(text, [], end - start)
    return [Word(w.text, w.start + start, w.end + start) for w in ws]


# ---------------- ASS ----------------
def _ass_color(hex_color: str, alpha: int = 0) -> str:
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _esc(t: str) -> str:
    return t.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def _fmt_time(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def group_words(words: list[Word], max_words: int, max_chars: int, gap: float = 0.6):
    groups, cur = [], []
    for w in words:
        if cur:
            text_len = sum(len(x.text) + 1 for x in cur) + len(w.text)
            if (len(cur) >= max_words or text_len > max_chars or w.start - cur[-1].end > gap):
                groups.append(cur)
                cur = []
        cur.append(w)
        if re.search(r"[.!?…]$", w.text):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def build_ass(words: list[Word], width: int, height: int, style: dict | None = None) -> str:
    st = {
        "font": "Montserrat-ExtraBold",
        "size": None,
        "color": "#FFFFFF",
        "highlight": "#FFD400",
        "outline_color": "#000000",
        "outline": None,
        "position": "bottom",  # bottom | center | top
        "uppercase": True,
        "max_words": None,
        "pop": True,
    }
    st.update(style or {})
    vertical = height > width
    size = st["size"] or int(width * (0.075 if vertical else 0.040))
    outline = st["outline"] if st["outline"] is not None else max(3, size // 12)
    max_words = st["max_words"] or (3 if vertical else 6)
    max_chars = 18 if vertical else 40
    fam, bold = font_family(st["font"])

    pos = st["position"]
    align = {"bottom": 2, "center": 5, "top": 8}[pos]
    margin_v = int(height * (0.26 if vertical else 0.08)) if pos != "center" else 0
    if pos == "top":
        margin_v = int(height * (0.14 if vertical else 0.06))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{fam},{size},{_ass_color(st['color'])},{_ass_color(st['highlight'])},{_ass_color(st['outline_color'])},{_ass_color('#000000', 0x60)},{-1 if bold else 0},0,0,0,100,100,0,0,1,{outline},{max(2, outline // 2)},{align},{int(width*0.07)},{int(width*0.07)},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    hl = _ass_color(st["highlight"])
    base = _ass_color(st["color"])
    lines = []
    groups = group_words(words, max_words, max_chars)
    for gi, g in enumerate(groups):
        g_end = g[-1].end + 0.25
        if gi + 1 < len(groups):
            g_end = min(g_end, groups[gi + 1][0].start)
        for wi, w in enumerate(g):
            s = w.start
            e = g[wi + 1].start if wi + 1 < len(g) else g_end
            if e <= s:
                continue
            parts = []
            for k, x in enumerate(g):
                t = _esc(x.text.upper() if st["uppercase"] else x.text)
                if k == wi:
                    pop = r"\fscx112\fscy112\t(0,90,\fscx100\fscy100)" if st["pop"] else ""
                    parts.append(f"{{\\c{hl}{pop}}}{t}{{\\c{base}\\fscx100\\fscy100}}")
                else:
                    parts.append(t)
            intro = r"{\fad(60,0)}" if wi == 0 else ""
            lines.append(f"Dialogue: 0,{_fmt_time(s)},{_fmt_time(e)},Cap,,0,0,0,,{intro}{' '.join(parts)}")
    return header + "\n".join(lines) + "\n"


def write_srt(words: list[Word], path: Path, max_words: int = 8):
    """YouTube'ga yuklash uchun oddiy .srt (so'zlar guruhlab)."""
    def ts(t):
        ms = int(round(t * 1000))
        return f"{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}"
    groups = group_words(words, max_words, 42, gap=0.8)
    with open(path, "w", encoding="utf-8") as f:
        for i, g in enumerate(groups, 1):
            f.write(f"{i}\n{ts(g[0].start)} --> {ts(g[-1].end)}\n{' '.join(w.text for w in g)}\n\n")


def read_srt(path: Path) -> list[Word]:
    """Tahrirlangan .srt dan so'zlar ro'yxati (vaqt segment ichida taqsimlanadi)."""
    text = Path(path).read_text(encoding="utf-8-sig")
    words = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [l for l in block.strip().splitlines() if l.strip()]
        tline = next((l for l in lines if "-->" in l), None)
        if not tline:
            continue
        a, b = [x.strip().replace(",", ".") for x in tline.split("-->")]

        def sec(x):
            h, m, s = x.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
        body = " ".join(lines[lines.index(tline) + 1:])
        words += distribute(body, sec(a), sec(b))
    return words
