"""Tests for several radios sharing the resource table (neoaprs/claims.py) and one port search at a
time (RadioRegistry.search_lock): searches wait for each other, held ports are never opened, found
ports are claimed, and two Mercury modems never get the same ports. Serial ports are
pseudo-terminals; the Mercury is the stand-in in tests/support/fakemercury.py.
"""

import asyncio
import contextlib
import logging
import os
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs import mercuryhelper, mercurymodem, serialholders, serialprobe, tncdriver
from neoaprs.claims import Claim, Claims
from neoaprs.config import DEFAULTS, Config
from neoaprs.mercury import Keying, SerialPort, SoundCard
from neoaprs.mercuryhelper import choose_setup, next_modem_ports, pair_ports
from neoaprs.mercurymodem import Mercury
from neoaprs.radiodriver import RunOverrides
from neoaprs.radiospec import HF_ID, RadioId
from neoaprs.serialholders import port_key
from neoaprs.services.radiofinder import RadioFinder
from neoaprs.source import Backoff, Source
from neoaprs.tnc import Tnc
from neoaprs.tncdriver import TncDriver, line_settings
from neoaprs.tncsearch import WAITING, PortSearch, held_elsewhere
from tests.support import fakemercury
from tests.support.env import idle_for, until, until_started
from tests.support.fakemercury import of_radio
from tests.support.clock import FixedClock
from tests.support.fakedriver import Rig, spec, with_radios
from tests.support.fakeradio import FakeRadio
from tests.support.ptyline import Ptys, feed, posix_only
from tests.support.radioconfig import with_radio
from tests.test_mercury_modem import HF, QUICK, _ports_of_this_test, stopped  # noqa: F401 (the fixture keeps two tests from taking the same ports)
from tests.test_tnc import kiss_of, tiny_backoff, ui_frame

T0 = FixedClock()()


async def links(tmp_path: Path, ptys: Ptys, count: int) -> tuple[list[int], list[str], str]:
    """`count` pseudo-terminals behind links port_1, port_2 ... in the test's folder: their masters,
    the links, and the pattern that matches them."""
    masters, paths = [], []
    for n in range(1, count + 1):
        master, path = ptys()
        (tmp_path / f"port_{n}").symlink_to(path)
        masters.append(master)
        paths.append(str(tmp_path / f"port_{n}"))
    return masters, paths, str(tmp_path / "port_*")


async def keep_feeding(master: int, data: bytes) -> None:
    while True:
        feed(master, data)
        await asyncio.sleep(0.03)


def serial_radio(
    radio: int,
    name: str,
    claims: Claims,
    lock: asyncio.Lock,
    port: str = "",
    pattern: str = "",
    nudge_sec: float = serialprobe.NUDGE_SEC,
) -> Tnc:
    """A serial radio's line as its driver makes it: the station's table and its one search at a
    time, the radio's id and name."""
    tnc = Tnc(
        port,
        pattern=pattern,
        backoff=tiny_backoff(),
        fallback_probe=False,
        check_sec=0.0,
        probe_nudge_sec=nudge_sec,
        claims=claims,
        search_lock=lock,
    )
    tnc.radio_id, tnc.radio_name = radio, name
    return tnc


# ---- the serial search


@posix_only
async def test_a_second_serial_radio_waits_while_the_first_searches_and_then_leaves_out_the_port_the_first_found(
    ptys: Ptys, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, "neoaprs")
    (first_master, second_master), (port_1, port_2), pattern = await links(tmp_path, ptys, 2)
    claims, lock = Claims(), asyncio.Lock()
    fm, fm2 = (
        serial_radio(1, "FM", claims, lock, pattern=pattern),
        serial_radio(3, "FM 2", claims, lock, pattern=pattern),
    )
    feeders: list[asyncio.Task[None]] = []
    starts = [asyncio.create_task(fm.start())]
    try:
        await until(lambda: sorted(fm.searching) == [port_1, port_2], 5.0)
        starts.append(asyncio.create_task(fm2.start()))
        await until(lambda: fm2._search.waiting)
        assert fm2.describe() == WAITING and fm2.searching == [] and lock.locked(), (
            "the second radio waits for its turn, and says so"
        )
        assert f"FM 2: {WAITING}" in caplog.text and any(line.endswith(WAITING) for line in fm2.lines)
        feeders.append(asyncio.create_task(keep_feeding(first_master, kiss_of(ui_frame()))))
        await until(lambda: fm.state is Source.State.CONNECTED and fm.path == port_1, 10.0)
        assert claims.all() == (Claim("serial", port_key(port_1), 1),), "the port the first radio found is its radio's"
        await until(lambda: fm2.searching == [port_2], 10.0)
        assert f"probe: skipping {port_1}: held by radio 1" in caplog.text and "FM 2: listening on" in caplog.text, (
            "the second searches in its turn, without the first's port"
        )
        feeders.append(asyncio.create_task(keep_feeding(second_master, kiss_of(ui_frame()))))
        await until(lambda: fm2.state is Source.State.CONNECTED and fm2.path == port_2, 10.0)
        assert (
            set(claims.all()) == {Claim("serial", port_key(port_1), 1), Claim("serial", port_key(port_2), 3)}
            and not lock.locked()
        )
        await fm.stop()
        assert claims.all() == (Claim("serial", port_key(port_2), 3),), "a stopped radio lets go of its port"
    finally:
        for task in feeders:
            task.cancel()
        await asyncio.gather(*feeders, return_exceptions=True)
        await fm.stop()
        await fm2.stop()
        await asyncio.gather(*starts, return_exceptions=True)


