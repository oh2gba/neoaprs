"""The status report (neoaprs/services/rigstatus.py) on a Tnc that is a stub, the real beacon, a fake rigctld on a free port and a clock the test holds: the first report after the first poll, nothing inside the
interval, nothing when it is the same, nothing while the radio is off (and one line in the log for that), the static text under the same rule, and what ?APRSS answers with."""
import logging
import socket
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs import ax25
from neoaprs.rigctld import RigError, read_rig
from neoaprs.services.beacon import Beacon
from neoaprs.services.rigstatus import RigStatus, clipped, freq_text
from neoaprs.source import Source
from tests.support.rig import ServiceRig
from tests.support.air import on_air
from tests.support.env import Env, remember_stop, until
from tests.support.fakes import FakeRigctld, rigctld

FIRST = "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:>211200zQRV 14.074 MHz USB"


class Rig(ServiceRig):
    def __init__(self, rigd: FakeRigctld | None, **changes: object) -> None:
        super().__init__(**({"status_rigctld": rigd.address} if rigd else {}), **changes)
        self.rigd = rigd
        self.beacon = Beacon(self.tnc, lambda: self.config, self.clock)
        self.status = RigStatus(self.tnc, lambda: self.config, self.beacon, self.clock, poll_sec=0.01, read=lambda host, port: read_rig(host, port, 0.3))
        remember_stop(self.status.stop)


# ---- the radio ------------------------------------------------------------------------------------------------------------------------------------

async def test_the_first_status_goes_out_after_the_first_poll_with_the_frequency_and_the_mode() -> None:
    rig = Rig(await rigctld())
    assert rig.status.rig_state == "unused" and rig.status.last_text == "" and rig.status.last_sent_at is None
    await rig.status.poll()
    assert rig.tnc.lines() == [FIRST]
    assert rig.status.rig_state == "on" and rig.status.last_text == "QRV 14.074 MHz USB" and rig.status.last_sent_at == rig.clock()
    assert ax25.decode(ax25.encode(rig.tnc.sent[0])) == rig.tnc.sent[0] and rig.tnc.sent[0].is_ui


async def test_a_changed_frequency_inside_the_interval_sends_nothing() -> None:
    rigd = await rigctld()
    rig = Rig(rigd)
    await rig.status.poll()
    rigd.hz = 7074000
    rig.clock.advance(29 * 60 + 59)
    await rig.status.poll()
    assert rig.tnc.lines() == [FIRST]


async def test_after_the_interval_a_changed_frequency_or_mode_sends() -> None:
    rigd = await rigctld()
    rig = Rig(rigd)
    await rig.status.poll()
    rigd.hz = 7074000
    rig.clock.advance(30 * 60)
    await rig.status.poll()
    assert rig.tnc.lines() == [FIRST, "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:>211230zQRV 7.074 MHz USB"]
    rigd.mode = "CW"                                                    # (the mode alone is a change too)
    rig.clock.advance(30 * 60)
    await rig.status.poll()
    assert rig.tnc.lines()[-1] == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:>211300zQRV 7.074 MHz CW"


async def test_after_the_interval_without_a_change_sends_nothing_and_a_change_within_a_kilohertz_is_none() -> None:
    rigd = await rigctld()
    rig = Rig(rigd)
    await rig.status.poll()
    rig.clock.advance(3 * 3600)
    await rig.status.poll()
    rigd.hz = 14074400                                                  # (the same kilohertz)
    await rig.status.poll()
    assert rig.tnc.lines() == [FIRST]
    rigd.hz = 14075000
    await rig.status.poll()
    assert rig.tnc.lines()[-1].endswith("QRV 14.075 MHz USB") and len(rig.tnc.sent) == 2


async def test_the_interval_is_the_setting_and_counts_from_the_status_that_went_out() -> None:
    rigd = await rigctld()
    rig = Rig(rigd, status_interval_min=5)
    await rig.status.poll()
    rigd.hz = 7074000
    rig.clock.advance(299)
    await rig.status.poll()
    assert len(rig.tnc.sent) == 1
    rig.clock.advance(1)
    await rig.status.poll()
    assert len(rig.tnc.sent) == 2


