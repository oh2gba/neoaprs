"""Tests for the icon: one drawing (ui/public/icons/icon.svg) and the script that renders every
raster file (scripts/make-icon.py) in the site's colours. PNG and .ico frames are read with the
standard library; the tests check the pixels at the ground and an outer wave."""

import importlib.util
import re
import struct
import zlib
from pathlib import Path
from types import ModuleType

import pytest

from tests.conftest import ROOT

PETROL = (10, 42, 61)
MINT = (166, 215, 212)
TILE, FULL_BLEED = "tile", "full bleed"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
FAVICON_SIZES = (16, 32, 48)
# Every raster icon: its frames' sizes, the PNG colour type (6 RGBA, 2 RGB) and the form: the
# rounded tile with transparent corners, or full bleed (the system masks it), the mark smaller.
FILES = {
    "neoaprs/desktop/icon.png": ((64,), 6, TILE),
    "neoaprs/desktop/icon.ico": (ICO_SIZES, 6, TILE),
    "site/favicon.ico": (FAVICON_SIZES, 6, TILE),
    "site/apple-touch-icon.png": ((180,), 6, TILE),
    "ui/public/favicon.ico": (FAVICON_SIZES, 6, TILE),
    "ui/public/icons/icon-192.png": ((192,), 6, TILE),
    "ui/public/icons/icon-512.png": ((512,), 6, TILE),
    "ui/public/icons/icon-maskable-512.png": ((512,), 2, FULL_BLEED),
    "ui/public/icons/apple-touch-icon.png": ((180,), 2, FULL_BLEED),
}
PAGE_COPIES = (
    "favicon.ico",
    "icons/icon.svg",
    "icons/icon-192.png",
    "icons/icon-512.png",
    "icons/icon-maskable-512.png",
    "icons/apple-touch-icon.png",
)
# The navy the icon had before it took the site's colours, and the card of the site's link preview
# that went with it: in none of the files where the icon's colours are written.
OLD = ("18345c", "60a5eb", "142c52", "24, 52, 92", "96, 165, 235", "20, 44, 82", "190, 214, 245")
WHERE_THE_COLOURS_ARE = (
    "ui/public/icons/icon.svg",
    "site/favicon.svg",
    "neoaprs/page/icons/icon.svg",
    "neoaprs/desktop/loading.py",
    "scripts/make-icon.py",
    "scripts/screenshots.py",
    "docs/palette.md",
    "site/style.css",
    "site/index.html",
    "ui/index.html",
    "ui/public/manifest.webmanifest",
    "ui/src/styles/tokens.css",
    "packaging/macos/make_icns.py",
)


