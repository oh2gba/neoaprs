"""The PMTiles format, version 3, as far as cutting a region out of an archive needs it: the header, the directories, the tile ids and the tiles a box touches.

An archive is a header of 127 bytes, a root directory in the first 16 KiB, a JSON metadata block, leaf directories and the tile data. A directory is a list of entries (a tile id, a run length, a length and an
offset), written as columns of varints (the tile ids as deltas, an offset of 0 for one that follows the entry before it) and compressed as the header says; an entry with a run length of 0 points to a leaf
directory that holds the tiles from its id up to the next entry's. A tile id counts the tiles of the zooms below, then follows the Hilbert curve over the zoom, so that the tiles of one quadrant of the
quadtree are one range of ids. Every number that comes from an archive is checked here before it is used: a `FormatError` says what is wrong with it, in a sentence for the log.
Pure code: the bytes come and go through the caller."""
import array
import math
import struct
import zlib
from bisect import bisect_right
from collections.abc import Iterator
from dataclasses import dataclass

HEADER_LENGTH = 127
ROOT_SPACE = 16384                          # the header and the root directory are in the first 16 KiB of an archive
MAGIC = b"PMTiles"
NONE, GZIP = 1, 2                           # the compressions of the directories that are read and written (brotli and zstd are not in the standard library)
MAX_ZOOM = 31                               # the deepest zoom a tile id of 64 bits holds
MAX_ROOT = 1024 * 1024                      # the most the root directory may unpack to (16 KiB of a real archive's root unpack to a few hundred kB)
MAX_LEAF = 4 * 1024 * 1024                  # the most a leaf directory may be, packed or unpacked (one of the planet's leaves is a few hundred kB)
MAX_LEAVES = 200_000                        # the leaf directories a cut reads in all (a country of the planet's archive is a few hundred)
LEAF_ROOT_SPACE = ROOT_SPACE - HEADER_LENGTH
FIRST_LEAF = 4096                           # the entries of a leaf the writer tries first, as go-pmtiles does
_TOP = 1 << 64
_HEADER = struct.Struct("<7sB11QBBBBBB4iBii")


class FormatError(ValueError):
    """The bytes are not what a PMTiles archive of version 3 holds; the text says what."""


@dataclass(frozen=True)
class Header:
    root_offset: int
    root_length: int
    metadata_offset: int
    metadata_length: int
    leaf_offset: int
    leaf_length: int
    data_offset: int
    data_length: int
    addressed_tiles: int
    tile_entries: int
    tile_contents: int
    clustered: bool
    internal_compression: int
    tile_compression: int
    tile_type: int
    min_zoom: int
    max_zoom: int
    bounds_e7: tuple[int, int, int, int]            # west, south, east, north in units of 1e-7 degrees
    center_zoom: int
    center_e7: tuple[int, int]                      # longitude, latitude


def parse_header(data: bytes) -> Header:
    if len(data) < HEADER_LENGTH or data[:7] != MAGIC:
        raise FormatError("the file is not a PMTiles archive")
    if data[7] != 3:
        raise FormatError(f"the archive is of PMTiles version {data[7]}, not 3")
    v = _HEADER.unpack_from(data)
    header = Header(v[2], v[3], v[4], v[5], v[6], v[7], v[8], v[9], v[10], v[11], v[12], bool(v[13]), v[14], v[15], v[16], v[17], v[18], (v[19], v[20], v[21], v[22]), v[23], (v[24], v[25]))
    if header.internal_compression not in (NONE, GZIP):
        raise FormatError(f"the directories of the archive are compressed with method {header.internal_compression}, which is not read")
    if not header.min_zoom <= header.max_zoom <= MAX_ZOOM:
        raise FormatError(f"the archive's zooms {header.min_zoom} to {header.max_zoom} are not possible")
    return header


def header_bytes(h: Header) -> bytes:
    return _HEADER.pack(MAGIC, 3, h.root_offset, h.root_length, h.metadata_offset, h.metadata_length, h.leaf_offset, h.leaf_length, h.data_offset, h.data_length, h.addressed_tiles, h.tile_entries,
                        h.tile_contents, int(h.clustered), h.internal_compression, h.tile_compression, h.tile_type, h.min_zoom, h.max_zoom, *h.bounds_e7, h.center_zoom, *h.center_e7)


