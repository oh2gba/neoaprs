"""A Mercury that hears nothing: its capture buffer full for hours (a Windows station's report,
`[WRN] [audio-cap] Buffer full in capture buffer!` a hundred times a second), the log thinned by
powers of ten, the modem restarted, then given up on with a problem the page shows.
"""

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from neoaprs import childprogram, mercuryhelper, mercurymodem, mercurystall
from neoaprs.claims import Claims
from neoaprs.mercurychannel import KEYED_MAX_SEC
from neoaprs.mercury import CAPTURE_FULL, SOURCE_COMMIT, capture_full
from neoaprs.mercurymodem import RECEIVE_STALLED
from neoaprs.mercurystall import GAP_SEC, RESTART_EVERY_SEC, STALL_SEC, StallWatch
from neoaprs.source import Source
from neoaprs.tnc import Tnc
from neoaprs.tncprofile import MERCURY
from neoaprs.web.radioview import radio_row
from tests.support.env import until_started
from tests.support.modemports import own_ports
from tests.test_mercury_modem import HF, modem, stopped
from tests.test_radio_health import HF as HF_SPEC
from tests.test_radio_health import at_work

ROOT = Path(__file__).resolve().parent.parent
REPORTED = "2026-11-26 06:26:18.361 [+384.378s] [WRN] [audio-cap] Buffer full in capture buffer!"
T0 = datetime(2026, 11, 26, 6, 26, 18, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _ports_of_this_test(monkeypatch: pytest.MonkeyPatch) -> None:
    own_ports(monkeypatch)


def test_the_line_mercury_writes_is_the_one_constant_and_comes_from_its_audioio_c() -> None:
    assert capture_full(REPORTED) and not capture_full("[WRN] [audio-play] playback took no audio for 1016 ms")
    source = ROOT / "build" / "mercury" / "work" / f"mercury-{SOURCE_COMMIT}" / "audioio" / "audioio.c"
    if not source.is_file():
        pytest.skip("the pinned Mercury's source is not unpacked here (scripts/build-mercury)")
    tag, text = CAPTURE_FULL.removeprefix("[WRN] [").split("] ", 1)
    assert f'HLOGW("{tag}", "{text}");' in source.read_text(encoding="utf-8")


# ---- the log


class Clocked(mercuryhelper.Program):
    pass


def test_a_repeated_warning_is_logged_the_1st_10th_100th_1000th_time_and_once_when_it_stops(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, "neoaprs.mercury.program")
    now = [1000.0]
    monkeypatch.setattr(childprogram.time, "monotonic", lambda: now[0])
    program = Clocked(lambda code, lines: None)
    program.clock = lambda: T0 + timedelta(seconds=now[0] - 1000.0)
    for n in range(2500):
        now[0] += 0.01
        program._tell(
            f"2026-11-26 06:26:{n % 60:02d}.{n % 1000:03d} [+{n}.000s] [WRN] [audio-cap] Buffer full in capture buffer!"
        )
    info = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert [line.rsplit("!", 1)[1] for line in info] == [
        "",
        " (the 10th time)",
        " (the 100th time)",
        " (the 1000th time)",
    ]
    now[0] += childprogram.QUIET_SEC + 1
    program._tell("[INF] [engine] something else")
    last = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO][-1]
    assert last == "[WRN] [audio-cap] Buffer full in capture buffer!: came 2500 times, the last at 2026-11-26 06:26:43Z"


def test_a_warning_said_once_gets_no_closing_line_and_the_end_of_the_run_closes_the_others(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, "neoaprs.mercury.program")
    program = mercuryhelper.Program(lambda code, lines: None)
    program._tell("[WRN] [audio] once")
    program._tell("[WRN] [audio] twice")
    program._tell("[WRN] [audio] twice")
    program._stopped_warnings(None)
    said = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert said[:2] == ["[WRN] [audio] once", "[WRN] [audio] twice"] and len(said) == 3
    assert said[2].startswith("[WRN] [audio] twice: came 2 times, the last at ")


# ---- when a run of the warning is a stall


