"""`POST /support/send`: Send logs of the Help group. The body is `{"page": {...}, "note": "..."}` (the page's facts as for `/support/bundle`, and what the person wrote, at most 2000 characters); the daemon makes the support bundle exactly as Download logs does and posts it with the
note, the call, the version and the platform to the project's server (`SUPPORT_URL`, `neoaprs/versions.py`), over https, in a thread. The answer is JSON, `{"ok": true, "ref": "NEO-20261103-1015-7F3A"}` (the reference the person can quote) or `{"ok": false, "reason": CODE}`.
Nothing is sent but by this request, which the page makes only when the person presses Send in its dialog; the route is behind the same login and Host gate as the bundle's.

The server answers the same JSON, `{"ok": true, "ref": ...}` or `{"ok": false, "reason": ...}` with a status that says it too; the reason it names is kept to the few the page has words for (`offline`, `rate`, `too_large`, `refused`)."""
import json
import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import tornado.web

from neoaprs.updatefetch import post
from neoaprs.versions import SUPPORT_URL

from .supporthandler import SupportBundle

log = logging.getLogger("neoaprs.web")

LOOPBACK_HOSTS = ("127.0.0.1", "localhost")
ENV_URL = "NEOAPRS_SUPPORT_URL"                  # development and tests: the address of a fake server on this computer, instead of SUPPORT_URL
MAX_NOTE = 2000                                  # characters of what the person writes (the dialog holds the same limit; the server cuts at it too)
MAX_SEND_BYTES = 20 * 1024 * 1024                # what the server takes in one request; a bundle is a megabyte or two
REFERENCE = re.compile(r"^NEO-\d{8}-\d{4}-[0-9A-F]{4,8}$")
REASONS = ("rate", "too_large")                 # what the server says that the page has a word for; everything else it refuses with is `refused`


@dataclass(frozen=True)
class Sent:
    """How the sending ended: the server's reference, or the reason it did not."""
    ok: bool
    ref: str = ""
    reason: str = ""
    detail: str = ""                                 # for the log: what the server said

    def wire(self) -> dict[str, Any]:
        return {"ok": True, "ref": self.ref} if self.ok else {"ok": False, "reason": self.reason}


def on_this_computer(text: str) -> bool:
    """Whether `text` is the address of a server on this computer: http or https, the host 127.0.0.1 or localhost, no user, no space."""
    try:
        parts = urlsplit(text)
        _ = parts.port                                  # (a port that is not a number raises)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and parts.hostname in LOOPBACK_HOSTS and "@" not in parts.netloc and not any(c.isspace() for c in text)


def support_url(environ: Mapping[str, str] = os.environ) -> str:
    """The server's address: the project's, or, for development and tests, the one of `NEOAPRS_SUPPORT_URL` when it is a server on this computer."""
    given = environ.get(ENV_URL, "").strip()
    return given if on_this_computer(given) else SUPPORT_URL


def answer_of(status: int, body: bytes) -> Sent:
    """What the server's answer means: a reference for `ok`, else the reason when it is one the page knows, else `refused`; a body that is not the JSON of the protocol is refused too."""
    try:
        said = json.loads(body)
    except ValueError:
        return Sent(False, reason="refused", detail=f"status {status}, no JSON")
    if not isinstance(said, dict):
        return Sent(False, reason="refused", detail=f"status {status}, no JSON object")
    ref = said.get("ref")
    if said.get("ok") is True and status == 200 and isinstance(ref, str) and REFERENCE.match(ref):
        return Sent(True, ref=ref)
    reason = said.get("reason")
    return Sent(False, reason=reason if reason in REASONS else "refused", detail=f"status {status}, {str(reason)[:40]!r}")


async def send_bundle(url: str, name: str, data: bytes, note: str, call: str, version: str, platform: str) -> Sent:
    """Posts the bundle with the note, the call, the version and the platform; `offline` when the server could not be reached."""
    if len(data) > MAX_SEND_BYTES:
        return Sent(False, reason="too_large", detail="over the limit, not sent")
    got = await post(url, {"note": note, "call": call, "version": version, "platform": platform}, {"bundle": (name, data)}, version, platform)
    if got is None:
        return Sent(False, reason="offline", detail="no connection")
    return answer_of(*got)


@tornado.web.stream_request_body
class SupportSend(SupportBundle):
    """The same protection and the same body as the bundle's route (`page`, 256 KB at the most), with the note beside the page."""

    async def post(self) -> None:
        body = self.json_body()
        note = body.get("note", "")
        if not isinstance(note, str):
            raise tornado.web.HTTPError(400, reason="Bad Request: the note is text")
        note = note.strip()[:MAX_NOTE]
        bundler = self.server.bundles
        if bundler.busy or bundler.sending:
            self.too_busy()
            return
        ctl = bundler.server.controller
        bundler.sending = True
        try:
            name, data = await self.made(body["page"])
            sent = await send_bundle(support_url(), name, data, note, ctl.config.station_call, ctl.updatecheck.version, ctl.updatecheck.platform)
        finally:
            bundler.sending = False
        size = f"{max(1, len(data) // 1024)} KB"
        if sent.ok:
            log.info("support logs sent: %s, %s, reference %s, a note of %d characters", name, size, sent.ref, len(note))
        else:
            log.warning("support logs not sent: %s (%s), %s, a note of %d characters", sent.reason, sent.detail, size, len(note))
        self.set_header("Content-Type", "application/json")
        self.set_header("Cache-Control", "no-store")
        self.finish(json.dumps(sent.wire()))
