"""Work out what a cut fetches and writes, from the directories of the source alone.

The directories that reach into the box are read and the entries of its tiles kept in tile id
order; each content gets its place when first named, so shared contents are stored once.
"""
import array
from bisect import bisect_left
from collections.abc import Iterator
from dataclasses import dataclass
from functools import partial

from .mapstate import Box
from .pmtilesformat import (HEADER_LENGTH, MAX_LEAF, MAX_LEAVES, MAX_ROOT, Entries, FormatError, Header, Leaf, Ranges, cover, decode, directories, header_bytes, touched, unpack)
from .pmtilesrange import CutError, Halt, Source, in_parallel, read

# Levels of leaves under the root that a reader of the format looks into.
MAX_LEAF_DEPTH = 3
# 120 MB of columns.
MAX_TILE_ENTRIES = 5_000_000
MAX_METADATA = 16 * 1024 * 1024
LEAF_CHUNK = 4 * 1024 * 1024
# Leaves this close to each other are fetched with one request.
LEAF_GAP = 64 * 1024
END = 1 << 64

# One request: start and end in the source, first piece, the piece after the last, and the place
# of the first piece in the new tile data.
Request = tuple[int, int, int, int, int]


@dataclass(frozen=True)
class Cut:
    # Tile entries of the archive.
    tiles: int
    # Size of the archive.
    bytes: int
    # Tiles held, a run counted tile by tile.
    addressed: int
    # Tile contents held, a shared one once.
    contents: int
    # Requests for the tile data.
    requests: int


@dataclass(frozen=True)
class Plan:
    cut: Cut
    # Everything before the tile data: header, root directory, metadata, leaf directories.
    head: bytes
    # Source offset of each content, in the order of the new tile data.
    piece_sources: "array.array[int]"
    piece_lengths: "array.array[int]"
    requests: list[Request]
    # Bytes the requests ask for, gaps included.
    fetched: int

    @property
    def data_offset(self) -> int:
        return len(self.head)

    @property
    def size(self) -> int:
        return self.cut.bytes


def make_plan(reader: Source, header: Header, box: Box | None, maxzoom: int, threads: int, halt: Halt, overfetch: float, max_request: int) -> Plan:
    """Return the plan to cut `box` (None: the world) to `maxzoom`.

    Raise FormatError for bad directories and CutError for a cut that cannot be made.
    """
    if not header.clustered:
        raise CutError("the archive is not clustered (its tiles are not in the order of their ids), so it cannot be cut")
    deepest = min(maxzoom, header.max_zoom)
    if deepest < header.min_zoom:
        raise CutError(f"the archive has no tiles of zoom {maxzoom} or less")
    entries = _entries(reader, header, cover(box, header.min_zoom, deepest), threads, halt)
    sources, lengths = _reencode(entries, header.data_offset, header.data_length)
    if header.metadata_length > MAX_METADATA:
        raise FormatError(f"the metadata of the archive is {header.metadata_length} bytes, more than {MAX_METADATA}")
    metadata = read(reader, header.metadata_offset, header.metadata_length)
    root, leaves = directories(entries, header.internal_compression)
    data_length = sum(lengths)
    new = _header(header, box, deepest, entries, len(sources), data_length, len(root), len(metadata), len(leaves))
    requests = _requests(sources, lengths, overfetch, max_request)
    head = header_bytes(new) + root + metadata + leaves
    cut = Cut(len(entries), len(head) + data_length, new.addressed_tiles, len(sources), len(requests))
    return Plan(cut, head, sources, lengths, requests, sum(end - start for start, end, *_ in requests))


def _header(old: Header, box: Box | None, deepest: int, entries: Entries, contents: int, data_length: int, root: int, metadata: int, leaves: int) -> Header:
    """Return the header of the new archive; bounds are the box's in 1e-7 degrees, truncated."""
    bounds, center = old.bounds_e7, old.center_e7
    if box is not None:
        bounds = (int(box[0] * 1e7), int(box[1] * 1e7), int(box[2] * 1e7), int(box[3] * 1e7))
        center = (int((box[0] + box[2]) / 2 * 1e7), int((box[1] + box[3]) / 2 * 1e7))
    first = HEADER_LENGTH + root + metadata
    return Header(HEADER_LENGTH, root, HEADER_LENGTH + root, metadata, first, leaves, first + leaves, data_length, sum(entries.run_lengths), len(entries), contents, True,
                  old.internal_compression, old.tile_compression, old.tile_type, old.min_zoom, deepest, bounds, min(max(old.center_zoom, old.min_zoom), deepest), center)


