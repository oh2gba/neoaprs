"""Files served over HTTP: the page (`Page`, from the snapshot in pagesnapshot.py) and the base map.

All answer only for a known Host name and carry the security headers.
"""

import datetime
import logging
import os
from collections.abc import Callable
from pathlib import Path, PurePath
from typing import Any, Iterator, Protocol

import tornado.httputil
import tornado.web

from neoaprs.worldmap import WORLD_FILE

from .headers import host_name, security_headers
from .pageerrors import one_line
from .pagesnapshot import PageFile, PageSnapshot, is_hidden

log = logging.getLogger("neoaprs.web")


class Gate(Protocol):
    def allowed(self, request: tornado.httputil.HTTPServerRequest) -> bool: ...
    def is_local(self, request: tornado.httputil.HTTPServerRequest) -> bool: ...


class HostGate(Protocol):
    @property
    def access(self) -> Gate: ...

    def host_allowed(self, header: str) -> bool: ...
    def note_foreign_host(self, shown: str) -> None: ...
    def secure_target(self, request: tornado.httputil.HTTPServerRequest) -> str | None: ...
    def this_computer_target(self, request: tornado.httputil.HTTPServerRequest) -> str | None: ...


def same_place(request: tornado.httputil.HTTPServerRequest) -> str:
    """Return the path and query for a redirect; it starts with a slash so the host cannot change."""
    path = request.path if request.path.startswith("/") else "/"
    return f"{path}?{request.query}" if request.query else path


def refuse_foreign_host(handler: tornado.web.RequestHandler, server: HostGate) -> bool:
    """Answer 403 and return True for a Host name that is not ours (DNS rebinding)."""
    header = handler.request.headers.get("Host", "")
    if server.host_allowed(header):
        return False
    shown = "".join(c if c.isprintable() else "?" for c in header[:80])
    server.note_foreign_host(shown)
    handler.set_status(403)
    handler.set_header("Content-Type", "text/plain; charset=utf-8")
    handler.set_header("X-Content-Type-Options", "nosniff")
    handler.finish(
        f"NeoAPRS does not answer to the name {shown!r}.\n"
        'If it is a name of this computer, allow it: neoaprs db set web/allowed_hosts "'
        + (host_name(shown) or "name")
        + '" (several names: separate them by commas), then restart NeoAPRS.\n'
    )
    return True


def refuse_plain(handler: tornado.web.RequestHandler, server: HostGate) -> bool:
    """Answer and return True for plain http from another device while the secure page is served.

    A page GET or HEAD is redirected with 307 (not permanent: the secure page can be switched off).
    """
    request = handler.request
    target = server.secure_target(request)
    if target is None:
        return False
    if request.method in ("GET", "HEAD") and request.headers.get("Upgrade", "").lower() != "websocket":
        handler.redirect(f"{target}{same_place(request)}", status=307)
        return True
    handler.set_status(403)
    handler.set_header("Content-Type", "text/plain; charset=utf-8")
    handler.set_header("X-Content-Type-Options", "nosniff")
    handler.finish(f"The page is on a secure connection now: open {target}/\n")
    return True


def send_to_this_computer(handler: tornado.web.RequestHandler, server: HostGate) -> bool:
    """Redirect a page GET or HEAD to http://127.0.0.1 (307) for another name of this computer.

    This applies only while the network is off, since no key is accepted then.
    """
    request = handler.request
    target = server.this_computer_target(request)
    if (
        target is None
        or request.method not in ("GET", "HEAD")
        or request.headers.get("Upgrade", "").lower() == "websocket"
    ):
        return False
    handler.redirect(f"{target}{same_place(request)}", status=307)
    return True


def refuse_unless_logged_in(handler: tornado.web.RequestHandler, server: HostGate) -> bool:
    """Answer 401 and return True when the device has not logged in; data routes are behind this."""
    if server.access.allowed(handler.request):
        return False
    handler.set_status(401)
    handler.set_header("Content-Type", "text/plain; charset=utf-8")
    handler.set_header("X-Content-Type-Options", "nosniff")
    handler.finish("Log in first: open the page and enter the access key.\n")
    return True


def is_hashed_asset(relative: PurePath) -> bool:
    """Return True for a file under assets/, whose name carries a content hash."""
    return len(relative.parts) > 1 and relative.parts[0] == "assets"


class TextErrors(tornado.web.RequestHandler):
    """Errors are a line of text, not Tornado's page; the log gets the details."""

    def write_error(self, status_code: int, **kwargs: Any) -> None:
        self.set_header("Content-Type", "text/plain; charset=utf-8")
        self.finish(f"{status_code} {self._reason}\n")

    def log_exception(self, typ: Any, value: Any, tb: Any) -> None:
        if isinstance(value, tornado.web.HTTPError):
            super().log_exception(typ, value, tb)  # Tornado logs an HTTPError with its message and no request
            return
        log.error(
            "Uncaught exception %s %s (%s)",
            self.request.method,
            one_line(self.request.path, MAX_LOGGED_PATH),
            self.request.remote_ip,
            exc_info=(typ, value, tb),
        )


