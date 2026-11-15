"""Find my radio through the page's socket: `find_radio` is told to the page that asked with `radio_search` messages and ends with `found`, `cancelled` or an `error` with a code; the radio's own line is let go for the time and
taken again after it. The ports are fakes (tests/support/faketnc.py): no device of the machine is listed or opened."""
from pathlib import Path

from neoaprs.services.radiofinder import RadioFinder
from neoaprs.services.radioprobe import Timing
from neoaprs.source import Source
from tests.support.env import Env, until
from tests.support.faketnc import FakeTncServer


QUICK = Timing(listen_sec=0.02, answer_sec=0.03, pace=0.001)


async def started(tmp_path: Path, ports: list[str], timing: Timing = QUICK) -> Env:
    e = Env(tmp_path / "data", web=True)
    await e.start()

    async def listed() -> list[str]:
        return ports

    e.ctl.radiofinder = RadioFinder(listed, e.ctl.hold_radio, e.ctl.release_radio, timing, claims=e.ctl.radios.claims, search_lock=e.ctl.radios.search_lock)
    return e


async def test_the_page_is_told_each_try_and_then_what_was_found_and_the_radios_line_is_taken_again(tmp_path: Path) -> None:
    tnc = await FakeTncServer("tnc2").start()
    e = await started(tmp_path, [tnc.url])
    page = await e.ws()
    await page.send({"cmd": "find_radio"})
    trying = await page.expect("radio_search")
    assert trying == {"type": "radio_search", "state": "trying", "port": tnc.url, "baud": None, "profile": "", "number": 1, "total": 1, "radio": None, "radio_type": ""}
    found = await page.expect("radio_search")
    assert found == {"type": "radio_search", "state": "found", "port": tnc.url, "baud": None, "profile": "kenwood-tnc2", "number": 0, "total": 0, "radio": None, "radio_type": "kenwood-tnc2"}, "the type found, beside the profile of before"
    await until(lambda: e.tnc.state is Source.State.CONNECTED)           # (the line the daemon let go is open again)
    await e.stop()
    await tnc.aclose()


async def test_the_radios_own_line_is_closed_while_the_search_runs(tmp_path: Path) -> None:
    tnc = await FakeTncServer("silent").start()
    e = await started(tmp_path, [tnc.url], Timing(listen_sec=30, answer_sec=30))
    page = await e.ws()
    await page.send({"cmd": "find_radio"})
    await page.expect("radio_search")
    await until(lambda: tnc.connections == 1)
    assert e.tnc.state is Source.State.STOPPED
    await page.send({"cmd": "find_radio_cancel"})
    assert (await page.expect("radio_search"))["state"] == "cancelled"
    await until(lambda: e.tnc.state is Source.State.CONNECTED)
    await e.stop()
    await tnc.aclose()


async def test_a_second_find_and_a_cancel_with_nothing_running_are_refused_with_a_code(tmp_path: Path) -> None:
    tnc = await FakeTncServer("silent").start()
    e = await started(tmp_path, [tnc.url], Timing(listen_sec=30, answer_sec=30))
    page = await e.ws()
    await page.send({"cmd": "find_radio_cancel"})
    error = await page.expect("error")
    assert (error["cmd"], error["code"]) == ("find_radio_cancel", "radio.not_running")
    await page.send({"cmd": "find_radio"})
    await page.expect("radio_search")
    await page.send({"cmd": "find_radio"})
    assert (await page.expect("error"))["code"] == "radio.busy"
    await page.send({"cmd": "find_radio_cancel"})
    assert (await page.expect("radio_search"))["state"] == "cancelled"
    await e.stop()
    await tnc.aclose()


async def test_no_answer_and_no_port_are_errors_with_a_code(tmp_path: Path) -> None:
    tnc = await FakeTncServer("silent").start()
    e = await started(tmp_path, [tnc.url])
    page = await e.ws()
    await page.send({"cmd": "find_radio"})
    assert (await page.expect("error"))["code"] == "radio.not_found"
    await tnc.aclose()
    e.ctl.radiofinder.ports = _none
    await page.send({"cmd": "find_radio"})
    assert (await page.expect("error"))["code"] == "radio.no_ports"
    await e.stop()


async def _none() -> list[str]:
    return []


async def test_a_daemon_with_a_pattern_that_matches_nothing_lists_no_port_to_try(tmp_path: Path) -> None:
    """The daemon of the tests (and of a demonstration) has a search pattern that matches nothing: Find my radio has nothing to open, not even the Bluetooth devices that are paired."""
    e = Env(tmp_path / "data", web=True)
    await e.start()
    page = await e.ws()
    await page.send({"cmd": "find_radio"})
    assert (await page.expect("error"))["code"] == "radio.no_ports"
    await e.stop()


async def test_the_finder_of_the_radios_side_by_side_is_given_the_radio_and_the_page_that_names_none_searches_for_radio_1(tmp_path: Path) -> None:
    """The finder app.py makes from I4 on (each radio's own hold, the station's table and its one search at a time) takes `find(trying, radio)` always: the page of before, which names no radio, finds radio 1."""
    e = Env(tmp_path / "data", web=True)
    await e.start()
    servers: list[FakeTncServer] = []

    async def listed() -> list[str]:
        return [servers[-1].url]

    e.ctl.radiofinder = RadioFinder(listed, e.ctl.hold_radio, e.ctl.release_radio, QUICK, claims=e.ctl.radios.claims, search_lock=e.ctl.radios.search_lock)
    page = await e.ws()
    for command in ({"cmd": "find_radio"}, {"cmd": "find_radio", "radio": 1}):
        servers.append(await FakeTncServer("tnc2").start())
        await page.send(command)
        found = [m for m in [await page.expect("radio_search"), await page.expect("radio_search")] if m["state"] != "trying"]
        assert [(m["state"], m["port"], m["radio"]) for m in found] == [("found", servers[-1].url, command.get("radio"))], command
        await until(lambda: e.tnc.state is Source.State.CONNECTED)
    await e.stop()
    for server in servers:
        await server.aclose()