def _entries(reader: Source, header: Header, ranges: Ranges, threads: int, halt: Halt) -> Entries:
    """Return the tile entries in the ranges, in id order; raise FormatError for bad directories."""
    root = decode(unpack(read(reader, header.root_offset, header.root_length), header.internal_compression, MAX_ROOT))
    parts, level = touched(root, ranges, 0, END, MAX_LEAVES)
    held, read_leaves = sum(len(part) for part in parts), 0
    for depth in range(1, MAX_LEAF_DEPTH + 2):
        if not level:
            break
        if depth > MAX_LEAF_DEPTH:
            raise FormatError(f"the leaf directories of the archive go deeper than {MAX_LEAF_DEPTH} levels")
        read_leaves += len(level)
        below: list[Leaf] = []
        for leaf, data in _leaves(reader, header, level, threads, halt):
            found, deeper = touched(decode(unpack(data, header.internal_compression, MAX_LEAF)), ranges, leaf[0], leaf[1], MAX_LEAVES - read_leaves - len(below))
            parts += found
            below += deeper
            held += sum(len(part) for part in found)
            if held > MAX_TILE_ENTRIES:
                raise CutError(f"the box holds more than {MAX_TILE_ENTRIES} tile entries; a smaller box or a lower zoom is needed")
        level = below
    return _joined(parts)


def _leaves(reader: Source, header: Header, level: list[Leaf], threads: int, halt: Halt) -> Iterator[tuple[Leaf, bytes]]:
    """Yield each leaf with its bytes, fetched in requests of neighbouring leaves."""
    chunks: list[list[Leaf]] = []
    for leaf in sorted(level, key=lambda leaf: leaf[3]):
        if leaf[2] > MAX_LEAF or leaf[3] + leaf[2] > header.leaf_length:
            raise FormatError(f"a leaf directory of the archive ({leaf[2]} bytes at {leaf[3]}) is not inside its {header.leaf_length} bytes of leaves")
        last = chunks[-1] if chunks else None
        if last and 0 <= leaf[3] - (last[-1][3] + last[-1][2]) <= LEAF_GAP and leaf[3] + leaf[2] - last[0][3] <= LEAF_CHUNK:
            last.append(leaf)
        else:
            chunks.append([leaf])
    for batch in range(0, len(chunks), threads):
        group = chunks[batch:batch + threads]
        got = in_parallel([partial(read, reader, header.leaf_offset + chunk[0][3], chunk[-1][3] + chunk[-1][2] - chunk[0][3]) for chunk in group], halt)
        for chunk, data in zip(group, got, strict=True):
            for leaf in chunk:
                yield leaf, data[leaf[3] - chunk[0][3]:leaf[3] - chunk[0][3] + leaf[2]]


def _joined(parts: list[Entries]) -> Entries:
    """Join the parts in order of their first ids; raise FormatError if two overlap."""
    joined = Entries()
    for part in sorted(parts, key=lambda part: part.tile_ids[0]):
        joined.extend(part)
    ids, runs = joined.tile_ids, joined.run_lengths
    for i in range(1, len(joined)):
        if ids[i] < ids[i - 1] + runs[i - 1]:
            raise FormatError(f"the directories of the archive name tile {ids[i]} twice")
    return joined


def _reencode(entries: Entries, data_offset: int, data_length: int) -> tuple["array.array[int]", "array.array[int]"]:
    """Give each content a place in the new tile data and write the places into the entries.

    Return the source offsets and lengths. Contents in source order are found by bisection."""
    sources, lengths, places = array.array("Q"), array.array("I"), array.array("Q")
    in_order, numbers = array.array("Q"), array.array("Q")
    others: dict[int, int] = {}
    place = 0
    for i, (offset, length) in enumerate(zip(entries.offsets, entries.lengths, strict=True)):
        if offset + length > data_length:
            raise FormatError(f"a tile of the archive ({length} bytes at {offset}) is not inside its {data_length} bytes of tile data")
        if not in_order or offset > in_order[-1]:
            number = None
        else:
            j = bisect_left(in_order, offset)
            number = numbers[j] if j < len(in_order) and in_order[j] == offset else others.get(offset)
        if number is None:
            number = len(sources)
            if not in_order or offset > in_order[-1]:
                in_order.append(offset)
                numbers.append(number)
            else:
                others[offset] = number
            sources.append(data_offset + offset)
            lengths.append(length)
            places.append(place)
            place += length
        elif lengths[number] != length:
            raise FormatError(f"two tiles of the archive share the content at {offset} with different lengths")
        entries.offsets[i] = places[number]
    return sources, lengths


def _requests(sources: "array.array[int]", lengths: "array.array[int]", overfetch: float, max_request: int) -> list[Request]:
    """Group the pieces into requests, bridging the smallest gaps up to `overfetch` of the data."""
    gaps = sorted(gap for gap in (sources[i] - sources[i - 1] - lengths[i - 1] for i in range(1, len(sources))) if gap > 0)
    budget, allowed = overfetch * sum(lengths), 0
    for gap in gaps:
        budget -= gap
        if budget < 0:
            break
        allowed = gap
    requests: list[Request] = []
    place = 0
    for i, (offset, length) in enumerate(zip(sources, lengths, strict=True)):
        if requests:
            start, end, first, _, at = requests[-1]
            if 0 <= offset - end <= allowed and offset + length - start <= max_request:
                requests[-1] = (start, offset + length, first, i + 1, at)
                place += length
                continue
        requests.append((offset, offset + length, i, i + 1, place))
        place += length
    return requests