def check_sections(h: Header, size: int) -> None:
    """FormatError unless every part the header names lies inside an archive of `size` bytes and the root directory in its first 16 KiB."""
    parts = {"root directory": (h.root_offset, h.root_length), "metadata": (h.metadata_offset, h.metadata_length), "leaf directories": (h.leaf_offset, h.leaf_length), "tile data": (h.data_offset, h.data_length)}
    for name, (offset, length) in parts.items():
        if offset < HEADER_LENGTH and length or offset + length > size:
            raise FormatError(f"the {name} of the archive ({length} bytes at {offset}) is not inside its {size} bytes")
    if h.root_offset + h.root_length > ROOT_SPACE:
        raise FormatError("the root directory of the archive is not in its first 16 KiB")


# ---- tile ids

def zxy_to_id(z: int, x: int, y: int) -> int:
    """The tile id of a tile: the tiles of the zooms below it, then its place on the Hilbert curve of its zoom."""
    d, s = 0, 1 << z >> 1
    while s:
        rx, ry = int(x & s > 0), int(y & s > 0)
        d += s * s * ((3 * rx) ^ ry)
        if not ry:
            if rx:
                x, y = s - 1 - x, s - 1 - y
            x, y = y, x
        s >>= 1
    return ((1 << 2 * z) - 1) // 3 + d


def id_to_zxy(tile_id: int) -> tuple[int, int, int]:
    z = 0
    while tile_id >= ((1 << 2 * (z + 1)) - 1) // 3:
        z += 1
    d, x, y, s = tile_id - ((1 << 2 * z) - 1) // 3, 0, 0, 1
    while s < 1 << z:
        rx, ry = 1 & d // 2, 1 & (d ^ (d // 2 & 1))
        if not ry:
            if rx:
                x, y = s - 1 - x, s - 1 - y
            x, y = y, x
        x, y, d, s = x + s * rx, y + s * ry, d // 4, s * 2
    return z, x, y


def tile_xy(lon: float, lat: float, z: int) -> tuple[int, int]:
    """The tile of zoom `z` a point is in, the way go-pmtiles' tile cover finds it (a point on an edge is in the tile east or south of it), held inside the world."""
    n = 1 << z
    x = (lon / 360.0 + 0.5) * n
    if lat < -85.0511:
        y = n - 1.0
    elif lat > 85.0511:
        y = 0.0
    else:
        sin = math.sin(lat * math.pi / 180.0)
        y = (0.5 + 0.5 * math.log((1.0 + sin) / (1.0 - sin)) / (-2 * math.pi)) * n
    return min(n - 1, max(0, math.floor(x))), min(n - 1, max(0, math.floor(y)))


Ranges = list[tuple[int, int]]                  # tile ids from the first up to the second, sorted and apart


def cover(box: tuple[float, float, float, float] | None, min_zoom: int, max_zoom: int) -> Ranges:
    """The tile ids of zoom `min_zoom` to `max_zoom` that the box (west, south, east, north; the whole world for None) touches: the tiles of its corners at the deepest zoom and every tile between them, and their
    parents. A quadrant that is inside the box whole is one range, so a box is as many ranges as the curve goes in and out of it, not as many as its tiles."""
    if box is None:
        return [(zxy_to_id(z, 0, 0), zxy_to_id(z + 1, 0, 0)) for z in range(min_zoom, max_zoom + 1)]
    west, south, east, north = box
    x0, y0 = tile_xy(west, north, max_zoom)
    x1, y1 = tile_xy(east, south, max_zoom)
    found: Ranges = []
    for z in range(min_zoom, max_zoom + 1):
        k = max_zoom - z
        found += _quadrants(z, x0 >> k, y0 >> k, x1 >> k, y1 >> k)
    return found


