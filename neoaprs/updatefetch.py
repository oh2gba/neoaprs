"""Small HTTP requests of the daemon, each run in its own thread so they work on every event loop.

A failure of any kind gives None. A POST returns the status and body even for a refusal;
`get_feed` is the GET of the map's traffic layers, unpacked within a bound.
"""
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
MAX_BYTES = 8192
# per wait for the server while the support file uploads
SEND_TIMEOUT_SEC = 60.0
# a layer's request, its whole answer included
FEED_TIMEOUT_SEC = 10.0
# wait beyond that for the request's thread (a server that drips its headers)
FEED_GRACE_SEC = 1.0
# the longest a `Retry-After` is believed
MAX_RETRY_AFTER_SEC = 3600
POST_TOTAL_SEC = 300.0
FEED_CHUNK = 65536
AUTHORIZATION = "Authorization"
PACKED = ("gzip", "x-gzip")


class _NotDowngraded(NotDowngraded):
    def check(self, newurl: str) -> None:
        # under the no-devices switch a server on this computer cannot redirect elsewhere
        nodevices.check_url(newurl, level=logging.DEBUG)


class _FeedRedirect(_NotDowngraded):
    """Pass basic authentication on a redirect only to the same scheme, host and port."""

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
    parts = urlsplit(url)
    if "@" not in parts.netloc:
        return url, None
    userinfo, _, hostport = parts.netloc.rpartition("@")
    user, _, password = userinfo.partition(":")
    token = base64.b64encode(f"{unquote(user)}:{unquote(password)}".encode()).decode("ascii")
    return urlunsplit(parts._replace(netloc=hostport)), f"Basic {token}"


def _read_by(response: http.client.HTTPResponse, limit: int, deadline: float) -> bytes | None:
    """Read at most `limit` + 1 bytes in pieces; return None if the monotonic `deadline` passes."""
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
    """Do not follow redirects of a POST; the redirect is the answer."""

    def redirect_request(self, req: urllib.request.Request, fp: IO[bytes], code: int, msg: str, headers: http.client.HTTPMessage, newurl: str) -> urllib.request.Request | None:
        return None


def request_url(base: str, version: str, platform: str, install_id: str = "") -> str:
    parts = urllib.parse.urlsplit(base)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    added = [("v", version), ("os", platform), *([("id", install_id)] if install_id else [])]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode([*query, *added])))


def get_answer(url: str, version: str, platform: str, timeout_sec: float = TIMEOUT_SEC, max_bytes: int = MAX_BYTES) -> tuple[int, bytes] | None:
    """Return the status and body of a GET of `url`; None if unreachable, too long or too slow."""
    if not url.startswith(("http://", "https://")):
        # urllib also reads file: and ftp: addresses
        return None
    deadline = time.monotonic() + timeout_sec
    request = urllib.request.Request(url, headers={"User-Agent": f"NeoAPRS/{version} ({platform})"})  # noqa: S310  (http or https only)
    try:
        # under the no-devices switch only this computer is reachable
        nodevices.check_url(url, level=logging.DEBUG)
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
    answer = get_answer(url, version, platform, timeout_sec, max_bytes)
    return answer[1] if answer is not None and answer[0] == 200 else None


def get(base: str, version: str, platform: str, install_id: str = "", timeout_sec: float = TIMEOUT_SEC) -> bytes | None:
    if not base.startswith(("http://", "https://")):
        return None
    return get_url(request_url(base, version, platform, install_id), version, platform, timeout_sec)


async def _quietly(work: Callable[[], bytes | None], name: str) -> bytes | None:
    try:
        return await asyncio.wait_for(in_thread(work, name), TIMEOUT_SEC + FEED_GRACE_SEC)
    except TimeoutError:
        log.debug("the update check did not end within %g s", TIMEOUT_SEC + FEED_GRACE_SEC)
        return None
    except Exception:
        log.exception("the update check failed")
        return None


async def fetch_answer(url: str, version: str, platform: str, max_bytes: int) -> tuple[int, bytes] | None:
    try:
        return await asyncio.wait_for(in_thread(lambda: get_answer(url, version, platform, max_bytes=max_bytes), "update-fetch"), TIMEOUT_SEC + FEED_GRACE_SEC)
    except TimeoutError:
        log.debug("the update check did not end within %g s", TIMEOUT_SEC + FEED_GRACE_SEC)
        return None
    except Exception:
        log.exception("the update check failed")
        return None