class SecurityHeaders(TextErrors):
    """Set the Server name and the security headers on every response."""

    def set_default_headers(self) -> None:
        self.set_header("Server", "NeoAPRS")
        for name, value in security_headers(self.request.headers.get("Host", "")).items():
            self.set_header(name, value)


class Secured(SecurityHeaders):
    """Base of the file routes: refuse foreign Hosts and set the security headers."""

    def prepare(self) -> None:
        server = self.application.settings["neoaprs_server"]
        if not refuse_foreign_host(self, server) and not refuse_plain(self, server):
            send_to_this_computer(self, server)


# A request path is the sender's, so the log gets a truncated line of it.
MAX_LOGGED_PATH = 200
# Content types of the page's own file kinds, identical on every system. The Windows registry may
# say application/javascript or text/plain, under which (with nosniff) a browser runs no script.
PAGE_TYPES = {
    "js": "text/javascript; charset=UTF-8",
    "mjs": "text/javascript; charset=UTF-8",
    "css": "text/css; charset=UTF-8",
    "html": "text/html; charset=UTF-8",
    "json": "application/json",
    "webmanifest": "application/manifest+json",
    "svg": "image/svg+xml",
    "png": "image/png",
    "ico": "image/x-icon",
    "woff2": "font/woff2",
    "pmtiles": "application/octet-stream",
}


class Files(Secured, tornado.web.StaticFileHandler):
    """File routes: page file kinds get their PAGE_TYPES content type."""

    def get_content_type(self) -> str:
        name = self.absolute_path.replace("\\", "/").rsplit("/", 1)[-1] if self.absolute_path else ""
        known = PAGE_TYPES.get(name.rsplit(".", 1)[-1].lower()) if "." in name else None
        return known or super().get_content_type()


class Page(Files):
    """The page's files, served from the start-up snapshot, never from the folder."""

    def initialize(self, path: str, snapshot: PageSnapshot, default_filename: str | None = None) -> None:  # type: ignore[override]
        super().initialize(path, default_filename)
        self.snapshot = snapshot
        self._file: PageFile | None = None

    def validate_absolute_path(self, root: str, absolute_path: str) -> str | None:
        """Return the path to serve; hidden files and source maps give 404."""
        try:
            relative = Path(absolute_path).relative_to(root)
        except ValueError:
            raise tornado.web.HTTPError(403, "%s is not in root static directory", self.path) from None
        if is_hidden(relative):
            raise tornado.web.HTTPError(404)
        name = self.default_filename or "" if relative == Path() else relative.as_posix()
        self._file = self.snapshot.get(name)
        if self._file is None:
            raise tornado.web.HTTPError(404)
        return os.path.join(root, name)

    def get_content_size(self) -> int:
        assert self._file is not None
        return len(self._file.data)

    def get_modified_time(self) -> datetime.datetime | None:
        assert self._file is not None
        return self._file.modified

    def compute_etag(self) -> str | None:
        assert self._file is not None
        return self._file.etag

    def get_content(self, abspath: str, start: int | None = None, end: int | None = None) -> Iterator[bytes]:  # type: ignore[override]
        assert self._file is not None
        yield self._file.data[start:end]

    def set_extra_headers(self, path: str) -> None:
        # A name under assets/ carries a content hash, so it never changes.
        self.set_header(
            "Cache-Control", "public, max-age=31536000, immutable" if is_hashed_asset(PurePath(path)) else "no-cache"
        )
        self.set_header("X-Content-Type-Options", "nosniff")


class Basemap(Files):
    """The detailed map `basemap.pmtiles` and the world map under it, behind the login.

    The world map is the data folder's file when valid, else the shipped one.
    """

    def initialize(
        self,
        path: str,
        default_filename: str | None = None,
        world: Callable[[], Path | None] | None = None,  # type: ignore[override]
    ) -> None:
        super().initialize(path, default_filename)
        self._world = world

    def prepare(self) -> None:
        server = self.application.settings["neoaprs_server"]
        if not refuse_foreign_host(self, server) and not refuse_plain(self, server):
            refuse_unless_logged_in(self, server)

    def set_extra_headers(self, path: str) -> None:
        self.set_header("Cache-Control", "no-cache")
        self.set_header("X-Content-Type-Options", "nosniff")

    def compute_etag(self) -> str | None:
        """Return a tag from the file's size and mtime (Tornado's hash is cached and size-limited)."""
        if self.absolute_path is None:
            return None
        try:
            status = os.stat(self.absolute_path)
        except OSError:
            return None
        return f'"{status.st_size:x}-{status.st_mtime_ns:x}"'

    async def get(self, path: str, include_body: bool = True) -> None:
        if path == WORLD_FILE and self._world is not None:
            found = self._world()
            if found is None:
                raise tornado.web.HTTPError(
                    404,
                    reason="Not Found: there is no world map (the one that ships with the program is missing and the data folder's is not a PMTiles file)",
                )
            self.root = os.path.abspath(found.parent)  # the shipped file has the same name in another folder
        if not os.path.isfile(os.path.join(self.root, path)):
            raise tornado.web.HTTPError(
                404,
                reason="Not Found: the base map is not in the data folder, fetch it in the Settings tab, Map, Download",
            )
        await super().get(path, include_body)
