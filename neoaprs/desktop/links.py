"""Which addresses stay in the app's window. The page is the daemon's own (one address, loopback); everything it links to is somebody else's site (the QRZ page of a call, the credits of the map), and
that is shown by the system's browser, never inside the window, which has no address bar and would be a browser with no way back. Clicks on links and new windows are routed (`route`: LINK_SCRIPT, which hands a click on another site's link to
LinkApi, and the new-window hook); a navigation by script or by a form is not."""
import webbrowser
from typing import Literal
from urllib.parse import urldefrag, urlsplit

Route = Literal["window", "browser", "block"]
INSIDE = ("about:blank", "about:srcdoc")
EXTERNAL_SCHEMES = ("http", "https", "mailto")
DEFAULT_PORTS = {"http": 80, "https": 443}


APP_MARK = "app"          # the fragment of the address the app's window loads: the page reads it (ui/src/lib/shell.ts) to know that page and daemon are one, and shows no Daemon mark


def window_url(page: str) -> str:
    """The address the app's window loads: the daemon's page with the mark that says it is shown in the app (a fragment: the daemon never sees it, a reload keeps it, and the address that Open in browser uses stays plain)."""
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
    """Is `url` an address of the host of `page`, by the same scheme: the daemon's page on another port, which is all a daemon that started again changes of its address?"""
    here, there = _origin(page), _origin(url)
    return here is not None and there is not None and here[:2] == there[:2]


def route(url: str, page: str) -> Route:
    """`window`: the page itself (same scheme, host and port as `page`), the blank page and a `blob:` address its own scripts made; `browser`: another site (http, https) or a mail address;
    `block`: anything else (`file:`, `javascript:`, `data:`, `ftp:`, an address that cannot be read), which nothing the page does needs."""
    if url in INSIDE:
        return "window"
    if url.startswith("blob:"):                               # (a blob: address names the origin that made it)
        return "window" if route(url[len("blob:"):], page) == "window" else "block"
    here, there = _origin(page), _origin(url)
    if here is not None and there == here:
        return "window"
    try:
        scheme = urlsplit(url).scheme.lower()
    except ValueError:
        return "block"
    return "browser" if scheme == "mailto" or (scheme in EXTERNAL_SCHEMES and there is not None) else "block"


def open_external(url: str, page: str) -> bool:
    """Hands an address that `route` sends to the browser to the system's browser (or mail program); False for any other, and when nothing could be started."""
    if route(url, page) != "browser":
        return False
    return bool(webbrowser.open(url))


# Runs in the page after it has loaded: a click on a link to another site is not followed inside the window but handed to Python, which routes it (links.py). (pywebview already sends the new windows that
# `target="_blank"` asks for to the browser; this is for a link that has no target.)
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
    """What the page's script may call: only this, and it only opens what links.route sends to the browser (`page_url` is the daemon's page once it is there)."""

    def __init__(self, page_url: str = "") -> None:
        self.page_url = page_url

    def open_external(self, url: str) -> bool:
        return open_external(str(url), self.page_url)
