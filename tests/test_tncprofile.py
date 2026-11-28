"""The TNC profiles (neoaprs/tncprofile.py) and what the Tnc does with each: the table, the entry
written step by step with its pauses, the Kenwood TNC-2 profile, the KISS-only profiles (serial and
TCP: no entry or keep-alive), and the keep-alive of a TNC with a command mode.
"""

import asyncio
import select
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs import ax25, kiss
from neoaprs.direwolf import PROFILE as DIREWOLF, PROFILE_300 as DIREWOLF_300
from neoaprs.radiotypes import BY_KEY as TYPES_BY_KEY, type_of
from neoaprs.source import Backoff, Source
from neoaprs.config import LAST_PORT
from neoaprs.tnc import ENTER_KISS, Tnc
from neoaprs.tncprofile import (
    BY_KEY,
    DEFAULT,
    DUMMY,
    EVERY_BY_KEY,
    KANTRONICS,
    KENWOOD_D710,
    KENWOOD_TNC2,
    KISS,
    KISS_EXIT,
    KISS_TCP,
    MERCURY,
    PROFILES,
    TNC_TEXT,
    Profile,
    names_tcp,
    profile_of,
    tcp_url,
)
from tests.support.env import RADIO_ROWS, Env, first_radios, idle_for, until
from tests.support.fakeradio import FakeRadio
from tests.support.ptyline import Ptys, heard, posix_only
from tests.test_silent import QUICK
from tests.test_tnc import MONITOR_LINE, NUDGE_BYTE, Rigs, hear_until, kiss_of, stops_rigs, tiny_backoff, ui_frame
from tests.test_tnc_pty import make_links


@pytest.fixture
def rig() -> Rigs:
    return Rigs()


# ---- the table


def test_the_table_has_the_profiles_the_page_offers_in_its_order_and_the_default_sends_no_text() -> None:
    assert [p.key for p in PROFILES] == [
        "kenwood-tnc2",
        "kenwood-d710",
        "kantronics",
        "kiss",
        "kiss-tcp",
        "tnc-text",
        "dummy",
    ]
    assert BY_KEY == {p.key: p for p in PROFILES} and len({p.name for p in PROFILES}) == len(PROFILES)
    assert DEFAULT is KISS and DEFAULT.enter == () and not DEFAULT.can_probe and not DEFAULT.detect_command_mode
    assert [p.transport for p in PROFILES] == ["serial", "serial", "serial", "serial", "tcp", "serial", "dummy"]
    assert (
        KISS_TCP.baud is None
        and DUMMY.baud is None
        and MERCURY.baud is None
        and all(p.baud == 9600 for p in PROFILES if p.transport == "serial")
    )
    assert all(type_of(p.key).limits.max_frame is None for p in PROFILES), "no FM type cuts a packet"
    assert (
        MERCURY not in PROFILES
        and MERCURY.transport == "modem"
        and type_of(MERCURY.key).limits.max_frame == 123
        and type_of(MERCURY.key).kind == "hf"
    ), "the Mercury profile is the Mercury radio's one profile, not a type of the FM radio"


def test_every_profile_is_named_by_its_types_key_so_a_line_of_it_knows_its_kind_and_its_limits() -> None:
    profiles = {**EVERY_BY_KEY, DIREWOLF.key: DIREWOLF, DIREWOLF_300.key: DIREWOLF_300}
    assert set(profiles) == set(TYPES_BY_KEY), (
        "one type for each profile, by the same key (the Sound card types' are Direwolf's, neoaprs/direwolf.py)"
    )
    for p in profiles.values():
        # Tnc.rtype: a profile whose key named no type would raise at the line's first read of its
        # kind or its frame cap
        t = type_of(p.key)
        tnc = Tnc("", profile=p)
        assert (
            tnc.rtype is t
            and t.profile == p.key
            and tnc.max_frame == t.limits.max_frame
            and tnc.label == ("hf radio" if t.kind == "hf" else "tnc")
        ), p.key
        assert tnc.rtype.limits.too_long(b"x" * 100, b"x" * 100) is None, (
            f"{p.key}: a frame of 100 bytes fits every radio"
        )
    lora = type_of("lora-tcp").limits
    assert (
        lora.too_long(b"x" * 251, b""),
        lora.too_long(b"x" * 200, b"x" * 253),
        lora.too_long(b"\xc0" * 130, b""),
    ) == (
        "251 bytes, the radio carries 250",
        "253 bytes of text, the radio carries 252",
        "263 bytes in KISS, the radio takes 256",
    ), "a LoRa radio keeps its type's limits"
    assert (
        type_of("mercury").limits.too_long(b"x" * 124, b"") == "124 bytes, the radio carries 123"
        and type_of("kiss").limits.too_long(b"x" * 400, b"x" * 400) is None
    )


