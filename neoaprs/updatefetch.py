"""One request of the update check: a GET of the version page with the program's version and platform and the number of this installation (when there is one) in the query and nothing else, in a thread of its own so that it works on every event loop (and a request that hangs does not hold up the
program's end). A failure of any kind is None: the check is asked again the next day. `fetch_url` is the same GET of any https address (the changelog of the latest release, for What's new), with a limit of its own."""
import http.client
import logging
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import IO

from .updatedownload import in_thread

log = logging.getLogger("neoaprs.update")

TIMEOUT_SEC = 30.0
MAX_BYTES = 8192                     # the answer is a few lines


class _NotDowngraded(urllib.request.HTTPRedirectHandler):
    """A redirect may not leave https for http."""

    def redirect_request(self, req: urllib.request.Request, fp: IO[bytes], code: int, msg: str, headers: http.client.HTTPMessage, newurl: str) -> urllib.request.Request | None:
        if req.full_url.startswith("https://") and not newurl.startswith("https://"):
            raise urllib.error.HTTPError(req.full_url, code, "redirect from https to http", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def request_url(base: str, version: str, platform: str, install_id: str = "") -> str:
    """The address of the page with `v`, `os` and, when there is one, `id` added to what it has in its query."""
    parts = urllib.parse.urlsplit(base)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    added = [("v", version), ("os", platform), *([("id", install_id)] if install_id else [])]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode([*query, *added])))


def get_url(url: str, version: str, platform: str, timeout_sec: float = TIMEOUT_SEC, max_bytes: int = MAX_BYTES) -> bytes | None:
    """The body of the answer to a GET of `url` (at most `max_bytes` of it), or None when it could not be reached or did not say 200."""
    if not url.startswith(("http://", "https://")):
        return None                                  # (urllib also reads file: and ftp: addresses)
    request = urllib.request.Request(url, headers={"User-Agent": f"NeoAPRS/{version} ({platform})"})
    try:
        with urllib.request.build_opener(_NotDowngraded).open(request, timeout=timeout_sec) as response:
            return bytes(response.read(max_bytes))
    except (OSError, ValueError, http.client.HTTPException) as e:
        log.debug("the update check could not reach %s: %r", url, e)
        return None


def get(base: str, version: str, platform: str, install_id: str = "", timeout_sec: float = TIMEOUT_SEC) -> bytes | None:
    """The body of the version page's answer, or None when the page could not be reached or did not say 200."""
    if not base.startswith(("http://", "https://")):
        return None
    return get_url(request_url(base, version, platform, install_id), version, platform, timeout_sec)


async def _quietly(work: Callable[[], bytes | None], name: str) -> bytes | None:
    """`work` on a thread of its own, awaited; an error that `get_url` did not expect is logged and is None too, as every other failure."""
    try:
        return await in_thread(work, name)
    except Exception:
        log.exception("the update check failed")
        return None


async def fetch(base: str, version: str, platform: str, install_id: str = "") -> bytes | None:
    """`get` on a thread of its own, awaited."""
    return await _quietly(lambda: get(base, version, platform, install_id), "update-check")


async def fetch_url(url: str, version: str, platform: str, max_bytes: int) -> bytes | None:
    """`get_url` on a thread of its own, awaited."""
    return await _quietly(lambda: get_url(url, version, platform, max_bytes=max_bytes), "update-fetch")
