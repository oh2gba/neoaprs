"""The silent radio: the line is open and nothing at all comes back, as when the TH-D7 is switched off and the USB adapter is still there. The keep-alive's check decides, the probes look for the radio
coming back, the first byte ends the silence cleanly (KISS is entered afresh and nothing is sent until it has settled), and every sender treats the state as not usable. The Tnc runs on a fake radio (a TCP server
on the loopback) with short periods; the senders' own cases are in their test files."""
import asyncio
import logging
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs.source import CHECKING, Source
from neoaprs.tnc import ENTER_KISS, KISS_EXIT, Tnc
from neoaprs.tncprofile import KISS, KISS_TCP, Profile
from tests.support.clock import FixedClock
from tests.support.env import Env, idle_for, until
from tests.support.fakeradio import FakeRadio
from tests.test_tnc import NO_DETECT, NUDGE_BYTE, SETTLE, Rig, Rigs, hear_until, kiss_of, news, nothing_runs, stops_rigs, tiny_backoff, ui_frame

ANSWER = b"KISS ON\r\nKISS      was OFF\r\ncmd:"
QUICK = {"check_sec": 0.1, "check_pause_sec": 0.02, "reply_sec": 0.05, "answer_sec": 0.1}
FAST = {"check_sec": 0.05, "check_pause_sec": 0.0, "reply_sec": 0.0, "answer_sec": 0.0, "probe_sec": 0.005}       # a probe takes a few milliseconds


@pytest.fixture
def rig() -> Rigs:
    return Rigs()


async def silent_rig(rig: Rigs, probe_answer_sec: float = 0.1, **kwargs: object) -> tuple[Rig, FixedClock]:
    """A Tnc whose check goes unanswered at once, and which has become SILENT; its probes wait `probe_answer_sec` for an answer."""
    clock = FixedClock()
    r = await rig(clock=clock, **{"probe_sec": 30.0, **QUICK, **kwargs})
    await until(lambda: r.tnc.state is Source.State.SILENT)
    r.tnc.watchdog.answer_sec, r.tnc.watchdog.sec = probe_answer_sec, 30.0       # (no second check while the test looks at the return)
    await r.radio.said(4096, 0.05)                                 # (what the check wrote)
    return r, clock


async def drain(radio: FakeRadio) -> None:
    """Reads what the port writes, as long as it runs, so that what the Tnc writes does not pile up."""
    while True:
        await radio.said(4096, 0.01)
        await asyncio.sleep(0.005)


@stops_rigs
async def test_a_check_that_nothing_answers_makes_the_radio_silent_and_describe_says_since_when(rig: Rigs) -> None:
    states: list[Source.State] = []
    r, clock = await silent_rig(rig)
    r.tnc.state_changed.connect(states.append)
    assert r.tnc.silent_since == clock.now and r.tnc.usable is False
    assert r.tnc.describe() == "silent since 12:00 (0 min)"
    clock.advance(17 * 60 + 30)
    assert r.tnc.describe() == "silent since 12:00 (17 min)"
    assert (r.tnc.stats.keepalive_checks, r.tnc.stats.watchdog_probes, r.tnc.stats.port_reopens) == (1, 0, 0)
    assert any("the radio is silent: nothing heard since 12:00 UTC, no answer to a check; probing every 30 s" in line for line in r.tnc.lines)
    assert r.tnc.send_frame(ui_frame()) is False and any("not sent: the radio is silent" in line for line in r.tnc.lines)


