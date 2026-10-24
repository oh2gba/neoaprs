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

    e.ctl.radiofinder = RadioFinder(listed, e.ctl.hold_tnc, e.ctl.release_tnc, timing)
    return e


async def test_the_page_is_told_each_try_and_then_what_was_found_and_the_radios_line_is_taken_again(tmp_path: Path) -> None:
    tnc = await FakeTncServer("tnc2").start()
    e = await started(tmp_path, [tnc.url])
    page = await e.ws()
    await page.send({"cmd": "find_radio"})
    trying = await page.expect("radio_search")
    assert trying == {"type": "radio_search", "state": "trying", "port": tnc.url, "baud": None, "profile": "", "number": 1, "total": 1}
    found = await page.expect("radio_search")
    assert found == {"type": "radio_search", "state": "found", "port": tnc.url, "baud": None, "profile": "kenwood-tnc2", "number": 0, "total": 0}
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
