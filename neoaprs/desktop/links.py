"""Decide which addresses stay in the app's window.

Everything but the daemon's own page opens in the system browser, because the window has no
address bar. Link clicks and new windows are routed with `route`; script navigation is not."""

import webbrowser
from typing import Literal
from urllib.parse import urldefrag, urlsplit

Route = Literal["window", "browser", "block"]
INSIDE = ("about:blank", "about:srcdoc")
EXTERNAL_SCHEMES = ("http", "https", "mailto")
DEFAULT_PORTS = {"http": 80, "https": 443}


# Address fragment telling the page (ui/src/lib/shell.ts) it runs inside the app,
# so it shows no Daemon mark.
APP_MARK = "app"


def window_url(page: str) -> str:
    """Return the page address with the app mark as a fragment (the daemon never sees it)."""
    return f"{urldefrag(page).url}#{APP_MARK}"


def _origin(url: str) -> tuple[str, str, int | None] | None:
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in DEFAULT_PORTS or not parts.hostname:
        return None
    return parts.scheme, parts.hostname.lower(), port if port is not None else DEFAULT_PORTS[parts.scheme]


def same_host(url: str, page: str) -> bool:
    """Return whether `url` has the same scheme and host as `page`, whatever the port.

    A restarted daemon may change only its port."""
    here, there = _origin(page), _origin(url)
    return here is not None and there is not None and here[:2] == there[:2]


def route(url: str, page: str) -> Route:
    """Return where `url` opens: `window` (the page itself), `browser` (http, https, mailto) or `block`."""
    if url in INSIDE:
        return "window"
    if url.startswith("blob:"):  # a blob: address names the origin that made it
        return "window" if route(url[len("blob:") :], page) == "window" else "block"
    here, there = _origin(page), _origin(url)
    if here is not None and there == here:
        return "window"
    try:
        scheme = urlsplit(url).scheme.lower()
    except ValueError:
        return "block"
    return "browser" if scheme == "mailto" or (scheme in EXTERNAL_SCHEMES and there is not None) else "block"


def open_external(url: str, page: str) -> bool:
    """Open an address that `route` sends to the browser; return False for any other or on failure."""
    if route(url, page) != "browser":
        return False
    return bool(webbrowser.open(url))


# Runs in the page after load: a click on a link to another site is handed to Python, which routes
# it. pywebview already sends `target="_blank"` windows to the browser; this covers links
# without a target.
LINK_SCRIPT = """(function () {
  if (window.__neoaprsLinks) { return; }
  window.__neoaprsLinks = true;
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    if (!a || new URL(a.href, location.href).origin === location.origin) { return; }
    e.preventDefault();
    e.stopPropagation();
    if (window.pywebview && window.pywebview.api) { window.pywebview.api.open_external(a.href); }
  }, true);
})();"""


class LinkApi:
    """The only API the page's script may call; it opens only what `route` sends to the browser."""

    def __init__(self, page_url: str = "") -> None:
        self.page_url = page_url

    def open_external(self, url: str) -> bool:
        return open_external(str(url), self.page_url)