def test_the_kenwood_tnc2_profile_is_what_the_tnc_always_did() -> None:
    assert KENWOOD_TNC2.enter == ((b"\rKISS ON\rRESTART\r", 3.0),) and ENTER_KISS == b"\rKISS ON\rRESTART\r"
    assert (
        KENWOOD_TNC2.exit_kiss == KISS_EXIT == b"\xc0\xff\xc0"
        and KENWOOD_TNC2.can_probe
        and KENWOOD_TNC2.detect_command_mode
        and KENWOOD_TNC2.settle_sec == 3.0
    )


def test_the_other_command_mode_profiles_have_the_sequences_of_their_sources() -> None:
    assert KENWOOD_D710.enter == (
        (b"TC 1\r", 1.0),
        (b"TN 2,0\r", 3.0),
        (b"HBAUD 1200\r", 1.0),
        (b"KISS ON\r", 1.0),
        (b"RESTART\r", 1.0),
    )
    assert KANTRONICS.enter == ((b"\rINTFACE KISS\rRESET\r", 3.0),)
    for profile in (KENWOOD_D710, KANTRONICS):
        assert profile.exit_kiss == KISS_EXIT and profile.can_probe and profile.detect_command_mode
    assert "tmd710_tncsetup" in KENWOOD_D710.note and "not documented" in KENWOOD_D710.note


def test_a_profile_that_sends_nothing_has_nothing_to_send() -> None:
    for profile in (KISS, KISS_TCP):
        assert (
            profile.enter == ()
            and profile.exit_kiss is None
            and not profile.can_probe
            and not profile.detect_command_mode
            and profile.settle_sec == 0.0
        )


def test_a_profile_that_contradicts_itself_is_refused() -> None:
    with pytest.raises(ValueError, match="how to enter and leave KISS"):
        replace(KENWOOD_TNC2, enter=())
    with pytest.raises(ValueError, match="how to enter and leave KISS"):
        replace(KENWOOD_TNC2, exit_kiss=None)
    with pytest.raises(ValueError, match="cannot be left"):
        replace(KISS, detect_command_mode=True)
    with pytest.raises(ValueError, match="nothing but KISS frames"):
        replace(KENWOOD_TNC2, transport="tcp")


def test_a_profile_that_reads_text_writes_nothing_to_its_line_and_one_that_would_is_refused() -> None:
    assert (
        TNC_TEXT.framing,
        TNC_TEXT.enter,
        TNC_TEXT.exit_kiss,
        TNC_TEXT.can_probe,
        TNC_TEXT.detect_command_mode,
        TNC_TEXT.transport,
        TNC_TEXT.baud,
    ) == ("text", (), None, False, False, "serial", 9600)
    assert all(p.framing == "kiss" for p in PROFILES if p is not TNC_TEXT), "every other profile speaks KISS"
    for wrong in (
        {"enter": ((b"MALL OFF\r", 1.0),)},
        {"exit_kiss": KISS_EXIT},
        {"can_probe": True, "enter": KENWOOD_TNC2.enter, "exit_kiss": KISS_EXIT},
        {"detect_command_mode": True, "enter": KENWOOD_TNC2.enter},
    ):
        with pytest.raises(ValueError, match="writes nothing to its line"):
            replace(TNC_TEXT, **wrong)  # type: ignore[arg-type]


def test_a_key_names_its_profile_and_a_wrong_one_names_the_keys() -> None:
    assert profile_of("kenwood-d710") is KENWOOD_D710 and profile_of(" kiss ") is KISS
    with pytest.raises(ValueError, match="kenwood-tnc2, kenwood-d710, kantronics, kiss, kiss-tcp, tnc-text, dummy"):
        profile_of("th-d7")


def test_a_tcp_address_is_told_from_a_device() -> None:
    assert (
        names_tcp("socket://127.0.0.1:8001")
        and names_tcp("TCP://pi:8100")
        and not names_tcp("/dev/ttyUSB0")
        and not names_tcp("COM3")
        and not names_tcp("")
    )
    assert (
        tcp_url("127.0.0.1", 8001) == "socket://127.0.0.1:8001"
        and tcp_url("::1", 8100) == "socket://[::1]:8100"
        and tcp_url("[::1]", 8100) == "socket://[::1]:8100"
    )


# ---- the entry, step by step


async def arrivals(radio: FakeRadio, count: int, timeout_sec: float = 3.0) -> list[tuple[bytes, float]]:
    """The next `count` things the Tnc wrote to the radio, each with the seconds since the one
    before (they are far enough apart to arrive one at a time)."""
    loop = asyncio.get_running_loop()
    out: list[tuple[bytes, float]] = []
    last = loop.time()
    while len(out) < count:
        data = await radio.said(1, timeout_sec)
        assert data, f"only {len(out)} of {count} steps came: {out}"
        out.append((data, loop.time() - last))
        last = loop.time()
    return out


