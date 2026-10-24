"""The downloads of Update now: a file of a release and its SHA256SUMS, fetched over https from addresses that `allowed` accepts (neoaprs/updateasset.py: GitHub's release page and its hosts of release files),
redirects included: a redirect anywhere else, or from https to http, ends the download. A file is written while its SHA-256 is computed, a little at a time, so that the progress can be told and a cancel is
seen between two pieces. Each runs in a thread of its own (`in_thread`), so that a download that hangs holds up neither the loop nor the program's end."""
import asyncio
import hashlib
import http.client
import logging
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any, Protocol

log = logging.getLogger("neoaprs.update")

TIMEOUT_SEC = 30.0
CHUNK = 256 * 1024
MAX_SUMS_BYTES = 64 * 1024                 # SHA256SUMS is a few lines
MAX_FILE_BYTES = 600 * 1024 * 1024         # the AppImage is about 150 MB
USER_AGENT = "NeoAPRS (+https://github.com/oh2gba/neoaprs)"

Allowed = Callable[[str], bool]
Progress = Callable[[int, int | None], None]          # (bytes so far, the size the server said or None)


class DownloadError(Exception):
    """The file could not be fetched; the text says why."""


class Cancelled(Exception):
    """The download was cancelled."""


class Response(Protocol):
    headers: Any

    def read(self, size: int = -1) -> bytes: ...
    def geturl(self) -> str: ...
    def close(self) -> None: ...


Opener = Callable[[str, Allowed], Response]


class _Guarded(urllib.request.HTTPRedirectHandler):
    """A redirect only to an address that is allowed."""

    def __init__(self, allowed: Allowed) -> None:
        super().__init__()
        self.allowed = allowed

    def redirect_request(self, req: urllib.request.Request, fp: IO[bytes], code: int, msg: str, headers: http.client.HTTPMessage, newurl: str) -> urllib.request.Request | None:
        if not self.allowed(newurl):
            raise DownloadError(f"the download was sent on to {newurl.split('?', 1)[0]}, which is not one of GitHub's addresses for release files")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_url(url: str, allowed: Allowed) -> Response:
    """The response to a GET of `url`, every redirect checked; DownloadError for an address that is not allowed, a server that does not answer, or an answer that is not 200."""
    if not allowed(url):
        raise DownloadError(f"{url} is not one of GitHub's addresses for release files")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        response: Response = urllib.request.build_opener(_Guarded(allowed)).open(request, timeout=TIMEOUT_SEC)
    except urllib.error.HTTPError as e:
        raise DownloadError(f"{url.rsplit('/', 1)[-1]}: the server answered {e.code} {e.reason}") from None
    except (OSError, ValueError, http.client.HTTPException) as e:
        raise DownloadError(f"{url.rsplit('/', 1)[-1]} could not be fetched: {e}") from None
    if not allowed(response.geturl()):
        response.close()
        raise DownloadError(f"the download ended at {response.geturl()}, which is not one of GitHub's addresses for release files")
    return response


def _size(response: Response) -> int | None:
    try:
        size = int(response.headers.get("Content-Length", ""))
    except (TypeError, ValueError):
        return None
    return size if size >= 0 else None


def fetch_bytes(url: str, allowed: Allowed, limit: int = MAX_SUMS_BYTES, opener: Opener = open_url) -> bytes:
    """The whole body of a small file (SHA256SUMS); DownloadError when it cannot be had or is longer than `limit`."""
    response = opener(url, allowed)
    try:
        body = response.read(limit + 1)
    except (OSError, http.client.HTTPException) as e:
        raise DownloadError(f"{url.rsplit('/', 1)[-1]} could not be read: {e}") from None
    finally:
        response.close()
    if len(body) > limit:
        raise DownloadError(f"{url.rsplit('/', 1)[-1]} is longer than {limit} bytes")
    return body


def fetch_file(url: str, target: Path, allowed: Allowed, progress: Progress, cancelled: threading.Event, opener: Opener = open_url, limit: int = MAX_FILE_BYTES) -> str:
    """Writes the file at `url` to `target` and gives its SHA-256 (lower case hex); `progress` is told after each piece. Cancelled when `cancelled` is set, DownloadError when it cannot be had, is larger
    than `limit` or is cut short. `target` is what was written so far when it fails: the caller removes it."""
    response = opener(url, allowed)
    total = _size(response)
    digest = hashlib.sha256()
    done = 0
    try:
        if total is not None and total > limit:
            raise DownloadError(f"{url.rsplit('/', 1)[-1]} is {total} bytes, more than an update can be")
        with target.open("wb") as out:
            while not cancelled.is_set():
                piece = response.read(CHUNK)
                if not piece:
                    break
                done += len(piece)
                if done > limit:
                    raise DownloadError(f"{url.rsplit('/', 1)[-1]} is more than {limit} bytes, more than an update can be")
                out.write(piece)
                digest.update(piece)
                progress(done, total)
    except (OSError, http.client.HTTPException) as e:
        raise DownloadError(f"{target.name} could not be downloaded: {e}") from None
    finally:
        response.close()
    if cancelled.is_set():
        raise Cancelled()
    if total is not None and done != total:
        raise DownloadError(f"{target.name} was cut short: {done} of {total} bytes")
    return digest.hexdigest()


async def in_thread[T](work: Callable[[], T], name: str = "update-download") -> T:
    """`work()` on a thread of its own, awaited; its exception is raised here. The thread is a daemon: one that hangs does not hold up the program's end."""
    loop = asyncio.get_running_loop()
    done: asyncio.Future[T] = loop.create_future()

    def finish(result: T | None, error: BaseException | None) -> None:
        if done.done():
            return
        if error is not None:
            done.set_exception(error)
        else:
            done.set_result(result)          # type: ignore[arg-type]

    def run() -> None:
        try:
            result, error = work(), None
        except BaseException as e:           # (handed to the loop as it is)
            result, error = None, e
        try:
            loop.call_soon_threadsafe(finish, result, error)
        except RuntimeError:                 # (the loop is closed: the program is ending)
            pass

    threading.Thread(target=run, name=name, daemon=True).start()
    return await done
