"""Small PMTiles archives (version 3) made up for the tests of the cut (neoaprs/pmtilescut.py), and a reader of their tiles, written apart from the program's code so that the two check each other.

    tiles = {(z, x, y): b"content", ...}
    data = archive(tiles, leaf=8)                          # the root and leaves of 8 entries; leaf=None: the root alone; deep=True: leaves of leaves
    data = archive(tiles, runs=False, shared=False)        # every tile an entry of its own and a content of its own
    tile_at(data, z, x, y)                                 # the stored bytes of a tile, None for one the archive does not have
    every_tile(data)                                       # {tile id: bytes} of all the tiles it addresses
    archive_of(root, leaves, data, metadata, **fields)     # the parts as they are, behind a header with these fields: for archives that lie
    planet(max_zoom)                                       # every tile of the world down to the zoom, 5461 of them to zoom 6: the source of the map tests, each tile a content of its own
    tiles_of(box, min_zoom, max_zoom)                      # the keys of the tiles that touch the box (west, south, east, north), counted by the tile numbers of the map and not by the program's cover

The tile ids here are the specification's: the tiles of the zooms below, then the Hilbert curve (the table of its four turns)."""
import functools
import gzip
import math
import struct
from collections.abc import Iterable
from typing import Any

FIELDS = ("root_offset", "root_length", "metadata_offset", "metadata_length", "leaf_offset", "leaf_length", "data_offset", "data_length", "addressed", "entries", "contents")
Entry = tuple[int, int, int, int]               # tile id, run length, length, offset


def tile_id(z: int, x: int, y: int) -> int:
    """By quadrants from the top: each turn of the curve is a quarter and a rotation of the one above."""
    index = 0
    for level in range(z - 1, -1, -1):
        half = 1 << level
        right, down = bool(x & half), bool(y & half)
        quarter = {(False, False): 0, (False, True): 1, (True, True): 2, (True, False): 3}[(right, down)]
        index = index * 4 + quarter
        x, y = x & (half - 1), y & (half - 1)
        if quarter == 0:
            x, y = y, x
        elif quarter == 3:
            x, y = half - 1 - y, half - 1 - x
    return ((1 << 2 * z) - 1) // 3 + index


def _number(value: int) -> bytes:
    out = b""
    while True:
        low, value = value & 127, value >> 7
        out += bytes([low | (128 if value else 0)])
        if not value:
            return out


def directory(entries: Iterable[Entry], packed: bool = True, follow: bool = True) -> bytes:
    """A directory of the entries as they are, in order or not; `follow` writes 0 for an offset that follows the entry before it."""
    rows = list(entries)
    body = _number(len(rows))
    previous = 0
    for row in rows:
        body += _number(row[0] - previous)
        previous = row[0]
    body += b"".join(_number(row[1]) for row in rows) + b"".join(_number(row[2]) for row in rows)
    for i, row in enumerate(rows):
        body += _number(0 if follow and i and row[3] == rows[i - 1][3] + rows[i - 1][2] else row[3] + 1)
    return gzip.compress(body, mtime=0) if packed else body


def header(**fields: int) -> bytes:
    """A header of version 3 with these fields (the numbers by their names in FIELDS, and clustered, internal, compression, kind, min_zoom, max_zoom, bounds, center_zoom, center)."""
    numbers = [fields.get(name, 0) for name in FIELDS]
    west, south, east, north = fields.get("bounds", (-1800000000, -850511287, 1800000000, 850511287))  # type: ignore[misc]
    lon, lat = fields.get("center", (0, 0))  # type: ignore[misc]
    tail = struct.pack("<BBBBBB", fields.get("clustered", 1), fields.get("internal", 2), fields.get("compression", 2), fields.get("kind", 1), fields.get("min_zoom", 0), fields.get("max_zoom", 0))
    return b"PMTiles" + bytes([fields.get("version", 3)]) + struct.pack("<11Q", *numbers) + tail + struct.pack("<4i", west, south, east, north) + struct.pack("<Bii", fields.get("center_zoom", 0), lon, lat)


def archive_of(root: bytes, leaves: bytes, data: bytes, metadata: bytes = b"{}", **fields: int) -> bytes:
    """The parts in the order go-pmtiles writes them behind a header that says where they are; a field given here wins over what the parts say."""
    places = {"root_offset": 127, "root_length": len(root), "metadata_offset": 127 + len(root), "metadata_length": len(metadata), "leaf_offset": 127 + len(root) + len(metadata),
              "leaf_length": len(leaves), "data_offset": 127 + len(root) + len(metadata) + len(leaves), "data_length": len(data)}
    return header(**(places | fields)) + root + metadata + leaves + data