def test_a_short_burst_is_no_stall_and_thirty_seconds_without_a_gap_is_one() -> None:
    watch = StallWatch()
    t = 0.0
    while t < STALL_SEC - 1:
        assert not watch.seen(t, T0)
        t += 1.0
    t += GAP_SEC + 1  # it stopped for a moment: a new run
    assert not watch.seen(t, T0)
    start = t
    stalls = []
    while t < start + STALL_SEC + 5:
        stalls.append(watch.seen(t, T0))
        t += 1.0
    assert stalls.count(True) == 1 and watch.stalls == 1 and watch.last_stall_at == T0


def test_a_stall_restarts_never_while_busy_at_most_every_ten_minutes_and_three_in_an_hour_gives_up() -> None:
    watch = StallWatch()

    def stall_at(t: float) -> None:
        for s in range(int(STALL_SEC) + 1):
            watch.seen(t + s, T0)
        assert watch.stalled

    stall_at(0.0)
    assert watch.action(STALL_SEC, busy=True) == "", "never while it is keyed or a test is on"
    assert watch.action(STALL_SEC, busy=False) == "restart"
    watch.restarted(STALL_SEC, T0)
    stall_at(100.0)
    assert watch.action(140.0, busy=False) == "", "not again within ten minutes"
    assert watch.action(STALL_SEC + RESTART_EVERY_SEC, busy=False) == "restart"
    watch.restarted(STALL_SEC + RESTART_EVERY_SEC, T0)
    stall_at(1300.0)
    watch.restarted(1340.0, T0)
    stall_at(2000.0)
    assert watch.action(2040.0, busy=False) == "give_up" and watch.restarts == 3
    assert watch.action(2041.0, busy=False) == "", "given up once"


# ---- the modem


async def test_a_stalled_mercury_is_started_again_and_after_three_restarts_in_an_hour_ended_with_a_problem(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    m = modem(tmp_path)
    await m.start(HF)
    try:
        await until_started(lambda: m.state == "running" and m.pid is not None)
        with caplog.at_level(logging.WARNING, "neoaprs.mercury"):
            t = 0.0
            for _ in range(3):
                first = m.starts
                for s in range(int(STALL_SEC) + 1):
                    m._capture_full(t + s)
                await until_started(lambda first=first: m.starts > first and m.state == "running")  # type: ignore[misc]
                t += RESTART_EVERY_SEC + 60
            assert m.stall.restarts == 3 and m.stall.stalls == 3
            for s in range(int(STALL_SEC) + 1):
                m._capture_full(t + s)
            await until_started(lambda: m.reason == "receive_stalled")
        assert m.state == "waiting" and m.problem == RECEIVE_STALLED and not m.running
        said = [r.getMessage() for r in caplog.records]
        assert (
            said.count(
                f"Mercury hears nothing: its capture buffer has been full for {STALL_SEC:g} s (its receive side stalled)"
            )
            == 4
        )
        assert [line for line in said if "is started again because" in line] == [
            f"Mercury is started again because it hears nothing (restart {n})" for n in (1, 2, 3)
        ]
    finally:
        await stopped(m)


async def test_warnings_while_keyed_or_testing_count_for_nothing_and_a_run_starts_afresh_after(tmp_path: Path) -> None:
    m = modem(tmp_path)
    await m.start(HF)
    try:
        await until_started(lambda: m.state == "running")
        starts = m.starts
        for s in range(10):
            m._capture_full(float(s))
        m._on_ptt(True, 10.0)
        for s in range(10, 20):
            m._capture_full(float(s))
        m._on_ptt(False, 20.0)
        m.test = "tune"
        for s in range(20, 200):
            m._capture_full(float(s))
        m.test = ""
        for s in range(201, 201 + int(STALL_SEC) - 1):
            m._capture_full(float(s))
        assert m.stall.stalls == 0 and m.starts == starts, "no stall right after the radio unkeys"
        m._capture_full(201.0 + STALL_SEC)
        assert m.stall.stalls == 1, "30 s of the warning after the unkey are a stall"
        await until_started(lambda: m.starts > starts and m.state == "running")  # (the restart it makes)
    finally:
        await stopped(m)


def test_no_closing_line_repeats_a_count_already_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, "neoaprs.mercury.program")
    program = mercuryhelper.Program(lambda code, lines: None)
    for _ in range(10):
        program._tell("[WRN] [audio] ten")
    for _ in range(11):
        program._tell("[WRN] [audio] eleven")
    program._stopped_warnings(None)
    said = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert not any("ten: came" in line for line in said), "the 10th time was said with its count"
    assert any(line.startswith("[WRN] [audio] eleven: came 11 times") for line in said)