def make_icon() -> ModuleType:
    spec = importlib.util.spec_from_file_location("make_icon_for_the_test", ROOT / "scripts" / "make-icon.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---- reading a PNG and an .ico with the standard library


def png(data: bytes) -> tuple[int, int, list[list[tuple[int, ...]]]]:
    """A PNG of 8 bits a channel, RGB or RGBA, not interlaced: its colour type, its side and its
    rows of pixels."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    at, idat, header = 8, b"", b""
    while at < len(data):
        length, kind = struct.unpack(">I4s", data[at : at + 8])
        body = data[at + 8 : at + 8 + length]
        header = body if kind == b"IHDR" else header
        idat += body if kind == b"IDAT" else b""
        at += 12 + length
    width, height, depth, colour, _, _, interlace = struct.unpack(">IIBBBBB", header)
    assert depth == 8 and colour in (2, 6) and interlace == 0, (depth, colour, interlace)
    channels = 4 if colour == 6 else 3
    raw, stride, rows, previous = zlib.decompress(idat), width * channels, [], bytearray(width * channels)
    for y in range(height):
        kind, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1 : (y + 1) * (stride + 1)])
        for i in range(stride):
            left = line[i - channels] if i >= channels else 0
            up, corner = previous[i], previous[i - channels] if i >= channels else 0
            if kind == 1:
                line[i] = (line[i] + left) & 255
            elif kind == 2:
                line[i] = (line[i] + up) & 255
            elif kind == 3:
                line[i] = (line[i] + (left + up) // 2) & 255
            elif kind == 4:
                p = left + up - corner
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - corner)
                line[i] = (line[i] + (left if pa <= pb and pa <= pc else up if pb <= pc else corner)) & 255
        rows.append([tuple(line[x * channels : (x + 1) * channels]) for x in range(width)])
        previous = line
    assert width == height, "an icon is square"
    return colour, width, rows


def frames(path: Path) -> list[tuple[int, int, list[list[tuple[int, ...]]]]]:
    """The images of a file: the one of a PNG, or every frame of an .ico (each must be a PNG)."""
    data = path.read_bytes()
    if path.suffix != ".ico":
        return [png(data)]
    _, kind, count = struct.unpack("<HHH", data[:6])
    assert kind == 1, "an icon file"
    out = []
    for i in range(count):
        size, offset = struct.unpack("<II", data[6 + 16 * i + 8 : 6 + 16 * i + 16])
        assert data[offset : offset + 8] == b"\x89PNG\r\n\x1a\n", (
            f"{path.name}: frame {i} is a bitmap, which this test cannot read"
        )
        out.append(png(data[offset : offset + size]))
    return out


def mint_over_petrol(pixel: tuple[int, ...]) -> float:
    """How much of the mint a pixel is when it is the mint laid over the petrol (1 the mint, 0 the
    petrol); -1 when it is not such a blend (another colour)."""
    parts = [(have - p) / (m - p) for have, p, m in zip(pixel[:3], PETROL, MINT)]
    return sum(parts) / 3 if max(parts) - min(parts) < 0.06 else -1.0


# ---- the raster files


@pytest.mark.parametrize("name", FILES)
def test_every_raster_icon_is_the_petrol_tile_with_the_mint_waves_at_its_sizes_and_in_its_form(name: str) -> None:
    sizes, colour_type, form = FILES[name]
    found = frames(ROOT / name)
    assert sorted(side for _, side, _ in found) == sorted(sizes), f"{name}: the sizes"
    for colour, side, rows in found:
        assert colour == colour_type, f"{name} {side} px: PNG colour type {colour}, the file's form is {colour_type}"
        unit, left = (side * 0.86, side * 0.07) if form == FULL_BLEED else (float(side), 0.0)
        top = left + (side * 0.014 if form == FULL_BLEED else 0.0)
        ground = rows[int(top + 0.1 * unit)][side // 2]  # above the pin, between the waves' ends
        # the right outer wave at the level of the pin's head
        wave = rows[int(top + 0.42 * unit)][int(left + 0.9 * unit)]
        corner = rows[0][0]
        assert all(abs(a - b) <= 2 for a, b in zip(ground[:3], PETROL)), (
            f"{name} {side} px: the ground is {ground[:3]}, not the petrol {PETROL}"
        )
        assert mint_over_petrol(wave) >= 0.5, (
            f"{name} {side} px: the outer wave is {wave[:3]}, not the mint {MINT} (over the petrol)"
        )
        if side >= 128:
            assert ground[:3] == PETROL and wave[:3] == MINT, f"{name} {side} px: at this size the colours are exact"
        if form == TILE:
            assert corner[3] <= 2, f"{name} {side} px: the tile's corner is not transparent ({corner})"
        else:
            assert corner[:3] == PETROL, f"{name} {side} px: full bleed, the corner is the petrol"


@pytest.mark.parametrize("name", FILES)
def test_every_raster_icon_strokes_its_waves_on_their_radius_as_the_svg_does(name: str) -> None:
    """The SVG centres a wave's stroke on its radius (0.40 of the side for the outer one, the stroke
    0.05, so from 0.375 to 0.425), the same on the page and on the desktop. At the head's level,
    0.36 out is the petrol between the waves and 0.415 out is the mint; from 128 px, where a pixel
    is narrow enough, 0.385 out is the mint too. The 16- and 24-px frames are too coarse to tell."""
    _, _, form = FILES[name]
    for _, side, rows in frames(ROOT / name):
        if side < 32:
            continue
        unit, left = (side * 0.86, side * 0.07) if form == FULL_BLEED else (float(side), 0.0)
        top = left + (side * 0.014 if form == FULL_BLEED else 0.0)
        y = int(top + 0.42 * unit)
        gap, inside, outside = (rows[y][int(left + at * unit)] for at in (0.86, 0.885, 0.915))
        assert mint_over_petrol(gap) < 0.3 and mint_over_petrol(outside) >= 0.6, (
            f"{name} {side} px: the outer wave is not stroked on its radius ({gap[:3]} before it, {outside[:3]} at its outer half)"
        )
        if side >= 128:
            assert mint_over_petrol(inside) >= 0.9 and mint_over_petrol(outside) >= 0.9, (
                f"{name} {side} px: the outer wave is not stroked on its radius ({inside[:3]}, {outside[:3]})"
            )


def test_the_page_carries_the_icons_of_ui_public_as_they_are() -> None:
    """scripts/build-page copies ui/public/ into neoaprs/page/: the icons there are the same bytes
    (tests/test_page_build.py compares the whole build where node is)."""
    assert [
        name
        for name in PAGE_COPIES
        if (ROOT / "neoaprs/page" / name).read_bytes() != (ROOT / "ui/public" / name).read_bytes()
    ] == []


def test_the_favicon_of_the_site_and_of_the_page_is_the_same_file() -> None:
    assert (ROOT / "site/favicon.ico").read_bytes() == (ROOT / "ui/public/favicon.ico").read_bytes()


# ---- the drawing


def test_the_svg_files_are_the_drawing_the_script_draws() -> None:
    assert make_icon().svg_problems() == []


def test_the_script_finds_an_svg_that_is_not_its_drawing(tmp_path: Path) -> None:
    module = make_icon()
    text = (ROOT / "ui/public/icons/icon.svg").read_text(encoding="utf-8")
    for name in module.SVGS:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text, encoding="utf-8")
    assert module.svg_problems(tmp_path) == []
    (tmp_path / module.SVGS[1]).write_text(text.replace("#a6d7d4", "#bbdaed"), encoding="utf-8")
    assert [p for p in module.svg_problems(tmp_path) if "not the same text" in p or "the colours are" in p] and len(
        module.svg_problems(tmp_path)
    ) == 2
    (tmp_path / module.SVGS[1]).write_text(text.replace('r="10.88"', 'r="11.5"'), encoding="utf-8")
    assert any("numbers that are not the drawing's" in p for p in module.svg_problems(tmp_path))
    (tmp_path / module.SVGS[1]).write_text(text.replace("</g>", '<circle cx="1" cy="1" r="1"/></g>'), encoding="utf-8")
    assert any("not the shapes of the drawing" in p for p in module.svg_problems(tmp_path))


def test_the_old_navy_of_the_icon_is_in_none_of_the_files_where_its_colours_are_written() -> None:
    found = [
        (name, old)
        for name in WHERE_THE_COLOURS_ARE
        for old in OLD
        if re.search(re.escape(old), (ROOT / name).read_text(encoding="utf-8"), re.I)
    ]
    assert found == []


def test_the_script_names_its_colours_and_they_are_the_palettes() -> None:
    module = make_icon()
    assert module.PETROL[:3] == PETROL and module.MINT[:3] == MINT
    palette = (ROOT / "docs/palette.md").read_text(encoding="utf-8")
    assert "petrol `#0a2a3d`" in palette and "mint `#a6d7d4`" in palette