async def test_a_radio_that_is_off_sends_nothing_and_the_log_says_so_once(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.status")
    rigd = await rigctld()
    rigd.radio_on = False
    rig = Rig(rigd)
    for _ in range(4):
        await rig.status.poll()
        rig.clock.advance(3600)
    assert rig.tnc.sent == [] and rig.status.rig_state == "off"
    told = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(told) == 1 and told[0].getMessage() == f"rigctld at {rigd.address}: rigctld answered RPRT -5: no status while it is away"
    rigd.radio_on = True                                                # the radio is switched on: a status at the next poll, one line for that
    await rig.status.poll()
    assert rig.status.rig_state == "on" and rig.tnc.lines() == [FIRST.replace("211200z", "211600z")]
    assert [r.getMessage() for r in caplog.records if "answers" in r.getMessage()] == [f"rigctld at {rigd.address}: the radio answers (14.074 MHz USB)"]
    rigd.radio_on = False
    await rig.status.poll()
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 2, "told again when it goes away again"


async def test_a_refused_connection_is_off_too_and_says_why(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.status")
    held = socket.socket()                                              # (bound and not listening: a connection is refused, and the port cannot go to another test meanwhile,
    held.bind(("127.0.0.1", 0))                                         #  whose own radio or rigctld would then get this test's questions)
    address = f"127.0.0.1:{held.getsockname()[1]}"
    rig = Rig(None, status_rigctld=address)
    try:
        await rig.status.poll()
        await rig.status.poll()
    finally:
        held.close()
    assert rig.tnc.sent == [] and rig.status.rig_state == "off"
    why = "no answer in time" if sys.platform == "win32" else "connection refused"          # (Windows takes about two seconds to refuse a connection: longer than rigctld is given)
    assert [r.getMessage() for r in caplog.records] == [f"rigctld at {address}: {why}: no status while it is away"]


async def test_a_rigctld_that_does_not_answer_is_off_and_a_nonsense_answer_too() -> None:
    rigd = await rigctld()
    rigd.responder = lambda line: b""
    rig = Rig(rigd)
    await rig.status.poll()
    assert rig.status.rig_state == "off" and rig.tnc.sent == []
    rigd.responder = lambda line: b"hello\n"
    await rig.status.poll()
    assert rig.status.rig_state == "off"
    rigd.responder = lambda line: b"0\nUSB\n" if line == "f" else b"USB\n"
    await rig.status.poll()
    assert rig.status.rig_state == "off", "a frequency of 0 is no frequency"


async def test_the_template_is_filled_in_and_cut_to_the_55_characters() -> None:
    rigd = await rigctld(hz=145500000, mode="FM")
    rig = Rig(rigd, status_template="{mode} on {freq}, OK")
    await rig.status.poll()
    assert rig.tnc.sent[0].info == b">211200zFM on 145.500 MHz, OK"
    assert freq_text(14074500) == "14.075 MHz" and freq_text(1296000000) == "1296.000 MHz" and freq_text(7000) == "0.007 MHz"
    assert clipped("x" * 70) == "x" * 55 and clipped("abc", 2) == "ab"


async def test_what_a_radio_names_its_mode_with_is_made_printable_ascii_without_the_tnc_switch_characters() -> None:
    assert clipped("PKT|USB~å") == "PKT?USB??"
    rigd = await rigctld(hz=145500000, mode="PKT~FM")
    rig = Rig(rigd)
    await rig.status.poll()
    assert rig.tnc.sent[0].info == b">211200zQRV 145.500 MHz PKT?FM"


async def test_a_static_status_that_is_too_long_or_not_ascii_makes_no_frame_and_is_told_once(caplog: pytest.LogCaptureFixture) -> None:
    rig = Rig(None, station_status="x" * 56)                # (a value that did not come through the settings check, a hand-made Config)
    with caplog.at_level(logging.WARNING, logger="neoaprs.status"):
        await rig.status.poll()
        await rig.status.poll()
    assert rig.tnc.sent == [] and [r.getMessage() for r in caplog.records].count("no status sent: the settings make no status: the status is 56 characters, more than the 55 that fit after its time") == 1


async def test_an_empty_template_sends_nothing() -> None:
    rig = Rig(await rigctld(), status_template="")
    await rig.status.poll()
    assert rig.tnc.sent == [] and rig.status.rig_state == "on"


# ---- the static text ---------------------------------------------------------------------------------------------------------------------------

async def test_the_static_text_goes_out_once_and_again_only_when_edited_and_after_the_interval() -> None:
    rig = Rig(None, station_status="QRV 145.500")
    await rig.status.poll()
    assert rig.status.rig_state == "unused" and rig.tnc.lines() == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1:>211200zQRV 145.500"]
    rig.clock.advance(3 * 3600)
    await rig.status.poll()
    assert len(rig.tnc.sent) == 1, "the same text is not sent again"
    rig.set(station_status="At the cottage")
    rig.clock.advance(-3 * 3600 + 60)
    await rig.status.poll()
    assert len(rig.tnc.sent) == 1, "edited, but inside the interval"
    rig.clock.advance(29 * 60)
    await rig.status.poll()
    assert rig.tnc.lines()[-1] == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:>211230zAt the cottage" and rig.status.last_text == "At the cottage"
    assert len(rig.tnc.sent) == 2


async def test_an_empty_static_text_sends_nothing() -> None:
    rig = Rig(None)
    await rig.status.poll()
    assert rig.tnc.sent == [] and rig.status.last_text == "" and rig.status.status_frame() is None


async def test_the_radio_is_used_once_the_setting_is_set_and_unused_when_it_is_cleared() -> None:
    rig = Rig(await rigctld(), station_status="static")
    await rig.status.poll()
    assert rig.status.rig_state == "on" and rig.status.last_text == "QRV 14.074 MHz USB"
    rig.set(status_rigctld="")
    await rig.status.poll()
    assert rig.status.rig_state == "unused"


# ---- the Tnc -------------------------------------------------------------------------------------------------------------------------------------

async def test_a_status_waits_while_the_radio_is_silent_and_is_sent_when_it_answers(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.status")
    rig = Rig(await rigctld())
    rig.tnc.state = Source.State.SILENT
    await rig.status.poll()
    await rig.status.poll()
    assert rig.tnc.sent == [] and rig.status.last_sent_at is None
    assert len([r for r in caplog.records if "the radio is silent: the status waits" in r.getMessage()]) == 1
    rig.tnc.state = Source.State.CONNECTED
    await rig.status.poll()
    assert rig.tnc.lines() == [FIRST]


async def test_a_status_waits_for_the_tnc_and_is_sent_at_the_next_poll_that_finds_it_there(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.status")
    rigd = await rigctld()
    rig = Rig(rigd)
    rig.tnc.state = Source.State.WAITING
    await rig.status.poll()
    await rig.status.poll()
    assert rig.tnc.sent == [] and rig.status.last_sent_at is None
    assert len([r for r in caplog.records if "TNC is not connected" in r.getMessage()]) == 1
    rig.tnc.state = Source.State.CONNECTED
    await rig.status.poll()
    assert rig.tnc.lines() == [FIRST]
    rig.tnc.takes = False
    rig.clock.advance(3600)
    rigd.hz = 7074000
    await rig.status.poll()
    assert len(rig.tnc.sent) == 1 and rig.status.last_sent_at != rig.clock(), "a frame the Tnc would not take is not counted as sent"
    rig.tnc.takes = True
    await rig.status.poll()
    assert rig.tnc.sent[-1].info.endswith(b"QRV 7.074 MHz USB") and len(rig.tnc.sent) == 2


async def test_settings_that_make_no_frame_send_nothing_and_do_not_stop_the_timer() -> None:
    rig = Rig(await rigctld(), station_call="TOOLONGCALL")
    await rig.status.start()
    await until(lambda: rig.status.rig_state == "on")
    assert rig.tnc.sent == []
    rig.set(station_call="OH2GBA")
    await until(lambda: len(rig.tnc.sent) == 1)
    await rig.status.stop()


# ---- ?APRSS and the timer ----------------------------------------------------------------------------------------------------------------------

async def test_aprss_answers_with_the_text_last_sent_stamped_with_the_time_of_the_answer() -> None:
    rigd = await rigctld()
    rig = Rig(rigd)
    assert rig.status.status_frame() is None
    await rig.status.poll()
    rigd.hz = 7074000
    rig.clock.advance(120)
    frame = rig.status.status_frame()
    assert frame is not None and frame.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:>211202zQRV 14.074 MHz USB", "the text last sent, not the dial now"


async def test_the_timer_polls_by_itself_and_stops() -> None:
    rig = Rig(await rigctld())
    await rig.status.start()
    await rig.status.start()                                            # (a second start does nothing)
    await until(lambda: rig.tnc.sent != [])
    assert rig.tnc.lines() == [FIRST]
    await rig.status.stop()


async def test_the_daemon_tells_the_page_the_status_and_the_state_of_the_radio(tmp_path: Path) -> None:
    rigd = await rigctld()
    e = Env(tmp_path, web=True)
    e.ctl.rigstatus.poll_sec = 0.02
    await e.start()
    e.feed(on_air("OH2ABC", b">hello"))                                     # (a frame heard: the TNC is in KISS mode and takes frames)
    await until(lambda: e.tnc.stats.packets == 1)
    page = await e.ws()
    first = await page.expect("status")
    assert first["station_status"] == "" and first["rig_state"] == "unused"
    assert await e.ctl.save_config(replace(e.ctl.config, status_rigctld=rigd.address))
    await until(lambda: e.ctl.rigstatus.last_text == "QRV 14.074 MHz USB")
    await page.send({"cmd": "status"})
    await page.until(lambda: page.of("status")[-1]["station_status"] == "QRV 14.074 MHz USB")
    assert page.of("status")[-1]["rig_state"] == "on"
    rigd.radio_on = False
    await until(lambda: e.ctl.rigstatus.rig_state == "off")
    await page.send({"cmd": "status"})
    await page.until(lambda: page.of("status")[-1]["rig_state"] == "off")
    assert page.of("status")[-1]["station_status"] == "QRV 14.074 MHz USB", "what was last sent stays"
    await e.stop()


async def test_read_rig_says_what_is_wrong_in_words() -> None:
    rigd = await rigctld(hz=14074000, mode="USB")
    reading = await read_rig("127.0.0.1", rigd.port, 1.0)
    assert (reading.hz, reading.mode) == (14074000, "USB")
    rigd.radio_on = False
    with pytest.raises(RigError, match="RPRT -5"):
        await read_rig("127.0.0.1", rigd.port, 1.0)
    rigd.responder = lambda line: b""
    with pytest.raises(RigError, match="no answer in time"):
        await read_rig("127.0.0.1", rigd.port, 0.2)
