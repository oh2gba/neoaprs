"""The transmit interlock (`config.can_transmit`, `services/interlock.py`, the Tnc's `permit`): a station with no call, or a call that is none (N0CALL, NOCALL, MYCALL, not an amateur call), transmits nothing at all, and the
defaults are such a station. The rules on their own, then the whole daemon on a pseudo-terminal radio that is never written to; with a call set, everything goes out as before."""
import asyncio
import logging
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs import ax25
from neoaprs.config import DEFAULTS, Config, can_transmit
from neoaprs.message import MessagingError
from tests.support.air import message_info, on_air, said
from tests.support.env import Env, until

SET_FIRST = "set your call first"


# ---- the rules ------------------------------------------------------------------------------------------------------------------------------

def test_the_defaults_are_a_station_with_no_call_and_no_position() -> None:
    assert (DEFAULTS.station_call, DEFAULTS.station_lat, DEFAULTS.station_lon, DEFAULTS.station_position) == ("", None, None, None)
    assert (DEFAULTS.beacon_interval_min, DEFAULTS.station_status, DEFAULTS.station_comment) == (0, "", "NeoAPRS")
    assert can_transmit(Config()) == SET_FIRST


@pytest.mark.parametrize("call", ["OH2GBA", "OH2GBA-7", "W1AW", "K1A", "3DA0RS", "oh2gba"])
def test_a_call_that_is_one_may_transmit(call: str) -> None:
    assert can_transmit(Config.from_data({"station/call": call})) is None


@pytest.mark.parametrize("call", ["N0CALL", "NOCALL", "MYCALL", "N0CALL-7", "nocall", "ABC", "123", "AB", "NEOAPRS"])
def test_a_placeholder_or_a_name_that_is_no_amateur_call_is_refused(call: str) -> None:
    reason = can_transmit(Config.from_data({"station/call": call}))
    assert reason is not None and reason.endswith(SET_FIRST)


@pytest.mark.parametrize("call", ["TOOLONGCALL", "OH2GBA-16", "OH 2GBA", "ÅÄÖ1AB"])
def test_a_call_that_is_no_call_at_all_is_refused_even_when_a_config_is_made_by_hand(call: str) -> None:
    reason = can_transmit(replace(DEFAULTS, station_call=call))
    assert reason is not None and reason.endswith(SET_FIRST)


def test_the_settings_take_an_empty_call_and_an_empty_position_and_write_them_empty() -> None:
    config = Config.from_data({"station/call": "oh2gba", "station/lat": "60.17", "station/lon": "24.94"})
    assert (config.station_call, config.station_position) == ("OH2GBA", (60.17, 24.94))
    cleared = Config.from_data({**config.to_data(), "station/call": "", "station/lat": " ", "station/lon": ""})
    assert (cleared.station_call, cleared.station_lat, cleared.station_lon) == ("", None, None)
    assert [Config.check(key, "") for key in ("station/call", "station/lat", "station/lon")] == ["", "", ""]
    assert cleared.to_data()["station/call"] == "" and cleared.to_data()["station/lat"] == ""
    with pytest.raises(ValueError, match="station/lat"):
        Config.check("station/lat", "95")


# ---- the whole daemon -----------------------------------------------------------------------------------------------------------------------

async def started(tmp_path: Path, **changes: object) -> Env:
    e = Env(tmp_path, operator=False)
    e.ctl.beacon.tick_sec, e.ctl.beacon.retry_sec = 0.02, 0.05
    e.ctl.messaging.tick_sec = 0.02
    e.ctl.rigstatus.poll_sec = 0.02
    await e.start()
    await asyncio.sleep(0.2)                                                # (the TNC has settled)
    if changes:
        assert await e.ctl.save_config(replace(e.ctl.config, **changes))    # type: ignore[arg-type]
    return e


async def quiet(e: Env, seconds: float = 0.4) -> None:
    """Nothing came out of the daemon's radio port in this time (the read blocks the loop, so what the daemon would send has had its turn first)."""
    await asyncio.sleep(0.2)
    assert await e.heard(1, seconds) == b"", "something was transmitted"


