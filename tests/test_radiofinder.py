"""Find my radio (neoaprs/services/radiofinder.py, radioprobe.py): the order ports and speeds are
tried in, the stop at the first TNC that answers, the profile that fits, a cancel, and the ports
listed; with radios side by side.
"""
import asyncio
import logging
from pathlib import Path

import pytest

from neoaprs import serialprobe, tncsearch
from neoaprs.claims import Claim, Claims
from neoaprs.coded import CodedError
from neoaprs.radiosearch import Found
from neoaprs.serialprobe import PortInfo
from neoaprs.services import radiofinder
from neoaprs.services.radiofinder import SPEEDS, RadioFinder
from neoaprs.services.radioprobe import Timing
from tests.support.env import until
from tests.support.faketnc import FakeTncServer, TncBrain, ears
from tests.support.finderrig import QUICK, Rig
from tests.support.virtualtime import virtual_time


async def serve(*kinds: str) -> list[FakeTncServer]:
    return [await FakeTncServer(kind).start() for kind in kinds]


class RadioRig(Rig):
    """A finder for one radio among others, as the registry makes it: its hold and release are told
    the radio's id, and it is given the station's table of resources and its one search at a time.
    """

    def __init__(self, ports: list[str], claims: Claims | None = None, lock: asyncio.Lock | None = None, **finder: object) -> None:
        super().__init__(ports, **finder)

        async def hold(radio: int) -> None:
            self.events.append(f"hold {radio}")

        self.finder = RadioFinder(self.finder.ports, hold, lambda radio: self.events.append(f"release {radio}"), self.finder.timing, claims=claims, search_lock=lock, **finder)


async def test_a_tnc_in_kiss_mode_that_has_heard_a_packet_is_found_without_a_word_being_written() -> None:
    [tnc] = await serve("kiss")
    rig = Rig([tnc.url])
    found = await rig.finder.find(rig.tried.append)
    assert found == Found(tnc.url, None, "kiss")
    assert tnc.brain.writes == []
    assert rig.events == ["hold", "release"]
    await until(lambda: tnc.closed == 1)
    await tnc.aclose()


async def test_a_tnc_in_command_mode_is_asked_with_a_carriage_return_and_put_in_kiss_by_the_profile_that_works() -> None:
    [tnc] = await serve("tnc2")
    rig = Rig([tnc.url])
    assert await rig.finder.find(rig.tried.append) == Found(tnc.url, None, "kenwood-tnc2")
    assert tnc.brain.writes[0] == b"\r"
    assert tnc.brain.in_kiss
    await tnc.aclose()


@pytest.mark.parametrize(("kind", "profile"), [("kantronics", "kantronics"), ("d710", "kenwood-d710")])
async def test_the_profiles_are_tried_in_turn_until_one_puts_the_tnc_in_kiss(kind: str, profile: str) -> None:
    [tnc] = await serve(kind)
    rig = Rig([tnc.url])
    found = await rig.finder.find(rig.tried.append)
    assert found == Found(tnc.url, None, profile)
    assert tnc.brain.in_kiss
    assert tnc.brain.writes[1] == b"\rKISS ON\rRESTART\r"            # the first profile is the TNC-2's
    await tnc.aclose()


async def test_a_port_is_tried_at_each_speed_in_order_and_the_search_stops_at_the_first_that_answers() -> None:
    async with virtual_time():
        brains = {("A", 1200): TncBrain("silent"), ("B", 57600): TncBrain("tnc2"), ("C", 9600): TncBrain("kiss")}
        ear = ears(brains)
        rig = Rig(["A", "B", "C"], line=ear)
        found = await rig.finder.find(rig.tried.append)
        assert found == Found("B", 57600, "kenwood-tnc2")
        assert ear.opened == [("A", s) for s in SPEEDS] + [("B", 9600), ("B", 57600)]
        assert ear.closed == ear.opened                                  # every port that was opened is closed again
        assert [(t.port, t.baud, t.number, t.total) for t in rig.tried][-1] == ("B", 57600, 9, 21)
        assert rig.events == ["hold", "release"]


