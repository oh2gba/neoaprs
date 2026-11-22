"""Read the bytes of a PMTiles archive for a cut, from a file or a web server by range requests.

A server must answer a range request with 206 and the matching Content-Range. A failed request
is repeated after each pause in `pauses`; a stop is checked between pieces of `CHUNK` bytes.
"""

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
from .httpstrust import USER_AGENT, https_handler
from .mapstate import Problem
from .pmtilesarchive import UNREACHABLE, Redirected

log = logging.getLogger("neoaprs.mapfetch")

TIMEOUT_SEC = 30.0
CHUNK = 256 * 1024
# Pauses between the tries of one request: four tries in all.
PAUSES_SEC = (2.0, 8.0, 30.0)
TRY_LATER = frozenset({408, 425, 429, 500, 502, 503, 504})
STOPPED = "stopped"
_RANGE = re.compile(r"bytes (\d{1,20})-(\d{1,20})/(\d{1,20})")

# Receives each piece with the archive offset of its first byte; a retried request starts again
# at its first offset.
Into = Callable[[int, bytes], None]


class CutError(Exception):
    """The cut cannot be done. The text is for the log; `problem` and `params` are for the page."""

    def __init__(self, text: str, problem: Problem = "failed", **params: int) -> None:
        super().__init__(text)
        self.problem: Problem = problem
        self.params = params


class _TryAgain(Exception):
    pass


class Source(Protocol):
    size: int

    def copy(self, offset: int, length: int, into: Into) -> None: ...
    def abort(self) -> None: ...
    def close(self) -> None: ...


class Halt:
    """The stop flag of a cut, shared by its threads. Once set it stays; `on` callbacks run."""

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
    """Run each piece of work on its own thread and return the results in order.

    The first failure sets `halt` and is raised; threads are daemons, late results are ignored."""
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
    """Return a small part of the archive (header, directory) whole."""
    if length == 0:
        return b""
    held = bytearray()

    def keep(at: int, piece: bytes) -> None:
        del held[at - offset :]
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
    def __init__(
        self, url: str, halt: Halt, pauses: tuple[float, ...] = PAUSES_SEC, timeout_sec: float = TIMEOUT_SEC
    ) -> None:
        self.url = url
        # Size of the archive, from the first answer.
        self.size = -1
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
                    log.warning(
                        "the map server did not give bytes %d to %d after %d tries: %s",
                        offset,
                        offset + length - 1,
                        attempt,
                        e,
                    )
                    raise CutError(UNREACHABLE, problem="unreachable") from None
                log.info(
                    "the map server did not give bytes %d to %d (try %d): %s", offset, offset + length - 1, attempt, e
                )
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
        request = urllib.request.Request(  # noqa: S310
            self.url, headers={"User-Agent": USER_AGENT, "Range": f"bytes={offset}-{offset + length - 1}"}
        )
        if self._halt.is_set():
            raise CutError(STOPPED)
        try:
            # Under the no-devices switch a server that is not on this computer is not reachable.
            nodevices.check_url(self.url)
            response: http.client.HTTPResponse = urllib.request.build_opener(
                https_handler(), Redirected, *nodevices.direct()
            ).open(request, timeout=self._timeout)
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
        """Raise CutError unless the answer is the range asked for, from an archive of same size."""
        if response.status != 206:
            raise CutError(
                f"the map server answered {response.status} to a range request and not 206: it cannot be cut from"
            )
        said = (response.headers.get("Content-Range") or "").strip()
        found = _RANGE.fullmatch(said)
        if found is None or (int(found.group(1)), int(found.group(2))) != (offset, offset + length - 1):
            raise CutError(
                f"the map server answered bytes {said[:80]!r} where bytes {offset} to {offset + length - 1} were asked for"
            )
        total = int(found.group(3))
        if self.size >= 0 and total != self.size:
            raise CutError(
                f"the archive on the map server changed while it was cut (its size was {self.size} bytes and is {total})"
            )
        self.size = total
        announced = response.headers.get("Content-Length")
        if announced is not None and announced.strip() != str(length):
            raise CutError(f"the map server announced {announced} bytes where {length} were asked for")

    def abort(self) -> None:
        """Shut the open connections so that a read waiting on a silent server ends."""
        with self._lock:
            for response in self._open:
                with contextlib.suppress(OSError, ValueError, AttributeError):
                    shut = socket.fromfd(response.fileno(), socket.AF_INET, socket.SOCK_STREAM)
                    with shut:
                        shut.shutdown(socket.SHUT_RDWR)

    def close(self) -> None:
        pass


def open_source(source: str, halt: Halt, pauses: tuple[float, ...] = PAUSES_SEC) -> FileSource | HttpSource:
    """Open the archive at an http(s) address or a path. Raise CutError if it cannot be opened."""
    scheme = source.split("://", 1)[0].lower() if "://" in source else ""
    if scheme in ("http", "https"):
        if nodevices.url_refused(source, "the map"):
            raise CutError(UNREACHABLE, problem="unreachable")
        return HttpSource(source, halt, pauses)
    if scheme:
        raise CutError("the map source is neither an http or https address nor a file")
    return FileSource(Path(source), halt)