async def test_a_fresh_install_transmits_nothing_whatever_it_is_asked_or_due(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    e = await started(tmp_path, beacon_interval_min=10, station_status="QRV", station_lat=60.17, station_lon=24.94)
    assert e.ctl.config.station_call == "" and e.ctl.stationbook.me is None
    e.now.advance(3600)                                                     # type: ignore[attr-defined]
    await quiet(e)                                                          # the beacon is due, the status is due
    assert e.ctl.beacon.last_sent is None and e.ctl.beacon.problem == SET_FIRST and e.ctl.rigstatus.last_text == ""
    with pytest.raises(MessagingError, match=SET_FIRST):
        await e.ctl.messaging.send("OH2RDG", "Hello")
    assert not e.ctl.beacon.send_now("request")
    frame = ax25.Frame(ax25.Address.parse("APZNEO"), ax25.Address.parse("OH2GBA"), (), info=b">sneaky")
    assert not e.tnc.send_frame(frame), "the Tnc itself refuses, whoever built the frame"
    await quiet(e)
    assert [p for p in await e.packets() if p.direction == "out"] == []
    told = [r.getMessage() for r in caplog.records if "no beacon sent" in r.getMessage() or "no status sent" in r.getMessage() or "no frame sent" in r.getMessage()]
    assert sorted(told) == ["no beacon sent: set your call first", "no frame sent: set your call first", "no status sent: set your call first"], "each refusal is told once, not once per try"
    await e.stop()


async def test_a_call_that_is_a_placeholder_gets_no_ack_and_no_answer_to_a_query(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    e = await started(tmp_path, station_call="N0CALL", station_lat=60.17, station_lon=24.94)
    assert can_transmit(e.ctl.config) is not None
    e.feed(on_air("OH2RDG", message_info("N0CALL", "Moi!", "12"), path="OH2RCH-2*"))
    e.feed(on_air("OH2RDG", message_info("N0CALL", "?APRSP"), path="OH2RCH-2*"))
    e.feed(on_air("OH2RDG", message_info("N0CALL", "?APRSD"), path="OH2RCH-2*"))
    e.feed(on_air("OH2RDG", b"?APRS?"))
    await until(lambda: e.tnc.stats.packets == 4)
    await quiet(e)
    assert [r.direction for r in e.ctl.messaging.records()] == ["in"], "the message to us is kept all the same"
    with pytest.raises(MessagingError, match=SET_FIRST):
        await e.ctl.messaging.send("OH2RDG", "Hello")
    refusals = [r.getMessage() for r in caplog.records if r.name == "neoaprs.interlock"]
    assert len(refusals) == len(set(refusals)) and any("no frame sent" in m for m in refusals) and any("no query answer sent" in m for m in refusals), "once for each kind"
    await e.stop()


async def test_with_a_call_set_the_same_things_go_out_and_a_waiting_beacon_goes_when_it_is_set(tmp_path: Path) -> None:
    e = await started(tmp_path, beacon_interval_min=10, station_lat=60.17, station_lon=24.94)
    e.now.advance(3600)                                                     # type: ignore[attr-defined]
    await quiet(e)
    assert e.ctl.beacon.last_sent is None
    assert await e.ctl.save_config(replace(e.ctl.config, station_call="OH2GBA"))
    me = e.ctl.stationbook.me
    assert me is not None and me.call == "OH2GBA" and (me.lat, me.lon) == (60.17, 24.94)
    await until(lambda: e.ctl.beacon.last_sent is not None)
    [beacon] = await said(e)
    assert beacon.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=6010.20N/02456.40E-NeoAPRS"
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "Moi!", "12"), path="OH2RCH-2*"))
    await until(lambda: e.tnc.stats.packets == 1)
    [ack] = await said(e)
    assert ack.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG   :ack12"
    record = await e.ctl.messaging.send("OH2RDG", "Hello")
    assert record.state == "sending" and record.attempts == 1
    await e.stop()


async def test_no_position_means_no_beacon_and_no_own_station_but_messages_go(tmp_path: Path) -> None:
    e = await started(tmp_path, station_call="OH2GBA")
    assert e.ctl.stationbook.me is None
    assert not e.ctl.beacon.send_now("request") and e.ctl.beacon.problem.endswith("set your position first")
    await quiet(e)
    await e.ctl.messaging.send("OH2RDG", "Hello")
    assert [f.tnc2() for f in await said(e)] == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG   :Hello{01}"]
    assert await e.ctl.save_config(replace(e.ctl.config, station_lat=60.17, station_lon=24.94))
    assert e.ctl.stationbook.me is not None
    assert await e.ctl.save_config(replace(e.ctl.config, station_lat=None, station_lon=None))
    assert e.ctl.stationbook.me is None, "and when the position is cleared it is an ordinary station again"
    await e.stop()


async def test_the_tnc_is_still_switched_to_kiss_with_no_call_set_that_is_no_transmission(tmp_path: Path) -> None:
    e = await started(tmp_path, tnc_profile="kenwood-tnc2")
    await asyncio.sleep(0.3)                                                # (the TNC was restarted for its profile)
    await e.until_connected()
    e.feed(b"OH2FZV-2>VP1R61,WIDE1,OH2RCH-2*:!6010.00N/02456.00E>test\r\n")                  # a TNC in command mode, monitoring
    await until(lambda: e.tnc.stats.bytes_out >= 17)
    assert await e.heard(17, 2.0) == b"\rKISS ON\rRESTART\r"
    await e.stop()