def archive(tiles: dict[tuple[int, int, int], bytes], leaf: int | None = None, deep: bool = False, runs: bool = True, shared: bool = True, packed: bool = True,
            metadata: bytes = b'{"name":"made up"}', **fields: int) -> bytes:
    """A clustered archive of the tiles: a content that several tiles have is stored once (`shared`), a row of tiles with one content is one entry (`runs`); the root alone, or leaves of `leaf` entries."""
    entries: list[Entry] = []
    data = b""
    stored: dict[bytes, int] = {}
    for tid, content in sorted((tile_id(*key), content) for key, content in tiles.items()):
        if runs and entries and entries[-1][0] + entries[-1][1] == tid and data[entries[-1][3]:entries[-1][3] + entries[-1][2]] == content:
            entries[-1] = (entries[-1][0], entries[-1][1] + 1, entries[-1][2], entries[-1][3])
            continue
        if not (shared and content in stored):
            stored[content] = len(data)
            data += content
        entries.append((tid, 1, len(content), stored[content]))
    root, leaves = _tree(entries, leaf, deep, packed)
    zooms = [z for z, _, _ in tiles]
    known = {"addressed": sum(e[1] for e in entries), "entries": len(entries), "contents": len(set(e[3] for e in entries)), "min_zoom": min(zooms), "max_zoom": max(zooms), "internal": 2 if packed else 1}
    return archive_of(root, leaves, data, metadata, **(known | fields))


def _tree(entries: list[Entry], leaf: int | None, deep: bool, packed: bool) -> tuple[bytes, bytes]:
    if leaf is None:
        return directory(entries, packed), b""
    leaves = b""
    pointers: list[Entry] = []
    for start in range(0, len(entries), leaf):
        block = directory(entries[start:start + leaf], packed)
        pointers.append((entries[start][0], 0, len(block), len(leaves)))
        leaves += block
    if deep:
        upper: list[Entry] = []
        for start in range(0, len(pointers), 2):
            block = directory(pointers[start:start + 2], packed)
            upper.append((pointers[start][0], 0, len(block), len(leaves)))
            leaves += block
        pointers = upper
    return directory(pointers, packed), leaves


# ---- reading

def _unpacked(data: bytes, packed: bool) -> list[Entry]:
    body = gzip.decompress(data) if packed else data
    numbers, value, shift = [], 0, 0
    for byte in body:
        value, shift = value | (byte & 127) << shift, shift + 7
        if byte < 128:
            numbers.append(value)
            value, shift = 0, 0
    count = numbers[0]
    ids, runs, lengths, offsets = (numbers[1 + k * count:1 + (k + 1) * count] for k in range(4))
    rows: list[Entry] = []
    tid = 0
    for i in range(count):
        tid += ids[i]
        offset = rows[-1][3] + rows[-1][2] if i and offsets[i] == 0 else offsets[i] - 1
        rows.append((tid, runs[i], lengths[i], offset))
    return rows


def fields_of(data: bytes) -> dict[str, Any]:
    numbers = struct.unpack_from("<11Q", data, 8)
    tail = struct.unpack_from("<BBBBBB4iBii", data, 96)
    return dict(zip(FIELDS, numbers, strict=True)) | {"clustered": tail[0], "internal": tail[1], "compression": tail[2], "kind": tail[3], "min_zoom": tail[4], "max_zoom": tail[5],
                                                       "bounds": tail[6:10], "center_zoom": tail[10], "center": tail[11:13]}


def every_tile(data: bytes) -> dict[int, bytes]:
    """Every tile the archive addresses, by its id, with the bytes stored for it."""
    f = fields_of(data)
    packed = f["internal"] == 2
    found: dict[int, bytes] = {}

    def walk(offset: int, length: int, depth: int) -> None:
        for tid, run, size, at in _unpacked(data[offset:offset + length], packed):
            if run == 0:
                assert depth < 4
                walk(int(f["leaf_offset"]) + at, size, depth + 1)
            for k in range(run):
                start = int(f["data_offset"]) + at
                found[tid + k] = data[start:start + size]
    walk(int(f["root_offset"]), int(f["root_length"]), 0)
    return found


def tile_at(data: bytes, z: int, x: int, y: int) -> bytes | None:
    return every_tile(data).get(tile_id(z, x, y))


# ---- sources for the tests of the map

@functools.cache
def planet(max_zoom: int = 6) -> bytes:
    """Every tile of the world from zoom 0 to `max_zoom`, each with a content of its own that says where it is, in leaves of 64 entries (the root and one level of leaves)."""
    return archive({(z, x, y): f"{z}/{x}/{y}".encode() * 2 for z in range(max_zoom + 1) for x in range(1 << z) for y in range(1 << z)}, leaf=64)


def tiles_of(box: tuple[float, float, float, float], min_zoom: int, max_zoom: int) -> set[tuple[int, int, int]]:
    """The tiles of the zooms that the box touches: the Web Mercator tile numbers of its north-west and south-east corners, and every tile between them."""
    west, south, east, north = box

    def number(lon: float, lat: float, z: int) -> tuple[int, int]:
        n = 1 << z
        y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
        return min(n - 1, max(0, math.floor((lon + 180) / 360 * n))), min(n - 1, max(0, math.floor(y)))
    found: set[tuple[int, int, int]] = set()
    for z in range(min_zoom, max_zoom + 1):
        (x0, y0), (x1, y1) = number(west, north, z), number(east, south, z)
        found |= {(z, x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}
    return found
