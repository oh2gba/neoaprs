#!/usr/bin/env python3
"""Draw every raster icon of NeoAPRS from one drawing: a map pin with radio waves on a petrol tile.

One run writes neoaprs/desktop/icon.png and icon.ico, site/favicon.ico, ui/public/favicon.ico,
site/apple-touch-icon.png and ui/public/icons/*.png (the maskable and Apple icons are full bleed).
The files are committed. A run first checks that icon.svg and favicon.svg match the drawing.
    .venv/bin/python scripts/make-icon.py              (needs Pillow)
    .venv/bin/python scripts/make-icon.py --out DIR    the same files under DIR
"""

import argparse
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# #0a2a3d: petrol, the tile and the pin's hole.
PETROL = (10, 42, 61, 255)
# #a6d7d4: mint, the outer waves.
MINT = (166, 215, 212, 255)
WHITE = (255, 255, 255, 255)  # pin and inner waves

# The drawing, in parts of the tile's side (the SVG's 64 grid).
TILE_CORNER = 0.2
PIN_X, PIN_Y, PIN_R = 0.5, 0.42, 0.17  # head centre and radius
# Where the head meets the point, in parts of PIN_R.
PIN_SHOULDER = (0.92, 0.40)
PIN_TIP = 0.80  # from the top
HOLE = 0.42  # in parts of PIN_R
# Each wave's radius (middle of its stroke) and colour.
WAVES = ((0.29, WHITE), (0.40, MINT))
WAVE_WIDTH = 0.05
WAVE_SPAN = 40
# Full bleed: the mark at 86 % of the side, 1.4 % below the middle (the maskable safe circle).
FULL_BLEED_MARK, FULL_BLEED_DROP = 0.86, 0.014
SCALE = 4  # drawn 4x then reduced, for smooth edges
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
FAVICON_SIZES = (16, 32, 48)
SVGS = ("ui/public/icons/icon.svg", "site/favicon.svg")


def hex_of(colour: tuple[int, int, int, int]) -> str:
    return "#fff" if colour == WHITE else "#{:02x}{:02x}{:02x}".format(*colour[:3])


def svg() -> str:
    """Return the drawing as the SVG files write it, to two decimals."""

    def n(x: float) -> str:
        return f"{x * 64:.2f}".rstrip("0").rstrip(".")

    cx, cy, r = PIN_X, PIN_Y, PIN_R
    sx, sy = PIN_SHOULDER
    c, s = math.cos(math.radians(WAVE_SPAN)), math.sin(math.radians(WAVE_SPAN))
    paths = "".join(
        f'<path d="M{n(cx + w * c)} {n(cy - w * s)}A{n(w)} {n(w)} 0 0 1 {n(cx + w * c)} {n(cy + w * s)}M{n(cx - w * c)} {n(cy + w * s)}A{n(w)} {n(w)} 0 0 1 {n(cx - w * c)} {n(cy - w * s)}" stroke="{hex_of(colour)}"/>'
        for w, colour in WAVES
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64"><rect width="64" height="64" rx="{n(TILE_CORNER)}" fill="{hex_of(PETROL)}"/>'
        f'<polygon points="{n(cx - r * sx)},{n(cy + r * sy)} {n(cx + r * sx)},{n(cy + r * sy)} {n(cx)},{n(PIN_TIP)}" fill="{hex_of(WHITE)}"/><circle cx="{n(cx)}" cy="{n(cy)}" r="{n(r)}" fill="{hex_of(WHITE)}"/>'
        f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(r * HOLE)}" fill="{hex_of(PETROL)}"/><g fill="none" stroke-width="{n(WAVE_WIDTH)}">{paths}</g></svg>'
    )


def parts(text: str) -> tuple[list[str], list[float], str]:
    """Split an SVG text into colours, numbers and the rest."""
    colours = re.findall(r"#[0-9a-fA-F]{3,6}\b", text)
    rest = re.sub(r"#[0-9a-fA-F]{3,6}\b", "C", text)
    numbers = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", rest)]
    return colours, numbers, re.sub(r"-?\d+(?:\.\d+)?", "N", rest)


