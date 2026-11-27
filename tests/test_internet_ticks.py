"""The two ticks of Internet (APRS-IS): Show Internet stations (`igate/enabled`) and Send what I hear
(`igate/gate`), each on its own, at the daemon level against a fake APRS-IS: what the login line
carries, what is gated, what is shown; and the passcode worked out from the call.
"""

import logging
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs import PROGRAM, VERSION
from neoaprs.aprsis import passcode_of
from tests.support.air import on_air
from tests.support.env import Env, idle_for, until
from tests.support.fakeaprsis import fake_aprsis
from tests.support.igateworld import iworld

FILTER = "r/60.17/24.94/150"
HEARD = "OH2RDG-7>APRS,WIDE1-1,WIDE2-1,qAO,OH2GBA:!6010.00N/02456.00E>hello"


def independent_passcode(call: str) -> int:
    """The same hash written another way: the high byte folds the characters at even places, the
    low byte those at odd places, each on its half of the seed."""
    base = call.upper().split("-")[0].encode("ascii")
    high, low = 0x73, 0xE2
    for c in base[0::2]:
        high ^= c
    for c in base[1::2]:
        low ^= c
    return (high << 8 | low) & 0x7FFF


def test_the_passcode_of_the_published_example_is_its_published_number() -> None:
    assert passcode_of("N0CALL") == "13023"


@pytest.mark.parametrize(
    "call", ["OH2GBA", "OH2GBA-10", "oh2gba-9", "W1AW", "K1A", "DL1ABC-15", "JA1XYZ", "VK2ABC", "A", "PY2ABCD"]
)
def test_the_passcode_is_the_hash_of_the_call_without_its_ssid_as_another_implementation_has_it(call: str) -> None:
    code = passcode_of(call)
    assert code == str(independent_passcode(call)) and 0 <= int(code) <= 32767
    assert code == passcode_of(call.split("-")[0].upper()), "the SSID and the case do not count"


def test_the_passcode_of_the_tests_call_is_the_one_the_tests_used_to_set_by_hand() -> None:
    assert passcode_of("OH2GBA") == "19628"


async def started(tmp_path: Path, show: bool, gate: bool, **settings: str):  # type: ignore[no-untyped-def]
    server = await fake_aprsis(verified=gate)
    e = Env(
        tmp_path,
        settings={
            "igate/enabled": str(show).lower(),
            "igate/gate": str(gate).lower(),
            "igate/server": server.address,
            **settings,
        },
    )
    await e.start()
    await e.until_usable()
    return server, e


@pytest.mark.parametrize(
    ("show", "gate", "login", "state"),
    [
        (True, False, f"pass -1 vers {PROGRAM} {VERSION} filter {FILTER}", "listening"),
        (False, True, f"pass 19628 vers {PROGRAM} {VERSION}", "connected"),
        (True, True, f"pass 19628 vers {PROGRAM} {VERSION} filter {FILTER}", "connected"),
    ],
)
async def test_each_combination_logs_in_as_it_should_gates_only_with_send_and_shows_only_with_show(
    tmp_path: Path, show: bool, gate: bool, login: str, state: str
) -> None:
    server, e = await started(tmp_path, show, gate)
    await until(lambda: e.ctl.igate.state == state)
    assert server.logins == [f"user OH2GBA {login}"], "a read-only login without Send; no filter without Show"
    e.feed(on_air("OH2RDG-7", b"!6010.00N/02456.00E>hello", path="WIDE1-1,WIDE2-1"))
    ours = e.ctl.config.station_call
    server.send(b"OH2NET>APRS,TCPIP*,qAC,TESTSRV:!6011.00N/02457.00E-internet station")
    server.send(b"OH2NET>APRS,TCPIP*,qAC,TESTSRV::" + f"{ours:<9}".encode() + b":hello from the net{4}")
    await until(lambda: e.ctl.aprsis.read == 2)
    if gate:
        await until(lambda: HEARD in server.packets and any(line.startswith(f"{ours}>APZ") for line in server.packets))
    await e.settled()
    await idle_for(0.3)
    assert (HEARD in server.packets) is gate and e.ctl.igate.gated == int(gate)
    assert any(line.startswith(f"{ours}>APZ") for line in server.packets) is gate, "our position goes with Send"
    net = e.ctl.stationbook.get("OH2NET")
    assert (net is not None) is show, "the internet's stations are there only with Show"
    assert [p.via for p in await e.packets() if p.via == "is"] == (["is", "is"] if show else []), (
        "nothing of the internet is stored without Show"
    )
    assert e.ctl.messaging.records() == [], "a message from the internet is never taken"
    assert await e.heard(1, timeout_sec=0.3) == b"", "nothing was transmitted: no ack, no answer"
    assert e.ctl.igate.made_up() is False and e.ctl.stationbook.get("OH2RDG-7") is not None
    await e.stop()


async def test_with_both_ticks_off_nothing_is_connected_to_and_nothing_is_gated(tmp_path: Path) -> None:
    server, e = await started(tmp_path, False, False)
    e.feed(on_air("OH2RDG-7", b"!6010.00N/02456.00E>hello", path="WIDE1-1,WIDE2-1"))
    await until(lambda: e.ctl.stationbook.get("OH2RDG-7") is not None)
    await idle_for(0.3)
    assert e.ctl.igate.state == "off" and server.connections == 0 and e.ctl.igate.gated == 0
    assert not e.ctl.igate.dropped, "a packet is not even counted while nothing is on"
    await e.stop()


async def test_a_passcode_set_by_hand_wins_over_the_one_of_the_call(tmp_path: Path) -> None:
    server, e = await started(tmp_path, False, True, **{"igate/password": "12345"})
    await until(lambda: e.ctl.igate.state == "connected")
    assert server.logins == [f"user OH2GBA pass 12345 vers {PROGRAM} {VERSION}"]
    await e.stop()


async def test_turning_show_off_while_sending_logs_in_again_without_the_filter_and_keeps_gating(
    tmp_path: Path,
) -> None:
    server, e = await started(tmp_path, True, True)
    await until(lambda: e.ctl.igate.state == "connected")
    assert await e.ctl.change_config(lambda c: replace(c, igate_enabled=False))
    await until(lambda: len(server.logins) == 2 and e.ctl.igate.state == "connected")
    assert server.logins[1] == f"user OH2GBA pass 19628 vers {PROGRAM} {VERSION}"
    e.feed(on_air("OH2RDG-7", b"!6010.00N/02456.00E>hello", path="WIDE1-1,WIDE2-1"))
    await until(lambda: HEARD in server.packets)
    await e.stop()


async def test_the_log_says_once_at_each_change_what_is_on(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="neoaprs.igate")
    server = await fake_aprsis()
    w = await iworld(server, igate_enabled=True, igate_gate=False, igate_password="")
    w.save(igate_gate=True)
    await until(lambda: len(server.logins) == 2)
    w.save(igate_enabled=False)
    await until(lambda: len(server.logins) == 3)
    w.save(igate_gate=False)
    await until(lambda: w.igate.state == "off")
    w.save(map_radius_km=80)
    await idle_for(0.1)
    said = [m.split(";")[0] for r in caplog.records if (m := r.getMessage()).startswith(("igate: on", "igate: off"))]
    assert said == [
        "igate: on, showing the internet's stations, gating nothing",
        "igate: on, showing the internet's stations and gating what the radios hear",
        "igate: on, gating what the radios hear, showing nothing of the internet",
        "igate: off",
    ]
    assert "19628" not in caplog.text
