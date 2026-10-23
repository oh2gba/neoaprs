"""The secure connection of the page (`web/https`; neoaprs/web/secureside.py, securehandlers.py): TLS on the port after the plain one with a real TLS client that trusts the authority, the redirect from the plain
port for a device other than this computer, the authority's certificate to download, and that nothing changes while the setting is off. As in tests/test_web_access.py a request is made to look as if it came from elsewhere
by saying that no address is the loopback (`away`)."""
import asyncio
import json
import logging
import socket
import ssl
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from tornado.httpclient import AsyncHTTPClient, HTTPClientError, HTTPRequest, HTTPResponse
from tornado.websocket import websocket_connect

from neoaprs.clock import utcnow
from neoaprs.web import access as web_access
from neoaprs.web import secureside
from neoaprs.web.access import COOKIE
from neoaprs.web.tls import fingerprint_of
from tests.support.env import Env, until
from tests.support.wsclient import WsClient

KEY = "k7m2-x9pq-4hrt"
HTTPS = {"web/network": "true", "web/key": KEY, "web/https": "true"}
LAN = "192.168.1.20"


class Lan:
    def __init__(self) -> None:
        self.addresses = [LAN]

    def __call__(self) -> list[str]:
        return list(self.addresses)


@pytest.fixture(autouse=True)
def lan(monkeypatch: pytest.MonkeyPatch) -> Lan:
    lan = Lan()
    monkeypatch.setattr("neoaprs.web.server.lan_addresses", lan)
    monkeypatch.setattr("neoaprs.web.secureside.lan_addresses", lan)
    return lan


@pytest.fixture
def away(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every request comes from an address that is not this computer's."""
    monkeypatch.setattr(web_access, "is_loopback", lambda ip: False)


async def served(tmp_path: Path, settings: dict[str, str] | None = None) -> Env:
    e = Env(tmp_path, web=True, settings=settings, clock=utcnow)         # (the real time: a real TLS client looks at the dates)
    await e.start()
    assert e.server is not None
    if (settings or {}).get("web/https") == "true" and (settings or {}).get("web/network") == "true":
        await until(lambda: e.server is not None and e.server.secure.state.on)
    return e


def secure_port(e: Env) -> int:
    assert e.server is not None
    return e.server.secure.port


def ca_file(e: Env) -> str:
    return str(e.dir / "tls" / "ca.crt")


async def https_fetch(e: Env, path: str = "/", headers: dict[str, str] | None = None, method: str = "GET", body: str | None = None, host: str = "127.0.0.1") -> HTTPResponse:
    """A request over TLS that trusts the authority and nothing else; an answer of 400 or more is returned."""
    request = HTTPRequest(f"https://{host}:{secure_port(e)}{path}", method=method, headers=headers, body=body, ca_certs=ca_file(e), follow_redirects=False, validate_cert=True)
    try:
        return await AsyncHTTPClient().fetch(request)
    except HTTPClientError as error:
        assert error.response is not None
        return error.response


def plain(e: Env, path: str = "/", host: str | None = None, method: str = "GET", body: str | None = None, headers: dict[str, str] | None = None) -> "asyncio.Future[HTTPResponse]":
    return asyncio.ensure_future(e.fetch(path, headers={**({} if host is None else {"Host": host}), **(headers or {})}, method=method, body=body))


async def secure_ws(e: Env, cookie: str | None = None) -> WsClient:
    request = HTTPRequest(f"wss://127.0.0.1:{secure_port(e)}/ws", headers=None if cookie is None else {"Cookie": cookie}, ca_certs=ca_file(e), connect_timeout=5)
    page = WsClient(await websocket_connect(request))
    e.pages.append(page)
    return page


async def served_certificate(e: Env) -> x509.Certificate:
    """What a client is given by the secure port, whether it trusts it or not."""
    pem = await asyncio.to_thread(ssl.get_server_certificate, ("127.0.0.1", secure_port(e)))
    return x509.load_pem_x509_certificate(pem.encode())


async def names_served(e: Env) -> set[str]:
    return names_of(await served_certificate(e))


async def until_served(e: Env, name: str) -> None:
    for _ in range(100):
        if name in await names_served(e):
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"{name} did not come into the certificate")


def names_of(cert: x509.Certificate) -> set[str]:
    value = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    return {*value.get_values_for_type(x509.DNSName), *(str(ip) for ip in value.get_values_for_type(x509.IPAddress))}


# ---- the secure page --------------------------------------------------------------------------------------------------------------------------------

