#!/usr/bin/env python3
"""Ssenariydan video yasash.

Misollar:
  python make_video.py projects/demo/scenario.yaml                 # ssenariydagi format
  python make_video.py projects/demo/scenario.yaml --format youtube
  python make_video.py projects/demo/scenario.yaml --all           # reels + youtube
  python make_video.py projects/demo/scenario.yaml --preview       # tez, past sifatli tekshiruv
"""
import argparse
import sys
from pathlib import Path

from studio.video import render_file


def main():
    ap = argparse.ArgumentParser(description="Ssenariy (YAML) -> MP4 video")
    ap.add_argument("scenario", type=Path)
    ap.add_argument("--format", "-f", choices=["reels", "shorts", "tiktok", "youtube", "square", "post"])
    ap.add_argument("--all", action="store_true", help="vertikal (reels) va gorizontal (youtube) ikkalasini")
    ap.add_argument("--out", "-o", type=Path)
    ap.add_argument("--preview", "-p", action="store_true", help="yarim o'lcham, tez kodlash")
    a = ap.parse_args()
    if not a.scenario.exists():
        sys.exit(f"Fayl topilmadi: {a.scenario}")
    formats = ["reels", "youtube"] if a.all else [a.format]
    for f in formats:
        render_file(a.scenario, f, None if a.all else a.out, a.preview)


if __name__ == "__main__":
    main()
