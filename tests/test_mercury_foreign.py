"""A Mercury that is not ours on the modem's ports, and one of ours that cannot key the radio: what a
Windows station's log showed (another program held COM10 and listened on 8100 and 8300; every start
of ours said `Cannot open COM10 (Windows error 5)` and then hung). The modem part never talks to the
other program, ends its own hung run at once and tries again for as long as the radio is on.
"""

import logging
import socket
import sys
from pathlib import Path

import pytest

from neoaprs import mercury, mercuryhelper, mercurymodem
from neoaprs.mercury import CONTROL_OFFSET, keying_failure
from neoaprs.claims import Claims
from neoaprs.clock import utcnow
from neoaprs.config import DEFAULTS
from neoaprs.mercurydriver import MercuryDriver
from neoaprs.mercurymodem import Mercury
from neoaprs.mercuryclaims import radio_folder
from neoaprs.radiodriver import RunOverrides
from neoaprs.radiospec import RadioSpec
from neoaprs.tncprofile import MERCURY_OWN
from tests.support.faketnc import UI
from neoaprs.cli.supportsummary import _mercury
from neoaprs.mercuryruns import PORTS_TAKEN, StartEnd
from neoaprs.tnc import Tnc
from neoaprs.web.supportstate import mercury_state
from neoaprs.radiotype import HF_ID
from neoaprs.source import Backoff, Source
from tests.support import fakemercury
from tests.support.clock import FixedClock
from tests.support.env import Env, until_started
from tests.support.fakemercury import Air, of_radio
from tests.support.modemports import own_ports
from tests.test_mercury_modem import HF, _alive, stopped

ROOT = Path(__file__).resolve().parent.parent
QUICK = Backoff([0.2, 0.2])
SOURCE = ROOT / "build" / "mercury" / "work" / f"mercury-{mercury.SOURCE_COMMIT}"


@pytest.fixture(autouse=True)
def _ports_of_this_test(monkeypatch: pytest.MonkeyPatch) -> None:
    own_ports(monkeypatch)


def modem(tmp_path: Path, keying_fails: str = "") -> Mercury:
    m = Mercury(
        tmp_path,
        finder=lambda: fakemercury.program(keying_fails=keying_fails),
        backoff=QUICK,
        control_backoff=Backoff([0.05, 0.05]),
        **of_radio(tmp_path),
    )
    m.ports = lambda: []
    return m


# ---- the lines


def test_the_lines_of_a_keying_that_cannot_be_set_up_are_mercurys_own_and_say_which_problem_it_is() -> None:
    assert keying_failure(
        "2026-11-28 05:47:54.123 [+0.066s] [ERR] [serial-ptt] Cannot open COM10 (Windows error 5)"
    ) == ("keying_in_use")
    assert keying_failure("[ERR] [serial-ptt] Cannot open COM3 (Windows error 2)") == "keying_missing"
    assert keying_failure("[ERR] [serial-ptt] Cannot open COM3 (Windows error 1450)") == "keying"
    assert keying_failure("[ERR] [serial-ptt] Cannot open /dev/ttyUSB0: Device or resource busy") == "keying_in_use"
    assert keying_failure("[ERR] [serial-ptt] Cannot open /dev/ttyUSB9: No such file or directory") == "keying_missing"
    assert keying_failure("[ERR] [serial-ptt] Cannot open /dev/ttyUSB0: Permission denied") == "keying"
    assert keying_failure("[ERR] [engine] Radio init failed: the engine is exiting") == "keying"
    assert keying_failure("[ERR] [serial-ptt] GetCommState(COM3) failed (Windows error 5)") == ""
    assert keying_failure("mercury_engine: radio init failed") == "", "the unstamped line comes before the one read"


async def test_the_counts_of_stalls_are_kept_across_starts_and_the_support_file_says_how_each_start_ended(
    tmp_path: Path,
) -> None:
    """The station's summary said "Hears nothing: 0 times" after 22 stalls: each off and on made a new count."""
    m = modem(tmp_path)
    m.stall.stalls, m.stall.restarts = 22, 3
    for _ in range(2):
        await m.start(HF)
        await until_started(lambda: m.state == "running")
    await stopped(m)
    assert (m.stall.stalls, m.stall.restarts) == (22, 3)
    assert [start.words() for start in m.start_log] == ["running", "running"]
    m.start_log.append(StartEnd(m.start_log[-1].at, ended="keying_in_use"))
    rows = dict(_mercury(mercury_state(m, Tnc())))
    assert rows["Hears nothing"].startswith("22 times") and rows["Restarted for it"].startswith("3 times")
    said = [value for key, value in _mercury(mercury_state(m, Tnc())) if key == "Mercury started"]
    assert len(said) == 3 and said[-1].endswith(": failed: keying_in_use")