async def test_the_page_is_served_over_tls_on_the_port_after_the_plain_one_to_a_client_that_trusts_the_authority(tmp_path: Path) -> None:
    e = await served(tmp_path, HTTPS)
    assert e.server is not None
    assert 0 < e.port < secure_port(e) <= e.port + secureside.PORT_TRIES
    for host in ("127.0.0.1", "localhost"):
        answer = await https_fetch(e, host=host)
        assert answer.code == 200 and b"<" in answer.body and "Content-Security-Policy" in answer.headers, host
    assert (await e.fetch("/")).code == 200, "and the loopback still has its plain port"


async def test_a_client_that_does_not_trust_the_authority_is_refused_by_the_handshake(tmp_path: Path) -> None:
    e = await served(tmp_path, HTTPS)
    with pytest.raises(ssl.SSLError):
        await asyncio.to_thread(ssl.create_default_context().wrap_socket(socket.socket(), server_hostname="127.0.0.1").connect, ("127.0.0.1", secure_port(e)))


async def test_the_certificate_names_the_computer_and_its_addresses_and_is_signed_by_the_authority_that_is_offered(tmp_path: Path) -> None:
    e = await served(tmp_path, HTTPS)
    cert = await served_certificate(e)
    assert {socket.gethostname().lower(), f"{socket.gethostname().lower()}.local", "localhost", "127.0.0.1", "::1", LAN} <= names_of(cert)
    ca = x509.load_der_x509_certificate((await e.fetch("/neoaprs-ca.crt")).body)
    cert.verify_directly_issued_by(ca)


async def test_the_socket_works_over_tls_and_the_page_is_told_about_the_secure_connection(tmp_path: Path) -> None:
    e = await served(tmp_path, HTTPS)
    page = await secure_ws(e)
    await page.expect("hello")
    await page.until(lambda: "config" in page.topics)
    config = page.topics["config"]
    ca = (await e.fetch("/neoaprs-ca.crt")).body
    assert config["https"] == {"on": True, "port": secure_port(e), "fingerprint": fingerprint_of(ca), "problem": ""}
    host = socket.gethostname().lower()
    assert config["urls"] == [f"https://{LAN}:{secure_port(e)}/", f"https://{host}.local:{secure_port(e)}/"], "the page is opened at the secure address"


async def test_the_access_checks_are_the_same_on_the_secure_port(tmp_path: Path, away: None) -> None:
    e = await served(tmp_path, HTTPS)
    assert (await https_fetch(e)).code == 200, "the page's files are free"
    assert (await https_fetch(e, "/access")).code == 401
    with pytest.raises(HTTPClientError) as refused:
        await secure_ws(e)
    assert refused.value.code == 401
    assert (await https_fetch(e, "/", headers={"Host": "evil.example"})).code == 403, "a Host name that is not ours"
    assert (await https_fetch(e, "/access", method="POST", body=json.dumps({"key": "aaaa-aaaa-aaaa"}))).code == 403
    answer = await https_fetch(e, "/access", method="POST", body=json.dumps({"key": KEY}))
    assert answer.code == 204
    header = answer.headers["Set-Cookie"]
    assert header.startswith(f"{COOKIE}=") and "Secure" in header and "HttpOnly" in header, "the cookie of a secure page is for secure pages"
    cookie = header.split(";")[0]
    page = await secure_ws(e, cookie)
    await page.expect("hello")


async def test_the_session_made_on_the_plain_port_is_not_marked_secure(tmp_path: Path, away: None) -> None:
    e = await served(tmp_path, {"web/network": "true", "web/key": KEY})
    answer = await e.fetch("/access", method="POST", body=json.dumps({"key": KEY}))
    assert answer.code == 204 and "Secure" not in answer.headers["Set-Cookie"]


# ---- the plain port ---------------------------------------------------------------------------------------------------------------------------------

async def test_a_device_on_the_plain_port_is_sent_to_the_same_address_on_the_secure_one(tmp_path: Path, away: None) -> None:
    e = await served(tmp_path, HTTPS)
    answer = await plain(e, "/index.html?x=1", host=f"{LAN}:{e.port}")
    assert answer.code == 307 and answer.headers["Location"] == f"https://{LAN}:{secure_port(e)}/index.html?x=1"
    local = f"{socket.gethostname().lower()}.local"
    assert (await plain(e, "/", host=f"{local}:{e.port}")).headers["Location"] == f"https://{local}:{secure_port(e)}/", "by name as well"
    assert (await plain(e, "/", host=f"{LAN}:{e.port}", method="HEAD")).code == 307
    assert (await plain(e, "/", host="evil.example")).code == 403, "a name that is not ours is refused before it is redirected"


async def test_an_address_in_brackets_is_redirected_in_brackets(tmp_path: Path, away: None) -> None:
    e = await served(tmp_path, HTTPS)
    answer = await plain(e, "/", host=f"[fe80::1]:{e.port}")
    assert answer.headers["Location"] == f"https://[fe80::1]:{secure_port(e)}/"


