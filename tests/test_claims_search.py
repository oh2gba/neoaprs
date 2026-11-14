"""Radios side by side on one table of the station's resources (neoaprs/claims.py) and one search at a time (RadioRegistry.search_lock), as the drivers' insides keep them (neoaprs/tnc.py, tncsearch.py, serialprobe.py,
mercurymodem.py, mercuryclaims.py, mercuryhelper.py): a second serial radio with no port waits while the first searches and says so, then leaves out the port the first found; a port another radio or the GPS
receiver holds is never opened, and the radio waits saying who holds it; the port a search found is its radio's before the next radio's search starts, and until its Tnc stops; a search that finds nothing gives its turn
to a radio that waits for it, and a port held meanwhile is closed at the next listing; two radios' Mercury modems are never given one pair of ports, nor pairs that share a port;
a modem's own choice of a sound card and a keying line leaves out what the others hold, and a card or a line the settings name that another radio holds is the modem's problem, with the holder. The serial ports are
pseudo-terminals behind links in a folder of the test (POSIX); the Mercury is the tests' stand-in (tests/support/fakemercury.py)."""
import asyncio
import logging
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs import mercuryhelper, mercurymodem, serialprobe
from neoaprs.claims import Claim, Claims
from neoaprs.mercury import Keying, SerialPort, SoundCard
from neoaprs.mercuryhelper import choose_setup, next_modem_ports, pair_ports
from neoaprs.mercurymodem import Mercury
from neoaprs.serialholders import port_key
from neoaprs.source import Backoff, Source
from neoaprs.tnc import Tnc
from neoaprs.tncsearch import WAITING, PortSearch, held_elsewhere
from tests.support import fakemercury
from tests.support.env import until, until_started
from tests.support.fakemercury import of_radio
from tests.support.fakeradio import FakeRadio
from tests.support.ptyline import Ptys, feed, posix_only
from tests.test_mercury_modem import HF, QUICK, _ports_of_this_test, stopped  # noqa: F401 (the fixture keeps two tests from taking the same ports)
from tests.test_tnc import kiss_of, tiny_backoff, ui_frame


async def links(tmp_path: Path, ptys: Ptys, count: int) -> tuple[list[int], list[str], str]:
    """`count` pseudo-terminals behind links port_1, port_2 ... in the test's folder: their masters, the links, and the pattern that matches them."""
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


def serial_radio(radio: int, name: str, claims: Claims, lock: asyncio.Lock, port: str = "", pattern: str = "", nudge_sec: float = serialprobe.NUDGE_SEC) -> Tnc:
    """A serial radio's line as its driver makes it: the station's table and its one search at a time, the radio's id and name."""
    tnc = Tnc(port, pattern=pattern, backoff=tiny_backoff(), fallback_probe=False, check_sec=0.0, probe_nudge_sec=nudge_sec, claims=claims, search_lock=lock)
    tnc.radio_id, tnc.radio_name = radio, name
    return tnc


# ---- the serial search

