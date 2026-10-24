"""Receive only (`station/transmit` false): the interlock's first reason, and the whole daemon on a fake radio that is never written to while it is off, whatever is due or asked (a beacon, a status, an object, an ack, an answer
to a query, a digipeatable packet, a message being sent). A new message and a retry are refused with the code `transmit.off`; a message being sent waits with its attempts and goes on when transmitting is switched on; the setting
is kept in the database, so it holds after a restart."""
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs.config import RECEIVE_ONLY, Config, can_transmit
from neoaprs.message import MessagingError
from neoaprs.ownobject import OwnError
from neoaprs.ownbulletin import PostError
from tests.support.air import message_info, on_air, said
from tests.support.env import Env, idle_for, quick_start, until

OFF = "receive only: transmitting is switched off"
NOTHING_SENT = "Receive only: nothing is sent"
BUSY = b"!6010.20N/02456.40E-test"


async def switch(e: Env, on: bool) -> None:
    assert await e.ctl.save_config(replace(e.ctl.config, station_transmit=on))


async def quiet(e: Env, seconds: float = 0.4) -> None:
    await idle_for(0.2)
    assert await e.heard(1, seconds) == b"", "something was transmitted"


# ---- the rule and the setting ---------------------------------------------------------------------------------------------------------------

def test_transmitting_is_on_by_default_and_off_is_the_first_reason() -> None:
    assert Config().station_transmit is True and Config.from_data({"station/call": "OH2GBA"}).station_transmit is True
    on = Config.from_data({"station/call": "OH2GBA"})
    assert can_transmit(on) is None
    off = replace(on, station_transmit=False)
    assert can_transmit(off) == RECEIVE_ONLY == OFF
    assert can_transmit(replace(Config(), station_transmit=False)) == OFF, "without a call too, the switch is what is said"


def test_the_setting_takes_true_and_false_and_refuses_the_rest() -> None:
    assert Config.check("station/transmit", " False ") == "false" and Config.check("station/transmit", "yes") == "true"
    assert Config.from_data({"station/transmit": "false"}).station_transmit is False
    assert Config().to_data()["station/transmit"] == "true"
    with pytest.raises(ValueError, match="station/transmit"):
        Config.check("station/transmit", "perhaps")


# ---- the whole daemon -----------------------------------------------------------------------------------------------------------------------

async def test_nothing_reaches_the_radio_while_it_is_off_and_what_waited_goes_when_it_is_on(tmp_path: Path) -> None:
    e = await quick_start(tmp_path, beacon=True, messaging=True, rigstatus=True, own=True, unpaced=True, settings={"digi/enabled": "true", "beacon/interval_min": "30", "station/status": "QRV"})
    await e.until_connected()
    e.ctl.ownobjects.set("LEADER", "object", lat=60.17, lon=24.94, symbol_table="/", symbol_code=">")
    sent = await e.ctl.messaging.send("OH2RDG", "Hello")
    assert sent.attempts == 1
    await idle_for(0.3)
    await e.heard(1, 0.1)
    while await e.heard(1, 0.3):                                            # (what went out while it was on)
        pass
    out_before = len([p for p in await e.packets() if p.direction == "out"])
    assert await e.ctl.save_config(replace(e.ctl.config, station_transmit=False, station_status="QRV again"))      # (the status has changed, so it is due)
    e.now.advance(3 * 3600)                                                 # type: ignore[attr-defined]
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "Moi!", "12"), path="OH2RCH-2*"))
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "?APRSP"), path="OH2RCH-2*"))
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "?APRSD"), path="OH2RCH-2*"))
    e.feed(on_air("OH2XYZ", BUSY, path="WIDE1-1,WIDE2-1"))                  # (the digipeater is on)
    await until(lambda: e.tnc.stats.packets == 4)
    await quiet(e, 0.8)
    assert e.ctl.beacon.last_sent is None and e.ctl.beacon.problem == OFF and e.tnc.stats.digipeated == 0
    record = e.ctl.messaging.get(sent.id)
    assert record is not None and record.state == "sending" and record.attempts == 1, "the message waits, with its attempts"
    assert not e.ctl.beacon.send_now("request") and await e.ctl.rigstatus.send_now() == OFF
    assert len([p for p in await e.packets() if p.direction == "out"]) == out_before, "no frame was even made"
    await switch(e, True)
    await until(lambda: (r := e.ctl.messaging.get(sent.id)) is not None and r.attempts == 2)
    frames = [f.tnc2() for f in await said(e, 3, 3.0)]
    assert any(f.startswith("OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=") for f in frames) and any(":Hello{" in f for f in frames) and any(":>" in f and "QRV again" in f for f in frames)
    assert len([f for f in frames if f.startswith("OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=")]) == 1, "one beacon, not one for each interval that passed"
    assert not any("ack12" in f for f in frames), "the ack that was not sent is not made up afterwards"
    await e.stop()


