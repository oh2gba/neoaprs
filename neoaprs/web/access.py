"""Who may use the page from another device.

This computer needs nothing; any other address needs, while `web/network` is on, the session cookie
that the access key bought. Page files are free; data routes and `LOCAL_ONLY` settings are guarded.
"""

import hashlib
import hmac
import json
import logging
import secrets
from collections.abc import Callable
from enum import Enum
from typing import Any

import tornado.httputil
import tornado.web

from neoaprs.clock import Clock
from neoaprs.config import Config
from neoaprs.configtypes import KEY_ALPHABET, KEY_GROUP_SIZE, KEY_GROUPS, access_key

from .addresses import as_address, is_loopback
from .headers import host_name, refuse_foreign_origin
from .pagefiles import Secured

log = logging.getLogger("neoaprs.web")

COOKIE = "neoaprs_session"
SESSION_DAYS = 365
SECURE_MARK = "s"  # token part that marks a session bought over https
_EXPIRES_DIGITS = 12
# Wrong keys from one address within WRONG_WINDOW_SEC, then it is shut out for BLOCK_SEC.
MAX_WRONG = 5
WRONG_WINDOW_SEC = 60.0
BLOCK_SEC = 300.0
MAX_TRACKED = 500  # addresses kept in the counts
# A request carrying one of these came through a proxy, whose address is not the visitor's.
PROXY_HEADERS = ("X-Forwarded-For", "Forwarded", "X-Real-Ip", "X-Forwarded-Host", "X-Forwarded-Proto", "Via")
# Names of this computer a request may carry in its Host, besides loopback addresses.
OWN_NAMES = ("localhost",)
# Settings a page on another device may not change; they name a program or address the daemon uses.
LOCAL_ONLY = frozenset({"messages/alert_command", "update/url", "map/source", "web/allowed_hosts", "web/proxy"})


def new_key() -> str:
    return access_key("".join(secrets.choice(KEY_ALPHABET) for _ in range(KEY_GROUPS * KEY_GROUP_SIZE)))


def through_proxy(request: tornado.httputil.HTTPServerRequest) -> bool:
    """Return True if the request came from this computer with a forwarding header: a proxy on it passed it on."""
    return is_loopback(request.remote_ip or "") and any(name in request.headers for name in PROXY_HEADERS)


def _last(value: str) -> str:
    """The last entry of a header a proxy appends to: the one the proxy on this computer wrote."""
    return value.rsplit(",", 1)[-1].strip()


def believe_proxy(request: tornado.httputil.HTTPServerRequest) -> None:
    """Take the visitor's address and the scheme from a proxy on this computer (`web/proxy`)."""
    for header in ("X-Forwarded-For", "X-Real-Ip"):
        if header in request.headers:
            visitor = as_address(_last(request.headers[header]))
            if visitor is not None:
                request.remote_ip = str(visitor)
            break
    scheme = _last(request.headers.get("X-Forwarded-Proto", "")).lower()
    if scheme in ("http", "https"):
        request.protocol = scheme


def is_local(request: tornado.httputil.HTTPServerRequest) -> bool:
    """Return True if the request comes from this computer itself, not through a proxy on it."""
    if not is_loopback(request.remote_ip or "") or any(name in request.headers for name in PROXY_HEADERS):
        return False
    name = host_name(request.headers.get("Host", ""))
    return name in OWN_NAMES or is_loopback(name)


def this_computer_target(request: tornado.httputil.HTTPServerRequest, network: bool, port: int) -> str | None:
    """Return `http://127.0.0.1:port` for a loopback request by another computer name, else None.

    Only while the page is closed to the network, when the key screen would be a dead end.
    """
    if (
        network
        or port == 0
        or not is_loopback(request.remote_ip or "")
        or any(name in request.headers for name in PROXY_HEADERS)
        or is_local(request)
    ):
        return None
    return f"http://127.0.0.1:{port}"


def _mac(key: str, body: str) -> str:
    return hmac.new(key.encode(), b"neoaprs-session " + body.encode(), hashlib.sha256).hexdigest()


def _typed(text: str) -> str:
    return "".join(c for c in text.lower() if c not in " -")


class Verdict(Enum):
    ACCEPTED = "accepted"
    WRONG = "wrong"
    BLOCKED = "blocked"


