"""Send logs (`POST /support/send`, neoaprs/web/supportsend.py): the daemon makes the support bundle exactly as Download logs does and posts it with the note to the project's server, here a fake one on the loopback
(tests/support/fakesupportserver.py). The multipart body, the answers of the server (ok, refused, too many, no answer, no connection), what the log says, who may ask, one at a time, and the address that cannot be changed to another
computer's."""
import asyncio
import io
import json
import logging
import socket
import zipfile
from pathlib import Path

import pytest

from neoaprs import VERSION
from neoaprs.updatefetch import multipart, post_form
from neoaprs.versions import SUPPORT_URL
from neoaprs.web import access as web_access
from neoaprs.web import supportsend
from neoaprs.web.supportsend import MAX_NOTE, answer_of, support_url
from tests.support.env import Env, until
from tests.support.fakesupportserver import FakeSupportServer, parse_form, support_server
from tests.support.supportdata import KEY

PAGE = {"build": "index-abc123.js", "browser": "Firefox 140 on Linux"}
REF = "NEO-20261103-1015-7F3A"


async def served(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake: FakeSupportServer | None = None, settings: dict[str, str] | None = None) -> tuple[Env, FakeSupportServer]:
    fake = fake or await support_server()
    monkeypatch.setenv(supportsend.ENV_URL, fake.url)
    e = Env(tmp_path, web=True, settings=settings)
    await e.start()
    return e, fake


async def send(e: Env, note: object = "It stopped beaconing after the update.", headers: dict[str, str] | None = None, body: str | None = None) -> tuple[int, dict[str, object]]:
    """(the status, the JSON answer) of a request to send the logs."""
    answer = await e.fetch("/support/send", method="POST", body=body if body is not None else json.dumps({"page": PAGE, "note": note}), headers=headers)
    try:
        return answer.code, json.loads(answer.body)
    except ValueError:
        return answer.code, {}


@pytest.fixture(autouse=True)
def lan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("neoaprs.web.server.lan_addresses", lambda: ["192.168.1.20"])


# ---- the multipart form and the answers

def test_a_multipart_body_holds_the_fields_and_the_file_whatever_is_in_them() -> None:
    content = b"PK\x03\x04\r\n--neoaprs-boundary\r\n\x00\xff" * 50
    kind, body = multipart({"note": "line one\r\nline two äあ\n\n", "call": "OH2GBA"}, {"bundle": ("a.zip", content)})
    assert kind.startswith("multipart/form-data; boundary=neoaprs-")
    fields, files = parse_form(kind, body)
    assert fields == {"note": "line one\r\nline two äあ\n\n", "call": "OH2GBA"} and files == {"bundle": ("a.zip", content)}


def test_the_answer_of_the_server_is_a_reference_or_a_reason_the_page_knows_or_refused() -> None:
    assert answer_of(200, json.dumps({"ok": True, "ref": REF}).encode()).wire() == {"ok": True, "ref": REF}
    assert answer_of(429, b'{"ok": false, "reason": "rate"}').wire() == {"ok": False, "reason": "rate"}
    assert answer_of(413, b'{"ok": false, "reason": "too_large"}').wire() == {"ok": False, "reason": "too_large"}
    for status, body in [(400, b'{"ok": false, "reason": "not_a_bundle"}'), (500, b'{"ok": false, "reason": "storage"}'), (200, b"<html>"), (200, b"[1]"), (200, b'{"ok": true}'), (200, b'{"ok": true, "ref": "x\\nBcc: y"}'),
                         (500, b'{"ok": true, "ref": "' + REF.encode() + b'"}'), (200, b'{"ok": false, "reason": {"a": 1}}')]:
        assert answer_of(status, body).wire() == {"ok": False, "reason": "refused"}, body


def test_the_address_is_the_projects_unless_a_server_of_this_computer_is_named() -> None:
    assert support_url({}) == SUPPORT_URL == "https://neo.oh2gba.eu/support/send.php"
    assert support_url({supportsend.ENV_URL: "http://127.0.0.1:8123/x/send.php"}) == "http://127.0.0.1:8123/x/send.php"
    for other in ("https://example.org/send.php", "http://192.168.1.5/send.php", "ftp://127.0.0.1/x", "http://user@127.0.0.1/x", "file:///etc/passwd", ""):
        assert support_url({supportsend.ENV_URL: other}) == SUPPORT_URL, other


