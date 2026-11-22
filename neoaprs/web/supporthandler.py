"""`POST /support/bundle`: the support bundle as a zip download.

The body is `{"page": {...}}`, at most 256 KB; the route is protected like the page's socket.
One bundle is made at a time (a second gets 429). The latest is kept for an hour for Send.
"""

import asyncio
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Protocol

import tornado.web

from neoaprs.controller import Controller

from .headers import refuse_foreign_origin
from .pagefiles import HostGate, SecurityHeaders, refuse_foreign_host, refuse_plain, refuse_unless_logged_in
from .pageerrors import PageErrors
from .supportstate import LiveHost, live_state

log = logging.getLogger("neoaprs.web")

MAX_BODY = 256 * 1024
RETRY_AFTER_SEC = 10
KEEP_SEC = 3600


class BundleHost(HostGate, Protocol):
    bundles: "Bundler"


class Bundler:
    def __init__(self, server: LiveHost) -> None:
        self.server = server
        self.busy = False  # a bundle is being made
        self.sending = False  # a bundle is being made and sent
        self.kept: tuple[str, bytes] | None = None  # (name, zip) of the latest download
        self.forgetting: asyncio.TimerHandle | None = None

    def keep(self, name: str, data: bytes) -> None:
        """Keep the downloaded bundle for an hour, replacing the previous one."""
        self.forget()
        self.kept = (name, data)
        self.forgetting = asyncio.get_running_loop().call_later(KEEP_SEC, self.forget)

    def forget(self) -> None:
        if self.forgetting is not None:
            self.forgetting.cancel()
        self.kept, self.forgetting = None, None

    async def make(self, page: dict[str, Any]) -> tuple[str, bytes]:
        """Return (file name, zip); state is read on the loop, files are zipped in a thread."""
        ctl: Controller = self.server.controller
        errors: PageErrors = self.server.api.page_errors
        # set before the first await so a concurrent request is refused
        self.busy = True
        try:
            live = await live_state(self.server)
            recorded = errors.snapshot()

            def build() -> tuple[str, bytes]:
                from neoaprs.cli.supportmake import make_bundle

                with tempfile.TemporaryDirectory(prefix="neoaprs-support-") as folder:
                    made = make_bundle(
                        ctl.data_dir,
                        Path(folder),
                        live=live,
                        page=page,
                        page_errors=recorded,
                        install=ctl.install,
                        running=True,
                        by="the running daemon, asked by the page",
                        now=ctl.clock,
                        call=ctl.config.station_call,
                    )
                    return made.path.name, made.path.read_bytes()

            return await asyncio.to_thread(build)
        finally:
            self.busy = False


@tornado.web.stream_request_body
class SupportBundle(SecurityHeaders):
    """Read the body in pieces so this route alone can allow 256 KB (the default is 64 KB)."""

    def initialize(self, server: BundleHost) -> None:
        self.server = server
        self.chunks: list[bytes] = []
        self.size = 0

    def prepare(self) -> None:
        if (
            refuse_foreign_host(self, self.server)
            or refuse_plain(self, self.server)
            or refuse_unless_logged_in(self, self.server)
        ):
            return
        refuse_foreign_origin(self.request)
        widen = getattr(self.request.connection, "set_max_body_size", None)
        if widen is not None:
            widen(MAX_BODY)

    def data_received(self, chunk: bytes) -> None:
        if not self._finished:
            self.chunks.append(chunk)
            self.size += len(chunk)

    def json_body(self) -> dict[str, Any]:
        """Return the body, a JSON object with a `page` object; raise 400 otherwise."""
        try:
            body = json.loads(b"".join(self.chunks))
            page = body["page"]
        except (ValueError, KeyError, TypeError, RecursionError):
            raise tornado.web.HTTPError(400, reason="Bad Request: the body is a JSON object with a page") from None
        if not isinstance(page, dict):
            raise tornado.web.HTTPError(400, reason="Bad Request: the page is a JSON object")
        return dict(body)

    def too_busy(self) -> None:
        self.set_status(429)
        self.set_header("Retry-After", str(RETRY_AFTER_SEC))
        self.finish("429 Too Many Requests: a support bundle is being made; try again in a moment\n")

    async def made(self, page: dict[str, Any]) -> tuple[str, bytes]:
        """Return (name, zip) for the page; raise 500 if the bundle cannot be made."""
        try:
            return await self.server.bundles.make(page)
        except Exception:
            log.exception("the support bundle for the page could not be made")
            raise tornado.web.HTTPError(
                500, reason="Internal Server Error: the support bundle could not be made, the log says why"
            ) from None

    async def post(self) -> None:
        page = self.json_body()["page"]
        bundler = self.server.bundles
        if bundler.busy or bundler.sending:
            self.too_busy()
            return
        name, data = await self.made(page)
        bundler.keep(name, data)
        log.info("support bundle made for the page: %s, %d KB", name, max(1, len(data) // 1024))
        self.set_header("Content-Type", "application/zip")
        self.set_header("Content-Disposition", f'attachment; filename="{name}"')
        self.set_header("Cache-Control", "no-store")
        self.finish(data)
