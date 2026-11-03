"""The frequencies the project suggests for the HF radio (neoaprs/services/frequencies.py, neoaprs/versions.py): the file `site/frequencies.json` and how it is understood (every entry checked, at most three), the service that asks for it a minute after
the start and when a page shows the HF box and not more often than every fifteen minutes (and never with the update check off), the last good list kept across a restart, a file that is bad or a server that is not there leaving it as it was, the fall-back
to the version page's dial and then to the built-in two, and the page's `hf_frequencies` and the list in the topic `hf`."""
import json
import logging
from pathlib import Path

import pytest

from neoaprs import mercury
from neoaprs.mercurymodem import Mercury
from neoaprs.services.frequencies import ENV_SWITCH, ENV_URL, FREQUENCIES_EVERY_SEC, Frequencies
from neoaprs.versions import FREQUENCIES_ROW, FREQUENCIES_URL, Frequency, frequencies_text, on_this_computer, parse_frequencies, suggested
from tests.support.env import Env, remember_stop, until
from tests.support.fakemercury import Air
from tests.support.storedb import store_at

ROOT = Path(__file__).resolve().parent.parent
FILE = b'{"frequencies": [{"band": "40 m", "dial": "7.0541 MHz USB"}, {"band": "20 m", "dial": "14.1070 MHz USB"}]}'
TWO = [Frequency("40 m", "7.0541 MHz USB"), Frequency("20 m", "14.1070 MHz USB")]
BUILT_IN = [Frequency(band, dial) for band, dial in mercury.SUGGESTED]


class Server:
    """The project's file as a fetch function: the answers in turn (None is a server that is not there), and what it was asked."""

    def __init__(self, *answers: bytes | None) -> None:
        self.answers = list(answers)
        self.asked: list[tuple[str, str, str, int]] = []

    async def __call__(self, address: str, version: str, platform: str, max_bytes: int) -> bytes | None:
        self.asked.append((address, version, platform, max_bytes))
        return self.answers.pop(0) if self.answers else self.answers_last

    answers_last: bytes | None = None


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def service(server: Server, clock: Clock | None = None, environ: dict[str, str] | None = None, **more: object) -> Frequencies:
    made = Frequencies("0.17.0", "linux", server, first_sec=0.05, environ={} if environ is None else environ, clock=clock or Clock(), **more)       # type: ignore[arg-type]
    remember_stop(made.stop)
    return made


# ---- the file

def test_the_file_of_the_site_is_a_list_the_daemon_understands_and_the_site_checks_the_same_two_forms() -> None:
    body = (ROOT / "site" / "frequencies.json").read_bytes()
    assert parse_frequencies(body) == TWO
    assert [(int(f.band.split()[0]), f.dial.split()[0]) for f in TWO] == [(40, dict(mercury.FREQUENCIES)[40]), (20, dict(mercury.FREQUENCIES)[20])], "the file ships the dials of FREQUENCIES"


def test_every_entry_is_checked_and_a_bad_one_is_dropped_a_band_once_and_three_at_most() -> None:
    good = {"band": "30 m", "dial": "10.1462 MHz USB"}
    assert parse_frequencies(json.dumps({"frequencies": [good]})) == [Frequency("30 m", "10.1462 MHz USB")]
    for bad in ({"band": "40", "dial": "7.0541 MHz USB"}, {"band": "40 m", "dial": "7.0541"}, {"band": "40 m", "dial": "7.0541 MHz FM"}, {"band": "<b>40 m</b>", "dial": "7.0541 MHz USB"}, {"band": "40 m"}, {"dial": "7.0541 MHz USB"},
                {"band": 40, "dial": "7.0541 MHz USB"}, "7.0541 MHz USB", None, {"band": "40 m", "dial": "1234.5 MHz USB"}, {"band": "1000 m", "dial": "7.0541 MHz USB"}):
        assert parse_frequencies(json.dumps({"frequencies": [bad, good]})) == [Frequency("30 m", "10.1462 MHz USB")], bad

    def entry(band: str, dial: str) -> dict[str, str]:
        return {"band": band, "dial": dial}

    found = parse_frequencies(json.dumps({"frequencies": [entry("40 m", "7.0541 MHz USB"), entry("40 m", "7.0600 MHz USB"), entry(" 20 m ", " 14.1070 MHz USB "), entry("30 m", "10.1462 MHz USB"), entry("17 m", "18.1000 MHz USB")]}))
    assert found == [Frequency("40 m", "7.0541 MHz USB"), Frequency("20 m", "14.1070 MHz USB"), Frequency("30 m", "10.1462 MHz USB")], "a band once, spaces cut, three at most"