@stops_rigs
async def test_the_d710_sequence_is_written_in_order_with_its_pauses_and_nothing_is_typed_in_until_it_has_settled(
    rig: Rigs,
) -> None:
    r = await rig(profile=KENWOOD_D710, pace=0.2, settle_sec=0.3)
    r.radio.feed(MONITOR_LINE)
    steps = await arrivals(r.radio, 5)
    assert [data for data, _ in steps] == [data for data, _ in KENWOOD_D710.enter]
    for (_, gap), (_, pause) in zip(steps[1:], KENWOOD_D710.enter):
        assert gap >= pause * 0.2 * 0.8, "each step waits for the pause of the one before"
    assert r.tnc.usable is False and r.tnc.send_frame(ui_frame()) is False, "the settle time is after the last step"
    await until(lambda: r.tnc.usable)
    assert r.tnc.send_frame(ui_frame()) and (await r.radio.said(5))[:1] == b"\xc0"


@stops_rigs
async def test_what_the_tnc_says_while_the_sequence_runs_is_thrown_away_and_it_is_entered_once(rig: Rigs) -> None:
    r = await rig(profile=KENWOOD_D710, pace=0.05, settle_sec=0.2)
    r.radio.feed(MONITOR_LINE)
    first = await arrivals(r.radio, 1)
    # An answer to the first step, in the middle of the sequence
    r.radio.feed(b"cmd:TC 1\r\nOH2AAA>APRS:text\r\n")
    rest = await arrivals(r.radio, 4)
    assert [data for data, _ in first + rest] == [data for data, _ in KENWOOD_D710.enter], (
        "the answer does not start another entry"
    )
    r.radio.feed(kiss_of(ui_frame("OH2XXX")))  # inside the settle time
    await idle_for(0.4)
    r.radio.feed(kiss_of(ui_frame("OH2BBB")))
    await until(lambda: r.packets)
    assert [p.source for p in r.packets] == ["OH2BBB"] and r.tnc.problem == "" and await r.radio.said(1, 0.3) == b""


@stops_rigs
async def test_the_kantronics_profile_enters_kiss_with_its_own_words(rig: Rigs) -> None:
    r = await rig(profile=KANTRONICS)
    r.radio.feed(b"cmd:")
    assert await r.radio.said(len(KANTRONICS.enter[0][0])) == b"\rINTFACE KISS\rRESET\r"
    assert await r.radio.said(1, 0.3) == b""


@stops_rigs
async def test_the_tnc2_profile_writes_its_one_step_at_once_and_settles_for_settle_sec(rig: Rigs) -> None:
    r = await rig(profile=KENWOOD_TNC2, settle_sec=0.4)
    r.radio.feed(MONITOR_LINE)
    assert await r.radio.said(len(ENTER_KISS)) == ENTER_KISS
    assert r.tnc.usable is False
    await until(lambda: r.tnc.usable)
    assert r.tnc.usable is True


# ---- the keep-alive of a profile with several steps


@stops_rigs
async def test_the_check_of_the_d710_leaves_kiss_asks_and_enters_again_with_the_whole_sequence(rig: Rigs) -> None:
    r = await rig(profile=KENWOOD_D710, pace=0.02, settle_sec=0.05, **QUICK)
    whole = KISS_EXIT + NUDGE_BYTE + b"".join(data for data, _ in KENWOOD_D710.enter)
    assert await hear_until(r.radio, whole, 5.0) == whole, "exit, the carriage return, then every step, in this order"
    assert (r.tnc.stats.keepalive_checks, r.tnc.last_watchdog_action) == (1, "check")


# ---- a profile that is sent nothing


async def quiet_for(radio: FakeRadio, seconds: float) -> bytes:
    await idle_for(seconds)
    return await radio.said(1, 0.05)


@pytest.mark.parametrize("profile", [KISS, KISS_TCP], ids=["kiss", "kiss-tcp"])
@stops_rigs
async def test_a_kiss_profile_sends_nothing_ever_not_for_text_not_for_silence_not_for_a_check(
    rig: Rigs, profile: Profile
) -> None:
    r = await rig(profile=profile, **QUICK)
    assert await quiet_for(r.radio, 0.6) == b"", "no keep-alive check and no carriage return after silence"
    assert r.tnc.state is Source.State.CONNECTED and r.tnc.stats.keepalive_checks == 0 and r.tnc._watchdog_task is None
    # The device is in command mode: that is said, not answered
    r.radio.feed(MONITOR_LINE + b"\r\ncmd:")
    await until(lambda: r.tnc.problem)
    assert "command mode" in r.tnc.problem and profile.name in r.tnc.problem
    assert await quiet_for(r.radio, 0.4) == b"", "no entry"
    assert r.tnc.state is Source.State.CONNECTED and r.tnc.silent_since is None and r.tnc.stats.bytes_out == 0


