"""One GET of the open data that the map shows ships and aircraft from (Digitraffic's AIS, adsb.fi's ADS-B): JSON, asked for gzip (Digitraffic answers 406 without it), at most `max_bytes` unpacked, with a
User-Agent and the `Digitraffic-User` header that Digitraffic asks an application to send. A failure of any kind is an error with the system's or the server's words, which the feed shows and tries again
after. Under the no-devices switch a server that is not on this computer is not there (`nodevices.check_url`). Only reads: nothing of the program is sent but the address itself."""
import gzip
import http.client
import json
import logging
import urllib.error
import urllib.request
import zlib
from typing import Any

from . import nodevices
from .httpstrust import https_handler

log = logging.getLogger("neoaprs.traffic")

TIMEOUT_SEC = 30.0


class FetchError(Exception):
    """Why the data could not be had, in words for the page's status row (`HTTP 503`, `timed out`, `not JSON`)."""


def _unpacked(body: bytes, encoding: str, max_bytes: int) -> bytes:
    if encoding.strip().lower() != "gzip":
        return body
    try:
        unpacker = zlib.decompressobj(16 + zlib.MAX_WBITS)
        data = unpacker.decompress(body, max_bytes + 1)
    except (zlib.error, gzip.BadGzipFile) as e:
        raise FetchError("the answer is not gzip") from e
    if len(data) > max_bytes:
        raise FetchError("the answer is too long")
    return data


def get_json(url: str, user: str, max_bytes: int, timeout_sec: float = TIMEOUT_SEC) -> Any:
    """The JSON of the answer to a GET of `url` (https only); raises FetchError."""
    if not url.startswith("https://"):
        raise FetchError("not an https address")
    request = urllib.request.Request(url, headers={"User-Agent": user, "Digitraffic-User": user, "Accept-Encoding": "gzip", "Accept": "application/json"})  # noqa: S310  (https only: above)
    try:
        nodevices.check_url(url, level=logging.DEBUG)
        with urllib.request.build_opener(https_handler(), *nodevices.direct()).open(request, timeout=timeout_sec) as response:
            body = bytes(response.read(max_bytes + 1))
            encoding = str(response.headers.get("Content-Encoding", ""))
    except urllib.error.HTTPError as e:
        raise FetchError(f"HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise FetchError(str(e.reason)) from e
    except (OSError, ValueError, http.client.HTTPException) as e:
        raise FetchError(str(e) or type(e).__name__) from e
    if len(body) > max_bytes:
        raise FetchError("the answer is too long")
    try:
        return json.loads(_unpacked(body, encoding, max_bytes))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise FetchError("the answer is not JSON") from e
