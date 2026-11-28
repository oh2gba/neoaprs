"""`POST /support/send`: send feedback and logs to the project's server.

The body is `{"page", "note", "file", "email"}`; `file` is true (new bundle), a kept bundle's name,
or false (note only); `email` is an optional address for a reply. The answer is `{"ok": true, "ref"}` or `{"ok": false, "reason"}`.
"""

import json
import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import tornado.web

from neoaprs.updatefetch import post
from neoaprs.versions import SUPPORT_URL, on_this_computer

from .supporthandler import SupportBundle

log = logging.getLogger("neoaprs.web")

# Tests: the address of a fake server on this computer, instead of SUPPORT_URL.
ENV_URL = "NEOAPRS_SUPPORT_URL"
MAX_NOTE = 2000  # characters; the dialog applies the same limit
# what send.php keeps of a note (support_note): tab, line break and printable text
_NOT_KEPT = re.compile("[^\t\n\x20-\x7e\xa0-\U0010ffff]")


def support_note(text: str) -> str:
    """Return the note as send.php keeps it: control characters dropped, cut to MAX_NOTE, trimmed."""
    # A lone surrogate from JSON cannot be encoded; it becomes "?".
    text = text.encode("utf-8", "replace").decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return _NOT_KEPT.sub("", text)[:MAX_NOTE].strip(" \t\n\r\0\x0b")
MAX_SEND_BYTES = 10 * 1024 * 1024  # what the server takes in one request
MAX_EMAIL = 254  # characters, the longest address RFC 5321 lets through
# blanks and controls, Unicode white space and lone surrogates; send.php and the page refuse the same
_NOT_IN_ADDRESS = re.compile(
    r"[\x00-\x20\x7f-\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff\ud800-\udfff]"
)
REFERENCE = re.compile(r"^NEO-\d{8}-\d{4}-[0-9A-F]{4,8}$")
# Reasons the page has words for; any other refusal is `refused`.
REASONS = ("rate", "too_large")


@dataclass(frozen=True)
class Sent:
    ok: bool
    ref: str = ""
    reason: str = ""
    detail: str = ""  # what the server said, for the log

    def wire(self) -> dict[str, Any]:
        return {"ok": True, "ref": self.ref} if self.ok else {"ok": False, "reason": self.reason}


def reply_address(value: object) -> str:
    """Return the address for a reply, or "" for none or one that is not an address."""
    if not isinstance(value, str) or len(value) > MAX_EMAIL or _NOT_IN_ADDRESS.search(value):
        return ""
    local, at, domain = value.partition("@")
    return value if at and local and domain and "@" not in domain else ""


def support_url(environ: Mapping[str, str] = os.environ) -> str:
    """Return SUPPORT_URL, or `NEOAPRS_SUPPORT_URL` when that is a server on this computer."""
    given = environ.get(ENV_URL, "").strip()
    return given if on_this_computer(given) else SUPPORT_URL


def answer_of(status: int, body: bytes) -> Sent:
    """Return a reference, a reason the page knows, or `refused` (also for a non-protocol body)."""
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
    return Sent(
        False, reason=reason if reason in REASONS else "refused", detail=f"status {status}, {str(reason)[:40]!r}"
    )


def told(sent: Sent, bundle: tuple[str, bytes] | None, chars: int) -> None:
    """Log the outcome of a send; never the note text."""
    size = "" if bundle is None else f"{max(1, len(bundle[1]) // 1024)} KB"
    if bundle is None and sent.ok:
        log.info("feedback sent without the logs: reference %s, a note of %d characters", sent.ref, chars)
    elif bundle is None:
        log.warning(
            "feedback without the logs not sent: %s (%s), a note of %d characters", sent.reason, sent.detail, chars
        )
    elif sent.ok:
        log.info("support logs sent: %s, %s, reference %s, a note of %d characters", bundle[0], size, sent.ref, chars)
    else:
        log.warning(
            "support logs not sent: %s (%s), %s, a note of %d characters", sent.reason, sent.detail, size, chars
        )


async def send_bundle(
    url: str, bundle: tuple[str, bytes] | None, note: str, email: str, call: str, version: str, platform: str
) -> Sent:
    """Post the note and the bundle (unless the note goes alone); `offline` if unreachable."""
    if bundle is not None and len(bundle[1]) > MAX_SEND_BYTES:
        return Sent(False, reason="too_large", detail="over the limit, not sent")
    got = await post(
        url,
        {"note": note, "email": email, "call": call, "version": version, "platform": platform},
        {} if bundle is None else {"bundle": bundle},
        version,
        platform,
    )
    if got is None:
        return Sent(False, reason="offline", detail="no connection")
    return answer_of(*got)


@tornado.web.stream_request_body
class SupportSend(SupportBundle):
    """The bundle route's protection and body, plus the note and the file choice."""

    def words(self, body: dict[str, Any]) -> tuple[str, bool | str]:
        """Return (note, file) where file is False, a downloaded bundle's name or True.

        Raise 400 on bad input.
        """
        note, file = body.get("note", ""), body.get("file", True)
        if not isinstance(note, str):
            raise tornado.web.HTTPError(400, reason="Bad Request: the note is text")
        if not isinstance(file, (bool, str)):
            raise tornado.web.HTTPError(
                400, reason="Bad Request: the file is true, false or the name of a downloaded one"
            )
        note = support_note(note)
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
            bundle = (
                None
                if file is False
                else bundler.kept
                if bundler.kept is not None and bundler.kept[0] == file
                else await self.made(body["page"])
            )
            sent = await send_bundle(
                support_url(),
                bundle,
                note,
                reply_address(body.get("email")),
                ctl.config.station_call,
                ctl.updatecheck.version,
                ctl.updatecheck.platform,
            )
        finally:
            bundler.sending = False
        if sent.ok:
            bundler.forget()
        told(sent, bundle, len(note))
        self.set_header("Content-Type", "application/json")
        self.set_header("Cache-Control", "no-store")
        self.finish(json.dumps(sent.wire()))