async def test_the_port_a_search_finds_is_held_for_its_radio_before_the_turn_is_given_to_the_next(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claims, seen, path = Claims(), [], "/dev/ttyUSB7"

    class Watched(asyncio.Lock):
        def release(self) -> None:
            # (what the next radio's search would leave out, at the moment it may start)
            seen.append(claims.all())
            super().release()

    async def heard(paths: list[str], *args: object, **kwargs: object) -> tuple[str, bytes]:
        return path, kiss_of(ui_frame())

    monkeypatch.setattr(serialprobe, "can_search", lambda: True)
    monkeypatch.setattr(serialprobe, "searchable_ports", lambda pattern: ([path], {}))
    monkeypatch.setattr(serialprobe, "probe_heard", heard)
    search = PortSearch(asyncio.ensure_future, lambda text: None, b"\r")
    found = await search.find(
        "/dev/ttyUSB*",
        9600,
        0.0,
        lambda heard: True,
        True,
        1.0,
        (),
        lambda: True,
        claims=claims,
        holder=3,
        lock=Watched(),
    )
    assert found[0] == path and seen == [(Claim("serial", serialprobe.claim_value(path) or path, 3),)], (
        "held before the lock is given back"
    )


@posix_only
async def test_a_radio_that_never_finds_its_port_gives_its_turn_to_a_radio_that_waits_and_takes_it_again_after(
    ptys: Ptys, tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    caplog.set_level(logging.INFO, "neoaprs")
    monkeypatch.setattr(serialprobe, "RELIST_SEC", 0.1)
    (_, second_master), (port_1, port_2), _ = await links(tmp_path, ptys, 2)
    claims, lock = Claims(), asyncio.Lock()
    # (its radio is switched off: port_1 never says a word)
    fm = serial_radio(1, "FM", claims, lock, pattern=port_1, nudge_sec=0.1)
    fm2 = serial_radio(3, "FM 2", claims, lock, pattern=port_2, nudge_sec=0.1)
    feeder = asyncio.create_task(keep_feeding(second_master, kiss_of(ui_frame())))
    starts = [asyncio.create_task(fm.start())]
    try:
        await until(lambda: fm.searching == [port_1], 5.0)
        starts.append(asyncio.create_task(fm2.start()))
        await until(lambda: fm2.state is Source.State.CONNECTED and fm2.path == port_2, 10.0)
        assert "FM: the search gives its turn to another radio" in caplog.text and claims.all() == (
            Claim("serial", port_key(port_2), 3),
        )
        await until(lambda: fm.searching == [port_1], 5.0)
        assert fm.state is Source.State.CONNECTING, "the first goes on with its search in its next turn"
    finally:
        feeder.cancel()
        await asyncio.gather(feeder, return_exceptions=True)
        await fm.stop()
        await fm2.stop()
        await asyncio.gather(*starts, return_exceptions=True)


@posix_only
async def test_a_port_another_radio_or_the_gps_receiver_takes_while_the_search_listens_is_closed_at_the_next_listing(
    ptys: Ptys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(serialprobe, "RELIST_SEC", 0.1)
    _, (port_1, port_2), pattern = await links(tmp_path, ptys, 2)
    claims = Claims()
    fm = serial_radio(1, "FM", claims, asyncio.Lock(), pattern=pattern)
    start = asyncio.create_task(fm.start())
    try:
        await until(lambda: sorted(fm.searching) == [port_1, port_2], 5.0)
        claims.hold(Claim("gps", port_key(port_2), None))
        await until(lambda: fm.searching == [port_1], 5.0)
        claims.release(None)
        await until(lambda: sorted(fm.searching) == [port_1, port_2], 5.0)
    finally:
        await fm.stop()
        await asyncio.gather(start, return_exceptions=True)


@posix_only
async def test_a_named_port_another_radio_or_the_gps_receiver_holds_is_never_opened_and_the_radio_waits_saying_who_holds_it(
    ptys: Ptys, tmp_path: Path
) -> None:
    _, (port,), _ = await links(tmp_path, ptys, 1)
    claims, lock = Claims(), asyncio.Lock()
    # (the HF radio's modem keys its radio on this port's RTS: one device, whichever the use)
    claims.hold(Claim("keying", port_key(port), 2))
    tnc = serial_radio(3, "FM 2", claims, lock, port=port)
    try:
        await tnc.start()
        assert tnc.state is Source.State.WAITING and tnc.problem == f"{port}: held by radio 2" and tnc.stats.opens == 0
        assert (
            held_elsewhere(claims, 3, port) == "held by radio 2"
            and held_elsewhere(claims, 2, port) == ""
            and held_elsewhere(None, 3, port) == ""
        )
        claims.release(2)
        claims.hold(Claim("gps", port_key(port), None))
        await until(lambda: tnc.problem == f"{port}: held by the GPS receiver")
        assert tnc.stats.opens == 0
        claims.release(None)
        await until(lambda: tnc.state is Source.State.CONNECTED, 5.0)
        assert claims.all() == (Claim("serial", port_key(port), 3),) and tnc.stats.opens == 1, (
            "free again: opened, and held for its radio"
        )
    finally:
        await tnc.stop()
    assert claims.all() == ()


async def test_a_kiss_tcp_line_holds_nothing_in_the_table() -> None:
    radio = FakeRadio()
    await radio.start()
    claims = Claims()
    tcp = Tnc(
        radio.url,
        backoff=tiny_backoff(),
        fallback_probe=False,
        check_sec=0.0,
        claims=claims,
        search_lock=asyncio.Lock(),
    )
    try:
        await tcp.start()
        await radio.connected()
        assert tcp.state is Source.State.CONNECTED and claims.all() == (), (
            "a KISS TCP address is a connection, no device of the station"
        )
    finally:
        await tcp.stop()
        await radio.aclose()


# ---- the pairs of ports of the modems


def test_the_table_hands_out_pairs_that_share_no_port_and_a_radios_own_pair_is_its_own() -> None:
    claims = Claims()
    claims.hold(Claim("modem_ports", "20000", 2))
    free = lambda port: True  # noqa: E731 (every pair of the machine free: the table alone decides)
    assert next_modem_ports(claims, 5, free, first=20000) == 20002, "20001's control port is 20000's ARQ data port"
    assert next_modem_ports(claims, 2, free, first=20000) == 20000, "the pair a radio holds is its own to take again"
    assert next_modem_ports(claims, 5, lambda port: port != 20002, first=20000) == 20003, (
        "a pair the probe finds taken is passed over too"
    )
    assert set(pair_ports(20000)).isdisjoint(pair_ports(20002)) and not set(pair_ports(20000)).isdisjoint(
        pair_ports(20001)
    )
    claims.hold(Claim("modem_ports", "20002", 7))
    with pytest.raises(OSError, match="no other radio's modem holds"):
        next_modem_ports(claims, 5, free, first=20000, tries=4)


def as_radio(config: Config, id: RadioId) -> Config:
    """The settings with radio `id` an HF radio whose own sound card and keying are radio 2's: a
    modem reads its own radio's (mercurymodem.own_choice), and the modems of these tests are radio
    5's too."""
    hf = config.radio(HF_ID)
    assert hf is not None
    return replace(config, radios=(*config.radios, replace(hf, id=id, position=id)))


async def test_two_radios_modems_are_started_on_pairs_that_share_no_port_and_hold_them_until_they_stop(
    tmp_path: Path,
) -> None:
    claims = Claims()
    two = Mercury(
        tmp_path,
        finder=fakemercury.program,
        backoff=QUICK,
        control_backoff=Backoff([0.05, 0.05]),
        **of_radio(tmp_path, 2, claims),
    )
    five = Mercury(
        tmp_path,
        finder=fakemercury.program,
        backoff=QUICK,
        control_backoff=Backoff([0.05, 0.05]),
        **of_radio(tmp_path, 5, claims),
    )
    two.ports = five.ports = lambda: []
    try:
        await two.start(HF)
        await five.start(as_radio(with_radio(HF, HF_ID, sound_card="plughw:2,0", keying="vox"), 5))
        await until_started(lambda: two.running and five.running)
        assert set(pair_ports(two.broadcast_port)).isdisjoint(pair_ports(five.broadcast_port)), (
            "two pairs that share no port"
        )
        assert {c for c in claims.all() if c.kind == "modem_ports"} == {
            Claim("modem_ports", str(two.broadcast_port), 2),
            Claim("modem_ports", str(five.broadcast_port), 5),
        }
        await two.stop()
        assert [c.holder for c in claims.all()] == [5, 5], (
            "the stopped modem's card, keying and pair are let go; the other's card and pair stay"
        )
    finally:
        await stopped(two)
        await stopped(five)


async def test_a_pair_the_table_holds_for_a_modem_that_is_down_is_not_given_to_another_though_it_is_free(
    tmp_path: Path,
) -> None:
    claims = Claims()
    two = Mercury(
        tmp_path,
        finder=fakemercury.program,
        backoff=Backoff([30.0]),
        control_backoff=Backoff([0.05, 0.05]),
        **of_radio(tmp_path, 2, claims),
    )
    five = Mercury(
        tmp_path,
        finder=fakemercury.program,
        backoff=QUICK,
        control_backoff=Backoff([0.05, 0.05]),
        **of_radio(tmp_path, 5, claims),
    )
    two.ports = five.ports = lambda: []
    try:
        await two.start(HF)
        await until_started(lambda: two.running)
        held = two.broadcast_port
        assert two._program._process is not None
        two._program._process.kill()
        # (down for the back-off: its pair is free on the machine, and still radio 2's)
        await until_started(lambda: two.state == "waiting")
        await until_started(lambda: mercuryhelper.pair_free(held))
        await five.start(as_radio(with_radio(HF, HF_ID, sound_card="plughw:2,0", keying="vox"), 5))
        await until_started(lambda: five.running)
        assert (
            set(pair_ports(held)).isdisjoint(pair_ports(five.broadcast_port))
            and Claim("modem_ports", str(held), 2) in claims.all()
        )
    finally:
        await stopped(two)
        await stopped(five)


# ---- the sound card and the keying line


async def test_a_card_or_a_keying_line_the_settings_name_and_another_radio_holds_is_the_modems_problem_with_the_holder(
    tmp_path: Path,
) -> None:
    claims = Claims()
    m = Mercury(
        tmp_path,
        finder=fakemercury.program,
        backoff=Backoff([30.0]),
        control_backoff=Backoff([0.05, 0.05]),
        **of_radio(tmp_path, 5, claims),
    )
    m.ports = lambda: []
    claims.hold(Claim("sound_card", "plughw:1,0", 2))
    await m.start(as_radio(HF, 5))
    try:
        assert (
            m.state == "waiting"
            and m.reason == "not_started"
            and m.problem == "the sound card plughw:1,0 is held by radio 2"
            and m.starts == 0
            and m.held() == []
        )
    finally:
        await m.stop()
    claims.release(2)
    claims.hold(Claim("serial", port_key("/dev/ttyUSB0"), 1))  # (the FM radio's port)
    await m.start(as_radio(HF, 5))
    try:
        assert (
            m.state == "waiting"
            and m.problem == "the keying line /dev/ttyUSB0 is held by radio 1"
            and m.starts == 0
            and m.held() == []
        ), "neither is held when one is refused"
        assert claims.all() == (Claim("serial", port_key("/dev/ttyUSB0"), 1),)
    finally:
        await stopped(m)


async def test_the_holder_of_a_card_the_settings_name_is_told_by_the_name_the_station_gives_it(tmp_path: Path) -> None:
    claims = Claims()
    # (the registry's names: the log and the Terminal say the radio as the page does)
    claims.name_of = lambda id: {2: "Mast"}.get(id, f"radio {id}")
    m = Mercury(
        tmp_path,
        finder=fakemercury.program,
        backoff=Backoff([30.0]),
        control_backoff=Backoff([0.05, 0.05]),
        **of_radio(tmp_path, 5, claims),
    )
    m.ports = lambda: []
    claims.hold(Claim("sound_card", "plughw:1,0", 2))
    await m.start(as_radio(HF, 5))
    try:
        assert m.state == "waiting" and m.problem == "the sound card plughw:1,0 is held by Mast", m.problem
    finally:
        await stopped(m)


async def test_the_modems_own_choice_of_a_keying_line_leaves_out_a_port_another_radio_holds(tmp_path: Path) -> None:
    claims = Claims()
    m = Mercury(
        tmp_path,
        finder=fakemercury.program,
        backoff=QUICK,
        control_backoff=Backoff([0.05, 0.05]),
        **of_radio(tmp_path, 2, claims),
    )
    m.ports = lambda: [SerialPort("/dev/ttyUSB0", 0x10C4, 0xEA60)]
    claims.hold(Claim("serial", port_key("/dev/ttyUSB0"), 1))
    await m.start(replace(HF, mercury_sound_card="", mercury_keying=""))
    try:
        await until_started(lambda: m.running)
        assert m.keying == Keying("vox"), "the one CP2102 port is the FM radio's: VOX"
    finally:
        await m.stop()
    claims.release(1)
    await m.start(replace(HF, mercury_sound_card="", mercury_keying=""))
    try:
        await until_started(lambda: m.running)
        assert (
            m.keying == Keying("rts", "/dev/ttyUSB0") and Claim("keying", port_key("/dev/ttyUSB0"), 2) in claims.all()
        ), "free: chosen, and held as the radio's keying line"
    finally:
        await stopped(m)


async def test_a_card_the_daemon_chose_that_another_radios_modem_took_meanwhile_is_chosen_anew_and_no_problem_is_shown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claims = Claims()
    asked: list[frozenset[str]] = []

    def choose(
        program: list[str],
        card: str,
        keying: str,
        ports: object,
        leave: object = (),
        held_cards: frozenset[str] = frozenset(),
        key: object = str,
    ) -> tuple[str, Keying]:
        asked.append(frozenset(held_cards))
        if len(asked) == 1:
            # (radio 5's modem chose the same codec at the same time, and held it first)
            claims.hold(Claim("sound_card", "plughw:1,0", 5))
        return ("plughw:2,0" if "plughw:1,0" in held_cards else "plughw:1,0"), Keying("vox")

    monkeypatch.setattr(mercurymodem, "choose_setup", choose)
    m = Mercury(
        tmp_path,
        finder=fakemercury.program,
        backoff=Backoff([30.0]),
        control_backoff=Backoff([0.05, 0.05]),
        **of_radio(tmp_path, 2, claims),
    )
    m.ports = lambda: []
    states: list[str] = []
    m.changed.connect(lambda: states.append(m.state))
    await m.start(replace(HF, mercury_sound_card="", mercury_keying=""))
    try:
        await until_started(lambda: m.running)
        assert (
            m.sound_card == "plughw:2,0"
            and asked == [frozenset(), frozenset({"plughw:1,0"})]
            and "waiting" not in states
        ), "chosen again at once, without the other's card: no problem to show"
        assert Claim("sound_card", "plughw:2,0", 2) in claims.all()
    finally:
        await stopped(m)


def test_the_daemons_own_choice_of_a_card_leaves_out_the_cards_other_radios_run_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cards = [
        SoundCard("plughw:1,0", "USB Audio CODEC", True, True),
        SoundCard("plughw:2,0", "USB PnP Sound Device", True, True),
        SoundCard("plughw:0,0", "HDA Intel PCH", True, True, True),
    ]
    monkeypatch.setattr(mercuryhelper, "list_sound_cards", lambda command, timeout_sec=15.0: cards)
    assert choose_setup(["mercury"], "", "vox", lambda: [])[0] == "plughw:1,0", (
        "two radios' cards: the codec is the radio's"
    )
    assert choose_setup(["mercury"], "", "vox", lambda: [], held_cards={"plughw:1,0"})[0] == "plughw:2,0", (
        "the codec is another radio's: the other card"
    )
    assert choose_setup(["mercury"], "plughw:1,0", "vox", lambda: [], held_cards={"plughw:1,0"})[0] == "plughw:1,0", (
        "a card the settings name is the settings' (the claim refuses it)"
    )


# ---- a port a radio is set to is that radio's, opened or not (claims.py: `named`, `others`)


def set_to(*ports: tuple[str, int]) -> Callable[[], tuple[Claim, ...]]:
    """What the station's table reads of the settings (the registry's serialprobe.named_ports):
    these radios are set to these ports."""
    return lambda: tuple(Claim("serial", port_key(port), radio) for port, radio in ports)


@posix_only
async def test_a_port_another_radio_is_set_to_is_never_opened_by_a_search_and_that_radio_gets_it(
    ptys: Ptys, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, "neoaprs")
    (_, board), (port_1, port_2), pattern = await links(tmp_path, ptys, 2)
    claims, lock = Claims(), asyncio.Lock()
    # (a LoRa board's radio 3 is set to port_2, and is started after radio 1)
    claims.named = set_to((port_2, 3))
    fm = serial_radio(1, "FM", claims, lock, pattern=pattern)
    lora = serial_radio(3, "LoRa", claims, lock, port=port_2)
    starts = [asyncio.create_task(fm.start())]
    feeder = asyncio.create_task(keep_feeding(board, kiss_of(ui_frame())))
    try:
        await until(lambda: fm.searching == [port_1], 5.0)
        starts.append(asyncio.create_task(lora.start()))
        await until(lambda: lora.state is Source.State.CONNECTED and lora.path == port_2, 5.0)
        await idle_for(0.3)
        assert fm.searching == [port_1] and fm.state is Source.State.CONNECTING, "the FM search never took the board"
        assert (
            "in use by another program" not in caplog.text
            and f"probe: skipping {port_2}: held by radio 3" in caplog.text
        )
    finally:
        feeder.cancel()
        await asyncio.gather(feeder, return_exceptions=True)
        await fm.stop()
        await lora.stop()
        await asyncio.gather(*starts, return_exceptions=True)


@posix_only
async def test_a_search_that_has_a_port_open_lets_go_of_it_when_another_radio_is_set_to_it_and_that_radio_gets_it(
    ptys: Ptys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(serialprobe, "RELIST_SEC", 0.1)
    (_, board), (port_1, port_2), pattern = await links(tmp_path, ptys, 2)
    claims, lock = Claims(), asyncio.Lock()
    fm = serial_radio(1, "FM", claims, lock, pattern=pattern)
    lora = serial_radio(3, "LoRa", claims, lock, port=port_2)
    starts = [asyncio.create_task(fm.start())]
    feeder: asyncio.Task[None] | None = None
    try:
        await until(lambda: sorted(fm.searching) == [port_1, port_2], 5.0)
        # (a save adds radio 3 on port_2: nothing restarts radio 1)
        claims.named = set_to((port_2, 3))
        await until(lambda: fm.searching == [port_1], 5.0)
        starts.append(asyncio.create_task(lora.start()))
        feeder = asyncio.create_task(keep_feeding(board, kiss_of(ui_frame())))
        await until(lambda: lora.state is Source.State.CONNECTED and lora.path == port_2, 5.0)
        assert fm.state is Source.State.CONNECTING and fm.path != port_2
    finally:
        if feeder is not None:
            feeder.cancel()
            await asyncio.gather(feeder, return_exceptions=True)
        await fm.stop()
        await lora.stop()
        await asyncio.gather(*starts, return_exceptions=True)


@posix_only
async def test_a_named_port_another_radio_holds_is_waited_for_and_no_other_port_is_searched_meanwhile(
    ptys: Ptys, tmp_path: Path
) -> None:
    (_, other), (port_1, port_2), pattern = await links(tmp_path, ptys, 2)
    claims, lock = Claims(), asyncio.Lock()
    # (radio 1 has the port: two radios stored with one port, or a swap in one save)
    claims.hold(Claim("serial", port_key(port_1), 1))
    tnc = Tnc(
        port_1,
        pattern=pattern,
        backoff=tiny_backoff(),
        fallback_probe=True,
        check_sec=0.0,
        claims=claims,
        search_lock=lock,
    )
    tnc.radio_id, tnc.radio_name = 3, "FM 2"
    feeder = asyncio.create_task(keep_feeding(other, kiss_of(ui_frame())))
    seen: list[list[str]] = []
    tnc.changed.connect(lambda: seen.append(tnc.searching))
    try:
        await tnc.start()
        await idle_for(0.5)
        assert (
            tnc.state is Source.State.WAITING and tnc.problem == f"{port_1}: held by radio 1" and tnc.stats.opens == 0
        )
        assert all(port_2 not in ports for ports in seen) and tnc.path != port_2, (
            "the radio waits for its own port: it takes no other TNC meanwhile"
        )
        claims.release(1)
        await until(lambda: tnc.state is Source.State.CONNECTED, 5.0)
        assert tnc.path == port_1
    finally:
        feeder.cancel()
        await asyncio.gather(feeder, return_exceptions=True)
        await tnc.stop()


@posix_only
async def test_two_searches_that_take_turns_nudge_each_port_once_and_say_their_turns_once(
    ptys: Ptys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, "neoaprs")
    monkeypatch.setattr(serialprobe, "RELIST_SEC", 0.1)
    # (one port, and its TNC says nothing)
    (master,), _, pattern = await links(tmp_path, ptys, 1)
    os.set_blocking(master, False)
    claims, lock = Claims(), asyncio.Lock()
    radios = [
        serial_radio(1, "FM", claims, lock, pattern=pattern, nudge_sec=0.1),
        serial_radio(3, "FM 2", claims, lock, pattern=pattern, nudge_sec=0.1),
    ]
    starts = [asyncio.create_task(radio.start()) for radio in radios]
    heard = b""
    try:
        for _ in range(40):
            await asyncio.sleep(0.05)
            with contextlib.suppress(BlockingIOError):
                heard += os.read(master, 4096)
    finally:
        for radio in radios:
            await radio.stop()
        await asyncio.gather(*starts, return_exceptions=True)
    gives = [r for r in caplog.records if "the search gives its turn" in r.getMessage()]
    assert len(gives) > 2, "the two took turns"
    assert heard.count(b"\r") <= 2, "one carriage return for each radio's search, however many turns it takes"
    for name in ("FM", "FM 2"):
        for words in ("the search gives its turn to another radio", WAITING, "listening on"):
            said = [
                r for r in caplog.records if r.levelno == logging.INFO and r.getMessage().startswith(f"{name}: {words}")
            ]
            assert len(said) <= 1, f"{name}: {words!r} is said once a search at INFO, at DEBUG after"
        assert sum(WAITING in line for line in radios[0 if name == "FM" else 1].lines) <= 1


def test_the_words_of_who_holds_a_port_name_the_radio() -> None:
    claims = Claims()
    claims.name_of = {2: "HF", 3: "FM 2"}.get  # type: ignore[assignment]
    # (a claim holds the port as port_key compares it: in upper case on Windows)
    claims.hold(Claim("keying", port_key("/dev/ttyUSB0"), 2))
    claims.hold(Claim("gps", port_key("/dev/ttyACM0"), None))
    assert (
        held_elsewhere(claims, 3, "/dev/ttyUSB0") == "held by HF"
        and held_elsewhere(claims, 3, "/dev/ttyACM0") == "held by the GPS receiver"
    )
    claims.named = set_to(("/dev/ttyUSB3", 3))
    assert held_elsewhere(claims, 1, "/dev/ttyUSB3") == "", (
        "a port another radio is only set to is not refused to a radio set to it too: the first to open it holds it"
    )
    assert claims.others(1, "serial") == {
        port_key("/dev/ttyUSB0"): 2,
        port_key("/dev/ttyACM0"): None,
        port_key("/dev/ttyUSB3"): 3,
    } and claims.held_by_others(3, "serial") == {port_key("/dev/ttyUSB0"), port_key("/dev/ttyACM0")}


def test_the_devices_the_settings_name_are_every_enabled_radios_port_and_keying_line_whatever_its_type_and_the_registry_puts_them_in_the_table() -> (
    None
):
    radios = [
        spec(1, port=""),
        spec(2, "hf", type="mercury", keying="rts:/dev/ttyUSB9", sound_card="plughw:1,0"),
        spec(3, "lora", type="lora-serial", port="/dev/ttyACM3"),
        spec(4, port="/dev/ttyUSB4", enabled=False),
        spec(5, port="/dev/ttyUSB5", removed_at=T0),
        spec(6, type="kiss-tcp", port="tcp://192.0.2.1:8001"),
    ]
    config = with_radios(DEFAULTS, radios)
    named = {Claim("keying", port_key("/dev/ttyUSB9"), 2), Claim("serial", port_key("/dev/ttyACM3"), 3)}
    assert set(serialprobe.named_ports(config)) == named, (
        "a radio that is off, a removed one, a TCP address and an empty port name no device"
    )
    assert set(serialprobe.named_ports(config, off_too=True)) == named | {Claim("serial", port_key("/dev/ttyUSB4"), 4)}
    rig = Rig(config)
    assert rig.claims.others(1, "serial") == {
        port_key("/dev/ttyUSB9"): 2,
        port_key("/dev/ttyACM3"): 3,
    } and rig.claims.others(3, "serial") == {port_key("/dev/ttyUSB9"): 2}, (
        "read from the settings in force: what radio 1's search leaves out"
    )
    rig.registry.sync(rig.config)
    assert rig.claims.words(3) == rig.registry.name_of(3) != "radio 3", "the holder by its name"


def test_radio_1_does_not_try_the_port_its_search_remembered_once_another_radio_is_set_to_it() -> None:
    radios = [spec(1, port=""), spec(3, "lora", type="lora-serial", port="/dev/ttyUSB0")]
    config = replace(with_radios(DEFAULTS, radios), serial_last_port="/dev/ttyUSB0")
    config.__dict__["radios"] = tuple(radios)
    assert line_settings(radios[0], config, RunOverrides()).port == "", (
        "an empty port: radio 1 searches, and its search leaves the board's port out"
    )
    assert (
        line_settings(radios[0], replace(config, serial_last_port="/dev/ttyUSB1"), RunOverrides()).port
        == "/dev/ttyUSB1"
    )


async def test_find_my_radio_passes_over_a_port_another_radio_is_set_to_and_not_the_radios_own(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, "neoaprs.tnc")
    claims = Claims()
    claims.named = set_to(("/dev/ttyACM3", 3), ("/dev/ttyUSB0", 1))
    finder = RadioFinder(
        lambda: asyncio.sleep(0, ["/dev/ttyUSB0", "/dev/ttyACM3"]),
        lambda radio: asyncio.sleep(0),
        lambda radio: None,
        claims=claims,
    )
    assert (
        finder._unclaimed(["/dev/ttyUSB0", "/dev/ttyACM3"], 1) == ["/dev/ttyUSB0"]
        and "passing over /dev/ttyACM3: held by radio 3" in caplog.text
    )
    assert finder._unclaimed(["/dev/ttyUSB0", "/dev/ttyACM3"], 3) == ["/dev/ttyACM3"]


def test_the_keying_choice_leaves_out_every_other_radios_port_on_or_off_and_the_modems_own_keying_is_its_own() -> None:
    gone = spec(1, port="/dev/ttyUSB0", removed_at=T0)
    hf, fm3, fm4 = (
        spec(2, "hf", type="mercury", keying="rts:/dev/ttyUSB2"),
        spec(3, port="/dev/ttyUSB3"),
        spec(4, port="/dev/ttyACM0", enabled=False),
    )
    station = with_radios(DEFAULTS, [gone, hf, fm3, fm4])
    assert set(mercurymodem.left_out(station, 2)) == {port_key("/dev/ttyUSB3"), port_key("/dev/ttyACM0")}, (
        "a removed radio's port is free, the modem's own keying line is its own"
    )
    assert port_key("/dev/ttyUSB2") in mercurymodem.left_out(station, 5)


def test_the_keying_choice_leaves_out_a_port_named_in_another_spelling_of_it_as_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ports left out are compared as the station's table compares them (port_key), the ports
    the system lists too: on Windows `com3`, `COM3` and `\\\\.\\COM3` are one port."""
    monkeypatch.setattr(serialholders, "_on_windows", lambda: True)
    monkeypatch.setattr(
        mercuryhelper,
        "list_sound_cards",
        lambda command, timeout_sec=15.0: [SoundCard("plughw:1,0", "USB Audio CODEC", True, True)],
    )
    station = replace(
        with_radios(DEFAULTS, [spec(2, "hf", type="mercury"), spec(3, port="com3")]),
        gps_device="com6",
        serial_skip="\\\\.\\COM5",
    )
    ports = [SerialPort(name, 0x10C4, 0xEA60) for name in ("COM3", "COM5", "COM6")]
    assert choose_setup(["mercury"], "plughw:1,0", "", lambda: ports, mercurymodem.left_out(station, 2))[1] == Keying(
        "vox"
    ), "radio 3's port, the GPS receiver's and the skipped one key no HF radio"
    assert choose_setup(
        ["mercury"],
        "plughw:1,0",
        "",
        lambda: [*ports, SerialPort("COM7", 0x10C4, 0xEA60)],
        mercurymodem.left_out(station, 2),
    )[1] == Keying("rts", "COM7")
    cards = [SoundCard("plughw:1,0", "USB Audio CODEC", True, True)]
    assert mercurymodem.proposal(
        cards,
        [serialprobe.PortInfo(p.device, "CP2102", "USB VID:PID=10C4:EA60", p.vid, p.pid) for p in ports],
        station,
        holder=2,
    ) == ("plughw:1,0", "vox"), "the page's proposal leaves them out alike"


async def test_the_modems_own_choice_keys_no_radio_on_the_port_another_radio_is_set_to_though_that_radio_has_not_opened_it(
    tmp_path: Path,
) -> None:
    claims = Claims()
    m = Mercury(
        tmp_path,
        finder=fakemercury.program,
        backoff=QUICK,
        control_backoff=Backoff([0.05, 0.05]),
        **of_radio(tmp_path, 2, claims),
    )
    # (the one CP2102 port of the machine: FM radio 3's TNC, unplugged or not yet opened)
    m.ports = lambda: [SerialPort("/dev/ttyUSB3", 0x10C4, 0xEA60)]
    config = with_radio(HF, HF_ID, sound_card="", keying="")
    config = with_radios(
        config,
        [
            spec(1, port="/dev/ttyUSB0", removed_at=T0),
            *(s for s in config.radios if s.id == 2),
            spec(3, port="/dev/ttyUSB3"),
        ],
    )
    await m.start(config)
    try:
        await until_started(lambda: m.running)
        assert m.keying == Keying("vox"), "the port radio 3 is set to keys no HF radio: VOX"
    finally:
        await stopped(m)


# ---- the moment between a save that names a port for a radio and the search's next listing (the
# second reading of the fixes)


@posix_only
async def test_a_board_that_speaks_after_a_save_named_its_port_for_another_radio_is_not_taken_by_a_search_that_has_it_open(
    ptys: Ptys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # (no listing comes within the test: the moment before it is what is tried)
    monkeypatch.setattr(serialprobe, "RELIST_SEC", 30.0)
    (_, board), (port_1, port_2), pattern = await links(tmp_path, ptys, 2)
    claims, lock = Claims(), asyncio.Lock()
    fm = serial_radio(1, "FM", claims, lock, pattern=pattern)
    lora = serial_radio(3, "LoRa", claims, lock, port=port_2)
    starts = [asyncio.create_task(fm.start())]
    feeder: asyncio.Task[None] | None = None
    try:
        await until(lambda: sorted(fm.searching) == [port_1, port_2], 5.0)
        # (a save adds the LoRa radio on port_2, and its board speaks before radio 3 is started)
        claims.named = set_to((port_2, 3))
        feeder = asyncio.create_task(keep_feeding(board, kiss_of(ui_frame())))
        await until(lambda: fm.searching == [port_1], 5.0)
        assert fm.state is Source.State.CONNECTING and fm.path != port_2 and claims.all() == (), (
            "the FM search closed the board's port and took nothing"
        )
        starts.append(asyncio.create_task(lora.start()))
        await until(lambda: lora.state is Source.State.CONNECTED and lora.path == port_2, 5.0)
    finally:
        if feeder is not None:
            feeder.cancel()
            await asyncio.gather(feeder, return_exceptions=True)
        await fm.stop()
        await lora.stop()
        await asyncio.gather(*starts, return_exceptions=True)


@posix_only
@pytest.mark.parametrize("fallback", [False, True], ids=["a board", "a tnc that searches when its port fails"])
async def test_a_radio_a_save_names_a_port_for_takes_it_at_once_from_a_search_that_has_it_open(
    ptys: Ptys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, fallback: bool
) -> None:
    caplog.set_level(logging.INFO, "neoaprs")
    monkeypatch.setattr(serialprobe, "RELIST_SEC", 30.0)
    _, (port_1, port_2), pattern = await links(tmp_path, ptys, 2)
    claims, lock = Claims(), asyncio.Lock()
    fm = serial_radio(1, "FM", claims, lock, pattern=pattern)
    radio = serial_radio(3, "FM 2", claims, lock, port=port_2, pattern=pattern)
    radio.fallback_probe = fallback
    starts = [asyncio.create_task(fm.start())]
    try:
        await until(lambda: sorted(fm.searching) == [port_1, port_2], 5.0)
        # (a save adds radio 3 on port_2, and it is started at once)
        claims.named = set_to((port_2, 3))
        starts.append(asyncio.create_task(radio.start()))
        await until(lambda: radio.state is Source.State.CONNECTED, 3.0)
        assert radio.path == port_2 and "in use by another program" not in caplog.text, (
            "its own port, at the first try, and not the words of another program"
        )
        assert f"probe: {port_2} is let go: a radio is set to it" in caplog.text
        await until(lambda: fm.searching == [port_1])
    finally:
        await fm.stop()
        await radio.stop()
        await asyncio.gather(*starts, return_exceptions=True)


async def test_a_port_the_search_heard_that_a_save_gave_another_radio_meanwhile_is_not_held_and_the_search_goes_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claims, board, tnc = Claims(), "/dev/ttyACM3", "/dev/ttyUSB7"
    answers = [board, tnc]

    async def heard(paths: list[str], *args: object, **kwargs: object) -> tuple[str, bytes]:
        if answers[0] == board:
            # (the save comes while the search hands its answer back)
            claims.named = set_to((board, 3))
        return answers.pop(0), kiss_of(ui_frame())

    monkeypatch.setattr(serialprobe, "can_search", lambda: True)
    monkeypatch.setattr(serialprobe, "searchable_ports", lambda pattern: ([board, tnc], {}))
    monkeypatch.setattr(serialprobe, "probe_heard", heard)
    search = PortSearch(asyncio.ensure_future, lambda text: None, b"\r")
    found = await search.find(
        "/dev/tty*",
        9600,
        0.0,
        lambda heard: True,
        True,
        1.0,
        (),
        lambda: True,
        claims=claims,
        holder=1,
        lock=asyncio.Lock(),
    )
    assert found[0] == tnc and claims.all() == (Claim("serial", serialprobe.claim_value(tnc) or tnc, 1),)


@posix_only
async def test_radio_1s_remembered_port_that_the_gps_receiver_holds_is_searched_past_and_its_tnc_is_found(
    ptys: Ptys, tmp_path: Path
) -> None:
    (_, tnc_master), (port_1, port_2), pattern = await links(tmp_path, ptys, 2)
    claims, lock = Claims(), asyncio.Lock()
    # (serial/last_port is the receiver's port now)
    claims.hold(Claim("gps", port_key(port_1), None))
    fm = serial_radio(1, "FM", claims, lock, port=port_1, pattern=pattern)
    fm.fallback_probe, fm.remembered = True, True
    feeder = asyncio.create_task(keep_feeding(tnc_master, kiss_of(ui_frame())))
    try:
        await fm.start()
        await until(lambda: fm.state is Source.State.CONNECTED, 10.0)
        assert fm.path == port_2 and Claim("serial", port_key(port_2), 1) in claims.all()
    finally:
        feeder.cancel()
        await asyncio.gather(feeder, return_exceptions=True)
        await fm.stop()


def test_radio_1_does_not_try_the_port_its_search_remembered_once_the_gps_receiver_reads_it_and_says_which_port_is_only_remembered() -> (
    None
):
    radios = [spec(1, port="")]
    config = replace(
        with_radios(DEFAULTS, radios), serial_last_port="/dev/ttyACM0", gps_source="serial", gps_device="/dev/ttyACM0"
    )
    assert line_settings(radios[0], config, RunOverrides()).port == "", (
        "radio 1 searches, and its search leaves the receiver's port out"
    )
    off = replace(config, gps_source="off")
    assert line_settings(radios[0], off, RunOverrides()).port == "/dev/ttyACM0" and tncdriver.remembered(
        radios[0], off, RunOverrides()
    )
    assert not tncdriver.remembered(radios[0], config, RunOverrides()) and not tncdriver.remembered(
        spec(1, port="/dev/ttyUSB0"), off, RunOverrides()
    )
    assert not tncdriver.remembered(radios[0], off, RunOverrides(port="/dev/ttyACM0")) and not tncdriver.remembered(
        spec(3, port=""), off, RunOverrides()
    )
    driver = TncDriver(radios[0], Claims())
    driver.configure(radios[0], off, RunOverrides())
    assert driver.line.remembered
    driver.configure(spec(1, port="/dev/ttyACM0"), off, RunOverrides())
    assert not driver.line.remembered


@posix_only
async def test_the_probe_closes_a_port_that_became_another_radios_while_it_listened_and_never_answers_with_it(
    ptys: Ptys, tmp_path: Path
) -> None:
    (first, second), (port_1, port_2), _ = await links(tmp_path, ptys, 2)
    frame, claimed, opened = kiss_of(ui_frame()), dict[str, str](), list[list[str]]()
    probe = asyncio.create_task(
        serialprobe.probe_heard(
            [port_1, port_2], 9600, 10.0, lambda heard: frame in heard, on_open=opened.append, claimed=claimed
        )
    )
    feeders: list[asyncio.Task[None]] = []
    try:
        await until(lambda: bool(opened) and sorted(opened[-1]) == [port_1, port_2])
        # (a save names port_2 for radio 3: no listing comes meanwhile)
        claimed[port_key(port_2)] = "held by radio 3"
        feeders.append(asyncio.create_task(keep_feeding(second, frame)))
        await until(lambda: opened[-1] == [port_1])
        assert not probe.done(), "the board's frame is not the answer"
        feeders.append(asyncio.create_task(keep_feeding(first, frame)))
        found = await asyncio.wait_for(probe, 5.0)
        assert found is not None and found[0] == port_1
    finally:
        for task in (*feeders, probe):
            task.cancel()
        await asyncio.gather(*feeders, probe, return_exceptions=True)


async def test_find_my_radio_passes_over_a_port_a_save_gave_another_radio_while_it_tried_the_others() -> None:
    claims, tried = Claims(), list[str]()
    finder = RadioFinder(
        lambda: asyncio.sleep(0, []), lambda radio: asyncio.sleep(0), lambda radio: None, claims=claims
    )

    async def try_port(path: str, *args: object) -> None:
        tried.append(path)
        # (a save adds the LoRa radio on the board's port while the first port is tried)
        claims.named = set_to(("/dev/ttyACM3", 3))

    finder._try_port = try_port  # type: ignore[method-assign,assignment]
    outcome: list[object] = []
    await finder._run(["/dev/ttyUSB0", "/dev/ttyACM3"], lambda trying: None, outcome, 1)  # type: ignore[arg-type]
    assert tried == ["/dev/ttyUSB0"] and outcome == [None]
