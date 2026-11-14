"""The bytes of a PMTiles archive that is cut (neoaprs/pmtilescut.py): from a file, or from a web server with range requests, so that a few MB are read out of an archive of the whole world.

A server must answer a range request with 206 and the Content-Range of the bytes asked for, of an archive whose size does not change between two answers; one that answers 200 with the whole body, or with
other bytes, is refused at once and its body is not read. A request that cannot be made, is cut short or is answered with a status that says to try later is made again after a pause, `len(pauses) + 1` times in
all; then the cut fails with words for the operator, and the log has what happened. The bytes come a piece at a time (`CHUNK`), and a stop is seen between two pieces; `abort` also shuts the connections that
are waiting, so that a server that has stopped sending holds nothing up. https goes through the project's opener (neoaprs/httpstrust.py) and the no-devices switch, and so does every redirect, which may not leave https for http."""
import contextlib
import http.client
import logging
import re
import socket
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

from . import nodevices
from .httpstrust import https_handler
from .pmtilesarchive import UNREACHABLE, USER_AGENT, Redirected

log = logging.getLogger("neoaprs.mapfetch")

TIMEOUT_SEC = 30.0
CHUNK = 256 * 1024
PAUSES_SEC = (2.0, 8.0, 30.0)               # between the tries of one request: four in all
TRY_LATER = frozenset({408, 425, 429, 500, 502, 503, 504})
STOPPED = "stopped"
_RANGE = re.compile(r"bytes (\d{1,20})-(\d{1,20})/(\d{1,20})")

Into = Callable[[int, bytes], None]         # told each piece with the offset in the archive of its first byte; a request tried again begins again at its first offset


class CutError(Exception):
    """The cut cannot be done; the text says why, in a sentence for the log."""


class _TryAgain(Exception):
    pass


class Source(Protocol):
    size: int

    def copy(self, offset: int, length: int, into: Into) -> None: ...
    def abort(self) -> None: ...
    def close(self) -> None: ...


