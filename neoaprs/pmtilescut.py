"""The detailed base map cut out of a big PMTiles archive (version 3, clustered: the Protomaps daily build of the whole world, read with range requests, or a file), as `pmtiles extract` does it.

The cut reads the header and the directories that the box reaches into (neoaprs/pmtilesplan.py; neoaprs/pmtilesformat.py has the format and which tiles a box touches) and writes a clustered archive of the tiles
of the box down to `maxzoom`: the header (the box and its centre, the zooms, the counts; the compressions, the tile type and the metadata as the source has them), the directories, the metadata and the tile
data in the order of the tile ids, a content that several tiles share once. The size of the archive is known before a byte of tile data is fetched: `estimate` (the dry run) says it, and a cut that would be
bigger than `max_bytes` is refused.

The tile data is fetched in few requests: pieces that lie next to each other in the source are one request, and so are pieces with a gap between them as long as all the gaps together are at most `OVERFETCH`
of the data (the smallest gaps first, as go-pmtiles' overfetch does); a request is at most `MAX_REQUEST` long. `threads` requests run at once (neoaprs/pmtilesrange.py tries a failed one again), each piece
written to its place in the file as it comes, so that only a piece of each is in memory. The percent told goes by the bytes of the requests that came, and only up; the size told is the part of the archive
that has come, in the same measure. The header and the directories are read on a thread that a stop does not wait for, so that a server that has not begun its answer holds nothing up. The archive is written to
a `.part` file beside the target and moved into place when it is whole; a failure or a stop removes it. `stop` ends a cut from another thread at once; `extract` is the cut for the event loop. Nothing here imports Tornado or the settings."""
import asyncio
import contextlib
import logging
import queue
import threading
from collections.abc import Callable
from pathlib import Path
from typing import IO

from .mapstate import Box
from .pmtilesarchive import DOWNLOAD_THREADS, replace_file
from .pmtilesformat import HEADER_LENGTH, FormatError, check_sections, parse_header
from .pmtilesplan import Cut, Plan, make_plan
from .pmtilesrange import PAUSES_SEC, STOPPED, CutError, Halt, Source, in_parallel, open_source, read

log = logging.getLogger("neoaprs.mapfetch")

OVERFETCH = 0.05                            # the gaps fetched with the tiles, at most this part of the tile data
MAX_REQUEST = 32 * 1024 * 1024
MAX_BYTES = 50 * 1000**3                    # the biggest archive made when the caller names no limit

__all__ = ["Cut", "CutError", "Cutting", "extract", "part_of"]


def part_of(target: Path) -> Path:
    """The file the archive is written to until it is whole."""
    return target.with_name(target.name + ".part")


class Cutting:
    """One cut, run in a thread with `estimate()` (the dry run) or `run()`; `stop()` from any other thread ends it at once with CutError("stopped")."""

    def __init__(self, source: str, target: Path, box: Box | None, maxzoom: int, max_bytes: int = MAX_BYTES, threads: int = DOWNLOAD_THREADS,
                 on_percent: Callable[[int], None] | None = None, pauses: tuple[float, ...] = PAUSES_SEC, on_size: Callable[[int], None] | None = None) -> None:
        self.source, self.target, self.box, self.maxzoom = source, target, box, maxzoom
        self.max_bytes = max_bytes
        self.threads = max(1, threads)
        self.on_percent = on_percent or (lambda percent: None)
        self.on_size = on_size or (lambda size: None)
        self.pauses = pauses
        self.halt = Halt()

    def stop(self) -> None:
        self.halt.set()

    def _open(self) -> Source:
        if self.halt.is_set():
            raise CutError(STOPPED)
        reader = open_source(self.source, self.halt, self.pauses)
        self.halt.on(reader.abort)
        return reader

    def _plan(self, reader: Source) -> Plan:
        return in_parallel([lambda: self._planned(reader)], self.halt)[0]

    def _planned(self, reader: Source) -> Plan:
        try:
            header = parse_header(read(reader, 0, HEADER_LENGTH))
            check_sections(header, reader.size)
            plan = make_plan(reader, header, self.box, self.maxzoom, self.threads, self.halt, OVERFETCH, MAX_REQUEST)
        except FormatError as e:
            raise CutError(f"the map source cannot be cut: {e}") from None
        if plan.size > self.max_bytes:
            raise CutError(f"the map would be {plan.size / 1e6:.0f} MB, more than the {self.max_bytes / 1e6:.0f} MB it may be")
        return plan

    def estimate(self) -> Cut:
        """What the archive would be, from its directories alone: no tile data is fetched and nothing is written."""
        reader = self._open()
        try:
            return self._plan(reader).cut
        finally:
            reader.close()

    def run(self) -> Cut:
        """Writes the archive at `target`, whole or not at all."""
        reader = self._open()
        part = part_of(self.target)
        try:
            return self._write(reader, part)
        except BaseException:
            self.halt.set()
            _remove(part)
            raise
        finally:
            reader.close()

    def _write(self, reader: Source, part: Path) -> Cut:
        plan = self._plan(reader)
        try:
            with part.open("w+b") as raw:
                out = _File(raw)
                try:
                    out.write_at(0, plan.head)
                    self.on_size(plan.data_offset)
                    _Download(reader, plan, out, self.halt, self.on_percent, self.on_size).run(self.threads)
                finally:
                    written = out.close()
        except OSError as e:
            raise CutError(f"{part.name} could not be written: {e.strerror or e}") from None
        if written != plan.size:
            raise CutError(f"the map was written with {written} bytes and not the {plan.size} it should have")
        try:
            replace_file(part, self.target)
        except OSError as e:
            log.warning("%s could not be moved over %s: %s", part.name, self.target.name, e)
            raise CutError("the new map could not be put in place of the one in use; try again") from None
        return plan.cut


