"""The gate of the page's server, held for every route at once. The routes are read from the running application, whatever `WebServer.start` registered (neoaprs/web/server.py), and each is asked the same
questions with every method its handler answers, so a route that is added later is asked them too without a change here:

    a request for a host name that is not ours is refused (403), from this computer too: the page of another site whose name was moved to this address (DNS rebinding) asks from here
    a device that has not logged in is refused (401) and the same request with a session reaches the handler; what is free on purpose is the short table FREE, each entry with why
    a request that changes something (POST, PUT, PATCH, DELETE) and the socket's handshake that carry the Origin of another site are refused (403), session or not
    while the secure page is served, plain http sends another device there (307) or refuses it (403); what plain http still answers is the table PLAIN
    every one of these answers carries the security headers

What a route does once the gate is passed is in its own tests (tests/test_web_access.py, test_web.py, test_web_https.py, test_support_web.py). As there, a request is made to look as if it came from another device
by saying that no address is the loopback (`away`). No test here leans on what makes a request "this computer": a request that has to be let in carries a session.
"""
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import tornado.routing
import tornado.web
import tornado.websocket
from tornado.httpclient import HTTPResponse

from neoaprs.clock import utcnow
from neoaprs.web import access as web_access
from neoaprs.web.access import COOKIE
from neoaprs.web.securehandlers import CA_PATH
from tests.support.env import Env, until

NETWORK = {"web/network": "true", "web/key": "k7m2-x9pq-4hrt"}
HTTPS = {**NETWORK, "web/https": "true"}
LAN = "192.168.1.20"
FOREIGN = "evil.example"
POSTED = '{"key": "aaaa-aaaa-aaaa"}'            # what every request with a body carries: a key that is not the key, and nothing a bundle could be made from, so a handler that is reached does nothing
READS = ("GET", "HEAD", "OPTIONS")              # the methods that only ask; every other one changes something, and a browser sends it with the Origin of the page that made it
BODIED = ("POST", "PUT", "PATCH")               # the methods an HTTP client sends with a body
HANDSHAKE = {"Connection": "Upgrade", "Upgrade": "websocket", "Sec-WebSocket-Version": "13", "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ=="}
BASEMAP = r"/(basemap\.pmtiles|basemap-world\.pmtiles)"

# A request for each route whose pattern has a group, which the pattern alone does not say: the route as neoaprs/web/server.py writes it -> a path. A route without a group is asked for by its own text.
PATHS = {BASEMAP: "/basemap.pmtiles", r"/()": "/", r"/(.*)": "/index.html"}

# What a device that has not logged in is given all the same: the route -> (the methods, the answer, why it is free). Every other route and method answers it 401.
FREE: dict[str, tuple[str, int, str]] = {
    r"/()": ("GET HEAD", 200, "the page's shell: it holds the key screen, so it loads before a key can be typed"),
    r"/(.*)": ("GET HEAD", 200, "the page's own files (the script and the styles of the key screen, the icons, the manifest): the same for everybody, and they hold no data"),
    r"/access": ("POST", 403, "the login itself: a device without a session posts the access key here, and a wrong key is told so"),
    re.escape(CA_PATH): ("GET HEAD", 404, "the authority's public certificate, which a device takes before it can open the secure page without a warning; there is none while the secure page is off"),
}
# What plain http still answers a device on the network while the secure page is served: the route -> why.
PLAIN = {re.escape(CA_PATH): "the certificate is the way to a secure page without a warning, so it is given on the port a device can open before it trusts anything"}

HEADERS = {"X-Frame-Options": "DENY", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "Cross-Origin-Resource-Policy": "same-origin", "Server": "NeoAPRS"}
POLICY = ("default-src 'self'", "script-src 'self'", "object-src 'none'", "base-uri 'none'", "form-action 'none'", "frame-ancestors 'none'")


