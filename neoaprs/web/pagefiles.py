"""The files the daemon serves over HTTP: the page's own (`Page`, from the snapshot of neoaprs/web/pagesnapshot.py) and the base map from the data folder (`Basemap`). All answer only for a Host name of ours and carry the security headers; the
files handler of Tornado does the byte ranges. A path that does not exist is a 404 with a line of text."""
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
from .pagesnapshot import PageFile, PageSnapshot, is_hidden

log = logging.getLogger("neoaprs.web")


class Gate(Protocol):
    def allowed(self, request: tornado.httputil.HTTPServerRequest) -> bool: ...


class HostGate(Protocol):
    @property
    def access(self) -> Gate: ...

    def host_allowed(self, header: str) -> bool: ...
    def note_foreign_host(self, shown: str) -> None: ...
    def secure_target(self, request: tornado.httputil.HTTPServerRequest) -> str | None: ...


def refuse_foreign_host(handler: tornado.web.RequestHandler, server: HostGate) -> bool:
    """Answers 403 and returns True when the request was made for a host name that is not ours (DNS rebinding: a page of another site whose name was moved to this address)."""
    header = handler.request.headers.get("Host", "")
    if server.host_allowed(header):
        return False
    shown = "".join(c if c.isprintable() else "?" for c in header[:80])
    server.note_foreign_host(shown)
    handler.set_status(403)
    handler.set_header("Content-Type", "text/plain; charset=utf-8")
    handler.set_header("X-Content-Type-Options", "nosniff")
    handler.finish(f"NeoAPRS does not answer to the name {shown!r}.\n"
                   "If it is a name of this computer, allow it: neoaprs db set web/allowed_hosts \"" + (host_name(shown) or "name") + "\" (several names: separate them by commas), then restart NeoAPRS.\n")
    return True


def refuse_plain(handler: tornado.web.RequestHandler, server: HostGate) -> bool:
    """Answers and returns True when the request came over plain http from another device while the secure page is served (neoaprs/web/securehandlers.py): a GET or HEAD of a page is sent on to the same address on the
    secure port (307: the secure page can be switched off again), the rest (the socket, a login, the map) is refused with a line that says where the page is."""
    request = handler.request
    target = server.secure_target(request)
    if target is None:
        return False
    if request.method in ("GET", "HEAD") and request.headers.get("Upgrade", "").lower() != "websocket":
        handler.redirect(f"{target}{request.uri or '/'}", status=307)
        return True
    handler.set_status(403)
    handler.set_header("Content-Type", "text/plain; charset=utf-8")
    handler.set_header("X-Content-Type-Options", "nosniff")
    handler.finish(f"The page is on a secure connection now: open {target}/\n")
    return True


def refuse_unless_logged_in(handler: tornado.web.RequestHandler, server: HostGate) -> bool:
    """Answers 401 and returns True when the request comes from a device that has not logged in (neoaprs/web/access.py): what carries data is behind it."""
    if server.access.allowed(handler.request):
        return False
    handler.set_status(401)
    handler.set_header("Content-Type", "text/plain; charset=utf-8")
    handler.set_header("X-Content-Type-Options", "nosniff")
    handler.finish("Log in first: open the page and enter the access key.\n")
    return True


def is_hashed_asset(relative: PurePath) -> bool:
    """A file under assets/, whose name has the hash of its content."""
    return len(relative.parts) > 1 and relative.parts[0] == "assets"


class TextErrors(tornado.web.RequestHandler):
    """An error is a line of text, not Tornado's page; Tornado logs a request whose handler raised with the whole request, which for the socket is /ws and for nothing else a secret, but the
    log gets the method, the path and the address, and the traceback."""

    def write_error(self, status_code: int, **kwargs: Any) -> None:
        self.set_header("Content-Type", "text/plain; charset=utf-8")
        self.finish(f"{status_code} {self._reason}\n")

    def log_exception(self, typ: Any, value: Any, tb: Any) -> None:
        if isinstance(value, tornado.web.HTTPError):
            super().log_exception(typ, value, tb)                    # an HTTPError is logged by Tornado with its own message and no request
            return
        log.error("Uncaught exception %s %s (%s)", self.request.method, self.request.path, self.request.remote_ip, exc_info=(typ, value, tb))