@stops_rigs
async def test_command_mode_text_while_silent_enters_kiss_and_connects_but_nothing_is_usable_until_the_settle_has_passed(rig: Rigs, caplog: pytest.LogCaptureFixture) -> None:
    r, clock = await silent_rig(rig)
    clock.advance(17 * 60)
    caplog.set_level(logging.INFO)
    caplog.clear()
    r.radio.feed(b"\r\ncmd:")                                      # the radio was switched on: its TNC is in command mode
    assert await hear_until(r.radio, ENTER_KISS, 1.0)
    assert r.tnc.state is Source.State.CONNECTED and r.tnc.silent_since is None
    assert r.tnc.usable is False and r.tnc.send_frame(ui_frame()) is False, "the TNC is restarting"
    assert news(caplog) == ["tnc: the radio answers again after 17 min; entering KISS"]
    assert any(line.endswith("NeoAPRS: the radio answers again after 17 min; entering KISS") for line in r.tnc.lines)
    await until(lambda: r.tnc.usable, 1.0)
    assert r.tnc.send_frame(ui_frame()) is True
    assert await hear_until(r.radio, kiss_of(ui_frame()), 1.0)
    assert await r.radio.said(1, 0.05) == b"", "KISS ON went out once"


@stops_rigs
async def test_the_allowance_to_enter_kiss_is_given_back_on_the_return_from_silence(rig: Rigs) -> None:
    r = await rig(**{"probe_sec": 30.0, "check_sec": 0.0})
    r.radio.feed(b"\r\ncmd:")                                      # a fresh open: KISS ON is sent, once
    assert await hear_until(r.radio, ENTER_KISS, 1.0)
    await idle_for(SETTLE + 0.05)
    assert r.tnc._entered
    r.tnc.went_silent()
    r.radio.feed(b"\r\ncmd:")                                      # the radio was switched off and on
    assert await hear_until(r.radio, ENTER_KISS, 1.0), "it is once for every answer, not once for every open"
    await until(lambda: r.tnc.usable, 1.0)
    assert r.tnc.problem == ""


@stops_rigs
async def test_a_kiss_frame_as_the_first_bytes_of_a_silent_radio_is_a_packet_and_nothing_is_entered(rig: Rigs) -> None:
    r, _ = await silent_rig(rig)
    r.radio.feed(kiss_of(ui_frame()))
    await until(lambda: r.tnc.state is Source.State.CONNECTED)
    assert r.tnc.usable and r.tnc.silent_since is None
    await until(lambda: len(r.packets) == 1)
    assert await r.radio.said(1, 0.1) == b""


@stops_rigs
async def test_a_frame_that_comes_in_two_reads_as_the_first_bytes_of_a_silent_radio_is_a_packet_and_nothing_is_entered(rig: Rigs) -> None:
    r, _ = await silent_rig(rig)
    await idle_for(SETTLE + 0.05)                                   # (the check's own entry has settled)
    wire = kiss_of(ui_frame())
    r.radio.feed(wire[:12])                                        # a line delivers a frame in several reads: the first holds the FEND and the start of the addresses
    await until(lambda: r.tnc.state is Source.State.CONNECTED)
    assert await r.radio.said(1, 0.1) == b"", "a piece of a frame is no reason to type KISS ON into a TNC that is in KISS"
    r.radio.feed(wire[12:])
    await until(lambda: len(r.packets) == 1)
    assert r.tnc.usable and r.tnc.describe().endswith("KISS, 1 packets")


@stops_rigs
async def test_the_tail_of_a_frame_as_the_first_bytes_of_a_silent_radio_is_not_command_mode_text(rig: Rigs) -> None:
    r, _ = await silent_rig(rig)
    await idle_for(SETTLE + 0.05)
    wire = kiss_of(ui_frame("OH7JHF-1", info=b"}OH2DPN>APJYC1,TCPIP,OH7JHF-1*::OH2GBA   :ack10"))
    r.radio.feed(wire[wire.index(b"}") + 1:])                       # the read began inside the frame: text that looks like a monitored packet, then the closing FEND
    await until(lambda: r.tnc.state is Source.State.CONNECTED)
    assert await r.radio.said(1, 0.1) == b""
    r.radio.feed(kiss_of(ui_frame()))
    await until(lambda: len(r.packets) == 1)