def test_the_lines_are_the_ones_the_pinned_mercury_writes() -> None:
    if not SOURCE.is_dir():
        pytest.skip("the pinned Mercury's source is not unpacked here (scripts/build-mercury)")
    serial = (SOURCE / "radio_io" / "serial_ptt.c").read_text(encoding="utf-8")
    engine = (SOURCE / "common" / "mercury_engine.c").read_text(encoding="utf-8")
    assert '#define PTT_LOG_TAG "serial-ptt"' in serial
    assert 'HLOGE(PTT_LOG_TAG, "Cannot open %s (Windows error %lu)",' in serial, mercury.KEYING_OPEN_WINDOWS
    assert 'HLOGE(PTT_LOG_TAG, "Cannot open %s: %s", g_cfg.device, strerror(errno));' in serial, (
        mercury.KEYING_OPEN_POSIX
    )
    tag, text = mercury.RADIO_INIT_FAILED.removeprefix("[ERR] [").split("] ", 1)
    assert f'HLOGE("{tag}", "{text}");' in engine


# ---- our own Mercury cannot key the radio


@pytest.mark.parametrize(
    ("said", "reason"), [("COM10 (Windows error 5)", "keying_in_use"), ("COM3 (Windows error 2)", "keying_missing")]
)
async def test_a_keying_port_that_cannot_be_opened_ends_the_hung_run_at_once_and_is_tried_again_while_the_radio_is_on(
    tmp_path: Path, said: str, reason: str
) -> None:
    m = modem(tmp_path, keying_fails=said)
    await m.start(HF)
    try:
        await until_started(lambda: m.reason == reason)
        first = m.start_log[0]
        assert m.state == "waiting" and first.ended == reason and not first.ran
        await until_started(lambda: m.starts >= 3)
        assert m.stall.stalls == m.stall.restarts == 0 and not m.stall.given_up, (
            "no stall and no restart of the stall: it is tried again for as long as the radio is on"
        )
        assert [s.words() for s in m.start_log][:2] == [f"failed: {reason}"] * 2
    finally:
        await stopped(m)


async def test_the_hung_run_is_ended_and_a_full_capture_buffer_after_it_is_no_stall(tmp_path: Path) -> None:
    m = modem(tmp_path, keying_fails="COM10 (Windows error 5)")
    m.backoff = Backoff([30.0])  # (one run is watched)
    await m.start(HF)
    try:
        await until_started(lambda: m.reason == "keying_in_use")
        pid = m.pid
        await until_started(lambda: not _alive(pid))
        for s in range(400):  # the ring Mercury filled in 384 s, said once a second
            m._capture_full(float(s))
        assert m.stall.stalls == 0 and not m.deaf, "a Mercury that said Radio init failed never hears nothing"
    finally:
        await stopped(m)


# ---- another program on the modem's ports


class Foreign:
    """Another program on a pair: a KISS port and a control port 200 above, each counting what it got."""

    def __init__(self) -> None:
        self.air = Air()
        self.station = self.air.station()

    @property
    def port(self) -> int:
        return self.station.port

    async def __aenter__(self) -> "Foreign":
        await self.air.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.air.aclose()


async def test_another_program_on_mercurys_own_ports_is_never_started_over_and_never_connected_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async with Foreign() as other:
        monkeypatch.setattr(mercuryhelper, "OWN_PAIR", other.port)
        monkeypatch.setattr(
            mercurymodem, "free_ports", lambda first=0, tries=50: mercuryhelper.free_ports(other.port, tries)
        )
        m = modem(tmp_path)
        await m.start(HF)
        try:
            with caplog.at_level(logging.WARNING, "neoaprs.mercury"):
                await until_started(lambda: m.reason == "ports_taken")
            assert m.problem == PORTS_TAKEN and m.starts == 0 and m.pid is None
            assert f"{other.port} on 127.0.0.1" in caplog.text, "the log says where"
            assert m.frame_hold() and m.refuses_line(), "the radio takes no frame"
            assert other.station.connections == other.station.control_connections == 0
        finally:
            await stopped(m)
    await m.start(HF)  # gone: the radio's own pair is its again
    try:
        await until_started(lambda: m.state == "running" and m.broadcast_port == other.port)
        assert m.frame_hold() == "" and m.refuses_line() == ""
    finally:
        await stopped(m)


