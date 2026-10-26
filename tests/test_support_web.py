"""The support bundle over HTTP (`POST /support/bundle`, neoaprs/web/supporthandler.py) and what the pages report about themselves (`page_error`, neoaprs/web/pageerrors.py), end to end on a daemon with its page's server; the line the
log has for a page that connects (neoaprs/web/browser.py) and for a setting that was saved."""
import asyncio
import io
import json
import logging
import threading
import zipfile
from pathlib import Path

import pytest

from neoaprs.web import access as web_access
from neoaprs.web import supporthandler
from neoaprs.web.access import COOKIE
from neoaprs.web.browser import browser_of
from neoaprs.web.pageerrors import KEPT, LOGGED_PER_MINUTE, PageErrors, one_line
from neoaprs.web.session import Connection
from neoaprs.web.supportwire import PageError
from tests.support.env import Env, until
from tests.support.supportdata import KEY
from tests.support.clock import FixedClock

NETWORK = {"web/network": "true", "web/key": KEY}
BODY = json.dumps({"page": {"build": "index-abc123.js", "browser": "Firefox 140 on Linux", "url": "http://127.0.0.1/"}})


async def served(tmp_path: Path, settings: dict[str, str] | None = None, clock: FixedClock | None = None) -> Env:
    e = Env(tmp_path, web=True, settings=settings, clock=clock)
    await e.start()
    return e


async def bundle(e: Env, body: str = BODY, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], dict[str, str]]:
    """(the status, the headers, the members of the zip) of a request for the bundle."""
    answer = await e.fetch("/support/bundle", method="POST", body=body, headers=headers)
    members = {}
    if answer.code == 200:
        with zipfile.ZipFile(io.BytesIO(answer.body)) as z:
            members = {n: z.read(n).decode("utf-8") for n in z.namelist()}
    return answer.code, dict(answer.headers), members


@pytest.fixture(autouse=True)
def lan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("neoaprs.web.server.lan_addresses", lambda: ["192.168.1.20"])


@pytest.fixture
def away(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web_access, "is_loopback", lambda ip: False)


# ---- the endpoint

async def test_a_page_of_this_computer_gets_the_bundle_as_a_download(tmp_path: Path) -> None:
    e = await served(tmp_path)
    code, headers, members = await bundle(e)
    assert code == 200 and headers["Content-Type"] == "application/zip"
    assert headers["Content-Disposition"] == 'attachment; filename="neoaprs-support-OH2GBA-20261021-120000Z.zip"'
    assert headers["Cache-Control"] == "no-store"
    assert {"README.txt", "summary.txt", "settings.json", "state.json", "doctor.txt", "database.txt", "packets.txt", "page.json", "page-errors.json"} <= set(members)
    assert json.loads(members["page.json"]) == json.loads(BODY)["page"]
    assert "running, up" in members["summary.txt"] and "the running daemon" in members["summary.txt"]


async def test_the_state_of_the_running_parts_is_in_the_bundle(tmp_path: Path) -> None:
    e = await served(tmp_path)
    state = json.loads((await bundle(e))[2]["state.json"])
    assert state["tnc"]["state"] == "connected" and state["tnc"]["path"] == e.link and "lines" in state["tnc"]
    assert state["gps"]["state"] == "off" and state["beacon"]["interval_min"] == 0 and state["beacon"]["transmit_blocked"] is None
    assert state["daemon"]["pages_open"] == 0 and state["daemon"]["threads"] >= 1 and state["daemon"]["tasks"] >= 1 and state["daemon"]["uptime_sec"] >= 0
    assert state["web"]["port"] == e.port and state["web"]["address"] == "127.0.0.1"
    assert set(state) >= {"made_at", "daemon", "web", "tnc", "gps", "beacon", "rig", "map", "update", "ports"} and isinstance(state["ports"], list)
    assert state["daemon"]["database"]["reads"] >= 0 and state["daemon"]["database"]["state"] == "open"


async def test_the_bundle_of_the_daemon_holds_the_errors_the_pages_reported_and_never_the_key(tmp_path: Path) -> None:
    e = await served(tmp_path, NETWORK)
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) >= 1)
    await page.send({"cmd": "page_error", "message": f"boom {KEY}", "stack": "at f (a.js:1:2)\nat g (b.js:3:4)", "source": "vue", "at": "2026-10-21T12:00:00Z", "build": "index-abc123.js"})
    await until(lambda: e.server is not None and len(e.server.api.page_errors.snapshot()) == 1)
    _, _, members = await bundle(e)
    errors = json.loads(members["page-errors.json"])
    assert len(errors) == 1 and errors[0]["source"] == "vue" and errors[0]["from"] == "127.0.0.1" and errors[0]["stack"].startswith("at f")
    assert all(KEY not in text and KEY.replace("-", "") not in text for text in members.values()), "the access key is in no member"
    assert json.loads(members["settings.json"])["values"]["web/key"] == f"(set, {len(KEY)} characters)"


