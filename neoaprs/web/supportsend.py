"""`POST /support/send`: Send feedback / logs of the Help group. The body is `{"page": {...}, "note": "...", "file": ...}` (the page's facts as for `/support/bundle`; what the person wrote, at most 2000 characters; and which file goes with it).
Without `file` (or with `true`) the daemon makes the support bundle exactly as Download logs does; with the name of the bundle the person downloaded from the dialog it sends that very one, the file they looked into, while it still has it
(`Bundler.kept`, an hour; a new one is made after that); with `false` no file goes, only the note, which then must have words. It posts the bundle and the note, the call, the version and the platform to the project's server
(`SUPPORT_URL`, `neoaprs/versions.py`), over https, in a thread. The answer is JSON, `{"ok": true, "ref": "NEO-20261103-1015-7F3A"}` (the reference the person can quote) or `{"ok": false, "reason": CODE}`.
The page makes this request when the person presses Send in its dialog; the route is behind the same login and Host gate as the bundle's.

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
MAX_SEND_BYTES = 10 * 1024 * 1024                # what the server takes in one request; a bundle is a megabyte or two
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


def told(sent: Sent, bundle: tuple[str, bytes] | None, chars: int) -> None:
    """The line of the log for a send: what went or why not, the size, the reference, and how long the note was; never its text."""
    size = "" if bundle is None else f"{max(1, len(bundle[1]) // 1024)} KB"
    if bundle is None and sent.ok:
        log.info("feedback sent without the logs: reference %s, a note of %d characters", sent.ref, chars)
    elif bundle is None:
        log.warning("feedback without the logs not sent: %s (%s), a note of %d characters", sent.reason, sent.detail, chars)
    elif sent.ok:
        log.info("support logs sent: %s, %s, reference %s, a note of %d characters", bundle[0], size, sent.ref, chars)
    else:
        log.warning("support logs not sent: %s (%s), %s, a note of %d characters", sent.reason, sent.detail, size, chars)


async def send_bundle(url: str, bundle: tuple[str, bytes] | None, note: str, call: str, version: str, platform: str) -> Sent:
    """Posts the note, the call, the version and the platform, with the bundle (its name, the zip) unless the note goes alone; `offline` when the server could not be reached."""
    if bundle is not None and len(bundle[1]) > MAX_SEND_BYTES:
        return Sent(False, reason="too_large", detail="over the limit, not sent")
    got = await post(url, {"note": note, "call": call, "version": version, "platform": platform}, {} if bundle is None else {"bundle": bundle}, version, platform)
    if got is None:
        return Sent(False, reason="offline", detail="no connection")
    return answer_of(*got)


@tornado.web.stream_request_body
class SupportSend(SupportBundle):
    """The same protection and the same body as the bundle's route (`page`, 256 KB at the most), with the note and the choice of the file beside the page."""

    def words(self, body: dict[str, Any]) -> tuple[str, bool | str]:
        """(the note, the file: `False` for none, the name of a downloaded bundle, `True` for a new one); a `400` for what is neither, and for no file and no words."""
        note, file = body.get("note", ""), body.get("file", True)
        if not isinstance(note, str):
            raise tornado.web.HTTPError(400, reason="Bad Request: the note is text")
        if not isinstance(file, (bool, str)):
            raise tornado.web.HTTPError(400, reason="Bad Request: the file is true, false or the name of a downloaded one")
        note = note.strip()[:MAX_NOTE].encode("utf-8", "replace").decode("utf-8")       # (JSON lets a lone surrogate through, a half of an emoji, which no form can carry: it is a "?")
        if file is False and note == "":
            raise tornado.web.HTTPError(400, reason="Bad Request: a note without the file has words")
        return note, file

    async def post(self) -> None:
        body = self.json_body()
        note, file = self.words(body)
        bundler = self.server.bundles
        if bundler.busy or bundler.sending:
            self.too_busy()
            return
        ctl = bundler.server.controller
        bundler.sending = True
        try:
            bundle = None if file is False else bundler.kept if bundler.kept is not None and bundler.kept[0] == file else await self.made(body["page"])
            sent = await send_bundle(support_url(), bundle, note, ctl.config.station_call, ctl.updatecheck.version, ctl.updatecheck.platform)
        finally:
            bundler.sending = False
        if sent.ok:
            bundler.forget()
        told(sent, bundle, len(note))
        self.set_header("Content-Type", "application/json")
        self.set_header("Cache-Control", "no-store")
        self.finish(json.dumps(sent.wire()))