class Access:
    """Settings and clock are read on each call, so a new key or switch takes effect at once."""

    def __init__(self, config: Callable[[], Config], clock: Clock, *, container: bool = False) -> None:
        self._config = config
        self._clock = clock
        # In a container a forwarder may hand a remote connection over from the loopback.
        self._container = container
        self._wrong: dict[str, list[float]] = {}  # per address, times of wrong keys
        self._blocked: dict[str, float] = {}  # per address, when the block ends
        self._proxy_told = False

    def take_proxy(self, request: tornado.httputil.HTTPServerRequest) -> bool:
        """Return False for a request through a proxy on this computer while `web/proxy` is off.

        With it on, the request is made the visitor's (`believe_proxy`); it is never this computer's."""
        if not through_proxy(request):
            return True
        if self._config().web_proxy:
            believe_proxy(request)
            return True
        if not self._proxy_told:
            self._proxy_told = True
            log.warning(
                "a request came through a proxy on this computer (%s) and was refused: a page behind a reverse proxy "
                "needs neoaprs db set web/proxy true",
                ", ".join(name for name in PROXY_HEADERS if name in request.headers),
            )
        return False

    def session(self, secure: bool = False) -> str:
        """Return a new session token; `secure` marks one bought over https."""
        body = f"{int(self._clock().timestamp()) + SESSION_DAYS * 86400}.{secrets.token_hex(8)}{'.' + SECURE_MARK if secure else ''}"
        return f"{body}.{_mac(self._config().web_key, body)}"

    def _session_valid(self, token: str, key: str, secure: bool) -> bool:
        """Return True if the token belongs to the key and has not expired (https only if `secure`)."""
        body, _, mac = token.rpartition(".")
        expires, *rest = body.split(".")
        # A crafted expiry is no session rather than an error.
        if not (expires.isascii() and expires.isdigit() and len(expires) <= _EXPIRES_DIGITS):
            return False
        if secure and rest[1:] != [SECURE_MARK]:
            return False
        return int(expires) > self._clock().timestamp() and hmac.compare_digest(mac.encode(), _mac(key, body).encode())

    def is_local(self, request: tornado.httputil.HTTPServerRequest) -> bool:
        """Return True if the request comes from this computer itself; never in a container."""
        return not self._container and is_local(request)

    def allowed(self, request: tornado.httputil.HTTPServerRequest) -> bool:
        """Return True for a local request; others need a valid session while the network is on."""
        if self.is_local(request):
            return True
        config = self._config()
        cookie = request.cookies.get(COOKIE)
        return (
            config.web_network
            and config.web_key != ""
            and cookie is not None
            and self._session_valid(cookie.value, config.web_key, request.protocol == "https")
        )

    def try_key(self, ip: str, typed: str) -> Verdict:
        now = self._clock().timestamp()
        self._forget(now)
        if self._blocked.get(ip, 0.0) > now:
            return Verdict.BLOCKED
        config = self._config()
        key = config.web_key.replace("-", "")
        if config.web_network and key and hmac.compare_digest(_typed(typed).encode(), key.encode()):
            self._wrong.pop(ip, None)
            return Verdict.ACCEPTED
        recent = [t for t in self._wrong.get(ip, []) if now - t < WRONG_WINDOW_SEC] + [now]
        self._wrong[ip] = recent
        if len(recent) >= MAX_WRONG:
            self._wrong.pop(ip)
            self._blocked[ip] = now + BLOCK_SEC
            log.warning(
                "%d wrong access keys from %s in a minute: it is shut out for %d minutes",
                MAX_WRONG,
                ip,
                int(BLOCK_SEC // 60),
            )
        else:
            log.warning("a wrong access key from %s", ip)
        return Verdict.WRONG

    def _forget(self, now: float) -> None:
        if len(self._wrong) + len(self._blocked) > MAX_TRACKED:
            self._blocked = {ip: until for ip, until in self._blocked.items() if until > now}
            self._wrong = {ip: [t for t in times if now - t < WRONG_WINDOW_SEC] for ip, times in self._wrong.items()}
            self._wrong = {ip: times for ip, times in self._wrong.items() if times}

    def give_session(self, handler: tornado.web.RequestHandler) -> None:
        secure = handler.request.protocol == "https"
        handler.set_cookie(
            COOKIE,
            self.session(secure),
            expires_days=SESSION_DAYS,
            path="/",
            httponly=True,
            samesite="Strict",
            secure=secure,
        )


class _Answer(Secured):
    """Routes of the key screen: responses are not cached and foreign-origin writes are refused."""

    def set_default_headers(self) -> None:
        super().set_default_headers()
        self.set_header("Cache-Control", "no-store")

    def prepare(self) -> None:
        super().prepare()
        if self._finished:
            return
        if self.request.method not in ("GET", "HEAD", "OPTIONS"):
            refuse_foreign_origin(self.request)

    @property
    def server(self) -> Any:
        return self.application.settings["neoaprs_server"]


class Login(_Answer):
    """GET: 204 if let in, else 401. POST `{"key": "..."}`: 204 and cookie, 403 wrong, 429 shut out."""

    def get(self) -> None:
        if not self.server.access.allowed(self.request):
            raise tornado.web.HTTPError(401)
        self.set_status(204)

    def post(self) -> None:
        if self.server.access.is_local(self.request):
            self.set_status(204)
            return
        try:
            typed = json.loads(self.request.body).get("key", "")
        except (ValueError, AttributeError, RecursionError):
            typed = None
        if not isinstance(typed, str) or len(typed) > 64:
            raise tornado.web.HTTPError(400)
        ip = self.request.remote_ip or ""
        verdict = self.server.access.try_key(ip, typed)
        if verdict is Verdict.BLOCKED:
            self.set_status(429)
            self.set_header("Retry-After", str(int(BLOCK_SEC)))
            self.finish("429 Too Many Requests\n")
            return
        if verdict is Verdict.WRONG:
            raise tornado.web.HTTPError(403)
        log.info("a device logged in from %s", ip)
        self.server.access.give_session(self)
        self.set_status(204)


class NewKey(_Answer):
    """POST makes a new access key, ending every session; the caller gets a session of the new one."""

    async def post(self) -> None:
        if not self.server.access.allowed(self.request):
            raise tornado.web.HTTPError(401)
        if not await self.server.renew_key():
            raise tornado.web.HTTPError(500)
        if not self.server.access.is_local(self.request):
            self.server.access.give_session(self)
        self.set_status(204)