@stops_rigs
async def test_other_bytes_from_a_silent_radio_enter_kiss_too(rig: Rigs) -> None:
    r, _ = await silent_rig(rig)
    r.radio.feed(b"\x00\x01noise")
    assert await hear_until(r.radio, ENTER_KISS, 1.0)
    assert r.tnc.state is Source.State.CONNECTED and r.tnc.usable is False


@stops_rigs
async def test_a_silent_radio_whose_tnc_may_not_enter_kiss_connects_without_it(rig: Rigs) -> None:
    r = await rig(profile=NO_DETECT, check_sec=0.0, probe_sec=30.0)
    r.tnc.went_silent()
    r.radio.feed(b"\r\ncmd:")
    await until(lambda: r.tnc.state is Source.State.CONNECTED)
    assert await r.radio.said(1, 0.1) == b"" and r.tnc.usable


@stops_rigs
async def test_probes_repeat_the_check_and_a_prompt_after_the_return_enters_kiss_and_connects_without_a_second_entry(rig: Rigs, caplog: pytest.LogCaptureFixture) -> None:
    r, _ = await silent_rig(rig, probe_sec=0.2, probe_answer_sec=0.5)
    caplog.set_level(logging.INFO)
    caplog.clear()
    assert await hear_until(r.radio, KISS_EXIT + NUDGE_BYTE, 2.0) == KISS_EXIT + NUDGE_BYTE
    assert (r.tnc.stats.watchdog_probes, r.tnc.last_watchdog_action) == (1, "probe")
    r.radio.feed(b"\r\ncmd:")
    assert await hear_until(r.radio, ENTER_KISS, 1.0)
    await until(lambda: r.tnc.state is Source.State.CONNECTED, 1.0)
    assert await r.radio.said(1, 0.3) == b"", "the probe did not enter KISS a second time"
    assert [m for m in news(caplog)] == ["tnc: the radio answers again after 0 min; entering KISS"]


@stops_rigs
async def test_a_probe_whose_return_is_not_answered_enters_kiss_and_an_answer_to_that_connects(rig: Rigs) -> None:
    r, _ = await silent_rig(rig, probe_sec=0.2, probe_answer_sec=1.0)
    assert await hear_until(r.radio, KISS_EXIT + NUDGE_BYTE + ENTER_KISS, 3.0)
    assert r.tnc.state is Source.State.SILENT
    r.radio.feed(ANSWER)
    await until(lambda: r.tnc.state is Source.State.CONNECTED, 1.0)
    assert await r.radio.said(1, 0.3) == b"", "no second entry"
    await until(lambda: r.tnc.usable, 1.0)
    assert r.tnc.stats.watchdog_probes == 1 and r.tnc.watchdog.probes == 0