async def test_the_socket_the_login_and_the_map_are_refused_on_the_plain_port_with_a_reason(tmp_path: Path, away: None) -> None:
    e = await served(tmp_path, HTTPS)
    (tmp_path / "basemap.pmtiles").write_bytes(b"0123456789")
    with pytest.raises(HTTPClientError) as refused:
        await e.ws()
    assert refused.value.code == 403 and refused.value.response is not None and f"https://127.0.0.1:{secure_port(e)}/" in refused.value.response.body.decode()
    for path, method in (("/access", "POST"), ("/access/new", "POST"), ("/basemap.pmtiles", "GET")):
        answer = await plain(e, path, method=method, body="{}" if method == "POST" else None)
        assert "Set-Cookie" not in answer.headers, path
        assert answer.code == (307 if method == "GET" else 403), path


async def test_the_loopback_keeps_its_plain_port_with_no_redirect_and_a_socket(tmp_path: Path) -> None:
    e = await served(tmp_path, HTTPS)
    assert (await e.fetch("/")).code == 200 and (await e.fetch("/access")).code == 204
    page = await e.ws()
    await page.expect("hello")
    assert (await e.fetch("/", headers={"X-Forwarded-For": "203.0.113.9"})).code == 307, "a request through a proxy on this computer is not this computer"


# ---- the authority's certificate --------------------------------------------------------------------------------------------------------------------

async def test_the_authority_certificate_is_a_download_in_der_on_both_ports_for_anyone_and_never_a_key(tmp_path: Path, away: None) -> None:
    e = await served(tmp_path, HTTPS)
    expected = x509.load_pem_x509_certificate((tmp_path / "tls" / "ca.crt").read_bytes()).public_bytes(serialization.Encoding.DER)
    for answer in (await e.fetch("/neoaprs-ca.crt", headers={"Host": f"{LAN}:{e.port}"}), await https_fetch(e, "/neoaprs-ca.crt")):
        assert answer.code == 200 and answer.body == expected, "the plain port does not redirect it"
        assert answer.headers["Content-Type"] == "application/x-x509-ca-cert"
        assert 'filename="NeoAPRS-CA.crt"' in answer.headers["Content-Disposition"] and "attachment" in answer.headers["Content-Disposition"]
        assert b"PRIVATE" not in answer.body
    assert (await e.fetch("/neoaprs-ca.crt", headers={"Host": "evil.example"})).code == 403
    for name in ("ca.key", "server.key", "tls/ca.key", "tls/server.key"):
        assert (await https_fetch(e, f"/{name}")).code in (403, 404), name


