"""One request of the update check: a GET of the version page with the program's version and platform in the query and nothing else, in a thread of its own so that it works on every event loop (and a request that hangs does not hold up the
program's end). A failure of any kind is None: the check is asked again the next day."""
import asyncio
import http.client
import logging
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import IO

log = logging.getLogger("neoaprs.update")

TIMEOUT_SEC = 30.0
MAX_BYTES = 8192                     # the answer is a few lines


class _NotDowngraded(urllib.request.HTTPRedirectHandler):
    """A redirect may not leave https for http."""

    def redirect_request(self, req: urllib.request.Request, fp: IO[bytes], code: int, msg: str, headers: http.client.HTTPMessage, newurl: str) -> urllib.request.Request | None:
        if req.full_url.startswith("https://") and not newurl.startswith("https://"):
            raise urllib.error.HTTPError(req.full_url, code, "redirect from https to http", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def request_url(base: str, version: str, platform: str) -> str:
    """The address of the page with `v` and `os` added to what it has in its query."""
    parts = urllib.parse.urlsplit(base)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode([*query, ("v", version), ("os", platform)])))


def get(base: str, version: str, platform: str, timeout_sec: float = TIMEOUT_SEC) -> bytes | None:
    """The body of the answer, or None when the page could not be reached or did not say 200."""
    if not base.startswith(("http://", "https://")):
        return None                                  # (urllib also reads file: and ftp: addresses)
    request = urllib.request.Request(request_url(base, version, platform), headers={"User-Agent": f"NeoAPRS/{version} ({platform})"})
    try:
        with urllib.request.build_opener(_NotDowngraded).open(request, timeout=timeout_sec) as response:
            return bytes(response.read(MAX_BYTES))
    except (OSError, ValueError, http.client.HTTPException) as e:
        log.debug("the update check could not reach %s: %r", base, e)
        return None


async def fetch(base: str, version: str, platform: str) -> bytes | None:
    """`get` on a thread of its own, awaited."""
    loop = asyncio.get_running_loop()
    done: asyncio.Future[bytes | None] = loop.create_future()

    def finish(body: bytes | None) -> None:
        if not done.done():
            done.set_result(body)

    def work() -> None:
        body = get(base, version, platform)
        try:
            loop.call_soon_threadsafe(finish, body)
        except RuntimeError:                         # (the loop is closed: the program is ending)
            pass

    threading.Thread(target=work, name="update-check", daemon=True).start()
    return await done

