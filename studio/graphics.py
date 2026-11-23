"""Grafika: matnni rasmga chizish, fonlar (rang, gradient, rasm, video), Ken Burns harakati."""
import re
import subprocess
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import font_path


def hex_rgb(c: str) -> tuple[int, int, int]:
    c = c.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


@lru_cache(maxsize=64)
def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(font_path(name)), size)


def _tokens(text: str):
    """'*so'z*' -> urg'u rangida. Qaytaradi: [(so'z, urg'u?), ...] va qatorlar ajratgichlari."""
    out = []
    accent = False
    for part in re.split(r"(\*)", text):
        if part == "*":
            accent = not accent
            continue
        for line_i, line in enumerate(part.split("\n")):
            if line_i > 0:
                out.append(("\n", False))
            for w in line.split(" "):
                if w:
                    out.append((w, accent))
    return out


def text_image(text: str, font: str = "Montserrat-ExtraBold", size: int = 90,
               color: str = "#FFFFFF", accent: str = "#FFD400", max_width: int = 900,
               max_height: int | None = None, align: str = "center", stroke: int = 0,
               stroke_color: str = "#000000", shadow: bool = True, box: str | None = None,
               box_pad: int = 30, box_radius: int = 28, uppercase: bool = False,
               line_spacing: float = 1.12) -> np.ndarray:
    """Matnni shaffof RGBA rasmga chizadi. *yulduzcha* ichidagi so'zlar urg'u rangida."""
    if uppercase:
        text = text.upper()
    tokens = _tokens(text)
    while True:
        f = _font(font, size)
        space = f.getlength(" ")
        lines, cur, cur_w = [], [], 0.0
        for w, acc in tokens:
            if w == "\n":
                lines.append(cur)
                cur, cur_w = [], 0.0
                continue
            ww = f.getlength(w)
            if cur and cur_w + space + ww > max_width:
                lines.append(cur)
                cur, cur_w = [], 0.0
            cur.append((w, acc, ww))
            cur_w += (space if len(cur) > 1 else 0) + ww
        lines.append(cur)
        asc, desc = f.getmetrics()
        line_h = int((asc + desc) * line_spacing)
        total_h = line_h * len(lines)
        widest = max((sum(x[2] for x in l) + space * (len(l) - 1) for l in lines if l), default=0)
        fits = widest <= max_width and (max_height is None or total_h <= max_height)
        if fits or size <= 24:
            break
        size = int(size * 0.92)

    pad = max(stroke * 2, 24 if shadow else 4) + (box_pad if box else 0)
    W = int(widest) + pad * 2
    H = total_h + pad * 2
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    def draw_text(d: ImageDraw.ImageDraw, fill_main, fill_acc, sw, sc):
        y = pad
        for l in lines:
            lw = sum(x[2] for x in l) + space * (len(l) - 1)
            x = pad + {"center": (widest - lw) / 2, "left": 0, "right": widest - lw}[align]
            for w, acc, ww in l:
                d.text((x, y), w, font=f, fill=fill_acc if acc else fill_main,
                       stroke_width=sw, stroke_fill=sc)
                x += ww + space
            y += line_h

    if shadow and not box:
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw_text(ImageDraw.Draw(sh), (0, 0, 0, 190), (0, 0, 0, 190), stroke, (0, 0, 0, 190))
        sh = sh.filter(ImageFilter.GaussianBlur(max(4, size // 14)))
        img.paste(sh, (0, max(3, size // 22)))
    if box:
        bd = ImageDraw.Draw(img)
        rgb = hex_rgb(box[:7])
        alpha = int(box[7:9], 16) if len(box) > 7 else 230
        bd.rounded_rectangle((pad - box_pad, pad - box_pad // 2, W - pad + box_pad, H - pad + box_pad // 2),
                             radius=box_radius, fill=rgb + (alpha,))
    draw_text(ImageDraw.Draw(img), hex_rgb(color) + (255,), hex_rgb(accent) + (255,),
              stroke, hex_rgb(stroke_color) + (255,))
    return np.array(img)


# ---------------- Fonlar ----------------
def gradient(w: int, h: int, colors: list[str], angle: float = 90) -> np.ndarray:
    """Chiziqli gradient. angle=90 - yuqoridan pastga."""
    cols = np.array([hex_rgb(c) for c in colors], dtype=np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    a = np.deg2rad(angle)
    proj = xx * np.cos(a) + yy * np.sin(a)
    proj = (proj - proj.min()) / (proj.max() - proj.min() + 1e-6)
    n = len(cols) - 1
    pos = proj * n
    i = np.clip(pos.astype(int), 0, n - 1)
    t = (pos - i)[..., None]
    img = cols[i] * (1 - t) + cols[i + 1] * t
    # yengil vin'etka
    cx, cy = w / 2, h / 2
    r = np.sqrt(((xx - cx) / w) ** 2 + ((yy - cy) / h) ** 2)
    img *= (1 - 0.35 * np.clip(r * 1.3, 0, 1) ** 2)[..., None]
    # yengil shovqin - gradientda "zinapoya" (banding) ko'rinmasligi uchun
    img += np.random.default_rng(0).uniform(-2.0, 2.0, img.shape[:2])[..., None]
    return np.clip(img, 0, 255).astype(np.uint8)


def load_image(path) -> np.ndarray:
    return np.array(Image.open(path).convert("RGB"))


def cover(img: np.ndarray, w: int, h: int, scale: float = 1.0) -> np.ndarray:
    """Rasmni kadrni to'liq qoplaydigan qilib kattalashtiradi (ortiqchasi qirqiladi)."""
    ih, iw = img.shape[:2]
    k = max(w / iw, h / ih) * scale
    nw, nh = int(round(iw * k)), int(round(ih * k))
    r = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC)
    x, y = (nw - w) // 2, (nh - h) // 2
    return r[y:y + h, x:x + w]


def contain_blur(img: np.ndarray, w: int, h: int) -> np.ndarray:
    """Rasmni to'liq ko'rsatadi, bo'sh joylarni xiralashtirilgan fon bilan to'ldiradi."""
    bg = cover(img, w // 4, h // 4)
    bg = cv2.GaussianBlur(bg, (0, 0), 12)
    bg = (cv2.resize(bg, (w, h), interpolation=cv2.INTER_LINEAR) * 0.55).astype(np.uint8)
    ih, iw = img.shape[:2]
    k = min(w / iw, h / ih)
    nw, nh = int(iw * k), int(ih * k)
    fg = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC)
    x, y = (w - nw) // 2, (h - nh) // 2
    bg[y:y + nh, x:x + nw] = fg
    return bg


def ease(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def ease_out(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3


class KenBurns:
    """Rasmga sekin zoom/pan harakati (subpiksel aniqlikda, titramasdan)."""

    def __init__(self, img: np.ndarray, w: int, h: int, motion: str = "zoom-in",
                 strength: float = 0.12, fit: str = "cover"):
        self.w, self.h, self.motion, self.s = w, h, motion, strength
        base = contain_blur(img, w, h) if fit == "blur" else cover(img, w, h)
        # zaxira bilan kattaroq nusxa (sifat uchun)
        self.big = cv2.resize(base, (int(w * (1 + strength) + 2), int(h * (1 + strength) + 2)),
                              interpolation=cv2.INTER_CUBIC) if motion != "none" else base
        self.base = base

    def frame(self, p: float) -> np.ndarray:
        if self.motion == "none":
            return self.base
        p = ease(p) * 0.85 + p * 0.15
        s = self.s
        bh, bw = self.big.shape[:2]
        if self.motion == "zoom-in":
            z = 1 + s * p
        elif self.motion == "zoom-out":
            z = 1 + s * (1 - p)
        else:
            z = 1 + s
        # chiqish kadridagi 1 piksel = katta rasmda (bw / (w*z)) piksel
        k = (bw / (self.w * (1 + s))) * (1 + s) / z
        vis_w, vis_h = self.w * k, self.h * k
        cx, cy = bw / 2, bh / 2
        free_x, free_y = (bw - vis_w) / 2, (bh - vis_h) / 2
        if self.motion == "pan-left":
            cx = bw / 2 + free_x * (1 - 2 * p)
        elif self.motion == "pan-right":
            cx = bw / 2 - free_x * (1 - 2 * p)
        elif self.motion == "pan-up":
            cy = bh / 2 + free_y * (1 - 2 * p)
        elif self.motion == "pan-down":
            cy = bh / 2 - free_y * (1 - 2 * p)
        x0, y0 = cx - vis_w / 2, cy - vis_h / 2
        M = np.array([[1 / k, 0, -x0 / k], [0, 1 / k, -y0 / k]], dtype=np.float32)
        return cv2.warpAffine(self.big, M, (self.w, self.h), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REFLECT)


class VideoReader:
    """Videoni kadrma-kadr o'qiydi (ffmpeg), kerakli o'lchamga keltirib. Qisqa bo'lsa aylanadi."""

    def __init__(self, path, w: int, h: int, fps: int, start: float = 0.0, fit: str = "cover",
                 loop: bool = True, speed: float = 1.0):
        self.w, self.h = w, h
        if fit == "blur":
            vf = (f"[0:v]fps={fps},split[a][b];"
                  f"[a]scale={w//4}:{h//4}:force_original_aspect_ratio=increase,crop={w//4}:{h//4},"
                  f"gblur=sigma=12,scale={w}:{h},eq=brightness=-0.12[bg];"
                  f"[b]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
                  f"[bg][fg]overlay=(W-w)/2:(H-h)/2,format=rgb24")
        else:
            vf = (f"[0:v]fps={fps},scale={w}:{h}:force_original_aspect_ratio=increase,"
                  f"crop={w}:{h},format=rgb24")
        if speed != 1.0:
            vf = vf.replace("[0:v]", f"[0:v]setpts=PTS/{speed},", 1)
        cmd = ["ffmpeg", "-v", "error"] + (["-stream_loop", "-1"] if loop else []) + \
              ["-ss", str(start), "-i", str(path), "-filter_complex", vf, "-an",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.size = w * h * 3
        self.last = np.zeros((h, w, 3), np.uint8)

    def next(self) -> np.ndarray:
        buf = self.proc.stdout.read(self.size)
        if len(buf) == self.size:
            self.last = np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3)
        return self.last

    def close(self):
        try:
            self.proc.stdout.close()
            self.proc.kill()
            self.proc.wait(timeout=5)
        except Exception:
            pass


def overlay(frame: np.ndarray, rgba: np.ndarray, x: int, y: int, opacity: float = 1.0,
            scale: float = 1.0) -> np.ndarray:
    """RGBA rasmni kadrga (x, y - markaz) joylashtiradi. frame joyida o'zgaradi."""
    if opacity <= 0.003:
        return frame
    if abs(scale - 1.0) > 0.002:
        nh, nw = max(1, int(rgba.shape[0] * scale)), max(1, int(rgba.shape[1] * scale))
        rgba = cv2.resize(rgba, (nw, nh), interpolation=cv2.INTER_LINEAR)
    h, w = rgba.shape[:2]
    x0, y0 = int(round(x - w / 2)), int(round(y - h / 2))
    H, W = frame.shape[:2]
    fx0, fy0, fx1, fy1 = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
    if fx0 >= fx1 or fy0 >= fy1:
        return frame
    src = rgba[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0]
    a = src[..., 3:4].astype(np.float32) * (opacity / 255.0)
    dst = frame[fy0:fy1, fx0:fx1].astype(np.float32)
    frame[fy0:fy1, fx0:fx1] = (src[..., :3] * a + dst * (1 - a)).astype(np.uint8)
    return frame
