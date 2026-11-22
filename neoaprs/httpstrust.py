"""Trust for every https request: the system's root certificates plus certifi's.

A fresh Windows installs a missing root only when a browser asks for one, so Python alone can fail
certificate verification. Extra roots change no check: name, dates and chain are still verified."""
import functools
import http.client
import logging
import ssl
import urllib.error
import urllib.request
from typing import IO

log = logging.getLogger("neoaprs.update")

USER_AGENT = "NeoAPRS (+https://github.com/oh2gba/neoaprs)"


@functools.cache
def https_context() -> ssl.SSLContext:
    """Return the SSL context: the system's roots, plus certifi's when it is installed."""
    context = ssl.create_default_context()
    try:
        import certifi
        context.load_verify_locations(cafile=certifi.where())
    except (ImportError, OSError) as e:
        log.info("the https requests trust the system's root certificates only: %s", e)
    return context


def https_handler() -> urllib.request.HTTPSHandler:
    """Return an https handler that uses `https_context`."""
    return urllib.request.HTTPSHandler(context=https_context())


class NotDowngraded(urllib.request.HTTPRedirectHandler):
    """Refuse a redirect from https to http. `check` sees each redirect target."""

    def check(self, newurl: str) -> None:
        """Raise to refuse the address."""

    def redirect_request(self, req: urllib.request.Request, fp: IO[bytes], code: int, msg: str, headers: http.client.HTTPMessage, newurl: str) -> urllib.request.Request | None:
        if req.full_url.startswith("https://") and not newurl.startswith("https://"):
            raise urllib.error.HTTPError(req.full_url, code, "redirect from https to http", headers, fp)
        self.check(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)
