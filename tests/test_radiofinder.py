"""Find my radio (neoaprs/services/radiofinder.py, radioprobe.py): the order the ports and speeds are tried in, that the search stops at the first TNC that answers, which profile fits what answers, what a cancel leaves,
and which ports are listed at all. The TNCs are fakes (tests/support/faketnc.py): a TCP server on the loopback, or a port that is not one and takes a speed. No device of the machine is listed or opened."""
import asyncio
from pathlib import Path

import pytest

from neoaprs import serialprobe
from neoaprs.coded import CodedError
from neoaprs.radiosearch import Found, Trying
from neoaprs.serialprobe import PortInfo
from neoaprs.services import radiofinder
from neoaprs.services.radiofinder import SPEEDS, RadioFinder
from neoaprs.services.radioprobe import Timing
from tests.support.env import until
from tests.support.faketnc import FakeTncServer, TncBrain, ears

QUICK = Timing(listen_sec=0.3, answer_sec=0.3, pace=0.001)          # (a fake TNC on the loopback answers at once, but a busy machine may take a while to pass it on)


class Rig:
    """A finder over a fixed list of ports, with a record of what it did to the radio's own line."""

    def __init__(self, ports: list[str], **finder: object) -> None:
        self.events: list[str] = []
        self.tried: list[Trying] = []

        async def listed() -> list[str]:
            return ports

        async def hold() -> None:
            self.events.append("hold")

        self.finder = RadioFinder(listed, hold, lambda: self.events.append("release"), QUICK, **finder)  # type: ignore[arg-type]


async def serve(*kinds: str) -> list[FakeTncServer]:
    return [await FakeTncServer(kind).start() for kind in kinds]


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
    ear = ears({("bt://AA:BB:CC:DD:EE:FF", 9600): TncBrain("kiss")})
    rig = Rig(["/dev/ttyUSB0", "bt://AA:BB:CC:DD:EE:FF"], line=ear)
    found = await rig.finder.find(rig.tried.append)
    assert found == Found("bt://AA:BB:CC:DD:EE:FF", None, "kiss")
    assert [(t.port, t.baud) for t in rig.tried][-1] == ("bt://AA:BB:CC:DD:EE:FF", None)
    assert ear.opened[-1] == ("bt://AA:BB:CC:DD:EE:FF", 9600)
    assert rig.tried[-1].total == len(SPEEDS) + 1


async def test_a_port_that_cannot_be_opened_is_passed_over_at_once_for_every_speed() -> None:
    ear = ears({("B", 9600): TncBrain("kiss")}, refused={"A"})
    rig = Rig(["A", "B"], line=ear)
    assert await rig.finder.find(rig.tried.append) == Found("B", 9600, "kiss")
    assert [t.port for t in rig.tried] == ["A", "B"]
    assert rig.tried[1].number == len(SPEEDS) + 1                    # (the speeds of A are counted, though they were not tried)


async def test_nothing_that_answers_is_not_found_and_the_radios_line_is_given_back() -> None:
    [silent] = await serve("silent")
    rig = Rig([silent.url])
    with pytest.raises(CodedError) as caught:
        await rig.finder.find(rig.tried.append)
    assert caught.value.code == "radio.not_found"
    assert rig.events == ["hold", "release"]
    assert not rig.finder.running
    await silent.aclose()


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
    """The system's list of ports is a fixed one; the Bluetooth list too. Nothing of the machine is read."""
    monkeypatch.setattr(serialprobe, "can_search", lambda: True)
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


def test_where_the_search_is_not_made_there_is_no_port_to_try(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_system(monkeypatch, ["COM3"])
    monkeypatch.setattr(serialprobe, "can_search", lambda: False)
    assert radiofinder.candidates(serialprobe.DEFAULT_PATTERN, ()) == []