def svg_problems(root: Path = ROOT) -> list[str]:
    """Return what keeps the SVG files from matching svg() (numbers may differ by 0.02)."""
    want_colours, want_numbers, want_rest = parts(svg())
    problems = []
    texts = {name: (root / name).read_text(encoding="utf-8").strip() for name in SVGS}
    if len(set(texts.values())) != 1:
        problems.append(f"{' and '.join(SVGS)} are not the same text")
    for name, text in texts.items():
        colours, numbers, rest = parts(text)
        if rest != want_rest or len(numbers) != len(want_numbers):
            problems.append(f"{name}: not the shapes of the drawing (tags, attributes or number of points)")
        elif colours != want_colours:
            problems.append(f"{name}: the colours are {colours}, the drawing's {want_colours}")
        else:
            off = [(have, want) for have, want in zip(numbers, want_numbers) if abs(have - want) > 0.02]
            if off:
                problems.append(f"{name}: numbers that are not the drawing's (have, want): {off}")
    return problems


# Pillow is imported where used so --help and the check need nothing.
def draw(size: int, *, full_bleed: bool = False):
    """Draw the icon at `size` px: a rounded tile (RGBA) or full bleed (RGB)."""
    from PIL import Image, ImageDraw

    big = size * SCALE
    image = Image.new("RGBA", (big, big), PETROL if full_bleed else (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    if full_bleed:
        unit = big * FULL_BLEED_MARK
        left, top = (big - unit) / 2, (big - unit) / 2 + big * FULL_BLEED_DROP
    else:
        unit, left, top = big, 0.0, 0.0
        d.rounded_rectangle((0, 0, big - 1, big - 1), radius=int(big * TILE_CORNER), fill=PETROL)
    cx, cy, r = left + unit * PIN_X, top + unit * PIN_Y, unit * PIN_R
    sx, sy = PIN_SHOULDER
    d.polygon([(cx - r * sx, cy + r * sy), (cx + r * sx, cy + r * sy), (cx, top + unit * PIN_TIP)], fill=WHITE)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=WHITE)
    d.ellipse((cx - r * HOLE, cy - r * HOLE, cx + r * HOLE, cy + r * HOLE), fill=PETROL)
    width = int(unit * WAVE_WIDTH)
    for radius, colour in WAVES:
        # Pillow strokes an arc inward, so the box is half a stroke out.
        w = radius * unit + width / 2
        box = (cx - w, cy - w, cx + w, cy + w)
        d.arc(box, start=-WAVE_SPAN, end=WAVE_SPAN, fill=colour, width=width)
        d.arc(box, start=180 - WAVE_SPAN, end=180 + WAVE_SPAN, fill=colour, width=width)
    image = image.resize((size, size), Image.LANCZOS)
    return image.convert("RGB") if full_bleed else image


def write(root: Path) -> list[Path]:
    """Every raster icon under `root`, at the paths of the repository."""
    favicon = draw(256)
    files = {
        "neoaprs/desktop/icon.png": lambda p: draw(64).save(p),
        "neoaprs/desktop/icon.ico": lambda p: favicon.save(p, sizes=[(s, s) for s in ICO_SIZES]),
        "site/favicon.ico": lambda p: favicon.save(p, sizes=[(s, s) for s in FAVICON_SIZES]),
        "site/apple-touch-icon.png": lambda p: draw(180).save(p),
        "ui/public/favicon.ico": lambda p: favicon.save(p, sizes=[(s, s) for s in FAVICON_SIZES]),
        "ui/public/icons/icon-192.png": lambda p: draw(192).save(p),
        "ui/public/icons/icon-512.png": lambda p: draw(512).save(p),
        "ui/public/icons/icon-maskable-512.png": lambda p: draw(512, full_bleed=True).save(p),
        "ui/public/icons/apple-touch-icon.png": lambda p: draw(180, full_bleed=True).save(p),
    }
    written = []
    for name, save in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        save(path)
        written.append(path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--out",
        default=str(ROOT),
        help="the folder the files are written under, at the repository's paths; default the repository, %(default)s",
    )
    args = parser.parse_args()
    problems = svg_problems()
    if problems:
        print(
            "make-icon: the SVG files are not the drawing of this script; nothing is written:\n  "
            + "\n  ".join(problems)
        )
        return 1
    for path in write(Path(args.out)):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