async def test_a_control_line_that_would_reach_another_program_is_not_opened_and_our_run_is_ended(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Windows station: the probe saw the other program's pair as free, ours started on it, hung."""
    async with Foreign() as other:
        pair = (other.port, other.port + CONTROL_OFFSET)
        monkeypatch.setattr(mercurymodem, "free_ports", lambda first=0, tries=50: pair)
        m = Mercury(
            tmp_path,
            finder=lambda: [sys.executable, "-c", "import time; time.sleep(600)"],  # listens on nothing
            backoff=Backoff([30.0]),
            control_backoff=Backoff([0.05, 0.05]),
            folder=radio_folder(tmp_path, HF_ID),  # (no table of claims: the pair is the probe's alone)
        )
        m.ports = lambda: []
        await m.start(HF)
        try:
            await until_started(lambda: m.reason == "ports_taken")
            pid = m.pid
            await until_started(lambda: not _alive(pid))
            assert other.station.control_connections == 0 and other.station.connections == 0
            assert m.start_log[-1].words() == "failed: ports_taken"
        finally:
            await stopped(m)


async def test_a_listener_of_our_own_run_is_ours_and_one_beside_it_on_every_address_is_not(tmp_path: Path) -> None:
    if sys.platform == "darwin":
        pytest.skip("macOS has no table of listeners to read")
    m = modem(tmp_path)
    await m.start(HF)
    try:
        await until_started(lambda: m.state == "running")
        assert m.others_on_ports() == [] and m.refuses_line() == ""
        with socket.socket(socket.AF_INET6 if socket.has_ipv6 else socket.AF_INET) as other:
            if other.family == socket.AF_INET6:
                other.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            try:
                other.bind(("::" if other.family == socket.AF_INET6 else "0.0.0.0", m.broadcast_port))
            except OSError:
                pytest.skip("this system does not let a second socket listen beside the modem's")
            other.listen()
            assert [f.port for f in m.others_on_ports()] == [m.broadcast_port]
            assert m.refuses_line()
    finally:
        await stopped(m)


# ---- the station of the log, through the daemon

HOUR_OF_BEACONS = 60  # one a minute


async def test_another_mercury_on_the_ports_gets_not_one_byte_in_an_hour_of_beacons_while_ours_cannot_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The probe saw the other program's pair as free (Windows read no table), ours started on it and
    said `Cannot open COM10 (Windows error 5)`. Every frame the station makes on the HF radio, beacons
    an hour long and a message, stays home; the radio says why and is not shown connected."""
    async with Foreign() as other:
        monkeypatch.setattr(mercurymodem, "free_ports", lambda first=0, tries=50: (other.port, other.port + 200))
        monkeypatch.setattr(mercurymodem, "next_modem_ports", lambda claims, holder, first=0, **_: first)
        clock = FixedClock()
        e = Env(
            tmp_path,
            clock=clock,
            settings={"hf/enabled": "true", "mercury/keying": "rts:COM10", "mercury/sound_card": "plughw:1,0"},
        )
        e.mercury._finder = lambda: fakemercury.program(keying_fails="COM10 (Windows error 5)")
        e.mercury.backoff = Backoff([0.2, 0.2])
        e.mercury._control_backoff = Backoff([0.05, 0.05])
        e.hf.backoff = Backoff([0.05, 0.1])
        await e.start(connected=False)
        try:
            await until_started(lambda: e.mercury.starts >= 2 and e.mercury.reason in ("keying_in_use", "ports_taken"))
            for _ in range(HOUR_OF_BEACONS):
                clock.advance(60.0)
                assert not e.beacon_2.send_now("interval")
            assert e.beacon_2.problem
            await e.ctl.messaging.send("OH2XYZ", "over HF while the modem cannot key")
            await until_started(lambda: e.mercury.starts >= 4)
            assert other.station.connections == 0 and other.station.control_connections == 0
            assert await other.station.said(1, 0.2) == b"" and other.station.frames_in == []
            assert e.hf.state is not Source.State.CONNECTED and e.hf.stats.bytes_out == 0
            assert e.mercury.stall.stalls == 0
        finally:
            await e.stop()


# ---- the operator's own Mercury


async def test_your_own_mercury_is_reached_at_its_address_starts_no_modem_and_its_line_follows_its_control_port(
    tmp_path: Path,
) -> None:
    air = Air()
    station = air.station()
    await air.start()
    spec = RadioSpec(
        2, "hf", MERCURY_OWN.key, "", True, 2, settings={"tcp_host": "127.0.0.1", "tcp_port": str(station.port)}
    )
    driver = MercuryDriver(spec, Claims(), radio_folder(tmp_path, 2), utcnow)
    driver.modem._finder = lambda: pytest.fail("no Mercury is started for the operator's own")  # type: ignore[assignment]
    driver.modem.changed.connect(driver.line.modem_changed)  # (wiring.py ties them)
    driver.line.backoff = Backoff([0.05, 0.1])
    driver.configure(spec, DEFAULTS, RunOverrides())
    try:
        await driver.start()
        await until_started(lambda: driver.modem.running and driver.line.usable)
        assert driver.line.port == station.url and driver.modem.starts == 0 and driver._own_card() == ""
        assert driver.line.send_frame(UI) and await station.said(1, 5.0)
        assert driver.line.rtype.limits.max_frame == mercury.MAX_PAYLOAD, "the frame limit of a Mercury radio"
        station.drop_control()  # its control port goes: the radio takes no frame and its line closes
        await until_started(lambda: driver.line.state is not Source.State.CONNECTED)
        assert not driver.line.send_frame(UI) and await station.said(1, 0.2) == b""
        await until_started(lambda: driver.modem.running and driver.line.usable)
        await driver.modem._end_for_good("hears nothing", "receive_stalled")
        await until_started(lambda: driver.line.state is not Source.State.CONNECTED)
        assert not driver.line.send_frame(UI) and await station.said(1, 0.2) == b"", "given up: the line is closed too"
    finally:
        await driver.stop()
        await air.aclose()