async def test_a_post_that_finds_no_server_is_none_and_one_that_is_refused_has_its_status_and_body() -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        closed = f"http://127.0.0.1:{probe.getsockname()[1]}/send.php"
    assert await asyncio.to_thread(post_form, closed, {"a": "b"}, {}, "0.1", "linux", 5.0) is None
    assert post_form("file:///etc/passwd", {}, {}, "0.1", "linux") is None and post_form("ftp://127.0.0.1/", {}, {}, "0.1", "linux") is None
    fake = await support_server({"ok": False, "reason": "rate"})
    fake.status = 429
    assert await asyncio.to_thread(post_form, fake.url, {"a": "b"}, {}, "0.1", "linux", 5.0) == (429, b'{"ok": false, "reason": "rate"}')
    fake.status, fake.body = 302, b""
    assert (await asyncio.to_thread(post_form, fake.url, {"a": "b"}, {}, "0.1", "linux", 5.0))[0] == 302, "a redirect is an answer, not followed"


# ---- the route

async def test_the_bundle_goes_with_the_note_the_call_the_version_and_the_platform_and_the_page_gets_the_reference(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    e, fake = await served(tmp_path, monkeypatch)
    assert await send(e) == (200, {"ok": True, "ref": REF})
    (got,) = fake.requests
    assert got.path == "/support/send.php" and got.headers["user-agent"].startswith(f"NeoAPRS/{VERSION} (") and got.headers["content-type"].startswith("multipart/form-data; boundary=")
    assert got.fields == {"note": "It stopped beaconing after the update.", "call": "OH2GBA", "version": VERSION, "platform": e.ctl.updatecheck.platform}
    name, data = got.files["bundle"]
    assert name == "neoaprs-support-OH2GBA-20261021-120000Z.zip"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        members = set(z.namelist())
        assert {"README.txt", "summary.txt", "settings.json", "page.json"} <= members and json.loads(z.read("page.json")) == PAGE


async def test_it_is_the_bundle_of_download_logs_with_the_secrets_taken_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    e, fake = await served(tmp_path, monkeypatch, settings={"web/network": "true", "web/key": KEY})
    assert (await send(e))[0] == 200
    plain = await e.fetch("/support/bundle", method="POST", body=json.dumps({"page": PAGE}))
    with zipfile.ZipFile(io.BytesIO(fake.requests[0].files["bundle"][1])) as sent, zipfile.ZipFile(io.BytesIO(plain.body)) as downloaded:
        assert sent.namelist() == downloaded.namelist()
        assert all(KEY not in sent.read(n).decode("utf-8") and KEY.replace("-", "") not in sent.read(n).decode("utf-8") for n in sent.namelist())


async def test_no_note_is_an_empty_one_and_a_long_one_is_cut_and_the_blanks_round_it_go(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    e, fake = await served(tmp_path, monkeypatch)
    assert (await send(e, body=json.dumps({"page": PAGE})))[0] == 200
    assert (await send(e, "  \n spaced \n "))[0] == 200
    assert (await send(e, "x" * 3000))[0] == 200
    assert [r.fields["note"] for r in fake.requests] == ["", "spaced", "x" * MAX_NOTE]


@pytest.mark.parametrize("note", [5, None, ["a"], {"a": 1}])
async def test_a_note_that_is_not_text_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, note: object) -> None:
    e, fake = await served(tmp_path, monkeypatch)
    assert (await send(e, note))[0] == 400 and fake.requests == []


async def test_a_body_that_is_not_the_page_is_refused_and_nothing_is_sent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    e, fake = await served(tmp_path, monkeypatch)
    for body in ("", "not json", "[1]", "{}", '{"note": "a"}', '{"page": 5}', '{"page": null}'):
        assert (await send(e, body=body))[0] == 400, body
    assert (await e.fetch("/support/send")).code == 405, "it is a POST"
    assert fake.requests == []


@pytest.mark.parametrize(("status", "answer", "reason"), [
    (400, {"ok": False, "reason": "not_a_bundle"}, "refused"),
    (429, {"ok": False, "reason": "rate"}, "rate"),
    (413, {"ok": False, "reason": "too_large"}, "too_large"),
    (500, {"ok": False, "reason": "storage"}, "refused"),
    (404, {}, "refused"),
])
async def test_what_the_server_refuses_is_told_in_a_reason_the_page_has_words_for(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, status: int, answer: dict[str, object], reason: str) -> None:
    fake = await support_server(answer)
    fake.status = status
    e, _ = await served(tmp_path, monkeypatch, fake)
    with caplog.at_level(logging.INFO, logger="neoaprs.web"):
        assert await send(e) == (200, {"ok": False, "reason": reason})
    lines = [r.getMessage() for r in caplog.records if "support logs" in r.getMessage()]
    assert len(lines) == 1 and lines[0].startswith(f"support logs not sent: {reason} (status {status}") and lines[0].endswith("a note of 38 characters")


async def test_a_server_that_gives_an_answer_that_is_no_json_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = await support_server()
    fake.body = b"<html>502 Bad Gateway</html>"
    fake.status = 502
    e, _ = await served(tmp_path, monkeypatch, fake)
    assert await send(e) == (200, {"ok": False, "reason": "refused"})


async def test_no_server_to_reach_is_offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        closed = f"http://127.0.0.1:{probe.getsockname()[1]}/support/send.php"
    monkeypatch.setenv(supportsend.ENV_URL, closed)
    e = Env(tmp_path, web=True)
    await e.start()
    assert await send(e) == (200, {"ok": False, "reason": "offline"})
    assert e.server is not None and not e.server.bundles.sending


async def test_a_bundle_over_the_limit_is_not_sent_at_all(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    e, fake = await served(tmp_path, monkeypatch)
    monkeypatch.setattr(supportsend, "MAX_SEND_BYTES", 100)
    assert await send(e) == (200, {"ok": False, "reason": "too_large"})
    assert fake.requests == []


async def test_the_log_says_what_was_sent_and_how_long_the_note_was_and_never_the_note(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    e, _ = await served(tmp_path, monkeypatch)
    with caplog.at_level(logging.INFO, logger="neoaprs.web"):
        await send(e, "my secret words")
    lines = [r.getMessage() for r in caplog.records if "support logs" in r.getMessage()]
    assert len(lines) == 1 and lines[0].startswith("support logs sent: neoaprs-support-OH2GBA-20261021-120000Z.zip, ") and lines[0].endswith(f", reference {REF}, a note of 15 characters")
    assert not any("secret words" in r.getMessage() for r in caplog.records)


async def test_only_one_is_made_and_sent_at_a_time(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    e, _ = await served(tmp_path, monkeypatch)
    started, release = asyncio.Event(), asyncio.Event()
    real = supportsend.send_bundle

    async def slow(*args: object) -> supportsend.Sent:
        started.set()
        await release.wait()
        return await real(*args)  # type: ignore[arg-type]
    monkeypatch.setattr(supportsend, "send_bundle", slow)
    first = asyncio.create_task(send(e))
    await started.wait()
    assert e.server is not None and e.server.bundles.sending
    answer = await e.fetch("/support/send", method="POST", body=json.dumps({"page": PAGE, "note": ""}))
    assert answer.code == 429 and int(answer.headers["Retry-After"]) > 0
    assert (await e.fetch("/support/bundle", method="POST", body=json.dumps({"page": PAGE}))).code == 429, "Download logs waits too"
    release.set()
    assert await first == (200, {"ok": True, "ref": REF})
    await until(lambda: not (e.server and e.server.bundles.sending))
    assert (await send(e))[0] == 200, "the next one can go"


@pytest.mark.expects_errors
async def test_a_bundle_that_cannot_be_made_is_a_500_and_nothing_is_sent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from neoaprs.web import supporthandler
    e, fake = await served(tmp_path, monkeypatch)

    def broken(*args: object, **kwargs: object) -> object:
        raise OSError("the disk is full")
    monkeypatch.setattr(supporthandler, "make_bundle", broken)
    assert (await send(e))[0] == 500
    assert fake.requests == [] and e.server is not None and not e.server.bundles.sending


@pytest.fixture
def away(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web_access, "is_loopback", lambda ip: False)


async def test_a_device_that_has_not_logged_in_sends_nothing_and_a_script_of_another_site_cannot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, away: None) -> None:
    e, fake = await served(tmp_path, monkeypatch, settings={"web/network": "true", "web/key": KEY})
    assert (await send(e))[0] == 401 and (await send(e, headers={"Origin": "http://evil.example.com"}))[0] in (401, 403)
    login = await e.fetch("/access", method="POST", body=json.dumps({"key": KEY}))
    cookie = login.headers["Set-Cookie"].split(";", 1)[0]
    assert fake.requests == []
    assert (await send(e, headers={"Cookie": cookie, "Origin": "http://evil.example.com"}))[0] == 403
    assert (await send(e, headers={"Cookie": cookie, "Host": "evil.example.com"}))[0] == 403
    assert await send(e, headers={"Cookie": cookie}) == (200, {"ok": True, "ref": REF}) and len(fake.requests) == 1