def _quadrants(z: int, x0: int, y0: int, x1: int, y1: int) -> Ranges:
    found: Ranges = []
    stack = [(0, 0, 0)]
    while stack:
        level, qx, qy = stack.pop()
        k = z - level
        if (qx + 1 << k) <= x0 or qx << k > x1 or (qy + 1 << k) <= y0 or qy << k > y1:
            continue
        if x0 <= qx << k and (qx + 1 << k) - 1 <= x1 and y0 <= qy << k and (qy + 1 << k) - 1 <= y1:
            start = zxy_to_id(z, 0, 0) + (zxy_to_id(level, qx, qy) - zxy_to_id(level, 0, 0) << 2 * k)
            found.append((start, start + (1 << 2 * k)))
            continue
        stack += [(level + 1, 2 * qx + dx, 2 * qy + dy) for dx in (0, 1) for dy in (0, 1)]
    found.sort()
    merged: Ranges = []
    for start, end in found:
        if merged and merged[-1][1] == start:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


# ---- directories

class Entries:
    """Directory entries as four columns, 24 bytes an entry, so that hundreds of thousands of them are a few MB."""

    def __init__(self) -> None:
        self.tile_ids = array.array("Q")
        self.run_lengths = array.array("I")
        self.lengths = array.array("I")
        self.offsets = array.array("Q")

    def __len__(self) -> int:
        return len(self.tile_ids)

    def add(self, tile_id: int, run_length: int, length: int, offset: int) -> None:
        self.tile_ids.append(tile_id)
        self.run_lengths.append(run_length)
        self.lengths.append(length)
        self.offsets.append(offset)

    def extend(self, other: "Entries") -> None:
        self.tile_ids.extend(other.tile_ids)
        self.run_lengths.extend(other.run_lengths)
        self.lengths.extend(other.lengths)
        self.offsets.extend(other.offsets)

    def __iter__(self) -> Iterator[tuple[int, int, int, int]]:
        return zip(self.tile_ids, self.run_lengths, self.lengths, self.offsets, strict=True)


def unpack(data: bytes, compression: int, limit: int) -> bytes:
    """The bytes of a directory or the metadata, unpacked; FormatError for bytes that do not unpack, or that would unpack to more than `limit`."""
    if compression == NONE:
        if len(data) > limit:
            raise FormatError(f"a directory of the archive is bigger than {limit} bytes")
        return data
    unpacker = zlib.decompressobj(wbits=31)
    try:
        out = unpacker.decompress(data, limit + 1)
    except zlib.error as e:
        raise FormatError(f"a directory of the archive does not unpack: {e}") from None
    if len(out) > limit:
        raise FormatError(f"a directory of the archive unpacks to more than {limit} bytes")
    if not unpacker.eof:
        raise FormatError("a directory of the archive is cut short")
    return out


def _varints(data: bytes) -> "array.array[int]":
    out = array.array("Q")
    value = shift = 0
    for byte in data:
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            if value >= _TOP:
                raise FormatError("a directory of the archive holds a number of more than 64 bits")
            out.append(value)
            value = shift = 0
        elif (shift := shift + 7) > 63:
            raise FormatError("a directory of the archive holds a number of more than 64 bits")
    if shift:
        raise FormatError("a directory of the archive ends in the middle of a number")
    return out


def decode(data: bytes) -> Entries:
    """The entries of an unpacked directory, checked: one count and four columns, the ids rising, a run of tiles not reaching the next entry, no empty tile, no offset before the start."""
    numbers = _varints(data)
    count = numbers[0] if numbers else -1
    if len(numbers) != 1 + 4 * count:
        raise FormatError("a directory of the archive does not hold the entries it says")
    ids, runs, lengths, raw = (numbers[1 + i * count:1 + (i + 1) * count] for i in range(4))
    entries, tile_id, offset = Entries(), 0, 0
    for i in range(count):
        if i and (not ids[i] or runs[i - 1] > ids[i]):
            raise FormatError("the entries of a directory of the archive are not in order")
        if not lengths[i] or not (i or raw[0]):
            raise FormatError("a directory of the archive has an entry without data")
        if runs[i] >= 1 << 32 or lengths[i] >= 1 << 32:
            raise FormatError("a directory of the archive has an entry of more than 32 bits")
        tile_id += ids[i]
        offset = offset + lengths[i - 1] if i and not raw[i] else raw[i] - 1
        if tile_id >= _TOP or offset >= _TOP:
            raise FormatError("a directory of the archive names a tile or an offset of more than 64 bits")
        entries.add(tile_id, runs[i], lengths[i], offset)
    return entries