@pytest.fixture(autouse=True)
def lan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("neoaprs.web.server.lan_addresses", lambda: [LAN])
    monkeypatch.setattr("neoaprs.web.secureside.lan_addresses", lambda: [LAN])


@pytest.fixture
def away(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every request comes from an address that is not this computer's."""
    monkeypatch.setattr(web_access, "is_loopback", lambda ip: False)


@dataclass(frozen=True)
class Route:
    pattern: str                                        # as neoaprs/web/server.py writes it
    handler: type[tornado.web.RequestHandler]
    path: str                                           # a request for it
    methods: tuple[str, ...]                            # the methods its handler answers

    @property
    def socket(self) -> bool:
        return issubclass(self.handler, tornado.websocket.WebSocketHandler)


def _rules(router: tornado.routing.RuleRouter) -> Iterator[tornado.routing.Rule]:
    """The rules of the application as Tornado holds them: a router of host names whose rules lead to the router of the paths."""
    for rule in router.rules:
        if isinstance(rule.target, tornado.routing.RuleRouter):
            yield from _rules(rule.target)
        else:
            yield rule


def routes_of(e: Env) -> list[Route]:
    """Every route the running server has, in its order, each with a path that reaches it and no route before it."""
    assert e.server is not None and e.server._app is not None
    rules = list(_rules(e.server._app.default_router))
    found: list[Route] = []
    for rule in rules:
        matcher, handler = rule.matcher, rule.target
        assert isinstance(matcher, tornado.routing.PathMatches) and isinstance(handler, type) and issubclass(handler, tornado.web.RequestHandler), f"a route of a kind this file does not know how to ask: {rule!r}"
        pattern = matcher.regex.pattern.removesuffix("$")
        path = PATHS.get(pattern) or (None if matcher.regex.groups else matcher.reverse())
        assert path is not None and matcher.regex.match(path), f"the route {pattern} has a pattern no path is made from by itself: give PATHS a path that asks for it"
        first = next(r.matcher for r in rules if isinstance(r.matcher, tornado.routing.PathMatches) and r.matcher.regex.match(path))
        assert first is matcher, f"the path {path} for the route {pattern} is answered by the earlier route {first.regex.pattern}"
        methods = tuple(m for m in handler.SUPPORTED_METHODS if getattr(handler, m.lower()) is not getattr(tornado.web.RequestHandler, m.lower()))
        found.append(Route(pattern, handler, path, methods))
    patterns = {route.pattern for route in found}
    assert any(route.socket for route in found) and all(route.methods for route in found), "the routes were not read as they are: the socket is not among them, or a handler answers no method"
    assert {*PATHS, *FREE, *PLAIN} <= patterns, f"a table of this file names a route the server no longer has: {sorted({*PATHS, *FREE, *PLAIN} - patterns)}"
    return found


def changes(method: str) -> bool:
    return method not in READS


def asked(routes: list[Route]) -> Iterator[tuple[Route, str]]:
    for route in routes:
        for method in route.methods:
            yield route, method


async def served(tmp_path: Path, settings: dict[str, str]) -> Env:
    """The daemon with its page on the network, and a base map in its data folder so that the map's route has something to give."""
    e = Env(tmp_path, web=True, settings=settings, clock=utcnow)         # (the real time: the secure side's certificates carry dates)
    (tmp_path / "basemap.pmtiles").write_bytes(b"0123456789")
    await e.start()
    return e


def session(e: Env) -> dict[str, str]:
    """The cookie of a device that has logged in with the key in force (the login itself is tests/test_web_access.py's)."""
    assert e.server is not None
    return {"Cookie": f"{COOKIE}={e.server.access.session()}"}


def own_origin(e: Env) -> dict[str, str]:
    """What a browser says of a request the page itself makes."""
    return {"Origin": f"http://127.0.0.1:{e.port}"}


async def ask(e: Env, route: Route, method: str, headers: dict[str, str] | None = None) -> HTTPResponse:
    """The answer to one request for the route. A handshake that is accepted opens a socket and leaves an HTTP client without an answer, which no request of this file may end in."""
    try:
        return await e.fetch(route.path, headers=headers, method=method, body=POSTED if method in BODIED else None)
    except AssertionError:
        raise AssertionError(f"{method} {route.pattern} with {sorted(headers or {})} got no answer an HTTP client can read: a socket was opened for it") from None


def lacking(answer: HTTPResponse) -> list[str]:
    """The security headers the answer does not carry (neoaprs/web/headers.py has them and why)."""
    policy = answer.headers.get("Content-Security-Policy", "")
    return [name for name, value in HEADERS.items() if answer.headers.get(name) != value] + [part for part in POLICY if part not in policy]


# ---- the host name ---------------------------------------------------------------------------------------------------------------------------------

async def test_no_route_answers_a_request_for_a_host_name_that_is_not_ours(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    e = await served(tmp_path, NETWORK)
    wrong: list[str] = []
    for who in ("this computer", "another device"):
        if who == "another device":
            monkeypatch.setattr(web_access, "is_loopback", lambda ip: False)
        for route, method in asked(routes_of(e)):
            answer = await ask(e, route, method, {"Host": FOREIGN, **session(e), **(HANDSHAKE if route.socket else {})})
            if answer.code != 403 or (method != "HEAD" and b"does not answer to the name" not in answer.body):
                wrong.append(f"{method} {route.pattern} from {who}: {answer.code}")
    assert wrong == [], "a route answers a request made for the name of another site: its handler's prepare() begins with refuse_foreign_host (neoaprs/web/pagefiles.py)"


# ---- the login -------------------------------------------------------------------------------------------------------------------------------------

async def test_a_device_that_has_not_logged_in_is_refused_on_every_route_that_is_not_free_and_let_in_with_a_session(tmp_path: Path, away: None) -> None:
    e = await served(tmp_path, NETWORK)
    routes = routes_of(e)
    stale = [f"{route.pattern}: {FREE[route.pattern][0]}" for route in routes if route.pattern in FREE and not set(FREE[route.pattern][0].split()) <= set(route.methods)]
    assert stale == [], "FREE names a method its route does not answer"
    wrong: list[str] = []
    for route, method in asked(routes):
        methods, status, _why = FREE.get(route.pattern, ("", 401, ""))
        expected = status if method in methods.split() else 401
        answer = await ask(e, route, method, own_origin(e) if changes(method) else None)
        if answer.code != expected:
            wrong.append(f"{method} {route.pattern} without a session: {answer.code}, not {expected}")
        if expected == 401:
            let_in = await ask(e, route, method, {**session(e), **(own_origin(e) if changes(method) else {})})
            if let_in.code in (401, 403) or let_in.code >= 500:
                wrong.append(f"{method} {route.pattern} with a session: {let_in.code}")
    assert wrong == [], "a route gives a device that has not logged in something else than this file says: put it behind the login (refuse_unless_logged_in of neoaprs/web/pagefiles.py), or say in FREE why it is free"
    assert all(len(why) > 30 for _methods, _status, why in FREE.values()) and all(len(why) > 30 for why in PLAIN.values())


# ---- the page of another site ----------------------------------------------------------------------------------------------------------------------

async def taken_from_another_site(e: Env, routes: list[Route], monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """What was not refused although it carried the Origin of another site: every method of the routes that changes something, and the handshake of a socket, asked with a session from this computer and then from another device."""
    other_site = {"Origin": f"http://{FOREIGN}"}
    wrong: list[str] = []
    for who in ("this computer", "another device"):
        if who == "another device":
            monkeypatch.setattr(web_access, "is_loopback", lambda ip: False)
        for route in routes:
            tries = [(method, {**other_site, **session(e)}) for method in route.methods if changes(method)]
            tries += [("GET", {**other_site, **session(e), **HANDSHAKE})] if route.socket else []
            for method, headers in tries:
                answer = await ask(e, route, method, headers)
                if answer.code != 403:
                    wrong.append(f"{method} {route.pattern} from {who}: {answer.code}")
    return wrong


async def test_a_request_that_changes_something_and_the_handshake_of_a_socket_from_the_page_of_another_site_are_refused_on_every_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    e = await served(tmp_path, NETWORK)
    wrong = await taken_from_another_site(e, routes_of(e), monkeypatch)
    assert wrong == [], "a route takes a request that changes something (POST, PUT, PATCH, DELETE), or opens a socket, for a script of another site: an Origin that is not the Host is refused in prepare() (a request) or in check_origin (a socket)"


class NoGate(tornado.web.RequestHandler):
    """A made-up handler that forgot the gate and answers the three methods beside POST that change something."""

    def put(self) -> None:
        self.set_status(204)

    patch = delete = put


async def test_a_route_that_answers_put_patch_or_delete_is_asked_from_the_page_of_another_site_like_a_post(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    e = await served(tmp_path, NETWORK)
    assert e.server is not None and e.server._app is not None
    e.server._app.add_handlers(r".*", [(r"/made-up", NoGate)])
    made_up = [route for route in routes_of(e) if route.pattern == "/made-up"]
    assert [route.methods for route in made_up] == [("DELETE", "PATCH", "PUT")], "a route added to the running application is read with the methods its handler answers"
    assert await taken_from_another_site(e, made_up, monkeypatch) == [f"{method} /made-up from {who}: 204" for who in ("this computer", "another device") for method in ("DELETE", "PATCH", "PUT")]


# ---- plain http beside the secure page -------------------------------------------------------------------------------------------------------------

async def test_while_the_secure_page_is_served_plain_http_sends_another_device_there_or_refuses_it_on_every_route(tmp_path: Path, away: None) -> None:
    e = await served(tmp_path, HTTPS)
    assert e.server is not None
    secure = e.server.secure
    await until(lambda: secure.state.on)
    there = f"https://127.0.0.1:{secure.port}"
    wrong: list[str] = []
    for route in routes_of(e):
        tries = [(method, {**session(e), **(own_origin(e) if changes(method) else {})}) for method in route.methods]
        tries += [("GET", {**session(e), **own_origin(e), **HANDSHAKE})] if route.socket else []
        for method, headers in tries:
            answer = await ask(e, route, method, headers)
            if route.pattern in PLAIN:
                right = answer.code == 200
            elif method in ("GET", "HEAD") and "Upgrade" not in headers:
                right = answer.code == 307 and answer.headers.get("Location") == there + route.path
            else:
                right = answer.code == 403 and there.encode() in answer.body
            if not right or lacking(answer):
                wrong.append(f"{method} {route.pattern}{' (a handshake)' if 'Upgrade' in headers else ''}: {answer.code} {answer.headers.get('Location', '')} {lacking(answer)}")
    assert wrong == [], "a route answers over plain http while the secure page is served: its handler's prepare() calls refuse_plain (neoaprs/web/pagefiles.py) after the host name, or PLAIN says why it stays"


# ---- the headers -----------------------------------------------------------------------------------------------------------------------------------

async def test_every_answer_of_every_route_carries_the_security_headers(tmp_path: Path, away: None) -> None:
    e = await served(tmp_path, NETWORK)
    wrong: list[str] = []
    for route, method in asked(routes_of(e)):
        mine = own_origin(e) if changes(method) else {}
        kinds = {"without a session": mine, "with a session": {**session(e), **mine}, "for the name of another site": {"Host": FOREIGN}, "from the page of another site": {**session(e), "Origin": f"http://{FOREIGN}"}}
        for kind, headers in kinds.items():
            answer = await ask(e, route, method, headers)
            if lacking(answer):
                wrong.append(f"{method} {route.pattern} {kind} ({answer.code}): {lacking(answer)}")
    assert wrong == [], "an answer went out without the security headers: the handler derives from SecurityHeaders (neoaprs/web/pagefiles.py)"
