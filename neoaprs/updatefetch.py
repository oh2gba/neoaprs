"""One request of the update check: a GET of the version page with the program's version and platform and the number of this installation (when there is one) in the query and nothing else, in a thread of its own so that it works on every event loop (and a request that hangs does not hold up the
program's end). A failure of any kind is None: the check is asked again the next day. `fetch_url` is the same GET of any https address (the changelog of the latest release, for What's new), with a limit of its own. `post_form` is the one POST of the
program, multipart/form-data, for Send feedback / logs of the Help group: it answers the status and the body of whatever the server said (a refusal carries its reason in the body), and None only when the server could not be reached. `get_answer` is the GET that says the status too (the sked board: a 404 is a board that has not been made yet), and `post_json` the POST of a JSON body that the sked board takes.

`get_feed` is the GET of the map's layers of traffic (an aircraft or ships service, an own aircraft receiver): it asks for a packed answer, unpacks it within a bound, and says the status, the body and how long a
`Retry-After` asks to wait; None when the address is not http(s), the server could not be reached, the answer is larger than its bounds or it did not come within its time. A `user:password@` in the
address (a receiver behind a password) is sent as basic authentication to that host only, never as a part of the host's name."""
import asyncio
import base64
import email.utils
import http.client
import logging
import secrets
import time
import zlib
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import IO
from urllib.parse import unquote, urlsplit, urlunsplit

from . import nodevices
from .updatedownload import in_thread
from .httpstrust import NotDowngraded, https_handler

log = logging.getLogger("neoaprs.update")

TIMEOUT_SEC = 30.0
MAX_BYTES = 8192                     # the answer is a few lines
SEND_TIMEOUT_SEC = 60.0              # of each wait for the server while the support file goes up (a megabyte or two over a slow line)
FEED_TIMEOUT_SEC = 10.0              # of a layer's question to its service or receiver, its whole answer included
FEED_GRACE_SEC = 1.0                 # beyond it, the most the daemon waits for the question's thread (a server that drips its head)
MAX_RETRY_AFTER_SEC = 3600           # the longest a `Retry-After` is believed
POST_TOTAL_SEC = 300.0               # the most the daemon waits for a POST in all, the upload and the answer
FEED_CHUNK = 65536                   # the answer is read in pieces of at most this, the time looked at between them
AUTHORIZATION = "Authorization"
PACKED = ("gzip", "x-gzip")


class _NotDowngraded(NotDowngraded):
    def check(self, newurl: str) -> None:
        nodevices.check_url(newurl, level=logging.DEBUG)             # (under the no-devices switch a server of this computer sends nobody on to another one)


class _FeedRedirect(_NotDowngraded):
    """A layer's redirect: the basic authentication goes on only to the same scheme, host and port."""

    def redirect_request(self, req: urllib.request.Request, fp: IO[bytes], code: int, msg: str, headers: http.client.HTTPMessage, newurl: str) -> urllib.request.Request | None:
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        said = req.get_header(AUTHORIZATION)
        if new is not None and said is not None and _origin(new.full_url) == _origin(req.full_url):
            new.add_unredirected_header(AUTHORIZATION, said)
        return new


def _origin(url: str) -> tuple[str, str, int | None]:
    parts = urlsplit(url)
    return parts.scheme, (parts.hostname or "").lower(), parts.port or (443 if parts.scheme == "https" else 80)


def without_password(url: str) -> tuple[str, str | None]:
    """The address without its `user:password@`, and the `Authorization` header that carries them (None when it has none)."""
    parts = urlsplit(url)
    if "@" not in parts.netloc:
        return url, None
    userinfo, _, hostport = parts.netloc.rpartition("@")
    user, _, password = userinfo.partition(":")
    token = base64.b64encode(f"{unquote(user)}:{unquote(password)}".encode()).decode("ascii")
    return urlunsplit(parts._replace(netloc=hostport)), f"Basic {token}"


def _read_by(response: http.client.HTTPResponse, limit: int, deadline: float) -> bytes | None:
    """At most `limit` + 1 bytes of the answer, read in pieces; None when `deadline` (time.monotonic) passes before it has all come."""
    pieces: list[bytes] = []
    size = 0
    while size <= limit:
        if time.monotonic() > deadline:
            return None
        piece = response.read1(min(FEED_CHUNK, limit + 1 - size))
        if not piece:
            break
        pieces.append(piece)
        size += len(piece)
    return b"".join(pieces)