async def test_the_log_says_a_bundle_was_made_for_the_page(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    e = await served(tmp_path)
    with caplog.at_level(logging.INFO, logger="neoaprs.web"):
        await bundle(e)
    lines = [r.getMessage() for r in caplog.records if "support bundle made for the page" in r.getMessage()]
    assert len(lines) == 1 and lines[0].startswith("support bundle made for the page: neoaprs-support-OH2GBA-20261021-120000Z.zip, ") and lines[0].endswith(" KB")


async def test_a_device_that_has_not_logged_in_gets_no_bundle_and_one_that_has_does(tmp_path: Path, away: None) -> None:
    e = await served(tmp_path, NETWORK)
    assert (await bundle(e))[0] == 401
    assert (await bundle(e, headers={"Cookie": f"{COOKIE}=nonsense"}))[0] == 401
    login = await e.fetch("/access", method="POST", body=json.dumps({"key": KEY}))
    cookie = login.headers["Set-Cookie"].split(";", 1)[0]
    code, _, members = await bundle(e, headers={"Cookie": cookie})
    assert code == 200 and "summary.txt" in members


async def test_no_bundle_for_a_name_that_is_not_ours_or_a_script_of_another_site(tmp_path: Path) -> None:
    e = await served(tmp_path)
    assert (await bundle(e, headers={"Host": "evil.example.com"}))[0] == 403
    assert (await bundle(e, headers={"Origin": "http://evil.example.com"}))[0] == 403
    assert (await bundle(e, headers={"Origin": f"http://127.0.0.1:{e.port}"}))[0] == 200


async def test_a_body_that_is_not_the_page_is_refused(tmp_path: Path) -> None:
    e = await served(tmp_path)
    for body in ("", "not json", "[1]", "{}", '{"page": 5}', '{"page": [1]}', '{"page": null}'):
        assert (await bundle(e, body))[0] == 400, body
    assert (await e.fetch("/support/bundle")).code == 405, "it is a POST"


async def test_a_body_over_256_kilobytes_is_refused_and_one_a_little_under_it_is_taken(tmp_path: Path) -> None:
    e = await served(tmp_path)
    big = json.dumps({"page": {"errors": "x" * (supporthandler.MAX_BODY + 100)}})
    assert (await bundle(e, big))[0] in (400, 413, 599), "the server cuts the connection"
    fits = json.dumps({"page": {"errors": "x" * (200 * 1024)}})
    code, _, members = await bundle(e, fits)
    assert code == 200 and len(json.loads(members["page.json"])["errors"]) == 200 * 1024


async def test_only_one_bundle_is_made_at_a_time(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    e = await served(tmp_path)
    started, release = threading.Event(), threading.Event()
    real = supporthandler.make_bundle

    def slow(*args: object, **kwargs: object) -> object:
        started.set()
        assert release.wait(10)
        return real(*args, **kwargs)  # type: ignore[arg-type]
    monkeypatch.setattr(supporthandler, "make_bundle", slow)
    assert e.server is not None
    first = asyncio.create_task(bundle(e))
    await until(started.is_set)
    answer = await e.fetch("/support/bundle", method="POST", body=BODY)
    assert answer.code == 429 and int(answer.headers["Retry-After"]) > 0 and e.server.bundles.busy
    release.set()
    assert (await first)[0] == 200
    assert not e.server.bundles.busy
    assert (await bundle(e))[0] == 200, "the next one can be made"


async def test_a_bundle_that_cannot_be_made_is_a_500_that_says_to_look_in_the_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    e = await served(tmp_path)

    def broken(*args: object, **kwargs: object) -> object:
        raise OSError("the disk is full")
    monkeypatch.setattr(supporthandler, "make_bundle", broken)
    answer = await e.fetch("/support/bundle", method="POST", body=BODY)
    assert answer.code == 500 and b"the log says why" in answer.body
    assert any("could not be made" in r.getMessage() and r.exc_info for r in caplog.records)
    assert e.server is not None and not e.server.bundles.busy


# ---- page_error

def connection(ip: str = "127.0.0.1") -> Connection:
    class Quiet:
        def send_json(self, text: str) -> None: ...
        def buffered(self) -> int:
            return 0

    class Out:
        def send(self, conn: Connection, message: dict[str, object]) -> None: ...
        def send_frame(self, conn: Connection, text: str) -> None: ...
    return Connection(Quiet(), Out(), ip)


def report(n: int = 0, source: str = "vue", message: str | None = None, stack: str | None = None) -> PageError:
    return PageError.model_validate({"cmd": "page_error", "message": message if message is not None else f"error {n}", "stack": stack if stack is not None else f"at f{n} (a.js:1:2)\nat g (b.js:3:4)",
                                     "source": source, "at": "2026-10-21T12:00:00Z", "build": "index-abc.js"})


def warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING and r.name == "neoaprs.web"]


def test_a_page_error_is_a_warning_with_the_source_the_build_the_message_and_the_first_line_of_the_stack(caplog: pytest.LogCaptureFixture) -> None:
    errors = PageErrors(FixedClock())
    errors.note(connection(), report(1, "promise"))
    assert warnings(caplog) == ["page error (promise) on page index-abc.js: error 1 | at f1 (a.js:1:2)"]
    errors.note(connection(), report(2, "window", stack=""))
    assert warnings(caplog)[-1] == "page error (window) on page index-abc.js: error 2 | "


def test_a_page_cannot_forge_a_line_of_the_log() -> None:
    assert one_line("a\nb\r\n2026-10-21 12:00:00Z  ERROR  fake\x00\x1b[31m", 100) == "a b 2026-10-21 12:00:00Z ERROR fake [31m"
    assert one_line("x" * 20, 10) == "x" * 9 + "…"


def test_a_message_with_a_line_break_is_one_line_in_the_log(caplog: pytest.LogCaptureFixture) -> None:
    PageErrors(FixedClock()).note(connection(), report(message="first\n2026-10-21 12:00:00Z  ERROR  forged", stack="\n\n  at real (x.js:1:1)\nat other"))
    (line,) = warnings(caplog)
    assert "\n" not in line and line.endswith("first 2026-10-21 12:00:00Z ERROR forged | at real (x.js:1:1)")


def test_twenty_a_minute_are_logged_and_the_rest_counted_in_one_line_when_the_minute_is_over(caplog: pytest.LogCaptureFixture) -> None:
    clock = FixedClock()
    errors = PageErrors(clock)
    conn = connection()
    for n in range(27):
        errors.note(conn, report(n))
    assert len(warnings(caplog)) == LOGGED_PER_MINUTE == 20, "the others wait for the end of the minute"
    clock.advance(61)
    errors.note(conn, report(100))
    lines = warnings(caplog)
    assert lines[20] == "7 more page errors not logged this minute" and lines[21].startswith("page error (vue)") and len(lines) == 22
    assert len(errors.snapshot()) == 28, "all of them are kept, logged or not"


def test_one_report_not_logged_is_told_in_the_singular(caplog: pytest.LogCaptureFixture) -> None:
    errors = PageErrors(FixedClock())
    conn = connection()
    for n in range(21):
        errors.note(conn, report(n))
    errors.forget(conn)
    assert warnings(caplog)[-1] == "1 more page error not logged this minute"
    errors.forget(conn)
    assert len(warnings(caplog)) == 21, "said once"


def test_each_connection_has_its_own_twenty(caplog: pytest.LogCaptureFixture) -> None:
    errors = PageErrors(FixedClock())
    one, two = connection("10.0.0.1"), connection("10.0.0.2")
    for n in range(30):
        errors.note(one, report(n))
    for n in range(5):
        errors.note(two, report(n))
    assert len(warnings(caplog)) == 25


async def test_the_line_about_the_flood_comes_when_the_minute_ends_though_no_report_follows(caplog: pytest.LogCaptureFixture) -> None:
    errors = PageErrors(FixedClock(), window_sec=0.1)
    conn = connection()
    for n in range(23):
        errors.note(conn, report(n))
    assert len(warnings(caplog)) == 20
    await until(lambda: "3 more page errors not logged this minute" in warnings(caplog))
    errors.forget(conn)
    assert len(warnings(caplog)) == 21, "said once"


def test_the_latest_hundred_are_kept_with_the_address_of_the_page(caplog: pytest.LogCaptureFixture) -> None:
    errors = PageErrors(FixedClock())
    conn = connection("192.168.1.20")
    for n in range(130):
        errors.note(conn, report(n))
    kept = errors.snapshot()
    assert len(kept) == KEPT == 100 and kept[0]["message"] == "error 30" and kept[-1]["message"] == "error 129"
    assert kept[-1]["from"] == "192.168.1.20" and kept[-1]["source"] == "vue" and kept[-1]["build"] == "index-abc.js" and kept[-1]["received_at"] == "2026-10-21T12:00:00Z"


def test_the_command_has_the_limits_of_the_protocol() -> None:
    ok = {"cmd": "page_error", "message": "m" * 2000, "stack": "s" * 8000, "source": "window", "at": "2026-10-21T12:00:00Z", "build": "b" * 64}
    PageError.model_validate(ok)
    for field, value in (("message", "m" * 2001), ("stack", "s" * 8001), ("build", "b" * 65), ("source", "worker"), ("at", "yesterday")):
        with pytest.raises(ValueError):
            PageError.model_validate({**ok, field: value})


async def test_a_page_reports_over_its_socket_and_is_not_answered(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    e = await served(tmp_path)
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) >= 1)
    seen = len(page.messages)
    with caplog.at_level(logging.WARNING, logger="neoaprs.web"):
        await page.send({"cmd": "page_error", "message": "x is undefined", "stack": "at render (Map.vue:10:5)", "source": "vue", "at": "2026-10-21T12:00:00Z", "build": "index-abc123.js"})
        await until(lambda: any("page error (vue)" in m for m in warnings(caplog)))
    assert "page error (vue) on page index-abc123.js: x is undefined | at render (Map.vue:10:5)" in warnings(caplog)
    await page.quiet(0.2)
    assert [m for m in page.messages[seen:] if m["type"] == "error"] == []
    await page.send({"cmd": "page_error", "message": "m", "stack": "", "source": "bogus", "at": "2026-10-21T12:00:00Z", "build": "b"})
    error = await page.expect("error")
    assert error["cmd"] == "page_error" and error["code"] == "invalid"