@stops_rigs
async def test_a_hundred_unanswered_probes_make_one_warning_and_no_info_and_every_fifth_reopens_the_port(rig: Rigs, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    r = await rig(clock=FixedClock(), **FAST)                       # (the check at the open finds nothing at once)
    feeder = asyncio.create_task(drain(r.radio))
    try:
        stats = r.tnc.stats
        await until(lambda: stats.watchdog_probes >= 100, 10.0)
        await until(lambda: r.tnc.state is Source.State.SILENT and stats.port_reopens == stats.watchdog_probes // 5 and stats.opens == 1 + stats.port_reopens, 5.0)          # (a reopen takes a moment, longer on Windows)
        told = [rec for rec in caplog.records if rec.name.startswith("neoaprs") and not rec.getMessage().startswith("tnc: opened")]
        assert [rec.levelno for rec in told] == [logging.WARNING]
        assert "the radio is silent" in told[0].getMessage()
        assert stats.port_reopens == stats.watchdog_probes // 5 and stats.opens == 1 + stats.port_reopens
        assert r.tnc.last_watchdog_action in ("probe", "reopen") and r.tnc.state is Source.State.SILENT
    finally:
        feeder.cancel()
        await asyncio.gather(feeder, return_exceptions=True)


@stops_rigs
async def test_the_fifth_probe_closes_and_opens_the_port_and_the_radio_stays_silent_across_it(rig: Rigs) -> None:
    r, _ = await silent_rig(rig, probe_sec=0.1, probe_answer_sec=0.0)
    feeder = asyncio.create_task(drain(r.radio))
    try:
        await until(lambda: r.tnc.stats.watchdog_probes == 4, 5.0)
        assert (r.tnc.stats.port_reopens, r.tnc.stats.opens) == (0, 1)
        await until(lambda: r.tnc.stats.port_reopens == 1, 5.0)
        await until(lambda: r.tnc.stats.opens == 2, 5.0)
        assert r.tnc.stats.watchdog_probes == 5 and r.tnc.last_watchdog_action == "reopen"
        assert r.tnc.state is Source.State.SILENT and r.tnc.silent_since is not None
        await until(lambda: r.tnc.stats.watchdog_probes == 6, 5.0)       # the probing goes on after the reopen
        r.radio.feed(b"\r\ncmd:")                                      # and a byte on the new line ends the silence
        await until(lambda: r.tnc.state is Source.State.CONNECTED, 2.0)
    finally:
        feeder.cancel()
        await asyncio.gather(feeder, return_exceptions=True)


async def test_a_line_that_is_lost_while_silent_is_waiting_and_comes_back_connected_with_the_count_over() -> None:
    radio = FakeRadio()
    await radio.start()
    tnc = Tnc(radio.url, backoff=tiny_backoff(), fallback_probe=False, settle_sec=SETTLE, probe_sec=0.05, **QUICK)
    await tnc.start()
    try:
        await until(lambda: tnc.state is Source.State.SILENT)
        await until(lambda: tnc.stats.watchdog_probes >= 2, 3.0)
        await radio.connected()
        radio.refuse()
        radio.drop()
        await until(lambda: tnc.state is Source.State.WAITING)
        assert tnc._watchdog_task is None and tnc.watchdog.probes == 0
        await radio.accept()
        await until(lambda: tnc.state is Source.State.CONNECTED)
        assert tnc.usable is False and tnc.why_unusable() == CHECKING and tnc.stats.opens == 2, "a fresh open is checked again"
    finally:
        await tnc.stop()
        await radio.aclose()
    nothing_runs(tnc)


@stops_rigs
async def test_stop_while_a_probe_waits_for_an_answer_leaves_nothing_running(rig: Rigs) -> None:
    r, _ = await silent_rig(rig, probe_sec=0.05, probe_answer_sec=30.0)
    await until(lambda: r.tnc.stats.watchdog_probes == 1)
    await idle_for(0.15)                                        # (inside the wait after KISS ON)
    await r.tnc.stop()
    nothing_runs(r.tnc)
    probes = r.tnc.stats.watchdog_probes
    await idle_for(0.2)
    assert r.tnc.stats.watchdog_probes == probes and r.tnc._looking is False


@stops_rigs
async def test_stop_while_silent_between_probes_leaves_nothing_running(rig: Rigs) -> None:
    r, _ = await silent_rig(rig, probe_sec=30.0)
    await r.tnc.stop()
    nothing_runs(r.tnc)
    assert r.tnc.silent_since is None


# ---- the senders over the socket, with the real Tnc

async def test_beacon_now_and_send_message_are_refused_over_the_socket_while_the_radio_is_silent_and_work_when_it_answers(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True, settings={"beacon/interval_min": "1440"})
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) >= 7)
    e.tnc.went_silent()
    await page.until(lambda: page.topics["tnc"]["state"] == "silent")
    assert page.topics["tnc"]["silent_since"] is not None and page.topics["tnc"]["describe"].startswith("silent since ")
    await page.send({"cmd": "beacon_now"})
    assert (await page.expect("error"))["text"] == "beacon_now: nothing was sent: the radio is silent"
    await page.send({"cmd": "send_message", "to": "OH2RDG", "text": "Hello Pekka"})
    assert (await page.expect("error"))["text"] == "send_message: the radio is silent"
    assert page.topics["messages"] == {} and e.ctl.beacon.last_sent is None
    e.feed(kiss_of(ui_frame()))
    await page.until(lambda: page.topics["tnc"]["state"] == "connected" and page.topics["tnc"]["silent_since"] is None)
    await page.send({"cmd": "send_message", "to": "OH2RDG", "text": "Hello Pekka"})
    await page.until(lambda: page.topics["messages"].get("1", {}).get("attempts") == 1)


