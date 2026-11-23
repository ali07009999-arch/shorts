#!/usr/bin/env bash
# Video studiyani o'rnatish: ffmpeg, Python kutubxonalari va modellar.
# Ishlatish:  bash setup.sh            (asosiy)
#             bash setup.sh --medium   (+ aniqroq Whisper medium modeli, ~1.5 GB)
set -e
cd "$(dirname "$0")"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "== ffmpeg o'rnatilmoqda"
  if command -v apt-get >/dev/null 2>&1; then sudo apt-get update -y && sudo apt-get install -y ffmpeg
  elif command -v brew >/dev/null 2>&1; then brew install ffmpeg
  else echo "ffmpeg ni qo'lda o'rnating: https://ffmpeg.org/download.html"; exit 1; fi
fi

echo "== Python kutubxonalari"
python3 -m pip install -q torch --index-url https://download.pytorch.org/whl/cpu
python3 -m pip install -q -r requirements.txt

echo "== Modellar yuklanmoqda (bir marta)"
python3 - "$@" <<'PY'
import sys, os
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
from transformers import AutoTokenizer, VitsModel
m = "facebook/mms-tts-uzb-script_cyrillic"
AutoTokenizer.from_pretrained(m); VitsModel.from_pretrained(m)
print("  ok: o'zbekcha ovoz (MMS)")
from faster_whisper import WhisperModel
for size in ["small"] + (["medium"] if "--medium" in sys.argv else []):
    WhisperModel(size, device="cpu", compute_type="int8"); print("  ok: whisper", size)
PY
echo "== Tayyor! Sinov:  python3 make_video.py projects/demo/scenario.yaml --preview"