class _NotFollowed(urllib.request.HTTPRedirectHandler):
    """A POST is not sent on to another address: its answer is the redirect itself."""

    def redirect_request(self, req: urllib.request.Request, fp: IO[bytes], code: int, msg: str, headers: http.client.HTTPMessage, newurl: str) -> urllib.request.Request | None:
        return None


def request_url(base: str, version: str, platform: str, install_id: str = "") -> str:
    """The address of the page with `v`, `os` and, when there is one, `id` added to what it has in its query."""
    parts = urllib.parse.urlsplit(base)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    added = [("v", version), ("os", platform), *([("id", install_id)] if install_id else [])]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode([*query, *added])))


def get_answer(url: str, version: str, platform: str, timeout_sec: float = TIMEOUT_SEC, max_bytes: int = MAX_BYTES) -> tuple[int, bytes] | None:
    """The status and the body of the answer to a GET of `url`, whatever the status; None when the address is not http(s), the server could not be reached, the answer is longer than `max_bytes` or has not all come
    `timeout_sec` after the start."""
    if not url.startswith(("http://", "https://")):
        return None                                  # (urllib also reads file: and ftp: addresses)
    deadline = time.monotonic() + timeout_sec
    request = urllib.request.Request(url, headers={"User-Agent": f"NeoAPRS/{version} ({platform})"})  # noqa: S310  (http or https only: the two lines above)
    try:
        nodevices.check_url(url, level=logging.DEBUG)                # (under the no-devices switch a server that is not on this computer is not there)
        with urllib.request.build_opener(https_handler(), _NotDowngraded, *nodevices.direct()).open(request, timeout=timeout_sec) as response:
            body = _read_by(response, max_bytes, deadline)
            if body is None or len(body) > max_bytes:
                log.debug("the answer of %s did not come whole within %g s or is longer than %d bytes", url, timeout_sec, max_bytes)
                return None
            return int(response.status), body
    except urllib.error.HTTPError as e:
        return int(e.code), b""
    except (OSError, ValueError, http.client.HTTPException) as e:
        log.debug("the update check could not reach %s: %r", url, e)
        return None


def get_url(url: str, version: str, platform: str, timeout_sec: float = TIMEOUT_SEC, max_bytes: int = MAX_BYTES) -> bytes | None:
    """The body of the answer to a GET of `url` (at most `max_bytes` of it), or None when it could not be reached or did not say 200."""
    answer = get_answer(url, version, platform, timeout_sec, max_bytes)
    return answer[1] if answer is not None and answer[0] == 200 else None


def get(base: str, version: str, platform: str, install_id: str = "", timeout_sec: float = TIMEOUT_SEC) -> bytes | None:
    """The body of the version page's answer, or None when the page could not be reached or did not say 200."""
    if not base.startswith(("http://", "https://")):
        return None
    return get_url(request_url(base, version, platform, install_id), version, platform, timeout_sec)


async def _quietly(work: Callable[[], bytes | None], name: str) -> bytes | None:
    """`work` on a thread of its own, awaited for `TIMEOUT_SEC` and a little more at most; an error that `get_url` did not expect is logged and is None too, as every other failure."""
    try:
        return await asyncio.wait_for(in_thread(work, name), TIMEOUT_SEC + FEED_GRACE_SEC)
    except TimeoutError:
        log.debug("the update check did not end within %g s", TIMEOUT_SEC + FEED_GRACE_SEC)
        return None
    except Exception:
        log.exception("the update check failed")
        return None


async def fetch_answer(url: str, version: str, platform: str, max_bytes: int) -> tuple[int, bytes] | None:
    """`get_answer` on a thread of its own, awaited; an error it did not expect is logged and is None too."""
    try:
        return await asyncio.wait_for(in_thread(lambda: get_answer(url, version, platform, max_bytes=max_bytes), "update-fetch"), TIMEOUT_SEC + FEED_GRACE_SEC)
    except TimeoutError:
        log.debug("the update check did not end within %g s", TIMEOUT_SEC + FEED_GRACE_SEC)
        return None
    except Exception:
        log.exception("the update check failed")
        return None


async def fetch(base: str, version: str, platform: str, install_id: str = "") -> bytes | None:
    """`get` on a thread of its own, awaited."""
    return await _quietly(lambda: get(base, version, platform, install_id), "update-check")


async def fetch_url(url: str, version: str, platform: str, max_bytes: int) -> bytes | None:
    """`get_url` on a thread of its own, awaited."""
    return await _quietly(lambda: get_url(url, version, platform, max_bytes=max_bytes), "update-fetch")


def multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes]]) -> tuple[str, bytes]:
    """(the Content-Type, the body) of a multipart/form-data form: the text `fields`, and the `files` as name -> (file name, content), the file names and field names plain ASCII."""
    boundary = "neoaprs-" + secrets.token_hex(16)
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode() + value.encode("utf-8") + b"\r\n")
    for name, (filename, content) in files.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + content + b"\r\n")
    return f"multipart/form-data; boundary={boundary}", b"".join(parts) + f"--{boundary}--\r\n".encode()


def _body_of(response: IO[bytes], max_bytes: int, timeout_sec: float) -> bytes:
    """The first `max_bytes` of the answer, read for `timeout_sec` at most (what has come by then is the answer); the rest is not read."""
    deadline = time.monotonic() + timeout_sec
    pieces: list[bytes] = []
    size = 0
    while size < max_bytes and time.monotonic() <= deadline:
        piece = response.read1(min(FEED_CHUNK, max_bytes - size)) if hasattr(response, "read1") else response.read(max_bytes - size)
        if not piece:
            break
        pieces.append(piece)
        size += len(piece)
    return b"".join(pieces)


def _post(url: str, content_type: str, body: bytes, version: str, platform: str, timeout_sec: float, max_bytes: int, server: str) -> tuple[int, bytes] | None:
    """The status and the body (at most `max_bytes`) of the answer to a POST of `body` to `url`, whatever the status (a refusal carries its reason in the body); None when the address is not http(s) or the
    server (`server`, for the log) could not be reached."""
    if not url.startswith(("http://", "https://")):
        return None
    request = urllib.request.Request(url, data=body, method="POST", headers={"User-Agent": f"NeoAPRS/{version} ({platform})", "Content-Type": content_type})  # noqa: S310  (http or https only: the lines above)
    try:
        nodevices.check_url(url)                                     # (under the no-devices switch nothing is sent to a server that is not on this computer)
        with urllib.request.build_opener(https_handler(), _NotFollowed, *nodevices.direct()).open(request, timeout=timeout_sec) as response:
            return int(response.status), _body_of(response, max_bytes, timeout_sec)
    except urllib.error.HTTPError as e:
        try:
            return int(e.code), _body_of(e, max_bytes, timeout_sec)
        except (OSError, http.client.HTTPException):
            return int(e.code), b""
    except (OSError, ValueError, http.client.HTTPException) as e:
        log.debug("%s %s could not be reached: %r", server, url, e)
        return None


def post_form(url: str, fields: dict[str, str], files: dict[str, tuple[str, bytes]], version: str, platform: str, timeout_sec: float = SEND_TIMEOUT_SEC, max_bytes: int = MAX_BYTES) -> tuple[int, bytes] | None:
    """The answer (`_post`) to a multipart POST of `fields` and `files` to `url`."""
    content_type, body = multipart(fields, files)
    return _post(url, content_type, body, version, platform, timeout_sec, max_bytes, "the support server")


async def post(url: str, fields: dict[str, str], files: dict[str, tuple[str, bytes]], version: str, platform: str) -> tuple[int, bytes] | None:
    """`post_form` on a thread of its own, awaited; an error it did not expect is logged and is None too."""
    try:
        return await asyncio.wait_for(in_thread(lambda: post_form(url, fields, files, version, platform), "support-send"), POST_TOTAL_SEC)
    except TimeoutError:
        log.debug("sending the support logs did not end within %g s", POST_TOTAL_SEC)
        return None
    except Exception:
        log.exception("sending the support logs failed")
        return None


def post_json(url: str, body: bytes, version: str, platform: str, timeout_sec: float = TIMEOUT_SEC, max_bytes: int = MAX_BYTES) -> tuple[int, bytes] | None:
    """The answer (`_post`) to a POST of the JSON `body` to `url`."""
    return _post(url, "application/json", body, version, platform, timeout_sec, max_bytes, "the project's server")


async def post_board(url: str, body: bytes, version: str, platform: str, max_bytes: int) -> tuple[int, bytes] | None:
    """`post_json` on a thread of its own, awaited, with a limit of its own (the answer carries the whole board); an error it did not expect is logged and is None too."""
    try:
        return await asyncio.wait_for(in_thread(lambda: post_json(url, body, version, platform, max_bytes=max_bytes), "sked-post"), TIMEOUT_SEC * 2 + FEED_GRACE_SEC)
    except TimeoutError:
        log.debug("posting to the HF test board did not end within %g s", TIMEOUT_SEC * 2 + FEED_GRACE_SEC)
        return None
    except Exception:
        log.exception("posting to the HF test board failed")
        return None


