"""Ssenariy (YAML) dan tayyor video yasaydigan asosiy dvigatel."""
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from . import captions as cap
from . import graphics as gx
from . import music as mus
from . import tts
from .audio import build_mix
from .config import CACHE_DIR, FONTS_DIR, FORMATS, OUTPUT_DIR, export_args

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}


@dataclass
class Scene:
    index: int
    data: dict
    start: float = 0.0
    duration: float = 3.0
    voice: Path | None = None
    voice_dur: float = 0.0
    voice_start: float = 0.0  # sahna ichida
    bg: object = None
    overlays: list = field(default_factory=list)  # (rgba, x, y, anim)
    words: list = field(default_factory=list)


class Project:
    def __init__(self, scenario: dict, base_dir: Path, fmt: str | None = None, preview: bool = False):
        self.s = scenario
        self.base = base_dir
        self.fmt = fmt or scenario.get("format", "reels")
        W, H = FORMATS[self.fmt]
        if preview:
            W, H = W // 2, H // 2
        self.W, self.H = W, H
        self.scale = W / FORMATS[self.fmt][0]
        self.vertical = H > W
        self.fps = int(scenario.get("fps", 30))
        self.preview = preview
        theme = {"font": "Montserrat-ExtraBold", "text_color": "#FFFFFF", "accent": "#FFD400",
                 "bg": "gradient:#0f2027,#203a43,#2c5364", "title_box": None, "uppercase": False}
        theme.update(scenario.get("theme", {}))
        self.theme = theme
        tr = scenario.get("transition", "fade")
        self.transition = tr if isinstance(tr, dict) else {"type": tr, "duration": 0.45}
        if self.transition["type"] == "none":
            self.transition["duration"] = 0.0
        self.scenes: list[Scene] = []

    # ---------- yordamchi ----------
    def path(self, p) -> Path:
        p = Path(str(p)).expanduser()
        if p.is_absolute():
            return p
        for root in (self.base, self.base.parent.parent, Path.cwd()):
            if (root / p).exists():
                return root / p
        return self.base / p

    def px(self, v: float) -> int:
        return int(round(v * self.scale))

    # ---------- 1. Ovoz ----------
    def prepare_audio(self):
        vcfg = {"engine": "mms", "lang": "uz", "gender": "male", "voice": None, "speed": 1.0}
        vcfg.update(self.s.get("voice", {}) or {})
        T = self.transition["duration"]
        for i, d in enumerate(self.s["scenes"]):
            sc = Scene(i, d)
            if d.get("audio"):  # o'zingiz yozgan ovoz
                sc.voice = self.path(d["audio"])
            elif d.get("say"):
                print(f"  [{i+1}] ovoz: {d['say'][:60]}...")
                sc.voice = tts.synthesize(d["say"], vcfg["engine"], d.get("lang", vcfg["lang"]),
                                          vcfg["gender"], d.get("voice_name", vcfg["voice"]),
                                          float(d.get("speed", vcfg["speed"])))
            if sc.voice:
                sc.voice_dur = tts.duration(sc.voice)
                sc.voice_start = float(d.get("voice_delay", 0.25 if i else 0.15))
            dur = d.get("duration", "auto")
            if dur == "auto" or dur is None:
                if sc.voice:
                    dur = sc.voice_start + sc.voice_dur + float(d.get("pause", 0.35)) + T
                else:
                    dur = 3.0
            sc.duration = max(float(dur), T + 0.5)
            self.scenes.append(sc)
        # vaqt chizig'i (o'tishlar sahnalarni ustma-ust qo'yadi)
        t = 0.0
        for k, sc in enumerate(self.scenes):
            sc.start = t
            t += sc.duration - (T if k < len(self.scenes) - 1 else 0)
        self.total = t

    # ---------- 2. Subtitr ----------
    def prepare_captions(self) -> list:
        ccfg = self.s.get("captions", {})
        if ccfg is False or (isinstance(ccfg, dict) and not ccfg.get("enabled", True)):
            return []
        ccfg = ccfg if isinstance(ccfg, dict) else {}
        use_whisper = ccfg.get("timing", "whisper") == "whisper"
        words = []
        for sc in self.scenes:
            text = sc.data.get("caption", sc.data.get("say"))
            if not sc.voice or sc.data.get("caption") is False:
                continue
            if not text and not sc.data.get("audio"):
                continue
            heard = []
            # o'z ovozingiz matnsiz berilsa, subtitr to'liq Whisper'dan olinadi
            if use_whisper or not text:
                try:
                    lang = sc.data.get("lang", (self.s.get("voice") or {}).get("lang", "uz"))
                    heard = cap.transcribe(sc.voice, lang, ccfg.get("model", "small"))
                except Exception as e:
                    print(f"  ! whisper ishlamadi ({type(e).__name__}), vaqt taxminiy bo'ladi")
            ws = cap.align_script(text, heard, sc.voice_dur) if text else heard
            off = sc.start + sc.voice_start
            words += [cap.Word(w.text, w.start + off, w.end + off) for w in ws]
        return words

    # ---------- 3. Fonlar va matnlar ----------
    def make_background(self, sc: Scene):
        d = sc.data
        bg = d.get("bg", self.theme["bg"])
        fit = d.get("fit", "cover")
        motion = d.get("motion", "zoom-in")
        W, H = self.W, self.H
        if isinstance(bg, str) and bg.startswith("gradient:"):
            cols = bg.split(":", 1)[1].split(",")
            img = gx.gradient(W, H, cols, float(d.get("angle", 90)))
            return ("static", img)
        if isinstance(bg, str) and bg.startswith("#"):
            return ("static", np.full((H, W, 3), gx.hex_rgb(bg), np.uint8))
        p = self.path(bg)
        if not p.exists():
            raise FileNotFoundError(f"Fon fayli topilmadi: {p}")
        if p.suffix.lower() in IMAGE_EXT:
            return ("image", gx.KenBurns(gx.load_image(p), W, H, motion,
                                         float(d.get("motion_strength", 0.12)), fit))
        if p.suffix.lower() in VIDEO_EXT:
            return ("video", (p, float(d.get("start", 0)), fit, float(d.get("video_speed", 1.0))))
        raise ValueError(f"Fon turi tushunarsiz: {bg}")

    def make_overlays(self, sc: Scene):
        d, th = sc.data, self.theme
        W, H = self.W, self.H
        ov = []
        font = d.get("font", th["font"])
        color = d.get("text_color", th["text_color"])
        accent = d.get("accent", th["accent"])
        box = d.get("title_box", th.get("title_box"))
        upper = d.get("uppercase", th.get("uppercase", False))
        pos = d.get("text_pos", "center")
        anim = d.get("anim", "pop")
        y_map = {"top": 0.22, "center": 0.42 if self.vertical else 0.45, "bottom": 0.62}
        y = H * float(d.get("text_y", y_map.get(pos, 0.42)))
        maxw = int(W * (0.86 if self.vertical else 0.78))

        if d.get("title"):
            size = self.px(d.get("title_size", 110 if self.vertical else 120))
            img = gx.text_image(d["title"], font, size, color, accent, maxw, int(H * 0.4), box=box,
                                stroke=self.px(d.get("stroke", 0)), uppercase=upper)
            ov.append([img, W / 2, y, anim, 0.0])
            y += img.shape[0] / 2
        if d.get("subtitle"):
            size = self.px(d.get("subtitle_size", 56 if self.vertical else 60))
            img = gx.text_image(d["subtitle"], d.get("subtitle_font", "Montserrat-SemiBold"), size,
                                d.get("subtitle_color", "#E6E6E6"), accent, maxw, int(H * 0.3))
            ov.append([img, W / 2, y + img.shape[0] / 2 + self.px(10), anim, 0.15])
        sc.overlays = ov

    # ---------- 4. Kadrlar ----------
    def _scene_frame(self, sc: Scene, lt: float, readers: dict) -> np.ndarray:
        kind, obj = sc.bg
        p = lt / sc.duration
        if kind == "static":
            frame = obj.copy()
        elif kind == "image":
            frame = obj.frame(p).copy()
        else:
            if sc.index not in readers:
                path, start, fit, speed = obj
                readers[sc.index] = gx.VideoReader(path, self.W, self.H, self.fps, start, fit, speed=speed)
            frame = readers[sc.index].next().copy()
        dim = sc.data.get("dim", 0.3 if (kind != "static" and sc.overlays) else 0.0)
        if dim:
            frame = (frame * (1 - float(dim))).astype(np.uint8)
        for img, x, y, anim, delay in sc.overlays:
            t = lt - 0.15 - delay
            out_t = sc.duration - lt
            fin = gx.ease_out(t / 0.45)
            op = fin * max(0.0, min(1.0, out_t / 0.3))
            sc_k, dy = 1.0, 0.0
            if anim == "pop":
                sc_k = 0.82 + 0.18 * gx.ease_out(t / 0.35) + 0.03 * np.sin(min(1, t / 0.5) * np.pi)
            elif anim == "slide":
                dy = (1 - fin) * self.px(80)
            elif anim == "none":
                op = 1.0
            gx.overlay(frame, img, x, y + dy, op, sc_k)
        return frame

    def _decor(self, frame: np.ndarray, t: float):
        """Butun video bo'ylab: progress chizig'i, watermark."""
        if self.s.get("progress_bar"):
            h = max(4, self.px(10))
            w = int(self.W * min(1.0, t / self.total))
            col = gx.hex_rgb(self.theme["accent"])
            frame[:h, :w] = col
        if self._wm is not None:
            gx.overlay(frame, self._wm, self._wm_xy[0], self._wm_xy[1], 0.85)
        return frame

    def _transition(self, a: np.ndarray, b: np.ndarray, p: float) -> np.ndarray:
        kind = self.transition["type"]
        p = gx.ease(p)
        if kind == "slide":
            off = int(self.W * p)
            out = np.empty_like(a)
            out[:, : self.W - off] = a[:, off:]
            out[:, self.W - off:] = b[:, : off]
            return out
        if kind == "zoom":
            k = 1 + 0.25 * p
            M = cv2.getRotationMatrix2D((self.W / 2, self.H / 2), 0, k)
            az = cv2.warpAffine(a, M, (self.W, self.H), borderMode=cv2.BORDER_REFLECT)
            return cv2.addWeighted(az, 1 - p, b, p, 0)
        if kind == "flash":
            if p < 0.5:
                return cv2.addWeighted(a, 1 - p * 2, np.full_like(a, 255), p * 2, 0)
            return cv2.addWeighted(np.full_like(b, 255), (1 - p) * 2, b, (p - 0.5) * 2, 0)
        return cv2.addWeighted(a, 1 - p, b, p, 0)

    # ---------- 5. Yig'ish ----------
    def render(self, out_path: Path, keep_temp: bool = False) -> Path:
        t0 = time.time()
        print(f"▶ Format: {self.fmt} {self.W}x{self.H}, {self.fps} fps")
        print("1/5 Ovoz tayyorlanmoqda...")
        self.prepare_audio()
        print(f"    Davomiyligi: {self.total:.1f} s, sahnalar: {len(self.scenes)}")
        print("2/5 Subtitrlar...")
        words = self.prepare_captions()
        print("3/5 Fon va matnlar...")
        for sc in self.scenes:
            sc.bg = self.make_background(sc)
            self.make_overlays(sc)
        self._wm = None
        if self.s.get("watermark"):
            self._wm = gx.text_image(self.s["watermark"], "Montserrat-SemiBold", self.px(34),
                                     "#FFFFFF", self.theme["accent"], self.W, shadow=True)
            m = self.px(40)
            self._wm_xy = (self.W - self._wm.shape[1] / 2 - m + self.px(16),
                           self.px(120 if self.vertical else 50))

        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix="render_", dir=CACHE_DIR if CACHE_DIR.exists() else None))
        print("4/5 Audio miks...")
        voices = [(sc.start + sc.voice_start, sc.voice, float(sc.data.get("voice_volume", 1.0)))
                  for sc in self.scenes if sc.voice]
        extra = []
        for sc in self.scenes:
            if sc.bg[0] == "video" and sc.data.get("video_volume", 0):
                path, start, _, _ = sc.bg[1]
                tr = tmp / f"va{sc.index}.wav"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(start), "-i", str(path),
                                "-t", str(sc.duration), "-vn", "-ac", "2", "-ar", "48000", str(tr)])
                if tr.exists():
                    extra.append((sc.start, tr, float(sc.data["video_volume"]), sc.duration))
        mcfg = self.s.get("music")
        music_path, mvol = None, 0.15
        if mcfg:
            mcfg = mcfg if isinstance(mcfg, dict) else {"file": mcfg}
            mvol = float(mcfg.get("volume", 0.15))
            f = mcfg.get("file", "generate")
            if f == "generate" or str(f).startswith("generate:"):
                mood = mcfg.get("mood", str(f).split(":", 1)[1] if ":" in str(f) else "calm")
                music_path = mus.generate_file(tmp / "music.wav", self.total + 1, mood)
            else:
                music_path = self.path(f)
        mix = build_mix(self.total, voices, tmp / "mix.wav", music_path, mvol,
                        float((mcfg or {}).get("duck", 0.35)) if isinstance(mcfg, dict) else 0.35, extra)

        vf = []
        if words:
            ccfg = self.s.get("captions") if isinstance(self.s.get("captions"), dict) else {}
            style = dict(ccfg.get("style", {}))
            style.setdefault("font", self.theme["font"])
            style.setdefault("highlight", self.theme["accent"])
            ass = cap.build_ass(words, self.W, self.H, style)
            (tmp / "captions.ass").write_text(ass, encoding="utf-8")
            fonts_rel = os.path.relpath(FONTS_DIR, tmp).replace("\\", "/")
            vf = ["-vf", f"ass=captions.ass:fontsdir={fonts_rel}"]
            cap.write_srt(words, out_path.with_suffix(".srt"))

        print("5/5 Kadrlar chizilmoqda va kodlanmoqda...")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{self.W}x{self.H}", "-r", str(self.fps), "-i", "-", "-i", str(mix.resolve())] + vf + \
              export_args(self.preview) + ["-r", str(self.fps), "-shortest", str(out_path.resolve())]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, cwd=tmp)
        nframes = int(round(self.total * self.fps))
        readers: dict = {}
        T = self.transition["duration"]
        cover_frame = None
        cover_t = float(self.s.get("cover_time", min(1.2, self.total / 2)))
        try:
            for fi in range(nframes):
                t = fi / self.fps
                active = [sc for sc in self.scenes if sc.start <= t < sc.start + sc.duration]
                if not active:
                    active = [self.scenes[-1]]
                if len(active) >= 2 and T > 0:
                    a, b = active[0], active[1]
                    fa = self._scene_frame(a, t - a.start, readers)
                    fb = self._scene_frame(b, t - b.start, readers)
                    frame = self._transition(fa, fb, (t - b.start) / T)
                else:
                    sc = active[-1]
                    frame = self._scene_frame(sc, t - sc.start, readers)
                # tugagan sahnalarning video o'quvchilarini yopamiz
                for idx in list(readers):
                    if self.scenes[idx].start + self.scenes[idx].duration < t:
                        readers.pop(idx).close()
                frame = self._decor(frame, t)
                if cover_frame is None and t >= cover_t:
                    cover_frame = frame.copy()
                proc.stdin.write(np.ascontiguousarray(frame).tobytes())
                if fi % (self.fps * 5) == 0:
                    print(f"    {t:5.1f}/{self.total:.1f} s", flush=True)
        finally:
            for r in readers.values():
                r.close()
            proc.stdin.close()
            proc.wait()
        if proc.returncode != 0:
            raise RuntimeError("ffmpeg xatosi (yuqoridagi xabarlarni ko'ring)")
        if cover_frame is not None:
            Image.fromarray(cover_frame).save(out_path.with_suffix(".jpg"), quality=92)
        if not keep_temp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        print(f"✔ Tayyor: {out_path}  ({time.time() - t0:.0f} s)")
        return out_path


def render_file(scenario_path: Path, fmt: str | None = None, out: Path | None = None,
                preview: bool = False) -> Path:
    import yaml
    scenario_path = Path(scenario_path).resolve()
    data = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
    proj = Project(data, scenario_path.parent, fmt, preview)
    if out is None:
        name = scenario_path.parent.name if scenario_path.stem == "scenario" else scenario_path.stem
        out = OUTPUT_DIR / f"{name}_{proj.fmt}{'_preview' if preview else ''}.mp4"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return proj.render(Path(out))