async def test_a_ptt_on_without_its_ptt_off_does_not_blind_the_watch_for_longer_than_a_frame_is_believed(
    tmp_path: Path,
) -> None:
    m = modem(tmp_path)
    await m.start(HF)
    try:
        await until_started(lambda: m.state == "running")
        m._on_ptt(True, 0.0)  # and no PTT OFF ever
        for s in range(int(KEYED_MAX_SEC) + 1):
            m._capture_full(float(s))
        assert m.stall.stalls == 0, "while a frame may be on the air the warnings count for nothing"
        start = int(KEYED_MAX_SEC) + 1
        for s in range(start, start + int(STALL_SEC) + 1):
            m._capture_full(float(s))
        assert m.stall.stalls == 1, "a PTT ON that is not believed any more pauses nothing"
    finally:
        await stopped(m)


async def test_a_stalled_mercury_says_it_hears_nothing_until_the_warning_stops_or_it_is_restarted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mercurymodem, "GAP_SEC", 0.05)  # (how often the end of it is looked for)
    m = modem(tmp_path)
    now = [1000.0]
    m.monotonic = lambda: now[0]  # the watch's clock, driven here: no margin of real time
    await m.start(HF)
    try:
        await until_started(lambda: m.state == "running")
        changes: list[bool] = []
        m.changed.connect(lambda: changes.append(m.deaf))
        m.stall._restarted.append(now[0])  # (restarted just now: the next restart waits ten minutes)
        for step in range(int(STALL_SEC) + 1):
            now[0] = 1000.0 + step
            m._capture_full(now[0])
        assert m.deaf and m.stall.stalls == 1 and m.starts == 1 and m.describe() == "Mercury DATAC3, hearing nothing"
        assert changes[-1] is True, "the page is told"
        now[0] += mercurystall.GAP_SEC + 1  # the warning stopped: it hears again
        await until_started(lambda: changes[-1] is False)
        assert not m.deaf and m.describe() == "Mercury DATAC3, listening"
    finally:
        await stopped(m)


async def test_the_row_of_a_connected_radio_whose_mercury_hears_nothing_has_the_code_on_the_wire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    m = modem(tmp_path)
    now = [1000.0]
    m.monotonic = lambda: now[0]  # the watch's clock, driven here
    line = Tnc("127.0.0.1:1", profile=MERCURY)
    line.modem = m
    line.state = Source.State.CONNECTED
    row = lambda: radio_row(HF_SPEC, (HF_SPEC,), at_work(line, "mercury"), Claims())  # noqa: E731
    await m.start(HF)
    try:
        await until_started(lambda: m.state == "running")
        assert row()["problem"] is None
        m.stall._restarted.append(now[0])  # (restarted just now: no restart while the test looks)
        for step in range(int(STALL_SEC) + 1):
            now[0] = 1000.0 + step
            m._capture_full(now[0])
        assert (row()["state"], row()["problem"]) == ("connected", {"code": "modem.receive_deaf", "params": {}})
        now[0] += mercurystall.GAP_SEC + 1  # the warning stopped: it hears again
        assert not m.deaf
        assert row()["problem"] is None
    finally:
        await stopped(m)


def test_the_watch_is_deaf_only_while_the_warning_comes_and_not_once_given_up() -> None:
    watch = StallWatch()
    for s in range(int(STALL_SEC) + 1):
        watch.seen(float(s), T0)
    assert watch.deaf(STALL_SEC + 1) and not watch.deaf(STALL_SEC + GAP_SEC + 1)
    watch.given_up = True
    assert not watch.deaf(STALL_SEC + 1)