async def test_a_new_message_a_retry_an_object_and_a_bulletin_are_refused_with_the_code(tmp_path: Path) -> None:
    e = await quick_start(tmp_path, messaging=True, own=True)
    sent = await e.ctl.messaging.send("OH2RDG", "Hello")
    e.ctl.messaging.cancel(sent.id)
    await switch(e, False)
    with pytest.raises(MessagingError) as new:
        await e.ctl.messaging.send("OH2RDG", "Hello again")
    assert (new.value.code, str(new.value)) == ("transmit.off", NOTHING_SENT)
    with pytest.raises(MessagingError) as again:
        e.ctl.messaging.retry(sent.id)
    assert again.value.code == "transmit.off"
    with pytest.raises(OwnError) as obj:
        e.ctl.ownobjects.set("LEADER", "object", lat=60.17, lon=24.94, symbol_table="/", symbol_code=">")
    assert obj.value.code == "transmit.off"
    with pytest.raises(PostError) as bulletin:
        e.ctl.ownbulletins.post("BLN1", "Net tonight")
    assert bulletin.value.code == "transmit.off"
    await e.stop()


async def test_a_message_that_is_being_sent_waits_without_using_up_an_attempt_or_failing(tmp_path: Path) -> None:
    e = await quick_start(tmp_path, messaging=True, unpaced=True)
    sent = await e.ctl.messaging.send("OH2RDG", "Hello")
    assert sent.attempts == 1 and sent.attempts_max == 4
    await said(e)
    await switch(e, False)
    for _ in range(6):                                                      # (far more than its four attempts and their waits)
        e.now.advance(1200)                                                 # type: ignore[attr-defined]
        await idle_for(0.1)
    record = e.ctl.messaging.get(sent.id)
    assert record is not None and (record.state, record.attempts) == ("sending", 1)
    await quiet(e)
    await switch(e, True)
    await until(lambda: (r := e.ctl.messaging.get(sent.id)) is not None and r.attempts >= 2)
    assert (await said(e))[0].tnc2().endswith(":Hello{01}")
    record = e.ctl.messaging.get(sent.id)
    assert record is not None and record.state == "sending", "it goes on with the schedule it had: not failed, and its attempts are the four that are left to make"
    await e.stop()


async def test_a_message_that_was_waiting_for_its_last_ack_does_not_fail_while_it_is_off(tmp_path: Path) -> None:
    e = await quick_start(tmp_path, messaging=True, unpaced=True)
    sent = await e.ctl.messaging.send("OH2RDG", "Hello")
    for step in range(3):
        e.now.advance(1000)                                                 # type: ignore[attr-defined]
        await until(lambda step=step: (r := e.ctl.messaging.get(sent.id)) is not None and r.attempts > step + 1)
    assert e.ctl.messaging.get(sent.id).attempts == 4                      # type: ignore[union-attr]
    await switch(e, False)
    e.now.advance(7200)                                                     # type: ignore[attr-defined]
    await idle_for(0.2)
    assert e.ctl.messaging.get(sent.id).state == "sending"                  # type: ignore[union-attr]
    e.feed(on_air("OH2RDG", b":OH2GBA   :ack" + sent.msg_id.encode(), path="OH2RCH-2*"))      # type: ignore[union-attr]
    await until(lambda: e.ctl.messaging.get(sent.id).state == "acked")      # type: ignore[union-attr]
    await e.stop()


async def test_the_switch_is_kept_in_the_database_and_holds_after_a_restart(tmp_path: Path) -> None:
    first = Env(tmp_path)
    await first.start()
    await switch(first, False)
    await first.stop()
    second = Env(tmp_path)
    await second.start()
    assert second.ctl.config.station_transmit is False and can_transmit(second.ctl.config) == OFF
    assert not second.ctl.beacon.send_now("request")
    await switch(second, True)
    await second.stop()
    third = Env(tmp_path)
    await third.start()
    assert third.ctl.config.station_transmit is True
    await third.stop()


async def test_over_the_socket_the_switch_is_a_setting_and_beacon_now_and_a_message_are_refused_with_the_code(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) >= 7)
    await page.send({"cmd": "set_config", "values": {"station/transmit": "false"}})
    await page.until(lambda: page.topics["config"]["values"]["station/transmit"] == "false")
    for command, name in (({"cmd": "beacon_now"}, "beacon_now"), ({"cmd": "send_message", "to": "OH2RDG", "text": "Hello"}, "send_message")):
        await page.send(command)
        error = await page.expect("error")
        assert (error["text"], error["code"]) == (f"{name}: {NOTHING_SENT}", "transmit.off")
    await page.send({"cmd": "set_config", "values": {"station/transmit": "perhaps"}})
    assert (await page.expect("error"))["text"].startswith("set_config: station/transmit: ")
    await page.send({"cmd": "set_config", "values": {"station/transmit": "true"}})
    await page.until(lambda: page.topics["config"]["values"]["station/transmit"] == "true")
    await e.stop()