async def test_a_beacon_due_during_the_outage_is_written_only_after_the_settle_as_a_kiss_frame_when_the_radio_comes_back(tmp_path: Path) -> None:
    e = Env(tmp_path, check_pause_sec=0.02, reply_sec=0.6, answer_sec=0.6, probe_sec=0.3)       # (the radio answers the probe within its reply time, before the probe's own KISS ON)
    e.ctl.beacon.tick_sec, e.ctl.beacon.retry_sec = 0.02, 0.05
    await e.start()
    e.tnc.set_check(0.1)                                             # (the settings of an Env have the checks off)
    await until(lambda: e.tnc.state is Source.State.SILENT)
    assert await e.ctl.save_config(replace(e.ctl.config, beacon_interval_min=1))
    e.now.advance(30 + 60)                                           # type: ignore[attr-defined]  (the first beacon, and an interval, passed in the night)
    await idle_for(0.2)
    assert e.ctl.beacon.last_sent is None and e.ctl.beacon.next_due is not None and e.ctl.beacon.next_due < e.now()
    assert await hear_until(e.radio, KISS_EXIT + NUDGE_BYTE, 3.0)   # a probe
    e.tnc.set_check(0)                                               # (a 0.1 s check would reset the quiet radio again at once)
    await e.radio.said(0, 0)                                         # (what earlier probes said is not looked at)
    e.radio.feed(b"\r\ncmd:")                                      # the radio is switched on and answers the probe
    assert await hear_until(e.radio, ENTER_KISS, 1.0)
    entered = asyncio.get_running_loop().time()
    assert e.tnc.usable is False and e.ctl.beacon.last_sent is None
    wanted = kiss_of(e.ctl.beacon.frame())
    assert await hear_until(e.radio, wanted, 3.0) == wanted, "nothing but the frame follows KISS ON"
    assert asyncio.get_running_loop().time() - entered >= 0.08, "the settle time (0.15 s) was waited out"
    await until(lambda: e.ctl.beacon.last_sent is not None)
    assert e.tnc.state is Source.State.CONNECTED and e.ctl.beacon.last_reason == "interval" and e.ctl.beacon.next_due == e.now() + timedelta(minutes=1)
    await e.stop()


# ---- a fresh open is not usable until the radio has shown that it is there

CHECK = KISS_EXIT + NUDGE_BYTE
ASKED = {"check_sec": 60.0, "check_pause_sec": 0.02, "reply_sec": 0.3, "answer_sec": 1.0}         # (the checks on; the radio has time to answer)
SHORT = {"check_sec": 60.0, "check_pause_sec": 0.02, "reply_sec": 0.05, "answer_sec": 0.1}


