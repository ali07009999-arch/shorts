# Shorts Studio — Instagram va YouTube uchun video yasash

Matn yozasiz → tayyor video chiqadi: ovoz (o'zbekcha), animatsiyali sarlavhalar,
so'zma-so'z yonib chiqadigan subtitrlar, fon musiqasi, o'tishlar, progress chizig'i.

| Format | O'lcham | Qayerga |
|---|---|---|
| `reels` / `shorts` / `tiktok` | 1080×1920 (9:16) | Instagram Reels, YouTube Shorts, TikTok |
| `youtube` | 1920×1080 (16:9) | Oddiy YouTube video |
| `square` | 1080×1080 (1:1) | Instagram post |
| `post` | 1080×1350 (4:5) | Instagram feed |

Eksport: H.264 + AAC 48 kHz, ovoz balandligi −14 LUFS (Instagram/YouTube standarti),
`+faststart`. Har videoga muqova (`.jpg`) va YouTube uchun subtitr fayli (`.srt`) ham yasaladi.

## Qanday ishlaymiz

1. Siz mavzu, matn, rasm yoki videolaringizni berasiz.
2. Claude `projects/<nom>/scenario.yaml` ssenariysini yozadi.
3. Video yasaladi: `python3 make_video.py projects/<nom>/scenario.yaml`
4. Natija `output/` papkasida: `<nom>_reels.mp4`, `.jpg` (muqova), `.srt` (subtitr).

## O'rnatish

```bash
bash setup.sh            # ffmpeg, Python kutubxonalari, o'zbekcha ovoz va Whisper modellari
bash setup.sh --medium   # + aniqroq Whisper (o'zbekcha subtitr uchun tavsiya)
```

## Buyruqlar

```bash
# Ssenariydan video
python3 make_video.py projects/demo/scenario.yaml              # ssenariydagi format
python3 make_video.py projects/demo/scenario.yaml -f youtube   # boshqa format
python3 make_video.py projects/demo/scenario.yaml --all        # reels + youtube
python3 make_video.py projects/demo/scenario.yaml --preview    # tez tekshirish (yarim o'lcham)

# O'zingiz suratga olgan videoga subtitr
python3 add_captions.py video.mp4                              # subtitr qo'shish
python3 add_captions.py video.mp4 -f reels --fit blur          # 16:9 → 9:16, xira fon bilan
python3 add_captions.py video.mp4 --music generate --mood lofi # + fon musiqasi
python3 add_captions.py video.mp4 --srt-only                   # avval .srt → tuzatish →
python3 add_captions.py video.mp4 --srt output/video_subtitr.srt   # → tuzatilgan matn bilan
```

## Ssenariy (scenario.yaml)

To'liq misol: [`projects/demo/scenario.yaml`](projects/demo/scenario.yaml).

```yaml
format: reels
voice:   {engine: mms, lang: uz, speed: 1.05}    # mms | edge | gtts
music:   {file: generate, mood: lofi, volume: 0.22}  # yoki file: assets/music/trek.mp3
captions: {timing: whisper, style: {position: bottom, uppercase: true}}
theme:   {font: Montserrat-ExtraBold, accent: "#FFD400"}
transition: fade          # fade | slide | zoom | flash | none
progress_bar: true
watermark: "@kanal_nomi"

scenes:
  - bg: "gradient:#1a2a6c,#b21f1f"          # rang "#101010", gradient, rasm yoki video fayl
    title: "Asosiy *urg'u* so'z"             # *yulduzcha* ichidagi so'z urg'u rangida
    subtitle: "Kichik matn"
    say: "Diktor aytadigan matn."            # ovozga aylanadi + subtitr bo'ladi
  - bg: assets/images/rasm.jpg
    motion: zoom-in                           # zoom-in | zoom-out | pan-left | pan-right | pan-up | pan-down | none
    title: "Rasm ustida matn"
    say: "..."
  - bg: assets/videos/klip.mp4
    fit: blur                                 # cover (qirqish) | blur (to'liq + xira fon)
    video_volume: 0.3                         # videoning o'z ovozi (0 - o'chiq)
    audio: assets/voice/mening_ovozim.mp3     # TTS o'rniga o'zingiz yozgan ovoz
    duration: 5                               # soniya (standart: ovoz uzunligiga qarab)
```

Sahna parametrlari: `title`, `subtitle`, `say`, `caption` (subtitrda boshqa matn), `audio`,
`bg`, `fit`, `motion`, `motion_strength`, `start` (video boshlanishi), `video_speed`, `video_volume`,
`dim` (fonni qoraytirish 0–1), `text_pos` (top/center/bottom), `text_y`, `anim` (pop/slide/fade/none),
`title_size`, `subtitle_size`, `title_box` (masalan `"#000000AA"`), `font`, `text_color`, `accent`,
`uppercase`, `duration`, `pause`, `speed`, `lang`.

## Ovoz haqida

- **mms** (standart) — oflayn ishlaydi, o'zbek tilini biladi, lekin ovoz biroz "robot"ga o'xshaydi.
  Lotin matn avtomatik kirillga o'giriladi, raqamlar so'zga aylanadi ("5" → "besh", "1-qadam" → "birinchi qadam").
- **edge** — eng tabiiy ovoz (`uz-UZ-SardorNeural` erkak, `uz-UZ-MadinaNeural` ayol). Internet kerak;
  o'z kompyuteringizda ishlaydi. Bu bulut muhitida bloklangan bo'lsa, avtomatik `mms` ga o'tadi.
- **O'z ovozingiz** — eng yaxshi natija: telefoningizga yozib, sahnaga `audio:` bilan bering.
- **gtts** — rus, ingliz, turk tillari uchun (o'zbek yo'q).

## Shriftlar (`assets/fonts`, OFL litsenziya)

O'zbek lotin (oʻ, gʻ) va kirill (ў, қ, ғ, ҳ) harflarini to'liq qo'llaydi:
`Montserrat-SemiBold/Bold/ExtraBold/Black`, `Oswald-Bold`, `NotoSans-Regular/Bold`.
`Anton` — faqat lotin (kirill yo'q).

## Musiqa

`music: {file: generate, mood: calm|lofi|upbeat|epic}` — oddiy fon musiqasini o'zi sintez qiladi
(mualliflik huquqi muammosiz). Yaxshiroq natija uchun litsenziyali treklarni `assets/music/`
ga qo'ying (masalan, YouTube Audio Library'dan). Mashhur qo'shiqlarni ishlatmang — video bloklanishi mumkin.

## Platforma maslahatlari

- **Reels/Shorts**: 9:16, 15–60 soniya eng yaxshi ishlaydi (3 daqiqagacha mumkin). Birinchi 1–2 soniyada
  qiziqtiruvchi "hook" bo'lsin. Pastki ~20% va o'ng chetni Instagram tugmalari yopadi — subtitrlar shuning uchun biroz yuqorida.
- **YouTube**: 16:9, `.srt` faylini YouTube Studio → Subtitles ga yuklang (qidiruvda yordam beradi).
- Muqova uchun yasalgan `.jpg` dan foydalaning yoki `cover_time: 2.5` bilan boshqa kadrni tanlang.

## Tuzilma

```
make_video.py        ssenariy → video
add_captions.py      tayyor videoga subtitr / format o'zgartirish
studio/              dvigatel: tts, uzbek (translit), captions, graphics, audio, music, video
assets/fonts|music|images
projects/<nom>/      ssenariy va shu videoga oid fayllar
output/              tayyor videolar (git'ga kirmaydi)
```