@pytest.mark.parametrize("profile", [KISS, KISS_TCP], ids=["kiss", "kiss-tcp"])
@stops_rigs
async def test_a_kiss_profile_reads_frames_and_writes_only_frames(rig: Rigs, profile: Profile) -> None:
    r = await rig(profile=profile)
    r.radio.feed(kiss_of(ui_frame("OH2CCC")))
    await until(lambda: r.packets)
    assert r.packets[0].source == "OH2CCC" and r.tnc.usable
    assert r.tnc.send_frame(ui_frame())
    assert await r.radio.said(1) == kiss.encode(ax25.encode(ui_frame()))
    assert await quiet_for(r.radio, 0.3) == b""


@stops_rigs
async def test_a_kiss_tnc_that_is_quiet_for_a_long_time_stays_connected_and_is_never_silent(rig: Rigs) -> None:
    r = await rig(profile=KISS_TCP, **QUICK)
    await idle_for(1.0)
    assert r.tnc.state is Source.State.CONNECTED and r.tnc.stats.watchdog_probes == 0 and r.tnc.silent_since is None
    assert r.tnc.describe() == f"{r.tnc.path}, listening, 0 packets"


# ---- the search


@posix_only
async def test_the_search_for_a_kiss_tnc_listens_and_writes_nothing_where_a_tnc2_is_nudged(
    ptys: Ptys, tmp_path: Path
) -> None:
    (master,), pattern = await make_links(tmp_path, ptys, 1)
    kiss_tnc = Tnc(pattern=pattern, profile=KISS, probe_seconds=0.3, probe_nudge_sec=0.05, backoff=Backoff([30.0]))
    try:
        await kiss_tnc.start()
        assert kiss_tnc.state is Source.State.WAITING and not select.select([master], [], [], 0)[0], (
            "the ports are listened to and nothing is written to them"
        )
    finally:
        await kiss_tnc.stop()
    tnc2 = Tnc(pattern=pattern, profile=KENWOOD_TNC2, probe_seconds=0.3, probe_nudge_sec=0.05, backoff=tiny_backoff())
    try:
        await tnc2.start()
        assert await asyncio.to_thread(heard, master, 1, 1.0) == b"\r"
    finally:
        await tnc2.stop()


# ---- the settings


async def seeded(tmp_path: Path, rows: dict[str, str], radio: FakeRadio) -> Env:
    """The daemon on a data folder that has these settings (radio 1's in the words of the Env:
    tests/support/env.py RADIO_ROWS), with no port given for the run."""
    e = Env(tmp_path, radio=False, operator=False)
    await e.ctl.open_database()
    await e.ctl.store.put_settings(
        {LAST_PORT if key == "serial/last_port" else key: value for key, value in rows.items() if key not in RADIO_ROWS}
    )
    for position, (kind, type, on, own) in enumerate(first_radios(rows, False), 1):
        assert await e.ctl.store.add_radio(kind, type, "", on, position, settings=own) == position
    await e.start(connected=False)
    return e


async def test_kiss_over_tcp_connects_to_the_host_and_port_of_the_settings(tmp_path: Path) -> None:
    radio = FakeRadio()
    await radio.start()
    e = await seeded(
        tmp_path,
        {
            "tnc/profile": "kiss-tcp",
            "tcp/host": "127.0.0.1",
            "tcp/port": str(radio.port),
            "serial/last_port": "/dev/ttyUSB9",
        },
        radio,
    )
    try:
        await until(lambda: e.tnc.state is Source.State.CONNECTED)
        await radio.connected()
        assert (
            e.tnc.path == f"socket://127.0.0.1:{radio.port}" and not e.tnc.fallback_probe and e.tnc.profile is KISS_TCP
        )
        radio.feed(MONITOR_LINE)
        radio.feed(kiss_of(ui_frame("OH2DDD")))
        await until(lambda: e.tnc.stats.packets == 1)
        assert await radio.said(1, 0.5) == b"", "nothing is said to a TCP KISS server but KISS frames"
        assert e.ctl.config.serial_last_port == "/dev/ttyUSB9", "the port that is not used is not replaced"
    finally:
        await e.stop()
        await radio.aclose()


async def test_a_fresh_install_on_a_socket_is_sent_nothing_for_text(tmp_path: Path) -> None:
    radio = FakeRadio()
    await radio.start()
    e = await seeded(tmp_path, {"serial/port": radio.url}, radio)
    try:
        await until(lambda: e.tnc.state is Source.State.CONNECTED)
        await radio.connected()
        assert e.tnc.profile is KISS
        radio.feed(MONITOR_LINE)
        await until(lambda: e.tnc.problem)
        assert await radio.said(1, 0.5) == b""
    finally:
        await e.stop()
        await radio.aclose()