@stops_rigs
async def test_a_fresh_tnc2_line_is_checked_at_once_and_nothing_else_is_written_until_the_radio_answers(rig: Rigs, caplog: pytest.LogCaptureFixture) -> None:
    r = await rig(**ASKED)
    caplog.set_level(logging.INFO)
    caplog.clear()
    begun = asyncio.get_running_loop().time()
    assert await hear_until(r.radio, CHECK, 0.5) == CHECK, "the exit frame and the carriage return, at once (the 60 s of the keep-alive are not waited for)"
    assert asyncio.get_running_loop().time() - begun < 0.5
    assert (r.tnc.stats.keepalive_checks, r.tnc.last_watchdog_action) == (1, "check")
    assert r.tnc.state is Source.State.CONNECTED and r.tnc.usable is False and r.tnc.why_unusable() == CHECKING
    assert r.tnc.send_frame(ui_frame()) is False and any("not sent: the TNC is checking that the radio is there" in line for line in r.tnc.lines)
    assert await r.radio.said(1, 0.1) == b"", "nothing else is written while the radio has not answered"
    r.radio.feed(b"\r\ncmd:")
    assert await hear_until(r.radio, ENTER_KISS, 1.0) == ENTER_KISS
    assert r.tnc.state is Source.State.CONNECTED and r.tnc.usable is False, "settling"
    await until(lambda: r.tnc.usable, 1.0)
    assert r.tnc.send_frame(ui_frame()) is True
    wire = kiss_of(ui_frame())
    assert await hear_until(r.radio, wire, 1.0) == wire, "a KISS frame, after the settle, and nothing else"
    assert news(caplog) == [] and r.tnc.problem == ""