async def fetch(base: str, version: str, platform: str, install_id: str = "") -> bytes | None:
    return await _quietly(lambda: get(base, version, platform, install_id), "update-check")


async def fetch_url(url: str, version: str, platform: str, max_bytes: int) -> bytes | None:
    return await _quietly(lambda: get_url(url, version, platform, max_bytes=max_bytes), "update-fetch")


def multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes]]) -> tuple[str, bytes]:
    """Return (Content-Type, body) of a multipart form; `files` maps field to (name, content)."""
    boundary = "neoaprs-" + secrets.token_hex(16)
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode() + value.encode("utf-8") + b"\r\n")
    for name, (filename, content) in files.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + content + b"\r\n")
    return f"multipart/form-data; boundary={boundary}", b"".join(parts) + f"--{boundary}--\r\n".encode()


def _body_of(response: IO[bytes], max_bytes: int, timeout_sec: float) -> bytes:
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
    """Return the status and body of a POST, whatever the status; None if unreachable."""
    if not url.startswith(("http://", "https://")):
        return None
    request = urllib.request.Request(url, data=body, method="POST", headers={"User-Agent": f"NeoAPRS/{version} ({platform})", "Content-Type": content_type})  # noqa: S310  (http or https only)
    try:
        # under the no-devices switch nothing is sent to another computer
        nodevices.check_url(url)
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
    content_type, body = multipart(fields, files)
    return _post(url, content_type, body, version, platform, timeout_sec, max_bytes, "the support server")


async def post(url: str, fields: dict[str, str], files: dict[str, tuple[str, bytes]], version: str, platform: str) -> tuple[int, bytes] | None:
    try:
        return await asyncio.wait_for(in_thread(lambda: post_form(url, fields, files, version, platform), "support-send"), POST_TOTAL_SEC)
    except TimeoutError:
        log.debug("sending the support logs did not end within %g s", POST_TOTAL_SEC)
        return None
    except Exception:
        log.exception("sending the support logs failed")
        return None


def post_json(url: str, body: bytes, version: str, platform: str, timeout_sec: float = TIMEOUT_SEC, max_bytes: int = MAX_BYTES) -> tuple[int, bytes] | None:
    return _post(url, "application/json", body, version, platform, timeout_sec, max_bytes, "the project's server")


async def post_board(url: str, body: bytes, version: str, platform: str, max_bytes: int) -> tuple[int, bytes] | None:
    """Run `post_json` on its own thread; the answer is the whole board."""
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
    """A layer's answer: status, unpacked body (empty for a refusal) and the `Retry-After` wait."""
    status: int
    body: bytes
    retry_after_sec: float | None = None


def retry_after(value: str | None, now: datetime | None = None) -> float | None:
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
    """Return the body unpacked (gzip or none), or None if too large, truncated or other packing."""
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
    """GET a layer's `url` asking for gzip; None if unreachable, over a bound or too slow.

    The log names only the host: an own receiver's address may carry more.
    """
    if not url.startswith(("http://", "https://")):
        return None
    deadline = time.monotonic() + timeout_sec
    url, authorization = without_password(url)
    request = urllib.request.Request(url, headers={**headers, "User-Agent": f"NeoAPRS/{version} ({platform})", "Accept-Encoding": "gzip"})  # noqa: S310  (http or https only)
    if authorization is not None:
        request.add_unredirected_header(AUTHORIZATION, authorization)
    host = urlsplit(url).hostname or "?"
    try:
        nodevices.check_url(url, level=logging.DEBUG)
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
    """Run `get_feed` on its own thread; a thread that hangs is left to end by itself."""
    try:
        return await asyncio.wait_for(in_thread(lambda: get_feed(url, version, platform, headers, max_packed, max_unpacked, timeout_sec), "layer-fetch"), timeout_sec + FEED_GRACE_SEC)
    except TimeoutError:
        log.debug("the question of %s did not end within %g s", urlsplit(url).hostname or "?", timeout_sec + FEED_GRACE_SEC)
        return None
    except Exception:
        log.exception("a question of the map's layers failed")
        return None
