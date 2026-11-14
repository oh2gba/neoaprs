"""What a cut (neoaprs/pmtilescut.py) fetches and writes, worked out from the directories of the source before a byte of tile data is fetched.

The root directory and, a level at a time, the leaf directories that reach into the box are read (at most `MAX_LEAF_DEPTH` levels of leaves, the leaves of one level in requests of up to `LEAF_CHUNK`
bytes, `threads` at once); the entries of the tiles in the box are kept, in the order of their ids. Each content gets its place in the new tile data the first time a tile names it, so that the new archive is
clustered and a shared content is there once. The pieces of the source to fetch are then grouped into requests. What is held is four columns of the entries kept (24 bytes each), two of the contents
(12 bytes each), the requests and the new directories; for a cut of 300 MB with 400 000 tiles about 20 MB."""
import array
from bisect import bisect_left
from collections.abc import Iterator
from dataclasses import dataclass
from functools import partial

from .mapstate import Box
from .pmtilesformat import (HEADER_LENGTH, MAX_LEAF, MAX_LEAVES, MAX_ROOT, Entries, FormatError, Header, Leaf, Ranges, cover, decode, directories, header_bytes, touched, unpack)
from .pmtilesrange import CutError, Halt, Source, in_parallel, read

MAX_LEAF_DEPTH = 3                          # the levels of leaves under the root that a reader of the format looks into
MAX_TILE_ENTRIES = 5_000_000                # 120 MB of columns
MAX_METADATA = 16 * 1024 * 1024
LEAF_CHUNK = 4 * 1024 * 1024
LEAF_GAP = 64 * 1024                        # leaves this close to each other are fetched with one request
END = 1 << 64

Request = tuple[int, int, int, int, int]    # the start and end in the source, the first piece and the one after the last, the place of the first piece in the new tile data


@dataclass(frozen=True)
class Cut:
    tiles: int                              # the tile entries of the archive (what go-pmtiles says as "fetching N tiles")
    bytes: int                              # the size of the archive
    addressed: int                          # the tiles it holds, a run of tiles counted tile by tile
    contents: int                           # the tile contents it holds, a shared one once
    requests: int                           # the requests for its tile data


@dataclass(frozen=True)
class Plan:
    cut: Cut
    head: bytes                             # the new header, root directory, metadata and leaf directories: everything before the tile data
    piece_sources: "array.array[int]"       # the offset in the source of each content, in the order of the new tile data
    piece_lengths: "array.array[int]"
    requests: list[Request]
    fetched: int                            # the bytes the requests ask for, gaps included

    @property
    def data_offset(self) -> int:
        return len(self.head)

    @property
    def size(self) -> int:
        return self.cut.bytes


def make_plan(reader: Source, header: Header, box: Box | None, maxzoom: int, threads: int, halt: Halt, overfetch: float, max_request: int) -> Plan:
    """The plan of the cut of `box` (the whole world for None) to `maxzoom` out of the archive whose header is `header`. FormatError for directories that are no good, CutError for a cut that cannot be."""
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
    """The header of the new archive. The bounds and the centre are the box's, in units of 1e-7 degrees cut toward zero as go-pmtiles writes them; the whole world keeps the source's."""
    bounds, center = old.bounds_e7, old.center_e7
    if box is not None:
        bounds = (int(box[0] * 1e7), int(box[1] * 1e7), int(box[2] * 1e7), int(box[3] * 1e7))
        center = (int((box[0] + box[2]) / 2 * 1e7), int((box[1] + box[3]) / 2 * 1e7))
    first = HEADER_LENGTH + root + metadata
    return Header(HEADER_LENGTH, root, HEADER_LENGTH + root, metadata, first, leaves, first + leaves, data_length, sum(entries.run_lengths), len(entries), contents, True,
                  old.internal_compression, old.tile_compression, old.tile_type, old.min_zoom, deepest, bounds, min(max(old.center_zoom, old.min_zoom), deepest), center)


def _entries(reader: Source, header: Header, ranges: Ranges, threads: int, halt: Halt) -> Entries:
    """The tile entries in the ranges, from the root and the leaves that reach into them, in the order of their ids; FormatError for directories that are not in order, too deep or too many."""
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
    """Each leaf with its bytes, fetched in requests of neighbouring leaves, `threads` requests at a time."""
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
    """The parts one after the other in the order of their first ids; FormatError where two of them overlap (a leaf that holds tiles of another's ids)."""
    joined = Entries()
    for part in sorted(parts, key=lambda part: part.tile_ids[0]):
        joined.extend(part)
    ids, runs = joined.tile_ids, joined.run_lengths
    for i in range(1, len(joined)):
        if ids[i] < ids[i - 1] + runs[i - 1]:
            raise FormatError(f"the directories of the archive name tile {ids[i]} twice")
    return joined


def _reencode(entries: Entries, data_offset: int, data_length: int) -> tuple["array.array[int]", "array.array[int]"]:
    """Gives each content a place in the new tile data, in the order the tiles name them, and writes the places into the entries; the offsets in the source archive and the lengths of the contents, in that order.
    A content is known by its offset: those that come in the order of the source are found by bisection in two columns, the few that come back from before in a dict."""
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
    """The pieces grouped into requests: neighbours in the source, and pieces with a gap between them as long as all such gaps together are at most `overfetch` of the data, the smallest first."""
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