@stops_rigs
async def test_a_fresh_line_whose_radio_does_not_answer_is_silent_within_the_answer_time_with_one_warning(rig: Rigs, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    r = await rig(clock=FixedClock(), **SHORT)
    caplog.clear()
    begun = asyncio.get_running_loop().time()
    await until(lambda: r.tnc.state is Source.State.SILENT, 2.0)
    assert asyncio.get_running_loop().time() - begun < 0.5
    assert await hear_until(r.radio, CHECK + ENTER_KISS, 1.0) == CHECK + ENTER_KISS
    assert await r.radio.said(1, 0.2) == b"", "the check and nothing else"
    assert news(caplog) == ["tnc: the radio is silent: nothing heard since 12:00 UTC, no answer to a check; probing every 30 s"]
    assert [rec.levelno for rec in caplog.records if rec.name.startswith("neoaprs")] == [logging.WARNING]
    assert r.tnc.usable is False and r.tnc.send_frame(ui_frame()) is False and any("not sent: the radio is silent" in line for line in r.tnc.lines)


async def test_a_packet_that_arrives_before_the_check_runs_confirms_the_line_and_no_check_is_made() -> None:
    radio = FakeRadio()
    await radio.start()
    tnc = Tnc(radio.url, backoff=tiny_backoff(), fallback_probe=False, settle_sec=SETTLE, **ASKED)
    try:
        await tnc.start()
        assert tnc.state is Source.State.CONNECTED and tnc.usable is False, "opened, and not heard from"
        port = tnc._port
        assert port is not None
        tnc._on_data(port, kiss_of(ui_frame()))                                    # (the line is read before the task of the check has run)
        assert tnc.usable is True and tnc.stats.packets == 1
        await radio.connected()
        assert await radio.said(1, 0.4) == b"" and tnc.stats.keepalive_checks == 0
        assert tnc.send_frame(ui_frame()) is True
    finally:
        await tnc.stop()
        await radio.aclose()


@pytest.mark.parametrize("profile", [KISS, KISS_TCP], ids=["kiss", "kiss-tcp"])
@stops_rigs
async def test_a_tnc_that_cannot_be_asked_is_usable_as_soon_as_the_line_is_open_and_nothing_is_written(rig: Rigs, profile: Profile) -> None:
    r = await rig(profile=profile, **SHORT)
    assert r.tnc.usable is True and r.tnc.why_unusable() != CHECKING
    assert r.tnc.send_frame(ui_frame()) is True
    wire = kiss_of(ui_frame())
    assert await r.radio.said(len(wire)) == wire
    assert await r.radio.said(1, 0.3) == b"" and r.tnc.stats.keepalive_checks == 0


@stops_rigs
async def test_a_line_that_is_opened_again_after_it_dropped_is_checked_again(rig: Rigs) -> None:
    r = await rig(**ASKED)
    await hear_until(r.radio, CHECK)
    r.radio.feed(b"\r\ncmd:")
    await hear_until(r.radio, ENTER_KISS)
    await until(lambda: r.tnc.usable, 1.0)
    r.radio.drop()
    await until(lambda: r.tnc.state is Source.State.WAITING)
    await until(lambda: r.tnc.state is Source.State.CONNECTED)
    assert r.tnc.stats.opens == 2 and r.tnc.usable is False and r.tnc.why_unusable() == CHECKING, "the new line has not shown the radio yet"
    assert await hear_until(r.radio, CHECK, 1.0) == CHECK and r.tnc.stats.keepalive_checks == 2
    assert r.tnc.send_frame(ui_frame()) is False


@stops_rigs
async def test_switching_the_checks_off_while_a_fresh_line_waits_makes_it_usable(rig: Rigs) -> None:
    r = await rig(**ASKED)
    await hear_until(r.radio, CHECK)
    assert r.tnc.usable is False
    r.tnc.set_check(0.0)
    await until(lambda: r.tnc.usable, 1.0)
    assert r.tnc._watchdog_task is None and r.tnc._looking is False


# ---- the beacon that falls due at the open waits for the radio

def tnc2_daemon(tmp_path: Path, **timings: float) -> Env:
    """A daemon on a fake radio with the Kenwood TNC-2 profile, the keep-alive on and a beacon that is due at the start."""
    e = Env(tmp_path, settings={"beacon/interval_min": "1"}, check_sec=60.0, check_pause_sec=0.02, probe_sec=30.0, **timings)
    e.ctl.beacon.tick_sec, e.ctl.beacon.retry_sec, e.ctl.beacon.first_delay_sec = 0.02, 0.05, 0.0
    return e


async def test_a_beacon_due_at_the_open_goes_out_only_after_the_radio_has_answered_and_the_tnc_has_settled(tmp_path: Path) -> None:
    e = tnc2_daemon(tmp_path, reply_sec=0.5, answer_sec=1.0)
    await e.start()
    assert await hear_until(e.radio, CHECK, 1.0) == CHECK
    await idle_for(0.2)                                                  # (many ticks of the beacon's timer)
    assert e.ctl.beacon.last_sent is None and e.tnc.usable is False and e.tnc.state is Source.State.CONNECTED
    assert await e.heard(1, 0.1) == b""
    e.feed(b"\r\ncmd:")                                                       # the radio is there
    assert await hear_until(e.radio, ENTER_KISS, 1.0) == ENTER_KISS
    assert e.ctl.beacon.last_sent is None, "settling"
    wanted = kiss_of(e.ctl.beacon.frame())
    assert await hear_until(e.radio, wanted, 3.0) == wanted, "nothing but the frame follows KISS ON"
    await until(lambda: e.ctl.beacon.last_sent is not None)
    assert e.ctl.beacon.last_reason == "interval"
    await e.stop()


async def test_a_beacon_due_at_the_open_is_not_sent_nor_remembered_when_the_radio_does_not_answer(tmp_path: Path) -> None:
    e = tnc2_daemon(tmp_path, reply_sec=0.05, answer_sec=0.1)
    await e.start()
    await until(lambda: e.tnc.state is Source.State.SILENT, 2.0)
    await idle_for(0.3)
    assert e.ctl.beacon.last_sent is None and e.ctl.beacon.next_due is not None and e.ctl.beacon.next_due <= e.now()
    assert await e.heard(len(CHECK + ENTER_KISS), 0.5) == CHECK + ENTER_KISS, "the check, and no frame"
    assert await e.heard(1, 0.2) == b"" and await e.packets() == []
    await e.stop()