def test_a_file_that_is_no_list_or_has_no_good_entry_is_none() -> None:
    for body in (b"", b"not json", b"[]", b'{"frequencies": "7.0541"}', b'{"frequencies": []}', b'{"frequencies": [{"band": "x"}]}', b'{"other": 1}', b"null"):
        assert parse_frequencies(body) is None, body


def test_the_box_shows_the_projects_list_else_the_version_pages_dial_else_the_built_in_two() -> None:
    assert suggested(TWO, "7.0443 MHz USB", BUILT_IN, "40 m") == TWO
    assert suggested([], "7.0443 MHz USB", BUILT_IN, "40 m") == [Frequency("40 m", "7.0443 MHz USB")]
    assert suggested([], "", BUILT_IN, "40 m") == BUILT_IN == TWO
    assert [dict(mercury.FREQUENCIES)[int(band.split()[0])] + " MHz USB" for band, _ in mercury.SUGGESTED] == [dial for _, dial in mercury.SUGGESTED], "the built-in two are dials of FREQUENCIES"


def test_the_list_is_kept_as_the_file_has_it_and_comes_back_the_same() -> None:
    assert parse_frequencies(frequencies_text(TWO)) == TWO


def test_the_address_is_the_projects_unless_a_server_on_this_computer_is_named() -> None:
    assert FREQUENCIES_URL == "https://neo.oh2gba.eu/frequencies.json"
    for good in ("http://127.0.0.1:8123/frequencies.json", "https://localhost/f.json"):
        assert on_this_computer(good), good
    for bad in ("https://neo.oh2gba.eu/frequencies.json", "http://127.0.0.1.evil.example/f.json", "http://user@127.0.0.1/f.json", "ftp://127.0.0.1/f", "http://127.0.0.1:port/f", "http://127.0.0.1/a b"):
        assert not on_this_computer(bad), bad
    assert service(Server()).url == FREQUENCIES_URL
    assert service(Server(), environ={ENV_URL: "http://127.0.0.1:8123/frequencies.json"}).url == "http://127.0.0.1:8123/frequencies.json"
    assert service(Server(), environ={ENV_URL: "https://evil.example/frequencies.json"}).url == FREQUENCIES_URL, "only a server of this computer is taken"


# ---- the service

async def test_the_server_is_asked_a_minute_after_the_start_and_the_list_is_told_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    server = Server(FILE)
    made = service(server)
    told = []
    made.changed.connect(lambda: told.append(list(made.listed)))
    with caplog.at_level(logging.INFO, logger="neoaprs.update"):
        await made.start()
        await until(lambda: made.listed == TWO)
    assert told == [TWO] and server.asked == [(FREQUENCIES_URL, "0.17.0", "linux", 8192)] and made.asked == 1
    assert any("the project suggests the frequencies 40 m 7.0541 MHz USB, 20 m 14.1070 MHz USB (was none)" in r.getMessage() for r in caplog.records), "a change of the list is a line at INFO"


async def test_a_page_that_shows_the_box_asks_at_most_every_fifteen_minutes_however_many_pages_there_are() -> None:
    server = Server(FILE)
    clock = Clock()
    made = service(server, clock)
    made.wanted()
    made.wanted()
    made.wanted()
    await until(lambda: made.listed == TWO)
    assert made.asked == 1, "three pages at once ask once"
    clock.now += FREQUENCIES_EVERY_SEC - 1
    made.wanted()
    assert made.asked == 1
    clock.now += 2
    server.answers_last = json.dumps({"frequencies": [{"band": "30 m", "dial": "10.1462 MHz USB"}]}).encode()
    made.wanted()
    await until(lambda: made.listed == [Frequency("30 m", "10.1462 MHz USB")])
    assert made.asked == 2 and FREQUENCIES_EVERY_SEC == 900.0


async def test_the_timer_of_the_first_minute_counts_as_an_asking_and_a_page_just_after_it_asks_nothing() -> None:
    server = Server(FILE)
    made = service(server)
    await made.start()
    await until(lambda: made.asked == 1)
    made.wanted()
    assert made.asked == 1


async def test_nothing_is_asked_while_the_update_check_is_off_in_the_environment() -> None:
    server = Server(FILE)
    made = service(server, environ={ENV_SWITCH: "0"})
    assert not made.enabled
    await made.start()
    made.wanted()
    await made.ask()
    await until(lambda: True)
    assert server.asked == [] and made.asked == 0 and made.listed == []


