"""Who may use the page from another device. On the loopback nobody is asked for anything. From any other address, and only while `web/network` is on, a request must carry the session cookie that the right
access key (`web/key`) bought: the page's files are free (they hold the key screen), everything that carries data (the socket, the base map) is refused until the device has logged in.

A session is `expires.nonce.mac`, the mac an HMAC of the first two parts under the access key, so that nothing is stored: it survives a restart, and a new key ends every session at once. The key itself is
never in a cookie. Wrong keys are counted for each address; too many in a minute shut that address out for a while. The key is compared in constant time.
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

from .addresses import is_loopback
from .headers import origin_is_host
from .pagefiles import Secured

log = logging.getLogger("neoaprs.web")

COOKIE = "neoaprs_session"
SESSION_DAYS = 365
_EXPIRES_DIGITS = 12                    # the most digits the expiry of a session token has (a Unix time has 10 until the year 2286)
MAX_WRONG = 5                              # wrong keys from one address in WRONG_WINDOW_SEC, then it is shut out for BLOCK_SEC
WRONG_WINDOW_SEC = 60.0
BLOCK_SEC = 300.0
MAX_TRACKED = 500                          # addresses kept in the counts
PROXY_HEADERS = ("X-Forwarded-For", "Forwarded", "X-Real-Ip")      # a request that carries one came through a proxy, whose own address is not the visitor's


def new_key() -> str:
    return access_key("".join(secrets.choice(KEY_ALPHABET) for _ in range(KEY_GROUPS * KEY_GROUP_SIZE)))


def is_local(request: tornado.httputil.HTTPServerRequest) -> bool:
    """Does the request come from this computer itself, not through a proxy on it?"""
    return is_loopback(request.remote_ip or "") and not any(name in request.headers for name in PROXY_HEADERS)


def _mac(key: str, body: str) -> str:
    return hmac.new(key.encode(), b"neoaprs-session " + body.encode(), hashlib.sha256).hexdigest()


def _typed(text: str) -> str:
    return "".join(c for c in text.lower() if c not in " -")


class Verdict(Enum):
    ACCEPTED = "accepted"
    WRONG = "wrong"
    BLOCKED = "blocked"


class Access:
    """`Access(config, clock)`: the settings in force and the clock are asked each time, so a new key or a switch takes effect at once."""

    def __init__(self, config: Callable[[], Config], clock: Clock) -> None:
        self._config = config
        self._clock = clock
        self._wrong: dict[str, list[float]] = {}          # per address, when the wrong keys came
        self._blocked: dict[str, float] = {}              # per address, until when it is shut out

    def session(self) -> str:
        body = f"{int(self._clock().timestamp()) + SESSION_DAYS * 86400}.{secrets.token_hex(8)}"
        return f"{body}.{_mac(self._config().web_key, body)}"

    def _session_valid(self, token: str, key: str) -> bool:
        body, _, mac = token.rpartition(".")
        expires = body.split(".", 1)[0]
        if not (expires.isascii() and expires.isdigit() and len(expires) <= _EXPIRES_DIGITS):          # (a crafted cookie with other digits, or thousands of them, is no session, not an error)
            return False
        return int(expires) > self._clock().timestamp() and hmac.compare_digest(mac.encode(), _mac(key, body).encode())

    def allowed(self, request: tornado.httputil.HTTPServerRequest) -> bool:
        """May this request have what carries data? Anything from this computer; from elsewhere only with a session of the key in force, and only while the network is on."""
        if is_local(request):
            return True
        config = self._config()
        cookie = request.cookies.get(COOKIE)
        return config.web_network and config.web_key != "" and cookie is not None and self._session_valid(cookie.value, config.web_key)

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
            log.warning("%d wrong access keys from %s in a minute: it is shut out for %d minutes", MAX_WRONG, ip, int(BLOCK_SEC // 60))
        else:
            log.warning("a wrong access key from %s", ip)
        return Verdict.WRONG

    def _forget(self, now: float) -> None:
        if len(self._wrong) + len(self._blocked) > MAX_TRACKED:
            self._blocked = {ip: until for ip, until in self._blocked.items() if until > now}
            self._wrong = {ip: [t for t in times if now - t < WRONG_WINDOW_SEC] for ip, times in self._wrong.items()}
            self._wrong = {ip: times for ip, times in self._wrong.items() if times}

    def give_session(self, handler: tornado.web.RequestHandler) -> None:
        handler.set_cookie(COOKIE, self.session(), expires_days=SESSION_DAYS, path="/", httponly=True, samesite="Strict", secure=handler.request.protocol == "https")


class _Answer(Secured):
    """The routes of the key screen: no answer is kept, and a script of another site is not answered."""

    def set_default_headers(self) -> None:
        super().set_default_headers()
        self.set_header("Cache-Control", "no-store")

    def prepare(self) -> None:
        super().prepare()
        if self._finished:
            return
        origin = self.request.headers.get("Origin")
        if self.request.method == "POST" and origin is not None and not origin_is_host(origin, self.request.headers.get("Host", "")):
            raise tornado.web.HTTPError(403)

    @property
    def server(self) -> Any:
        return self.application.settings["neoaprs_server"]


class Login(_Answer):
    """GET asks whether this device is let in (204, or 401: the page shows the key screen); POST with the key as `{"key": "..."}` logs it in: 204 and the session cookie, 403 for a wrong key, 429 while shut out."""

    def get(self) -> None:
        if not self.server.access.allowed(self.request):
            raise tornado.web.HTTPError(401)
        self.set_status(204)

    def post(self) -> None:
        if is_local(self.request):
            self.set_status(204)
            return
        try:
            typed = json.loads(self.request.body).get("key", "")
        except (ValueError, AttributeError):
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
    """POST makes a new access key, which ends every session; the device that asked gets a session of the new key."""

    async def post(self) -> None:
        if not self.server.access.allowed(self.request):
            raise tornado.web.HTTPError(401)
        if not await self.server.renew_key():
            raise tornado.web.HTTPError(500)
        if not is_local(self.request):
            self.server.access.give_session(self)
        self.set_status(204)