class Halt:
    """The stop of a cut, for every thread of it: once set it stays, and what was handed to `on` is called (a wait that ends, the connections that are shut)."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._then: list[Callable[[], None]] = []

    def set(self) -> None:
        with self._lock:
            self._event.set()
            then = list(self._then)
        for call in then:
            call()

    def is_set(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float) -> bool:
        return self._event.wait(timeout)

    def on(self, call: Callable[[], None]) -> None:
        with self._lock:
            self._then.append(call)
            now = self._event.is_set()
        if now:
            call()


def in_parallel[T](work: list[Callable[[], T]], halt: Halt) -> list[T]:
    """Each piece of work on a thread of its own, at once; their results in order. The first failure sets `halt`, which ends the others, and is raised; a halt from outside raises CutError(STOPPED) as soon as
    it is set. The threads are daemons, and one that still waits for a server when this returns ends by itself: what it delivers late is not taken."""
    results: list[T | None] = [None] * len(work)
    failures: list[BaseException] = []
    over, lock, left = threading.Event(), threading.Lock(), [len(work)]

    def run(index: int) -> None:
        try:
            result = work[index]()
        except BaseException as e:
            with lock:
                failures.append(e)
            halt.set()
            over.set()
            return
        with lock:
            results[index] = result
            left[0] -= 1
            if not left[0]:
                over.set()

    if not work:
        return []
    halt.on(over.set)
    for index in range(len(work)):
        threading.Thread(target=run, args=(index,), name="map-cut", daemon=True).start()
    over.wait()
    with lock:
        real = [e for e in failures if not (isinstance(e, CutError) and str(e) == STOPPED)]
        if real:
            raise real[0]
        if left[0]:
            raise CutError(STOPPED)
        return cast(list[T], results)


def read(source: Source, offset: int, length: int) -> bytes:
    """A small part of the archive (the header, a directory), held whole."""
    held = bytearray()

    def keep(at: int, piece: bytes) -> None:
        del held[at - offset:]
        held.extend(piece)
    source.copy(offset, length, keep)
    return bytes(held)


class FileSource:
    def __init__(self, path: Path, halt: Halt) -> None:
        try:
            self._file = path.open("rb")
            self.size = path.stat().st_size
        except OSError as e:
            raise CutError(f"the map file {path.name} cannot be read: {e.strerror or e}") from None
        self._halt = halt
        self._lock = threading.Lock()

    def copy(self, offset: int, length: int, into: Into) -> None:
        end = offset + length
        while offset < end:
            if self._halt.is_set():
                raise CutError(STOPPED)
            with self._lock:
                self._file.seek(offset)
                piece = self._file.read(min(CHUNK, end - offset))
            if not piece:
                raise CutError(f"the archive ends at {offset}, before the {end} bytes its directories name")
            into(offset, piece)
            offset += len(piece)

    def abort(self) -> None:
        pass

    def close(self) -> None:
        self._file.close()


class HttpSource:
    def __init__(self, url: str, halt: Halt, pauses: tuple[float, ...] = PAUSES_SEC, timeout_sec: float = TIMEOUT_SEC) -> None:
        self.url = url
        self.size = -1                              # the size of the archive, from the first answer
        self._halt = halt
        self._pauses = pauses
        self._timeout = timeout_sec
        self._lock = threading.Lock()
        self._open: set[http.client.HTTPResponse] = set()

    def copy(self, offset: int, length: int, into: Into) -> None:
        for attempt, pause in enumerate((*self._pauses, None), start=1):
            try:
                return self._once(offset, length, into)
            except _TryAgain as e:
                if self._halt.is_set():
                    raise CutError(STOPPED) from None
                if pause is None:
                    log.warning("the map server did not give bytes %d to %d after %d tries: %s", offset, offset + length - 1, attempt, e)
                    raise CutError(UNREACHABLE) from None
                log.info("the map server did not give bytes %d to %d (try %d): %s", offset, offset + length - 1, attempt, e)
            if self._halt.wait(pause):
                raise CutError(STOPPED)

    def _once(self, offset: int, length: int, into: Into) -> None:
        response = self._request(offset, length)
        try:
            at, end = offset, offset + length
            while at < end:
                if self._halt.is_set():
                    raise CutError(STOPPED)
                piece = response.read(min(CHUNK, end - at))
                if not piece:
                    raise _TryAgain(f"the answer was cut short at {at - offset} of {length} bytes")
                into(at, piece)
                at += len(piece)
        except (OSError, http.client.HTTPException) as e:
            raise _TryAgain(str(e) or type(e).__name__) from None
        finally:
            with self._lock:
                self._open.discard(response)
            response.close()

    def _request(self, offset: int, length: int) -> http.client.HTTPResponse:
        request = urllib.request.Request(self.url, headers={"User-Agent": USER_AGENT, "Range": f"bytes={offset}-{offset + length - 1}"})  # noqa: S310  (http or https only: `open_source`)
        if self._halt.is_set():
            raise CutError(STOPPED)
        try:
            nodevices.check_url(self.url)                                       # (under the no-devices switch a server that is not on this computer is not there)
            response: http.client.HTTPResponse = urllib.request.build_opener(https_handler(), Redirected, *nodevices.direct()).open(request, timeout=self._timeout)
        except urllib.error.HTTPError as e:
            e.close()
            if e.code in TRY_LATER:
                raise _TryAgain(f"the server answered {e.code} {e.reason}") from None
            raise CutError(f"the map server answered {e.code} {e.reason}") from None
        except (OSError, http.client.HTTPException) as e:
            raise _TryAgain(str(e) or type(e).__name__) from None
        except ValueError as e:
            raise CutError(f"the map source is not an address that can be asked: {e}") from None
        with self._lock:
            self._open.add(response)
        try:
            self._check(response, offset, length)
        except CutError:
            with self._lock:
                self._open.discard(response)
            response.close()
            raise
        return response

    def _check(self, response: http.client.HTTPResponse, offset: int, length: int) -> None:
        """CutError unless the answer is the range asked for, of an archive of the same size as before."""
        if response.status != 206:
            raise CutError(f"the map server answered {response.status} to a range request and not 206: it cannot be cut from")
        said = (response.headers.get("Content-Range") or "").strip()
        found = _RANGE.fullmatch(said)
        if found is None or (int(found.group(1)), int(found.group(2))) != (offset, offset + length - 1):
            raise CutError(f"the map server answered bytes {said[:80]!r} where bytes {offset} to {offset + length - 1} were asked for")
        total = int(found.group(3))
        if self.size >= 0 and total != self.size:
            raise CutError(f"the archive on the map server changed while it was cut (its size was {self.size} bytes and is {total})")
        self.size = total
        announced = response.headers.get("Content-Length")
        if announced is not None and announced.strip() != str(length):
            raise CutError(f"the map server announced {announced} bytes where {length} were asked for")

    def abort(self) -> None:
        """Shuts the connections that are open, so that a read that waits for a server that sends nothing ends now."""
        with self._lock:
            for response in self._open:
                with contextlib.suppress(OSError, ValueError, AttributeError):
                    shut = socket.fromfd(response.fileno(), socket.AF_INET, socket.SOCK_STREAM)
                    with shut:
                        shut.shutdown(socket.SHUT_RDWR)

    def close(self) -> None:
        pass


def open_source(source: str, halt: Halt, pauses: tuple[float, ...] = PAUSES_SEC) -> FileSource | HttpSource:
    """The archive at a web address (http or https) or a path. CutError for another kind of address, a file that cannot be read, and under the no-devices switch a server that is not on this computer."""
    scheme = source.split("://", 1)[0].lower() if "://" in source else ""
    if scheme in ("http", "https"):
        if nodevices.url_refused(source, "the map"):
            raise CutError(UNREACHABLE)
        return HttpSource(source, halt, pauses)
    if scheme:
        raise CutError("the map source is neither an http or https address nor a file")
    return FileSource(Path(source), halt)