@posix_only
async def test_a_second_serial_radio_waits_while_the_first_searches_and_then_leaves_out_the_port_the_first_found(ptys: Ptys, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs")
    (first_master, second_master), (port_1, port_2), pattern = await links(tmp_path, ptys, 2)
    claims, lock = Claims(), asyncio.Lock()
    fm, fm2 = serial_radio(1, "FM", claims, lock, pattern=pattern), serial_radio(3, "FM 2", claims, lock, pattern=pattern)
    feeders: list[asyncio.Task[None]] = []
    starts = [asyncio.create_task(fm.start())]
    try:
        await until(lambda: sorted(fm.searching) == [port_1, port_2], 5.0)
        starts.append(asyncio.create_task(fm2.start()))
        await until(lambda: fm2._search.waiting)
        assert fm2.describe() == WAITING and fm2.searching == [] and lock.locked(), "the second radio waits for its turn, and says so"
        assert f"FM 2: {WAITING}" in caplog.text and any(line.endswith(WAITING) for line in fm2.lines)
        feeders.append(asyncio.create_task(keep_feeding(first_master, kiss_of(ui_frame()))))
        await until(lambda: fm.state is Source.State.CONNECTED and fm.path == port_1, 10.0)
        assert claims.all() == (Claim("serial", port_key(port_1), 1),), "the port the first radio found is its radio's"
        await until(lambda: fm2.searching == [port_2], 10.0)
        assert f"probe: skipping {port_1}: held by radio 1" in caplog.text and "FM 2: listening on" in caplog.text, "the second searches in its turn, without the first's port"
        feeders.append(asyncio.create_task(keep_feeding(second_master, kiss_of(ui_frame()))))
        await until(lambda: fm2.state is Source.State.CONNECTED and fm2.path == port_2, 10.0)
        assert set(claims.all()) == {Claim("serial", port_key(port_1), 1), Claim("serial", port_key(port_2), 3)} and not lock.locked()
        await fm.stop()
        assert claims.all() == (Claim("serial", port_key(port_2), 3),), "a stopped radio lets go of its port"
    finally:
        for task in feeders:
            task.cancel()
        await asyncio.gather(*feeders, return_exceptions=True)
        await fm.stop()
        await fm2.stop()
        await asyncio.gather(*starts, return_exceptions=True)


async def test_the_port_a_search_finds_is_held_for_its_radio_before_the_turn_is_given_to_the_next(monkeypatch: pytest.MonkeyPatch) -> None:
    claims, seen, path = Claims(), [], "/dev/ttyUSB7"

    class Watched(asyncio.Lock):
        def release(self) -> None:
            seen.append(claims.all())                                              # (what the next radio's search would leave out, at the moment it may start)
            super().release()

    async def heard(paths: list[str], *args: object, **kwargs: object) -> tuple[str, bytes]:
        return path, kiss_of(ui_frame())

    monkeypatch.setattr(serialprobe, "can_search", lambda: True)
    monkeypatch.setattr(serialprobe, "searchable_ports", lambda pattern: ([path], {}))
    monkeypatch.setattr(serialprobe, "probe_heard", heard)
    search = PortSearch(asyncio.ensure_future, lambda text: None, b"\r")
    found = await search.find("/dev/ttyUSB*", 9600, 0.0, lambda heard: True, True, 1.0, (), lambda: True, claims=claims, holder=3, lock=Watched())
    assert found[0] == path and seen == [(Claim("serial", serialprobe.claim_value(path) or path, 3),)], "held before the lock is given back"


@posix_only
async def test_a_radio_that_never_finds_its_port_gives_its_turn_to_a_radio_that_waits_and_takes_it_again_after(ptys: Ptys, tmp_path: Path, caplog: pytest.LogCaptureFixture,
                                                                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    caplog.set_level(logging.INFO, "neoaprs")
    monkeypatch.setattr(serialprobe, "RELIST_SEC", 0.1)
    (_, second_master), (port_1, port_2), _ = await links(tmp_path, ptys, 2)
    claims, lock = Claims(), asyncio.Lock()
    fm = serial_radio(1, "FM", claims, lock, pattern=port_1, nudge_sec=0.1)              # (its radio is switched off: port_1 never says a word)
    fm2 = serial_radio(3, "FM 2", claims, lock, pattern=port_2, nudge_sec=0.1)
    feeder = asyncio.create_task(keep_feeding(second_master, kiss_of(ui_frame())))
    starts = [asyncio.create_task(fm.start())]
    try:
        await until(lambda: fm.searching == [port_1], 5.0)
        starts.append(asyncio.create_task(fm2.start()))
        await until(lambda: fm2.state is Source.State.CONNECTED and fm2.path == port_2, 10.0)
        assert "FM: the search gives its turn to another radio" in caplog.text and claims.all() == (Claim("serial", port_key(port_2), 3),)
        await until(lambda: fm.searching == [port_1], 5.0)
        assert fm.state is Source.State.CONNECTING, "the first goes on with its search in its next turn"
    finally:
        feeder.cancel()
        await asyncio.gather(feeder, return_exceptions=True)
        await fm.stop()
        await fm2.stop()
        await asyncio.gather(*starts, return_exceptions=True)


@posix_only
async def test_a_port_another_radio_or_the_gps_receiver_takes_while_the_search_listens_is_closed_at_the_next_listing(ptys: Ptys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
async def test_a_named_port_another_radio_or_the_gps_receiver_holds_is_never_opened_and_the_radio_waits_saying_who_holds_it(ptys: Ptys, tmp_path: Path) -> None:
    _, (port,), _ = await links(tmp_path, ptys, 1)
    claims, lock = Claims(), asyncio.Lock()
    claims.hold(Claim("keying", port_key(port), 2))                               # (the HF radio's modem keys its radio on this port's RTS: one device, whichever the use)
    tnc = serial_radio(3, "FM 2", claims, lock, port=port)
    try:
        await tnc.start()
        assert tnc.state is Source.State.WAITING and tnc.problem == f"{port}: held by radio 2" and tnc.stats.opens == 0
        assert held_elsewhere(claims, 3, port) == "held by radio 2" and held_elsewhere(claims, 2, port) == "" and held_elsewhere(None, 3, port) == ""
        claims.release(2)
        claims.hold(Claim("gps", port_key(port), None))
        await until(lambda: tnc.problem == f"{port}: held by the GPS receiver")
        assert tnc.stats.opens == 0
        claims.release(None)
        await until(lambda: tnc.state is Source.State.CONNECTED, 5.0)
        assert claims.all() == (Claim("serial", port_key(port), 3),) and tnc.stats.opens == 1, "free again: opened, and held for its radio"
    finally:
        await tnc.stop()
    assert claims.all() == ()


async def test_a_kiss_tcp_line_holds_nothing_in_the_table() -> None:
    radio = FakeRadio()
    await radio.start()
    claims = Claims()
    tcp = Tnc(radio.url, backoff=tiny_backoff(), fallback_probe=False, check_sec=0.0, claims=claims, search_lock=asyncio.Lock())
    try:
        await tcp.start()
        await radio.connected()
        assert tcp.state is Source.State.CONNECTED and claims.all() == (), "a KISS TCP address is a connection, no device of the station"
    finally:
        await tcp.stop()
        await radio.aclose()


# ---- the pairs of ports of the modems

def test_the_table_hands_out_pairs_that_share_no_port_and_a_radios_own_pair_is_its_own() -> None:
    claims = Claims()
    claims.hold(Claim("modem_ports", "20000", 2))
    free = lambda port: True                                                      # noqa: E731 (every pair of the machine free: the table alone decides)
    assert next_modem_ports(claims, 5, free, first=20000) == 20002, "20001's control port is 20000's ARQ data port"
    assert next_modem_ports(claims, 2, free, first=20000) == 20000, "the pair a radio holds is its own to take again"
    assert next_modem_ports(claims, 5, lambda port: port != 20002, first=20000) == 20003, "a pair the probe finds taken is passed over too"
    assert set(pair_ports(20000)).isdisjoint(pair_ports(20002)) and not set(pair_ports(20000)).isdisjoint(pair_ports(20001))
    claims.hold(Claim("modem_ports", "20002", 7))
    with pytest.raises(OSError, match="no other radio's modem holds"):
        next_modem_ports(claims, 5, free, first=20000, tries=4)


async def test_two_radios_modems_are_started_on_pairs_that_share_no_port_and_hold_them_until_they_stop(tmp_path: Path) -> None:
    claims = Claims()
    two = Mercury(tmp_path, finder=fakemercury.program, backoff=QUICK, control_backoff=Backoff([0.05, 0.05]), **of_radio(tmp_path, 2, claims))
    five = Mercury(tmp_path, finder=fakemercury.program, backoff=QUICK, control_backoff=Backoff([0.05, 0.05]), **of_radio(tmp_path, 5, claims))
    two.ports = five.ports = lambda: []
    try:
        await two.start(HF)
        await five.start(replace(HF, mercury_sound_card="plughw:2,0", mercury_keying="vox"))
        await until_started(lambda: two.running and five.running)
        assert set(pair_ports(two.broadcast_port)).isdisjoint(pair_ports(five.broadcast_port)), "two pairs that share no port"
        assert {c for c in claims.all() if c.kind == "modem_ports"} == {Claim("modem_ports", str(two.broadcast_port), 2), Claim("modem_ports", str(five.broadcast_port), 5)}
        await two.stop()
        assert [c.holder for c in claims.all()] == [5, 5], "the stopped modem's card, keying and pair are let go; the other's card and pair stay"
    finally:
        await stopped(two)
        await stopped(five)


async def test_a_pair_the_table_holds_for_a_modem_that_is_down_is_not_given_to_another_though_it_is_free(tmp_path: Path) -> None:
    claims = Claims()
    two = Mercury(tmp_path, finder=fakemercury.program, backoff=Backoff([30.0]), control_backoff=Backoff([0.05, 0.05]), **of_radio(tmp_path, 2, claims))
    five = Mercury(tmp_path, finder=fakemercury.program, backoff=QUICK, control_backoff=Backoff([0.05, 0.05]), **of_radio(tmp_path, 5, claims))
    two.ports = five.ports = lambda: []
    try:
        await two.start(HF)
        await until_started(lambda: two.running)
        held = two.broadcast_port
        assert two._program._process is not None
        two._program._process.kill()
        await until_started(lambda: two.state == "waiting")                    # (down for the back-off: its pair is free on the machine, and still radio 2's)
        await until_started(lambda: mercuryhelper.pair_free(held))
        await five.start(replace(HF, mercury_sound_card="plughw:2,0", mercury_keying="vox"))
        await until_started(lambda: five.running)
        assert set(pair_ports(held)).isdisjoint(pair_ports(five.broadcast_port)) and Claim("modem_ports", str(held), 2) in claims.all()
    finally:
        await stopped(two)
        await stopped(five)


# ---- the sound card and the keying line

async def test_a_card_or_a_keying_line_the_settings_name_and_another_radio_holds_is_the_modems_problem_with_the_holder(tmp_path: Path) -> None:
    claims = Claims()
    m = Mercury(tmp_path, finder=fakemercury.program, backoff=Backoff([30.0]), control_backoff=Backoff([0.05, 0.05]), **of_radio(tmp_path, 5, claims))
    m.ports = lambda: []
    claims.hold(Claim("sound_card", "plughw:1,0", 2))
    await m.start(HF)
    try:
        assert m.state == "waiting" and m.reason == "not_started" and m.problem == "the sound card plughw:1,0 is held by radio 2" and m.starts == 0 and m.held() == []
    finally:
        await m.stop()
    claims.release(2)
    claims.hold(Claim("serial", port_key("/dev/ttyUSB0"), 1))                      # (the FM radio's port)
    await m.start(HF)
    try:
        assert m.state == "waiting" and m.problem == "the keying line /dev/ttyUSB0 is held by radio 1" and m.starts == 0 and m.held() == [], "neither is held when one is refused"
        assert claims.all() == (Claim("serial", port_key("/dev/ttyUSB0"), 1),)
    finally:
        await stopped(m)


async def test_the_modems_own_choice_of_a_keying_line_leaves_out_a_port_another_radio_holds(tmp_path: Path) -> None:
    claims = Claims()
    m = Mercury(tmp_path, finder=fakemercury.program, backoff=QUICK, control_backoff=Backoff([0.05, 0.05]), **of_radio(tmp_path, 2, claims))
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
        assert m.keying == Keying("rts", "/dev/ttyUSB0") and Claim("keying", port_key("/dev/ttyUSB0"), 2) in claims.all(), "free: chosen, and held as the radio's keying line"
    finally:
        await stopped(m)


async def test_a_card_the_daemon_chose_that_another_radios_modem_took_meanwhile_is_chosen_anew_and_no_problem_is_shown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claims = Claims()
    asked: list[frozenset[str]] = []

    def choose(program: list[str], card: str, keying: str, ports: object, leave: object = (), held_cards: frozenset[str] = frozenset()) -> tuple[str, Keying]:
        asked.append(frozenset(held_cards))
        if len(asked) == 1:
            claims.hold(Claim("sound_card", "plughw:1,0", 5))                     # (radio 5's modem chose the same codec at the same time, and held it first)
        return ("plughw:2,0" if "plughw:1,0" in held_cards else "plughw:1,0"), Keying("vox")

    monkeypatch.setattr(mercurymodem, "choose_setup", choose)
    m = Mercury(tmp_path, finder=fakemercury.program, backoff=Backoff([30.0]), control_backoff=Backoff([0.05, 0.05]), **of_radio(tmp_path, 2, claims))
    m.ports = lambda: []
    states: list[str] = []
    m.changed.connect(lambda: states.append(m.state))
    await m.start(replace(HF, mercury_sound_card="", mercury_keying=""))
    try:
        await until_started(lambda: m.running)
        assert m.sound_card == "plughw:2,0" and asked == [frozenset(), frozenset({"plughw:1,0"})] and "waiting" not in states, "chosen again at once, without the other's card: no problem to show"
        assert Claim("sound_card", "plughw:2,0", 2) in claims.all()
    finally:
        await stopped(m)


def test_the_daemons_own_choice_of_a_card_leaves_out_the_cards_other_radios_run_on(monkeypatch: pytest.MonkeyPatch) -> None:
    cards = [SoundCard("plughw:1,0", "USB Audio CODEC", True, True), SoundCard("plughw:2,0", "USB PnP Sound Device", True, True), SoundCard("plughw:0,0", "HDA Intel PCH", True, True, True)]
    monkeypatch.setattr(mercuryhelper, "list_sound_cards", lambda command, timeout_sec=15.0: cards)
    assert choose_setup(["mercury"], "", "vox", lambda: [])[0] == "plughw:1,0", "two radios' cards: the codec is the radio's"
    assert choose_setup(["mercury"], "", "vox", lambda: [], held_cards={"plughw:1,0"})[0] == "plughw:2,0", "the codec is another radio's: the other card"
    assert choose_setup(["mercury"], "plughw:1,0", "vox", lambda: [], held_cards={"plughw:1,0"})[0] == "plughw:1,0", "a card the settings name is the settings' (the claim refuses it)"
