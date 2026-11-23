"""O'zbek tili yordamchilari: lotin -> kirill transliteratsiya va sonlarni so'z bilan yozish.

MMS TTS modeli faqat kirill yozuvini tushunadi, shuning uchun lotin matnni avtomatik
kirillga o'giramiz. Raqamlar ham so'zga aylantiriladi ("5" -> "besh").
"""
import re

APOSTROPHES = "'‘’ʻʼ`´"
VOWELS_LAT = set("aeiouAEIOU")

_SINGLE = {
    "a": "а", "b": "б", "d": "д", "e": "е", "f": "ф", "g": "г", "h": "ҳ", "i": "и",
    "j": "ж", "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п", "q": "қ",
    "r": "р", "s": "с", "t": "т", "u": "у", "v": "в", "x": "х", "y": "й", "z": "з",
    "c": "с", "w": "в",
}
_DOUBLE = {"sh": "ш", "ch": "ч", "yo": "ё", "yu": "ю", "ya": "я", "ye": "е"}


def normalize_apostrophes(text: str) -> str:
    """o' g' kabi yozuvlarni to'g'ri belgi (ʻ) bilan almashtiradi."""
    text = re.sub(r"([oOgG])[" + APOSTROPHES + "]", r"\1ʻ", text)
    return text


def _case(src: str, dst: str) -> str:
    if src[:1].isupper():
        return dst.upper() if (len(src) > 1 and src[1:].isupper()) else dst[:1].upper() + dst[1:]
    return dst


def latin_to_cyrillic(text: str) -> str:
    out = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        lo = ch.lower()
        nxt = text[i + 1] if i + 1 < n else ""
        prev = text[i - 1] if i > 0 else ""
        # oʻ / gʻ
        if lo in "og" and nxt and nxt in APOSTROPHES:
            out.append(_case(ch, "ў" if lo == "o" else "ғ"))
            i += 2
            continue
        # s'h -> сҳ (Is'hoq)
        if lo == "s" and nxt in APOSTROPHES and i + 2 < n and text[i + 2].lower() == "h":
            out.append(_case(ch, "с") + _case(text[i + 2], "ҳ"))
            i += 3
            continue
        pair = (ch + nxt).lower()
        if pair in _DOUBLE:
            dst = _DOUBLE[pair]
            if pair == "ye" and (not prev.isalpha()):
                dst = "е"
            out.append(_case(ch + nxt, dst))
            i += 2
            continue
        if lo == "e":
            # so'z boshida yoki unlidan keyin -> э
            out.append(_case(ch, "э" if (not prev.isalpha() or prev in VOWELS_LAT) else "е"))
            i += 1
            continue
        if ch in APOSTROPHES:
            # tutuq belgisi (maʼno) -> ъ, qolganlari qoladi
            out.append("ъ" if prev.isalpha() and nxt.isalpha() else ch)
            i += 1
            continue
        if lo in _SINGLE:
            out.append(_case(ch, _SINGLE[lo]))
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


# ---------------- Sonlar ----------------
_ONES = ["nol", "bir", "ikki", "uch", "toʻrt", "besh", "olti", "yetti", "sakkiz", "toʻqqiz"]
_TENS = ["", "oʻn", "yigirma", "oʻttiz", "qirq", "ellik", "oltmish", "yetmish", "sakson", "toʻqson"]


def _under_1000(n: int) -> list[str]:
    words = []
    h, r = divmod(n, 100)
    if h:
        words += ([] if h == 1 else [_ONES[h]]) + ["yuz"]
    t, o = divmod(r, 10)
    if t:
        words.append(_TENS[t])
    if o:
        words.append(_ONES[o])
    return words


def number_to_words(n: int) -> str:
    if n == 0:
        return "nol"
    if n < 0:
        return "minus " + number_to_words(-n)
    parts = []
    for value, name in ((10**9, "milliard"), (10**6, "million"), (1000, "ming")):
        q, n = divmod(n, value)
        if q:
            parts += ([] if (q == 1 and name == "ming") else _under_1000(q)) + [name]
    parts += _under_1000(n)
    return " ".join(parts)


def ordinal(n: int) -> str:
    w = number_to_words(n)
    return w + ("nchi" if w[-1] in "aeiou" else "inchi")


def expand_numbers(text: str) -> str:
    """Matndagi raqamlarni o'zbekcha so'zlarga aylantiradi."""
    text = re.sub(r"(\d+)\s*%", lambda m: number_to_words(int(m.group(1))) + " foiz", text)
    # 1-qadam -> birinchi qadam
    text = re.sub(r"\b(\d+)-(?=\w)", lambda m: ordinal(int(m.group(1))) + " ", text)
    # 3.5 / 3,5 -> uch butun besh
    text = re.sub(r"(\d+)[.,](\d+)", lambda m: number_to_words(int(m.group(1))) + " butun "
                  + number_to_words(int(m.group(2))), text)
    text = re.sub(r"\d+", lambda m: number_to_words(int(m.group(0))), text)
    return text


def prepare_for_tts(text: str) -> str:
    """Lotin (yoki kirill) matnni MMS uchun kirill, kichik harf, raqamsiz holga keltiradi."""
    text = normalize_apostrophes(text)
    text = expand_numbers(text)
    text = latin_to_cyrillic(text)
    return text.lower()


if __name__ == "__main__":
    for s in ["Assalomu alaykum! Bugun 5 ta foydali odat haqida gaplashamiz.",
              "Oʻzbekiston, gʻalaba, maʼno, Is'hoq, yeyish, ertaga, yaxshi, 1-qadam, 25% chegirma, 1999"]:
        print(s, "->", prepare_for_tts(s))