@dataclass(frozen=True)
class FeedAnswer:
    """What a layer's service or receiver answered: the status, the body unpacked (empty for a refusal) and the seconds its `Retry-After` asks to wait (None when it says none)."""
    status: int
    body: bytes
    retry_after_sec: float | None = None


def retry_after(value: str | None, now: datetime | None = None) -> float | None:
    """The seconds a `Retry-After` asks to wait: a number of seconds, or a date (from `now`, at least 0); None for none or one that cannot be read."""
    text = (value or "").strip()
    if not text:
        return None
    if text.isascii() and text.isdigit():
        return float(MAX_RETRY_AFTER_SEC if len(text) > 12 else min(int(text), MAX_RETRY_AFTER_SEC))
    try:
        when = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return min(float(MAX_RETRY_AFTER_SEC), max(0.0, (when - (now or datetime.now(UTC))).total_seconds()))


def unpacked(body: bytes, encoding: str, max_unpacked: int) -> bytes | None:
    """The body as it was before it was packed (gzip, or none); None when it is larger than `max_unpacked` unpacked, is cut short, is not gzip after all or is packed another way."""
    if encoding in ("", "identity"):
        return body if len(body) <= max_unpacked else None
    if encoding not in PACKED:
        return None
    unpacker = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        out = unpacker.decompress(body, max_unpacked + 1)
    except zlib.error:
        return None
    return out if len(out) <= max_unpacked and unpacker.eof else None


def get_feed(url: str, version: str, platform: str, headers: Mapping[str, str], max_packed: int, max_unpacked: int, timeout_sec: float = FEED_TIMEOUT_SEC) -> FeedAnswer | None:
    """The answer to a GET of a layer's `url` with the program's User-Agent, `headers` and a packed answer asked for; None when the address is not http(s), the server could not be reached, or the answer is
    larger than `max_packed` as it travels or `max_unpacked` unpacked, or it has not all come `timeout_sec` after the start. The log names the host, never the address as typed (an own receiver's may carry more)."""
    if not url.startswith(("http://", "https://")):
        return None
    deadline = time.monotonic() + timeout_sec
    url, authorization = without_password(url)
    request = urllib.request.Request(url, headers={**headers, "User-Agent": f"NeoAPRS/{version} ({platform})", "Accept-Encoding": "gzip"})  # noqa: S310  (http or https only: the lines above)
    if authorization is not None:
        request.add_unredirected_header(AUTHORIZATION, authorization)
    host = urlsplit(url).hostname or "?"
    try:
        nodevices.check_url(url, level=logging.DEBUG)                # (under the no-devices switch a server that is not on this computer is not there)
        with urllib.request.build_opener(https_handler(), _FeedRedirect, *nodevices.direct()).open(request, timeout=timeout_sec) as response:
            packed = _read_by(response, max_packed, deadline)
            if packed is None:
                log.debug("the answer of %s did not come within %g s", host, timeout_sec)
                return None
            body = None if len(packed) > max_packed else unpacked(packed, str(response.headers.get("Content-Encoding", "")).strip().lower(), max_unpacked)
            if body is None:
                log.debug("the answer of %s is larger than its bounds or cannot be unpacked", host)
                return None
            return FeedAnswer(int(response.status), body, retry_after(response.headers.get("Retry-After")))
    except urllib.error.HTTPError as e:
        return FeedAnswer(int(e.code), b"", retry_after(e.headers.get("Retry-After") if e.headers is not None else None))
    except (OSError, ValueError, http.client.HTTPException) as e:
        log.debug("%s could not be reached: %r", host, e)
        return None


async def fetch_feed(url: str, version: str, platform: str, headers: Mapping[str, str], max_packed: int, max_unpacked: int, timeout_sec: float = FEED_TIMEOUT_SEC) -> FeedAnswer | None:
    """`get_feed` on a thread of its own, awaited for `timeout_sec` and a little more at most (the thread of a server that drips its head is left to end on its own); an error it did not expect is logged and
    is None too."""
    try:
        return await asyncio.wait_for(in_thread(lambda: get_feed(url, version, platform, headers, max_packed, max_unpacked, timeout_sec), "layer-fetch"), timeout_sec + FEED_GRACE_SEC)
    except TimeoutError:
        log.debug("the question of %s did not end within %g s", urlsplit(url).hostname or "?", timeout_sec + FEED_GRACE_SEC)
        return None
    except Exception:
        log.exception("a question of the map's layers failed")
        return None