async def test_a_page_that_leaves_has_its_flood_told(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    e = await served(tmp_path)
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) >= 1)
    with caplog.at_level(logging.WARNING, logger="neoaprs.web"):
        for n in range(23):
            await page.send({"cmd": "page_error", "message": f"m{n}", "stack": "", "source": "window", "at": "2026-10-21T12:00:00Z", "build": "b"})
        assert e.server is not None
        await until(lambda: len(e.server.api.page_errors.snapshot()) == 23 if e.server else False)
        await page.aclose()
        await until(lambda: "3 more page errors not logged this minute" in warnings(caplog))


# ---- the browser in the log, the settings in the log

def test_a_browser_is_named_in_a_few_words_from_its_user_agent() -> None:
    cases = {
        "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0": "Firefox 140 on Linux",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.2592.87": "Edge 126 on Windows",
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36": "Chrome 126 on Android 14",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1": "Safari 17 on iOS",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15": "Safari 17 on macOS",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) QtWebEngine/6.8.0 Chrome/122.0.0.0 Safari/537.36": "NeoAPRS window (Qt) 6 on Linux",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) OPR/110.0.0.0 Chrome/124.0.0.0 Safari/537.36": "Opera 110 on Linux",
        "": "no User-Agent",
    }
    for agent, shown in cases.items():
        assert browser_of(agent) == shown, agent
    odd = browser_of("curl/8.5.0\nERROR  fake line")
    assert odd == "unknown browser (curl/8.5.0 ERROR fake line)" and "\n" not in odd