async def test_a_server_that_is_not_there_or_a_file_that_is_bad_leaves_the_last_good_list_as_it_was() -> None:
    server = Server(FILE, None, b"not json", b'{"frequencies": []}')
    clock = Clock()
    made = service(server, clock)
    told = []
    made.changed.connect(lambda: told.append(1))
    for expect in (1, 2, 3, 4):
        made.wanted()
        await until(lambda expect=expect: made.asked == expect and len(server.asked) == expect)       # type: ignore[misc]
        clock.now += FREQUENCIES_EVERY_SEC + 1
    assert made.listed == TWO and told == [1], "the same list again is told once, nothing else"


async def test_the_same_list_again_changes_nothing_and_tells_nothing() -> None:
    server = Server(FILE, FILE)
    clock = Clock()
    made = service(server, clock)
    told = []
    made.changed.connect(lambda: told.append(1))
    made.wanted()
    await until(lambda: len(told) == 1)
    clock.now += FREQUENCIES_EVERY_SEC + 1
    made.wanted()
    await until(lambda: len(server.asked) == 2)
    assert told == [1]


async def test_the_last_good_list_is_kept_and_told_at_the_next_start_before_the_server_is_asked(tmp_path: Path) -> None:
    store = await store_at(tmp_path / "neoaprs.sqlite")
    made = service(Server(FILE), memory=store)
    made.wanted()
    await until(lambda: made.listed == TWO)
    await until(lambda: True)
    assert parse_frequencies(await store.setting(FREQUENCIES_ROW) or "") == TWO, "kept in the settings table, as a row that is not a setting"
    told = []
    again = Frequencies("0.17.0", "linux", Server(None), first_sec=3600.0, environ={}, memory=store)
    remember_stop(again.stop)
    again.changed.connect(lambda: told.append(list(again.listed)))
    await again.start()
    await until(lambda: told == [TWO])
    await store.put_settings({FREQUENCIES_ROW: "garbage"})
    third = Frequencies("0.17.0", "linux", Server(None), first_sec=3600.0, environ={}, memory=store)
    remember_stop(third.stop)
    await third.start()
    await until(lambda: True)
    assert third.listed == [], "a row someone edited by hand is as good as none"


# ---- the box

async def test_the_hf_topic_has_the_list_and_a_page_that_shows_the_box_asks_for_it(tmp_path: Path) -> None:
    air = Air(frame_sec=0.2)
    station = air.station()
    e = Env(tmp_path, radio=station, web=True)
    await e.start()
    server = Server(FILE)
    e.ctl.frequencies._fetch = server
    e.ctl.frequencies._environ = {}
    page = await e.ws()
    await page.send({"cmd": "subscribe", "topics": ["hf"]})
    await page.until(lambda: page.topics["hf"]["modem"]["state"] == "running")
    assert page.topics["hf"]["modem"]["frequencies"] == [{"band": "40 m", "dial": "7.0541 MHz USB"}, {"band": "20 m", "dial": "14.1070 MHz USB"}], "the built-in two until something better is known"
    assert "dial" not in page.topics["hf"]["modem"]
    server.answers = [json.dumps({"frequencies": [{"band": "30 m", "dial": "10.1462 MHz USB"}]}).encode()]
    await page.send({"cmd": "hf_frequencies"})
    await page.until(lambda: page.topics["hf"]["modem"]["frequencies"] == [{"band": "30 m", "dial": "10.1462 MHz USB"}])
    assert len(server.asked) == 1
    await page.send({"cmd": "hf_frequencies"})
    await page.quiet(0.3)
    assert len(server.asked) == 1, "the second asking is within the fifteen minutes"
    await e.stop()
    await air.aclose()


async def test_the_version_pages_dial_is_what_the_box_suggests_when_the_project_has_no_list(tmp_path: Path) -> None:
    assert Mercury(tmp_path).frequencies == BUILT_IN
    air = Air(frame_sec=0.2)
    station = air.station()
    e = Env(tmp_path, radio=station, web=True)
    await e.start()
    e.ctl.updatecheck.hf_dial = "7.0443 MHz USB"
    e.ctl.updatecheck.dial_changed.emit("7.0443 MHz USB")
    assert e.ctl.mercury.frequencies == [Frequency("40 m", "7.0443 MHz USB")]
    e.ctl.frequencies.listed = TWO
    e.ctl.frequencies.changed.emit()
    assert e.ctl.mercury.frequencies == TWO, "the project's list wins"
    e.ctl.frequencies.listed = []
    e.ctl.frequencies.changed.emit()
    assert e.ctl.mercury.frequencies == [Frequency("40 m", "7.0443 MHz USB")]
    await e.stop()
    await air.aclose()
