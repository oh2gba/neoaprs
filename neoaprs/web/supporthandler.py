"""`POST /support/bundle`: the support bundle (neoaprs/cli/supportmake.py) for the page's Support button. The body is `{"page": {...}}`, what the page tells of itself (its build, the browser, its recent errors), at most 256 KB; the answer is the zip,
`application/zip`, as a download.

It is protected as the page's socket is: only for a Host name of ours, never over plain http when the secure page is served, and from another device only with the session of the access key; a request of another site's script (an
`Origin` that is not the `Host`) is refused. One bundle is made at a time (a second request is answered `429`), in a thread, so that the loop goes on with the radio while the logs are read."""
import asyncio
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Protocol

import tornado.web

from neoaprs.cli.supportmake import make_bundle
from neoaprs.controller import Controller

from .headers import origin_is_host
from .pagefiles import HostGate, SecurityHeaders, refuse_foreign_host, refuse_plain, refuse_unless_logged_in
from .pageerrors import PageErrors
from .supportstate import LiveHost, live_state

log = logging.getLogger("neoaprs.web")

MAX_BODY = 256 * 1024
RETRY_AFTER_SEC = 10


class BundleHost(HostGate, Protocol):
    """What the handler needs of the WebServer."""
    bundles: "Bundler"


class Bundler:
    """Makes the bundles of a running daemon, one at a time."""

    def __init__(self, server: LiveHost) -> None:
        self.server = server
        self.busy = False

    async def make(self, page: dict[str, Any]) -> tuple[str, bytes]:
        """(the name of the file, the zip). The state is read here, on the loop; the files are read and the zip is written in a thread."""
        ctl: Controller = self.server.controller
        errors: PageErrors = self.server.api.page_errors
        self.busy = True                                     # (before the first wait: a second request that comes meanwhile is refused)
        try:
            live = await live_state(self.server)
            recorded = errors.snapshot()

            def build() -> tuple[str, bytes]:
                with tempfile.TemporaryDirectory(prefix="neoaprs-support-") as folder:
                    made = make_bundle(ctl.data_dir, Path(folder), live=live, page=page, page_errors=recorded, install=ctl.install, running=True, by="the running daemon, asked by the page", now=ctl.clock, call=ctl.config.station_call)
                    return made.path.name, made.path.read_bytes()
            return await asyncio.to_thread(build)
        finally:
            self.busy = False


@tornado.web.stream_request_body
class SupportBundle(SecurityHeaders):
    """The body is read in pieces so that its size can be held to 256 KB for this route alone (the rest of the server takes 64 KB)."""

    def initialize(self, server: BundleHost) -> None:
        self.server = server
        self.chunks: list[bytes] = []
        self.size = 0

    def prepare(self) -> None:
        if refuse_foreign_host(self, self.server) or refuse_plain(self, self.server) or refuse_unless_logged_in(self, self.server):
            return
        origin = self.request.headers.get("Origin")
        if origin is not None and not origin_is_host(origin, self.request.headers.get("Host", "")):
            raise tornado.web.HTTPError(403)
        widen = getattr(self.request.connection, "set_max_body_size", None)
        if widen is not None:
            widen(MAX_BODY)

    def data_received(self, chunk: bytes) -> None:
        if not self._finished:
            self.chunks.append(chunk)
            self.size += len(chunk)

    async def post(self) -> None:
        try:
            body = json.loads(b"".join(self.chunks))
            page = body["page"]
        except (ValueError, KeyError, TypeError):
            raise tornado.web.HTTPError(400, reason="Bad Request: the body is a JSON object with a page") from None
        if not isinstance(page, dict):
            raise tornado.web.HTTPError(400, reason="Bad Request: the page is a JSON object")
        bundler = self.server.bundles
        if bundler.busy:
            self.set_status(429)
            self.set_header("Retry-After", str(RETRY_AFTER_SEC))
            self.finish("429 Too Many Requests: a support bundle is being made; try again in a moment\n")
            return
        try:
            name, data = await bundler.make(page)
        except Exception:
            log.exception("the support bundle for the page could not be made")
            raise tornado.web.HTTPError(500, reason="Internal Server Error: the support bundle could not be made, the log says why") from None
        log.info("support bundle made for the page: %s, %d KB", name, max(1, len(data) // 1024))
        self.set_header("Content-Type", "application/zip")
        self.set_header("Content-Disposition", f'attachment; filename="{name}"')
        self.set_header("Cache-Control", "no-store")
        self.finish(data)
