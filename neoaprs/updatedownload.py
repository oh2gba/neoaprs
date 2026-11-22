"""Download a release file and its SHA256SUMS over https from addresses `allowed` accepts.

Redirects are checked too. Each download runs in its own thread (`in_thread`) so a hang holds up
neither the loop nor the program's end.
"""

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
from . import nodevices
from .httpstrust import USER_AGENT, https_handler

log = logging.getLogger("neoaprs.update")

TIMEOUT_SEC = 30.0
CHUNK = 256 * 1024
MAX_SUMS_BYTES = 64 * 1024
MAX_FILE_BYTES = 600 * 1024 * 1024

Allowed = Callable[[str], bool]
# (bytes so far, the size the server announced or None)
Progress = Callable[[int, int | None], None]


class DownloadError(Exception):
    """The file could not be fetched. `status` is a non-200 HTTP status, else None."""

    def __init__(self, text: str, status: int | None = None) -> None:
        super().__init__(text)
        self.status = status


class Cancelled(Exception):
    """The download was cancelled."""


class Response(Protocol):
    headers: Any

    def read(self, size: int = -1) -> bytes: ...
    def geturl(self) -> str: ...
    def close(self) -> None: ...


Opener = Callable[[str, Allowed], Response]


class _Guarded(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only to an allowed address."""

    def __init__(self, allowed: Allowed) -> None:
        super().__init__()
        self.allowed = allowed

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: http.client.HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        if not self.allowed(newurl):
            raise DownloadError(
                f"the download was sent on to {newurl.split('?', 1)[0]}, which is not one of GitHub's addresses for release files"
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_url(url: str, allowed: Allowed) -> Response:
    """Return the response to a GET of `url`; raise DownloadError unless the answer is 200."""
    if not allowed(url):
        raise DownloadError(f"{url} is not one of GitHub's addresses for release files")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310  (`allowed` checks the address and every redirect)
    try:
        # under the no-devices switch only this computer is reachable
        nodevices.check_url(url)
        response: Response = urllib.request.build_opener(https_handler(), _Guarded(allowed), *nodevices.direct()).open(
            request, timeout=TIMEOUT_SEC
        )
    except urllib.error.HTTPError as e:
        raise DownloadError(f"{url.rsplit('/', 1)[-1]}: the server answered {e.code} {e.reason}", e.code) from None
    except (OSError, ValueError, http.client.HTTPException) as e:
        raise DownloadError(f"{url.rsplit('/', 1)[-1]} could not be fetched: {e}") from None
    if not allowed(response.geturl()):
        response.close()
        raise DownloadError(
            f"the download ended at {response.geturl()}, which is not one of GitHub's addresses for release files"
        )
    return response


def _size(response: Response) -> int | None:
    try:
        size = int(response.headers.get("Content-Length", ""))
    except (TypeError, ValueError):
        return None
    return size if size >= 0 else None


def fetch_bytes(url: str, allowed: Allowed, limit: int = MAX_SUMS_BYTES, opener: Opener = open_url) -> bytes:
    """Return the whole body of a small file; raise DownloadError if unreadable or over `limit`."""
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


def fetch_file(
    url: str,
    target: Path,
    allowed: Allowed,
    progress: Progress,
    cancelled: threading.Event,
    opener: Opener = open_url,
    limit: int = MAX_FILE_BYTES,
) -> str:
    """Write the file at `url` to `target` and return its SHA-256 as hex.

    Raise Cancelled or DownloadError; on failure `target` holds partial data for the caller to remove.
    """
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
                    raise DownloadError(
                        f"{url.rsplit('/', 1)[-1]} is more than {limit} bytes, more than an update can be"
                    )
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
    """Run `work()` on its own daemon thread and await it; its exception is raised here."""
    loop = asyncio.get_running_loop()
    done: asyncio.Future[T] = loop.create_future()

    def finish(result: T | None, error: BaseException | None) -> None:
        if done.done():
            return
        if error is not None:
            done.set_exception(error)
        else:
            done.set_result(result)  # type: ignore[arg-type]

    def run() -> None:
        try:
            result, error = work(), None
        except BaseException as e:  # handed to the loop as it is
            result, error = None, e
        try:
            loop.call_soon_threadsafe(finish, result, error)
        except RuntimeError:  # the loop is closed: the program is ending
            pass

    threading.Thread(target=run, name=name, daemon=True).start()
    return await done