class SecurityHeaders(TextErrors):
    """The Server name and the security headers on every answer, of the files routes and of the socket."""

    def set_default_headers(self) -> None:
        self.set_header("Server", "NeoAPRS")
        for name, value in security_headers(self.request.headers.get("Host", "")).items():
            self.set_header(name, value)


class Secured(SecurityHeaders):
    """What every answer of the files routes has: no answer for a Host name that is not ours, and the security headers."""

    def prepare(self) -> None:
        # the server is in the application's settings, not an argument of initialize(): the files handler keeps its signature
        server = self.application.settings["neoaprs_server"]
        if not refuse_foreign_host(self, server):
            refuse_plain(self, server)


PAGE_TYPES = {                                                # the types of the page's own kinds of file, the same on every system: the registry of Windows
    "js": "text/javascript; charset=UTF-8",                    # may say application/javascript, or text/plain, under which (with nosniff) a browser runs no script
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
    """What the page's two kinds of file routes have: the page's own kinds of file have the types of PAGE_TYPES on every system, whatever the system's table says (the registry of Windows may not know a suffix, or
    name JavaScript text/plain); anything else is what the system's table says."""

    def get_content_type(self) -> str:
        name = self.absolute_path.replace("\\", "/").rsplit("/", 1)[-1] if self.absolute_path else ""
        known = PAGE_TYPES.get(name.rsplit(".", 1)[-1].lower()) if "." in name else None
        return known or super().get_content_type()


class Page(Files):
    """The page's files, answered from the snapshot the daemon took at its start (neoaprs/web/pagesnapshot.py), never from the folder: the shell and what is copied from ui/public are asked about at every load (the ETag
    answers with a 304 while they are the same), the hashed files of assets/ are kept for good. Byte ranges, HEAD and the ETag are the file handler's own; what it reads from the disk (the size, the time, the content) is read from the snapshot."""

    def initialize(self, path: str, snapshot: PageSnapshot, default_filename: str | None = None) -> None:  # type: ignore[override]
        super().initialize(path, default_filename)
        self.snapshot = snapshot
        self._file: PageFile | None = None

    def validate_absolute_path(self, root: str, absolute_path: str) -> str | None:
        """Nothing whose name (or a folder's above it) starts with a dot is served, and no source map (the snapshot does not hold them either); 404, as for a file that is not there. The folder itself is its default file."""
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
        self.set_header("Cache-Control", "public, max-age=31536000, immutable" if is_hashed_asset(PurePath(path)) else "no-cache")      # (the hash in a name of assets/ is that of its content)
        self.set_header("X-Content-Type-Options", "nosniff")


class Basemap(Files):
    """data/basemap.pmtiles (the detailed map) and the world map under it, OpenStreetMap extracts (neoaprs/services/mapfetch.py makes the first): the route names the two files, so nothing else of the data folder is reachable. The world
    map is the data folder's own `basemap-world.pmtiles` when it has a good one, else the one that ships with the program (`world`, neoaprs/worldmap.py), so the page has a map before anything is downloaded. A file that is not there is a 404
    with a line that says what to do. A PMTiles reader asks for pieces of the file, which is what the handler's byte ranges are for; it is an octet stream, which Tornado does not compress, so a range is a range of the file. It is behind the
    login: the page's files are free, the map is data."""

    def initialize(self, path: str, default_filename: str | None = None, world: Callable[[], Path | None] | None = None) -> None:     # type: ignore[override]
        super().initialize(path, default_filename)
        self._world = world

    def prepare(self) -> None:
        server = self.application.settings["neoaprs_server"]
        if not refuse_foreign_host(self, server) and not refuse_plain(self, server):
            refuse_unless_logged_in(self, server)

    def set_extra_headers(self, path: str) -> None:
        self.set_header("Cache-Control", "no-cache")
        self.set_header("X-Content-Type-Options", "nosniff")

    async def get(self, path: str, include_body: bool = True) -> None:
        if path == WORLD_FILE and self._world is not None:
            found = self._world()
            if found is None:
                raise tornado.web.HTTPError(404, reason="Not Found: there is no world map (the one that ships with the program is missing and the data folder's is not a PMTiles file)")
            self.root = os.path.abspath(found.parent)                        # (the shipped file has the same name, in another folder)
        if not os.path.isfile(os.path.join(self.root, path)):
            raise tornado.web.HTTPError(404, reason="Not Found: the base map is not in the data folder, fetch it in the Settings tab, Map, Download")
        await super().get(path, include_body)