async def test_a_socket_or_bluetooth_port_has_no_speed_and_is_tried_once() -> None:
    async with virtual_time():
        ear = ears({("bt://AA:BB:CC:DD:EE:FF", 9600): TncBrain("kiss")})
        rig = Rig(["/dev/ttyUSB0", "bt://AA:BB:CC:DD:EE:FF"], line=ear)
        found = await rig.finder.find(rig.tried.append)
        assert found == Found("bt://AA:BB:CC:DD:EE:FF", None, "kiss")
        assert [(t.port, t.baud) for t in rig.tried][-1] == ("bt://AA:BB:CC:DD:EE:FF", None)
        assert ear.opened[-1] == ("bt://AA:BB:CC:DD:EE:FF", 9600)
        assert rig.tried[-1].total == len(SPEEDS) + 1


async def test_a_port_that_cannot_be_opened_is_passed_over_at_once_for_every_speed() -> None:
    async with virtual_time():
        ear = ears({("B", 9600): TncBrain("kiss")}, refused={"A"})
        rig = Rig(["A", "B"], line=ear)
        assert await rig.finder.find(rig.tried.append) == Found("B", 9600, "kiss")
        assert [t.port for t in rig.tried] == ["A", "B"]
        # The speeds of A are counted, though they were not tried
        assert rig.tried[1].number == len(SPEEDS) + 1


async def test_nothing_that_answers_is_not_found_and_the_radios_line_is_given_back() -> None:
    [silent] = await serve("silent")
    rig = Rig([silent.url])
    with pytest.raises(CodedError) as caught:
        await rig.finder.find(rig.tried.append)
    assert caught.value.code == "radio.not_found"
    assert rig.events == ["hold", "release"]
    assert not rig.finder.running
    await silent.aclose()


async def test_a_search_for_one_radio_lets_go_of_that_radios_line_alone_and_gives_it_back() -> None:
    [tnc] = await serve("kiss")
    rig = RadioRig([tnc.url])
    assert await rig.finder.find(rig.tried.append, 3) == Found(tnc.url, None, "kiss")
    assert rig.events == ["hold 3", "release 3"]
    await tnc.aclose()