async def test_the_log_has_no_key(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    await served(tmp_path, HTTPS)
    assert b"PRIVATE KEY" in (tmp_path / "tls" / "ca.key").read_bytes()
    assert "PRIVATE" not in caplog.text


# ---- while it is off --------------------------------------------------------------------------------------------------------------------------------

async def test_with_the_setting_off_nothing_changes(tmp_path: Path, away: None) -> None:
    e = await served(tmp_path, {"web/network": "true", "web/key": KEY})
    assert e.server is not None and e.server.secure.port == 0 and e.server.secure.server is None
    assert not (tmp_path / "tls").exists(), "no key is made for a setting that is off"
    answer = await plain(e, "/", host=f"{LAN}:{e.port}")
    assert answer.code == 200, "no redirect"
    assert (await plain(e, "/neoaprs-ca.crt", host=f"{LAN}:{e.port}")).code == 404
    urls = e.server.reach()
    assert urls and all(u.startswith("http://") for u in urls)


async def test_the_setting_without_the_network_does_nothing_either(tmp_path: Path) -> None:
    e = await served(tmp_path, {"web/https": "true"})
    assert e.server is not None and e.server.secure.port == 0 and not (tmp_path / "tls").exists()
    assert (await e.fetch("/")).code == 200


# ---- the switch -------------------------------------------------------------------------------------------------------------------------------------

async def test_the_switch_starts_and_stops_the_secure_page_while_the_daemon_runs_and_the_page_is_told(tmp_path: Path) -> None:
    e = await served(tmp_path, {"web/network": "true", "web/key": KEY})
    page = await e.ws()
    await page.until(lambda: "config" in page.topics)
    assert page.topics["config"]["https"]["on"] is False
    await page.send({"cmd": "set_config", "values": {"web/https": "true"}})
    await page.until(lambda: page.topics["config"]["https"]["on"])
    assert e.server is not None and (tmp_path / "tls" / "ca.key").is_file()
    assert (await https_fetch(e)).code == 200
    secure = await secure_ws(e)
    await secure.expect("hello")
    first = page.topics["config"]["https"]["fingerprint"]
    await page.send({"cmd": "set_config", "values": {"web/https": "false"}})
    await page.until(lambda: not page.topics["config"]["https"]["on"])
    await secure.until(lambda: secure.closed_with is not None)
    assert secure.closed_with is not None and secure.closed_with[0] == 1001
    with pytest.raises(OSError):
        await asyncio.to_thread(socket.create_connection, ("127.0.0.1", e.server.secure.state.port or 1), 1)
    assert (tmp_path / "tls" / "ca.key").is_file(), "the authority stays for the next time"
    await page.send({"cmd": "set_config", "values": {"web/https": "true"}})
    await page.until(lambda: page.topics["config"]["https"]["on"])
    assert page.topics["config"]["https"]["fingerprint"] == first, "the devices that trusted it still do"


async def test_the_network_off_stops_the_secure_page_too(tmp_path: Path) -> None:
    e = await served(tmp_path, HTTPS)
    page = await e.ws()
    await page.until(lambda: "config" in page.topics)
    await page.send({"cmd": "set_config", "values": {"web/network": "false"}})
    await page.until(lambda: not page.topics["config"]["https"]["on"])
    assert e.server is not None and e.server.secure.server is None and page.topics["config"]["urls"] == []
    await page.send({"cmd": "set_config", "values": {"web/network": "true"}})
    await page.until(lambda: page.topics["config"]["https"]["on"])
    assert (await https_fetch(e)).code == 200


# ---- the certificate follows the computer -----------------------------------------------------------------------------------------------------------

async def test_a_new_address_of_the_computer_is_in_the_certificate_after_the_next_change_of_the_settings_and_the_authority_stays(tmp_path: Path, lan: Lan) -> None:
    e = await served(tmp_path, HTTPS)
    before = await served_certificate(e)
    fingerprint = (await e.fetch("/neoaprs-ca.crt")).body
    lan.addresses = ["10.1.2.3"]
    assert e.server is not None
    e.server.settings_changed(e.ctl.config)
    await until_served(e, "10.1.2.3")
    after = await served_certificate(e)
    assert after.serial_number != before.serial_number and (await e.fetch("/neoaprs-ca.crt")).body == fingerprint
    assert (await https_fetch(e, host="127.0.0.1")).code == 200, "the new certificate is the one the clients get, and they still trust it"


async def test_the_certificate_is_looked_at_now_and_then_without_a_change_of_the_settings(tmp_path: Path, lan: Lan, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(secureside, "RECHECK_SEC", 0.05)
    e = await served(tmp_path, HTTPS)
    lan.addresses = ["10.9.8.7"]
    await until_served(e, "10.9.8.7")


# ---- when it cannot start ---------------------------------------------------------------------------------------------------------------------------

@pytest.mark.expects_errors
async def test_if_the_certificates_cannot_be_made_the_plain_page_goes_on_and_the_page_is_told_why(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    (tmp_path / "tls").write_text("in the way")                  # where the folder of the keys should be
    e = Env(tmp_path, web=True, settings=HTTPS, clock=utcnow)
    await e.start()
    assert e.server is not None
    assert (await e.fetch("/")).code == 200 and e.server.secure.port == 0
    page = await e.ws()
    await page.until(lambda: "config" in page.topics)
    https = page.topics["config"]["https"]
    assert https["on"] is False and https["port"] == 0 and "tls" in https["problem"] and https["fingerprint"] == ""
    assert any("secure connection is not working" in r.getMessage() for r in caplog.records)
    assert (await e.fetch("/neoaprs-ca.crt")).code == 404


@pytest.mark.expects_errors
async def test_if_no_port_after_the_plain_one_is_free_the_plain_page_goes_on_and_the_page_is_told_why(tmp_path: Path) -> None:
    e = await served(tmp_path, {"web/network": "true", "web/key": KEY})
    held: list[socket.socket] = []
    try:
        for port in range(e.port + 1, e.port + 1 + secureside.PORT_TRIES):          # (one that cannot be taken is taken already, which is as good)
            blocker = socket.socket()
            blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)          # (as Tornado binds: a port that only has connections on it is free)
            try:
                blocker.bind(("", port))
                blocker.listen()
            except OSError:
                blocker.close()
                continue
            held.append(blocker)
        page = await e.ws()
        await page.until(lambda: "config" in page.topics)
        await page.send({"cmd": "set_config", "values": {"web/https": "true"}})
        await page.until(lambda: "cannot listen" in page.topics["config"]["https"]["problem"])
        https = page.topics["config"]["https"]
        assert https["on"] is False and https["port"] == 0 and (await e.fetch("/")).code == 200
        assert e.server is not None and e.server.secure.retry_sec == secureside.RETRY_SEC, "looked at again soon"
    finally:
        for blocker in held:
            blocker.close()