def _remove(part: Path) -> None:
    try:
        part.unlink(missing_ok=True)
    except OSError as e:
        log.warning("%s could not be deleted: %s", part.name, e)


class _File:
    """The `.part` file, written at places from several threads; once it is closed a thread that comes late writes nothing."""

    def __init__(self, raw: IO[bytes]) -> None:
        self._raw = raw
        self._lock = threading.Lock()
        self._open = True

    def write_at(self, position: int, data: bytes) -> None:
        with self._lock:
            if self._open:
                self._raw.seek(position)
                self._raw.write(data)

    def close(self) -> int:
        """Ends the writing; the size of the file."""
        with self._lock:
            self._open = False
            return self._raw.seek(0, 2)


class _Download:
    """The requests of a plan on `threads` threads, each piece written to its place in the file as it comes; the first failure stops the others."""

    def __init__(self, reader: Source, plan: Plan, out: _File, halt: Halt, on_percent: Callable[[int], None], on_size: Callable[[int], None]) -> None:
        self.reader, self.plan, self.out, self.halt, self.on_percent, self.on_size = reader, plan, out, halt, on_percent, on_size
        self._lock = threading.Lock()
        self._done = 0
        self._percent = -1

    def run(self, threads: int) -> None:
        work: queue.SimpleQueue[int] = queue.SimpleQueue()
        for index in range(len(self.plan.requests)):
            work.put(index)
        in_parallel([lambda: self._worker(work)] * min(threads, len(self.plan.requests)), self.halt)
        self._report(100)

    def _worker(self, work: "queue.SimpleQueue[int]") -> None:
        while not self.halt.is_set():
            try:
                index = work.get_nowait()
            except queue.Empty:
                return
            self._fetch(index)
        raise CutError(STOPPED)

    def _fetch(self, index: int) -> None:
        start, end, first, last, place = self.plan.requests[index]
        pieces = _Pieces(self.plan, first, last, place)
        best = start

        def into(at: int, data: bytes) -> None:
            nonlocal best
            for position, chunk in pieces.place(at, data):
                self.out.write_at(self.plan.data_offset + position, chunk)
            if at + len(data) > best:
                self._advance(at + len(data) - best)
                best = at + len(data)
        self.reader.copy(start, end - start, into)

    def _advance(self, count: int) -> None:
        """More bytes have come: the percent, when it is higher, and the size are told. Told under the lock, so that what two requests report at once reaches the page in the order it was counted
        (told after the lock was let go, a smaller size could follow a larger one: the suite saw it once, 14 November 2026)."""
        with self._lock:
            self._done += count
            if self.halt.is_set():
                return
            percent = min(99, self._done * 100 // max(1, self.plan.fetched))
            if percent > self._percent:
                self._percent = percent
                self.on_percent(percent)
            self.on_size(self.plan.data_offset + (self.plan.size - self.plan.data_offset) * self._done // max(1, self.plan.fetched))


    def _report(self, percent: int) -> None:
        with self._lock:
            if percent > self._percent and not self.halt.is_set():
                self._percent = percent
                self.on_percent(percent)

class _Pieces:
    """Where the bytes of one request go: the pieces it holds, in the order of the source, each to its place in the new tile data; the gaps between them are dropped. A request that is tried again
    delivers from its start again, and the places start over with it."""

    def __init__(self, plan: Plan, first: int, last: int, place: int) -> None:
        self.sources, self.lengths = plan.piece_sources, plan.piece_lengths
        self.first, self.last, self.start = first, last, place
        self.index, self.at, self.seen = first, place, -1

    def place(self, at: int, data: bytes) -> list[tuple[int, bytes]]:
        """The parts of the bytes from `at` that are tiles, each with its place in the new tile data."""
        if at <= self.seen:
            self.index, self.at = self.first, self.start
        self.seen = at
        out: list[tuple[int, bytes]] = []
        end = at + len(data)
        while self.index < self.last and self.sources[self.index] < end:
            begin, length = self.sources[self.index], self.lengths[self.index]
            low, high = max(at, begin), min(end, begin + length)
            if low < high:
                out.append((self.at + low - begin, data[low - at:high - at]))
            if begin + length > end:
                break
            self.index, self.at = self.index + 1, self.at + length
        return out


async def extract(source: str, target: Path, box: Box | None, maxzoom: int, dry_run: bool = False, on_percent: Callable[[int], None] | None = None,
                  max_bytes: int = MAX_BYTES, threads: int = DOWNLOAD_THREADS, on_size: Callable[[int], None] | None = None) -> Cut:
    """The cut on the event loop: `on_percent` and `on_size` are told on the loop, and a task that is cancelled stops the cut and waits for its thread, which ends at once. CutError for a cut that fails."""
    loop = asyncio.get_running_loop()
    told = on_percent or (lambda percent: None)

    sized = on_size or (lambda size: None)

    def from_thread(call: Callable[[int], None]) -> Callable[[int], None]:
        def tell(value: int) -> None:
            with contextlib.suppress(RuntimeError):                        # (the loop is closed: the program is ending)
                loop.call_soon_threadsafe(call, value)
        return tell

    cutting = Cutting(source, target, box, maxzoom, max_bytes, threads, from_thread(told), on_size=from_thread(sized))
    thread = asyncio.ensure_future(asyncio.to_thread(cutting.estimate if dry_run else cutting.run))
    try:
        return await asyncio.shield(thread)
    except asyncio.CancelledError:
        cutting.stop()
        with contextlib.suppress(Exception):
            await thread
        raise
