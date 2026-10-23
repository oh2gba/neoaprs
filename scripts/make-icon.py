#!/usr/bin/env python3
"""Draws the icon of the desktop app: neoaprs/desktop/icon.png (64x64, the tray) and icon.ico (16 to 256 px, the Windows executable, the shortcuts and the tray there). A map pin (the station) with two arcs of
radio waves on each side, on a dark rounded square. The two files are committed; this script is how they were made and how to change them. It needs Pillow, which the app's extra has on Windows only:
    uv run --with Pillow scripts/make-icon.py [--out DIR]
"""
import argparse
from pathlib import Path

NAVY = (24, 52, 92, 255)
BLUE = (96, 165, 235, 255)
WHITE = (255, 255, 255, 255)
SIZES = (16, 24, 32, 48, 64, 128, 256)
SCALE = 4                                    # drawn four times as large, then reduced: smooth edges


def draw(size: int):                         # -> PIL.Image.Image (Pillow is imported where it is used, so that --help needs nothing)
    from PIL import Image, ImageDraw
    big = size * SCALE
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    d.rounded_rectangle((0, 0, big - 1, big - 1), radius=big // 5, fill=NAVY)
    cx, cy, r = big * 0.5, big * 0.42, big * 0.17            # a map pin: the station, with the radio waves going out from it on both sides
    d.polygon([(cx - r * 0.92, cy + r * 0.40), (cx + r * 0.92, cy + r * 0.40), (cx, big * 0.80)], fill=WHITE)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=WHITE)
    d.ellipse((cx - r * 0.42, cy - r * 0.42, cx + r * 0.42, cy + r * 0.42), fill=NAVY)
    for radius in (0.29, 0.40):
        w = radius * big
        box = (cx - w, cy - w, cx + w, cy + w)
        d.arc(box, start=-40, end=40, fill=BLUE if radius > 0.3 else WHITE, width=int(big * 0.05))
        d.arc(box, start=140, end=220, fill=BLUE if radius > 0.3 else WHITE, width=int(big * 0.05))
    return image.resize((size, size), Image.LANCZOS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "neoaprs" / "desktop"), help="the folder to write icon.png and icon.ico into; default %(default)s")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    draw(64).save(out / "icon.png")
    draw(256).save(out / "icon.ico", sizes=[(s, s) for s in SIZES])
    print(f"wrote {out / 'icon.png'} and {out / 'icon.ico'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
