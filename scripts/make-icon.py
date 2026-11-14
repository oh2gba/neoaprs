#!/usr/bin/env python3
"""Draws every raster icon of NeoAPRS from the one drawing: a map pin (the station) with two arcs of radio waves on each side, on a rounded petrol tile; the pin and the inner waves white, the outer waves mint.
One run writes them all, each at its size and in its form:
    neoaprs/desktop/icon.png                 64 px, the tray (the desktop app's window and tray on Linux)
    neoaprs/desktop/icon.ico                 16 to 256 px, the Windows executable, the shortcuts and the tray there; packaging/macos/make_icns.py makes the macOS icon of it
    site/favicon.ico, ui/public/favicon.ico  16, 32 and 48 px, the project page's and the program's page's (the same file)
    site/apple-touch-icon.png                180 px, the rounded tile
    ui/public/icons/icon-192.png, icon-512.png                       the installed page's icons, the rounded tile
    ui/public/icons/icon-maskable-512.png, apple-touch-icon.png      full bleed, no corners (the system rounds or masks them): the mark smaller, the tips of its outer waves at the edge of the maskable safe circle
The files are committed; this is how they are made and how to change them. scripts/build-page carries the page's (ui/public/) into neoaprs/page/.
The drawing is the one of ui/public/icons/icon.svg, which is written by hand and is the same text as site/favicon.svg (and neoaprs/desktop/loading.py MARK): a run first checks that the two SVG files are
that drawing, in these colours and to 0.02 of their 64 grid, and writes nothing when they are not (tests/test_icon.py holds the same). It needs Pillow (the app's extra has it on Windows only):
    .venv/bin/python scripts/make-icon.py              (or: uv run --with Pillow scripts/make-icon.py)
    .venv/bin/python scripts/make-icon.py --out DIR    the same files under DIR, at the same paths (a look, a test)
"""
import argparse
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PETROL = (10, 42, 61, 255)       # #0a2a3d: petrol, the tile and the pin's hole (ui/src/styles/tokens.css: --text of the light theme, --panel of the dark; the site's --ink)
MINT = (166, 215, 212, 255)      # #a6d7d4: mint, the outer waves (tokens.css: --hf-soft-bg and --ok-soft-fg of the dark theme; the site's --hf-soft)
WHITE = (255, 255, 255, 255)     # the pin and the inner waves

# The drawing, in parts of the tile's side (the SVG's 64 grid times 1/64).
TILE_CORNER = 0.2                # the radius of the tile's corners
PIN_X, PIN_Y, PIN_R = 0.5, 0.42, 0.17    # the pin's head: its centre and radius
PIN_SHOULDER = (0.92, 0.40)      # where the head meets the point, in parts of PIN_R: across and down from the centre
PIN_TIP = 0.80                   # the point, from the top
HOLE = 0.42                      # the hole in the head, in parts of PIN_R
WAVES = ((0.29, WHITE), (0.40, MINT))    # each wave's radius (the middle of its stroke) from the head's centre, and its colour
WAVE_WIDTH = 0.05                # the stroke
WAVE_SPAN = 40                   # degrees above and below the level, on the right and the left
FULL_BLEED_MARK, FULL_BLEED_DROP = 0.86, 0.014          # full bleed: the mark at 86 % of the side, 1.4 % of it below the middle (measured from the files of 23 October 2026); the outer waves' tips reach 2 px past the safe circle of 80 % at 512, as they always did
SCALE = 4                        # drawn four times as large, then reduced: smooth edges
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
FAVICON_SIZES = (16, 32, 48)
SVGS = ("ui/public/icons/icon.svg", "site/favicon.svg")


def hex_of(colour: tuple[int, int, int, int]) -> str:
    return "#fff" if colour == WHITE else "#{:02x}{:02x}{:02x}".format(*colour[:3])


def svg() -> str:
    """The drawing as the SVG files write it, from the numbers above (to two decimals; the files are written by hand and may round otherwise)."""
    def n(x: float) -> str:
        return f"{x * 64:.2f}".rstrip("0").rstrip(".")
    cx, cy, r = PIN_X, PIN_Y, PIN_R
    sx, sy = PIN_SHOULDER
    c, s = math.cos(math.radians(WAVE_SPAN)), math.sin(math.radians(WAVE_SPAN))
    paths = "".join(f'<path d="M{n(cx + w * c)} {n(cy - w * s)}A{n(w)} {n(w)} 0 0 1 {n(cx + w * c)} {n(cy + w * s)}M{n(cx - w * c)} {n(cy + w * s)}A{n(w)} {n(w)} 0 0 1 {n(cx - w * c)} {n(cy - w * s)}" stroke="{hex_of(colour)}"/>' for w, colour in WAVES)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64"><rect width="64" height="64" rx="{n(TILE_CORNER)}" fill="{hex_of(PETROL)}"/>'
            f'<polygon points="{n(cx - r * sx)},{n(cy + r * sy)} {n(cx + r * sx)},{n(cy + r * sy)} {n(cx)},{n(PIN_TIP)}" fill="{hex_of(WHITE)}"/><circle cx="{n(cx)}" cy="{n(cy)}" r="{n(r)}" fill="{hex_of(WHITE)}"/>'
            f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(r * HOLE)}" fill="{hex_of(PETROL)}"/><g fill="none" stroke-width="{n(WAVE_WIDTH)}">{paths}</g></svg>')


def parts(text: str) -> tuple[list[str], list[float], str]:
    """An SVG text as its colours, its numbers and what is left (the tags and the words) with each colour and number replaced by a mark."""
    colours = re.findall(r"#[0-9a-fA-F]{3,6}\b", text)
    rest = re.sub(r"#[0-9a-fA-F]{3,6}\b", "C", text)
    numbers = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", rest)]
    return colours, numbers, re.sub(r"-?\d+(?:\.\d+)?", "N", rest)


def svg_problems(root: Path = ROOT) -> list[str]:
    """What keeps the SVG files from being this drawing: [] when each is the same text and that text is svg() but for a number rounded otherwise (to 0.02 of the 64 grid)."""
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


def draw(size: int, *, full_bleed: bool = False):         # -> PIL.Image.Image (Pillow is imported where it is used, so that --help and the check need nothing)
    """The icon at `size` px: the rounded tile with transparent corners (RGBA), or full bleed (RGB): the square petrol, the mark smaller and a little lower."""
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
        w = radius * unit + width / 2               # Pillow strokes an arc inward from its box: the box is half a stroke out, so that the stroke's middle is the radius, as in the SVG
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
    parser.add_argument("--out", default=str(ROOT), help="the folder the files are written under, at the repository's paths; default the repository, %(default)s")
    args = parser.parse_args()
    problems = svg_problems()
    if problems:
        print("make-icon: the SVG files are not the drawing of this script; nothing is written:\n  " + "\n  ".join(problems))
        return 1
    for path in write(Path(args.out)):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