async def test_what_another_radio_or_the_gps_receiver_holds_is_not_tried_and_the_radios_own_port_is(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.tnc")
    other, gps, own = await serve("kiss", "kiss", "kiss")
    claims = Claims()
    # A socket holds nothing in the table; a Bluetooth port would, by the same value
    claims.hold(Claim("serial", serialprobe.claim_value(other.url) or other.url.lower(), 1))
    claims.hold(Claim("gps", gps.url.lower(), None))
    claims.hold(Claim("serial", own.url.lower(), 3))
    rig = RadioRig([other.url, gps.url, own.url], claims=claims)
    assert await rig.finder.find(rig.tried.append, 3) == Found(own.url, None, "kiss")
    assert [t.port for t in rig.tried] == [own.url] and other.connections == gps.connections == 0, "never opened"
    assert f"find the radio: passing over {other.url}: held by radio 1" in caplog.text and f"passing over {gps.url}: held by the GPS receiver" in caplog.text
    with pytest.raises(CodedError) as caught:
        await RadioRig([other.url, gps.url], claims=claims).finder.find(rig.tried.append, 3)
    assert caught.value.code == "radio.no_ports", "with every port held by others there is none to try"
    for server in (other, gps, own):
        await server.aclose()


async def test_a_search_waits_for_its_turn_while_another_radio_searches_and_is_cancelled_while_it_waits(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.tnc")
    [tnc] = await serve("kiss")
    lock = asyncio.Lock()
    await lock.acquire()                                                           # (another radio's search runs)
    rig = RadioRig([tnc.url], lock=lock)
    task = asyncio.create_task(rig.finder.find(rig.tried.append, 3))
    await until(lambda: rig.events == ["hold 3"] and "waiting while another radio looks for its port" in caplog.text)
    assert rig.tried == [] and tnc.connections == 0, "nothing is tried before its turn"
    lock.release()
    assert await task == Found(tnc.url, None, "kiss")
    assert rig.events == ["hold 3", "release 3"] and not lock.locked(), "the turn is given back with the line"
    await lock.acquire()
    task = asyncio.create_task(rig.finder.find(rig.tried.append, 3))
    await until(lambda: rig.events[-1] == "hold 3")
    assert rig.finder.cancel() and await task is None
    assert rig.events[-1] == "release 3" and lock.locked(), "a cancel while it waits gives the line back and takes no turn"
    lock.release()
    await tnc.aclose()


async def test_a_port_another_radios_search_takes_while_this_one_waits_for_its_turn_is_passed_over_and_not_counted(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.tnc")
    taken, own = await serve("kiss", "kiss")
    claims, lock = Claims(), asyncio.Lock()
    await lock.acquire()                                                           # (another radio's search runs)
    rig = RadioRig([taken.url, own.url], claims=claims, lock=lock)
    task = asyncio.create_task(rig.finder.find(rig.tried.append, 3))
    await until(lambda: rig.events == ["hold 3"])
    # The other search found its radio there, and holds the port
    claims.hold(Claim("serial", taken.url.lower(), 1))
    lock.release()
    assert await task == Found(own.url, None, "kiss")
    assert [(t.port, t.number, t.total) for t in rig.tried] == [(own.url, 1, 1)] and taken.connections == 0, "looked at again in its turn: never opened, and not in the totals"
    assert f"find the radio: passing over {taken.url}: held by radio 1" in caplog.text
    await taken.aclose()
    await own.aclose()


async def test_no_port_to_try_is_said_before_the_radios_line_is_let_go() -> None:
    rig = Rig([])
    with pytest.raises(CodedError) as caught:
        await rig.finder.find(rig.tried.append)
    assert caught.value.code == "radio.no_ports"
    assert rig.events == []


async def test_a_cancel_ends_the_search_closes_the_port_and_gives_the_line_back() -> None:
    [silent] = await serve("silent")
    rig = Rig([silent.url])
    rig.finder.timing = Timing(listen_sec=30, answer_sec=30)
    task = asyncio.create_task(rig.finder.find(rig.tried.append))
    await until(lambda: silent.connections == 1)
    assert rig.finder.running
    assert rig.finder.cancel()
    assert await task is None
    await until(lambda: silent.closed == 1)
    assert rig.events == ["hold", "release"]
    assert not rig.finder.running
    assert not rig.finder.cancel()                                   # (nothing is running now)
    await silent.aclose()


async def test_a_second_search_is_refused_while_one_runs() -> None:
    [silent] = await serve("silent")
    rig = Rig([silent.url])
    rig.finder.timing = Timing(listen_sec=30, answer_sec=30)
    task = asyncio.create_task(rig.finder.find(rig.tried.append))
    await until(lambda: silent.connections == 1)
    with pytest.raises(CodedError) as caught:
        await rig.finder.find(rig.tried.append)
    assert caught.value.code == "radio.busy"
    rig.finder.cancel()
    await task
    await silent.aclose()


async def test_the_stop_of_the_daemon_ends_a_search_that_runs() -> None:
    [silent] = await serve("silent")
    rig = Rig([silent.url])
    rig.finder.timing = Timing(listen_sec=30, answer_sec=30)
    task = asyncio.create_task(rig.finder.find(rig.tried.append))
    await until(lambda: silent.connections == 1)
    await rig.finder.stop()
    assert await task is None
    await silent.aclose()


# ---- which ports are listed

def fake_system(monkeypatch: pytest.MonkeyPatch, ports: list[str], held: set[str] = frozenset()) -> None:  # type: ignore[assignment]
    """The system's list of ports is a fixed one; the Bluetooth list too. Nothing of the machine is
    read."""
    monkeypatch.setattr(serialprobe, "can_search", lambda: True)
    monkeypatch.setattr(serialprobe, "can_find", lambda: True)
    monkeypatch.setattr(serialprobe, "searchable_ports", lambda pattern: (ports, {}))
    monkeypatch.setattr(radiofinder, "held_by", lambda path: "held by rotctld (pid 1)" if path in held else "")
    monkeypatch.setattr(serialprobe, "paired_bluetooth_ports", lambda: [PortInfo("bt://AA:BB:CC:DD:EE:FF", "Bluetooth: TNC", "", None, None)])


def test_the_ports_are_those_of_the_search_without_the_skipped_and_the_held(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_system(monkeypatch, ["/dev/a", "/dev/b", "/dev/c"], held={"/dev/c"})
    assert radiofinder.candidates("/dev/neoaprs-test-*", ("/dev/b",)) == ["/dev/a"]


def test_the_paired_bluetooth_devices_are_tried_when_the_pattern_is_the_default_one_and_not_when_it_was_narrowed(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_system(monkeypatch, ["/dev/a"])
    assert radiofinder.candidates(serialprobe.DEFAULT_PATTERN, ()) == ["/dev/a", "bt://AA:BB:CC:DD:EE:FF"]
    assert radiofinder.candidates("/dev/neoaprs-test-*", ()) == ["/dev/a"]


def test_where_find_my_radio_is_not_made_there_is_no_port_to_try(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_system(monkeypatch, ["COM3"])
    monkeypatch.setattr(serialprobe, "can_find", lambda: False)
    assert radiofinder.candidates(serialprobe.DEFAULT_PATTERN, ()) == []


# ---- the edges: a caller that is cancelled, a search that fails

async def test_a_search_whose_caller_is_cancelled_closes_the_port_and_gives_the_line_back() -> None:
    [silent] = await serve("silent")
    rig = Rig([silent.url], timing=Timing(listen_sec=30, answer_sec=30))
    caller = asyncio.create_task(rig.finder.find(rig.tried.append))
    await until(lambda: silent.connections == 1)
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    await until(lambda: silent.closed == 1)
    assert rig.events == ["hold", "release"] and not rig.finder.running
    await silent.aclose()


@pytest.mark.expects_errors
async def test_a_search_that_fails_for_a_reason_of_its_own_is_said_to_have_failed() -> None:
    async def hold() -> None:
        raise RuntimeError("the line cannot be let go")

    async def ports() -> list[str]:
        return ["/dev/a"]

    finder = RadioFinder(ports, hold, lambda: None, QUICK, line=ears({}))
    with pytest.raises(CodedError) as caught:
        await finder.find(lambda trying: None)
    assert caught.value.code == "radio.failed" and not finder.running


async def test_the_log_says_which_ports_are_tried_and_what_the_search_found(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.tnc")
    [tnc] = await serve("kiss")
    rig = Rig([tnc.url])
    await rig.finder.find(rig.tried.append)
    said = [r.getMessage() for r in caplog.records if r.name == "neoaprs.tnc"]
    assert said == [f"find the radio: trying {tnc.url}", f"find the radio: found on {tnc.url} at no speed, profile kiss"]
    await tnc.aclose()


async def test_a_port_a_save_gives_a_radio_while_find_my_radio_tries_it_is_let_go_at_once_and_the_search_goes_on(caplog: pytest.LogCaptureFixture) -> None:
    """The radio a save sets to the port opens it at its first try (tncsearch.let_go reaches Find my
    radio's line as it reaches the searches' listeners), and what the port said is no answer: it is
    that radio's."""
    caplog.set_level(logging.INFO, "neoaprs")
    given, other = await serve("kiss", "kiss")
    rig = Rig([given.url, other.url], timing=Timing(listen_sec=1.5, answer_sec=0.3, pace=0.001))
    finding = asyncio.create_task(rig.finder.find(rig.tried.append))
    try:
        key = serialprobe.port_key(given.url)
        await until(lambda: key in serialprobe.LISTENING and serialprobe.LISTENING[key].is_open, 3.0)
        tncsearch.let_go(given.url)
        # At once, not when the try of the port ends
        await until(lambda: given.closed == 1, 1.0)
        assert await finding == Found(other.url, None, "kiss")
        assert f"passing over {given.url}: {given.url}: a radio is set to it" in caplog.text
    finally:
        finding.cancel()
        await asyncio.gather(finding, return_exceptions=True)
        await given.aclose()
        await other.aclose()