async def test_the_log_says_which_browser_connected(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    e = await served(tmp_path)
    with caplog.at_level(logging.INFO, logger="neoaprs.web"):
        page = await e.ws()
        await page.until(lambda: len(page.of("state")) >= 1)
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("page connected from")]
    assert len(lines) == 1 and lines[0].startswith("page connected from 127.0.0.1: ")
    assert lines[0].split(": ", 1)[1].startswith(("unknown browser (", "no User-Agent"))


async def test_a_setting_saved_from_the_page_is_logged_with_its_old_value_and_a_secret_only_as_set(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    e = await served(tmp_path, {"station/comment": "old comment"})
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) >= 1)
    with caplog.at_level(logging.INFO, logger="neoaprs.web"):
        await page.send({"cmd": "set_config", "values": {"station/comment": "new comment", "web/network": "true", "station/call": "OH2GBA"}})
        await until(lambda: any(r.getMessage().startswith("settings: web/network") for r in caplog.records))
        await page.until(lambda: page.topics["config"]["values"]["web/key"] != "")
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("settings: ")]
    assert "settings: station/comment = new comment (was old comment)" in lines and "settings: web/network = true (was false)" in lines
    assert not any("station/call" in line for line in lines), "a value that did not change is not told"
    key = page.topics["config"]["values"]["web/key"]
    with caplog.at_level(logging.INFO, logger="neoaprs.web"):
        await page.send({"cmd": "set_config", "values": {"web/key": ""}})
        await until(lambda: any(r.getMessage().startswith("settings: web/key") for r in caplog.records))
    assert f"settings: web/key = (empty) (was (set, {len(key)} characters))" in [r.getMessage() for r in caplog.records]
    assert key not in caplog.text


async def test_an_empty_value_and_a_long_one_are_shown_as_such(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    e = await served(tmp_path, {"station/status": "was here"})
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) >= 1)
    with caplog.at_level(logging.INFO, logger="neoaprs.web"):
        await page.send({"cmd": "set_config", "values": {"station/status": ""}})
        await until(lambda: any(r.getMessage().startswith("settings: station/status") for r in caplog.records))
    assert "settings: station/status = (empty) (was was here)" in [r.getMessage() for r in caplog.records]