def _varint(value: int, out: bytearray) -> None:
    while value >= 0x80:
        out.append(value & 0x7F | 0x80)
        value >>= 7
    out.append(value)


def encode(entries: Entries, start: int, end: int, compression: int) -> bytes:
    """Entries `start` to `end` as a directory, compressed."""
    out = bytearray()
    _varint(end - start, out)
    last = 0
    for tile_id in entries.tile_ids[start:end]:
        _varint(tile_id - last, out)
        last = tile_id
    for column in (entries.run_lengths, entries.lengths):
        for value in column[start:end]:
            _varint(value, out)
    for i in range(start, end):
        follows = i > start and entries.offsets[i] == entries.offsets[i - 1] + entries.lengths[i - 1]
        _varint(0 if follows else entries.offsets[i] + 1, out)
    return zlib.compress(bytes(out), wbits=31) if compression == GZIP else bytes(out)


def directories(entries: Entries, compression: int) -> tuple[bytes, bytes]:
    """The root directory and the leaf directories that hold the entries: the root alone when it fits beside the header, else leaves of 4096 entries or more (a fifth more at each try, as go-pmtiles
    does) until the root of their pointers fits."""
    if len(entries) < ROOT_SPACE:
        root = encode(entries, 0, len(entries), compression)
        if len(root) <= LEAF_ROOT_SPACE:
            return root, b""
    size = max(float(FIRST_LEAF), len(entries) / 3500)
    while True:
        pointers, leaves = Entries(), bytearray()
        for start in range(0, len(entries), int(size)):
            leaf = encode(entries, start, min(len(entries), start + int(size)), compression)
            pointers.add(entries.tile_ids[start], 0, len(leaf), len(leaves))
            leaves += leaf
        root = encode(pointers, 0, len(pointers), compression)
        if len(root) <= LEAF_ROOT_SPACE:
            return root, bytes(leaves)
        size *= 1.2


Leaf = tuple[int, int, int, int]                 # a leaf directory: the first tile id it holds, the id it holds up to, its length and its offset in the leaf directories


def touched(entries: Entries, ranges: Ranges, low: int, end: int, room: int) -> tuple[list[Entries], list[Leaf]]:
    """The tile entries of a directory that lie in the ranges (a run of tiles cut down to the part inside, the way go-pmtiles does), a list of them for each stretch between two leaves, and the leaves whose ids
    reach into a range. The directory holds the ids from `low` up to `end` (a leaf, those its parent gives it); an entry outside them is a FormatError, and so is a leaf beyond the `room` left of MAX_LEAVES."""
    parts = [Entries()]
    leaves: list[Leaf] = []
    after_leaf = False
    starts = [start for start, _ in ranges]
    count = len(entries)
    for i, (tile_id, run, length, offset) in enumerate(entries):
        upper = tile_id + run if run else (entries.tile_ids[i + 1] if i + 1 < count else end)
        if tile_id < low or upper > end:
            raise FormatError(f"a directory of the archive names tile {tile_id}, outside the ids {low} to {end} its parent gives it")
        j = max(0, bisect_right(starts, tile_id) - 1)
        while j < len(ranges) and ranges[j][0] < upper:
            first, last = max(tile_id, ranges[j][0]), min(upper, ranges[j][1])
            if first < last and not run:
                if len(leaves) >= room:
                    raise FormatError(f"the box reaches into more than {MAX_LEAVES} leaf directories of the archive")
                leaves.append((tile_id, upper, length, offset))
                after_leaf = True
                break
            if first < last:
                if after_leaf:
                    parts.append(Entries())
                    after_leaf = False
                parts[-1].add(first, last - first, length, offset)
            j += 1
    return [part for part in parts if len(part)], leaves
