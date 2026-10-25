"""The queries and the message board inside the whole daemon, the radio a pseudo-terminal: a query to us gives the right frame on the line, a message to a bulletin or a group is on the board and not
acked, ?APRSS answers with the status last sent, and the controller starts and stops the parts."""
import logging
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs.clock import utc
from neoaprs.bulletin import BulletinRecord
from tests.support.air import message_info, on_air, said
from tests.support.env import Env, idle_for, quick_start, until


async def started(tmp_path: Path, **changes: object) -> Env:
    e = await quick_start(tmp_path, messaging=True, rigstatus=True)
    if changes:
        assert await e.ctl.save_config(replace(e.ctl.config, **changes))    # type: ignore[arg-type]
    return e


async def heard(e: Env, packets: int) -> None:
    """The radio has been read until this many packets (said() blocks the loop, so it comes after)."""
    await until(lambda: e.tnc.stats.packets == packets)


# ---- the queries ---------------------------------------------------------------------------------------------------------------------------------

async def test_aprsp_gives_the_beacons_position_frame_on_the_line(tmp_path: Path) -> None:
    e = await started(tmp_path)
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "?APRSP"), path="OH2RCH-2*"))
    await heard(e, 1)
    [frame] = await said(e)
    assert frame.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=6010.20N/02456.40E-NeoAPRS" and frame == e.ctl.beacon.frame()
    sent = [p for p in await e.packets() if p.direction == "out"]
    assert [p.kind for p in sent] == ["position"], "it is in the packet log as a packet we sent"
    await e.stop()


async def test_aprsp_goes_by_the_path_the_operator_set_for_the_asker(tmp_path: Path) -> None:
    e = await started(tmp_path)
    await e.ctl.prefbook.set_path("OH2RDG", "OH2RCH-2")
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "?APRSP", "7"), path="OH2RCH-2*"))
    await heard(e, 1)
    frames = await said(e, 2)                                               # (the query carries an id, so it is acked too, by the same path)
    assert sorted(f.tnc2() for f in frames) == ["OH2GBA>APZNEO,OH2RCH-2::OH2RDG   :ack7", "OH2GBA>APZNEO,OH2RCH-2:=6010.20N/02456.40E-NeoAPRS"]
    await e.stop()


async def test_the_answer_to_an_rf_only_asker_ends_with_rfonly_and_one_that_cannot_is_not_sent(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    e = await started(tmp_path)
    await e.ctl.prefbook.set_rf_only("OH2RDG", True)
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "?APRSP", "7"), path="OH2RCH-2*"))
    await heard(e, 1)
    frames = await said(e, 2)                                               # (the ack of the numbered query goes the same way)
    assert sorted(f.tnc2() for f in frames) == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1,RFONLY::OH2RDG   :ack7", "OH2GBA>APZNEO,WIDE1-1,WIDE2-1,RFONLY:=6010.20N/02456.40E-NeoAPRS"]
    await e.ctl.prefbook.set_path("OH2RDG", ",".join(f"OH2RC{n}" for n in range(8)))
    e.now.advance(600)                                                      # type: ignore[attr-defined]
    with caplog.at_level(logging.WARNING, "neoaprs.queries"):
        e.feed(on_air("OH2RDG", message_info("OH2GBA", "?APRSP", "8"), path="OH2RCH-2*"))
        await heard(e, 2)
    assert await said(e, 1, 0.3) == [] and any("path too long for RF only" in r.getMessage() for r in caplog.records)
    await e.stop()


async def test_aprss_gives_the_status_report_last_sent_and_nothing_before_one_went(tmp_path: Path) -> None:
    e = await started(tmp_path)
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "?APRSS")))
    await heard(e, 1)
    assert await said(e, 1, 0.3) == []
    assert await e.ctl.save_config(replace(e.ctl.config, station_status="QRV 145.500"))
    await until(lambda: e.ctl.rigstatus.last_text == "QRV 145.500")
    [sent] = await said(e)
    assert sent.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:>211200zQRV 145.500", "the status goes out by itself, once"
    e.now.advance(60)                                                       # type: ignore[attr-defined]  (the same query is answered again after half a minute)
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "?APRSS")))
    await heard(e, 2)
    [frame] = await said(e)
    assert frame.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:>211201zQRV 145.500"
    await e.stop()


async def test_aprsd_gives_a_message_to_the_asker_with_the_calls_heard_direct_in_the_last_hour(tmp_path: Path) -> None:
    e = await started(tmp_path)
    e.feed(on_air("OH2PU-9", b">hello", path=""))
    await heard(e, 1)
    e.now.advance(120)                                                      # type: ignore[attr-defined]
    e.feed(on_air("OH2RCH-2", b">digi", path=""))
    e.feed(on_air("OH2FAR", b">far away", path="OH2RCH-2*"))
    await heard(e, 3)
    e.now.advance(120)                                                      # type: ignore[attr-defined]
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "?APRSD"), path="OH2RCH-2*"))
    await heard(e, 4)
    [frame] = await said(e)
    assert frame.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG   :Directs= OH2RCH-2 OH2PU-9"
    e.now.advance(3600)                                                     # type: ignore[attr-defined]
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "?APRSD"), path="OH2RCH-2*"))
    await heard(e, 5)
    [later] = await said(e)
    assert later.tnc2().endswith(":Directs= none"), "an hour on, none of them was heard direct in the last hour"
    await e.stop()


async def test_aprst_and_ping_give_the_path_the_query_came_by(tmp_path: Path) -> None:
    e = await started(tmp_path)
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "?APRST"), destination="APZNEO", path="WIDE1*,OH2RCH-2*,WIDE2-1"))
    await heard(e, 1)
    [frame] = await said(e)
    assert frame.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG   :OH2RDG>APZNEO,WIDE1*,OH2RCH-2*,WIDE2-1:"
    e.now.advance(60)                                                       # type: ignore[attr-defined]
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "?PING?"), destination="APRS", path=""))
    await heard(e, 2)
    [ping] = await said(e)
    assert ping.tnc2().endswith(":OH2RDG>APRS:")
    await e.stop()


async def test_the_general_query_gives_our_position_after_the_wait_and_not_again_for_ten_minutes(tmp_path: Path) -> None:
    e = await started(tmp_path)
    e.ctl.queries._delay = lambda: 0.1                                     # (0 to 120 s in the field)
    e.feed(on_air("OH2RDG", b"?APRS?", path="OH2RCH-2*"))
    await heard(e, 1)
    await idle_for(0.4)                                                # (said() blocks the loop: the wait runs out before it is read)
    [frame] = await said(e, 1, 2.0)
    assert frame.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=6010.20N/02456.40E-NeoAPRS"
    e.feed(on_air("OH2ABC", b"?APRS?"))
    await heard(e, 2)
    await idle_for(0.4)
    assert await said(e, 1, 0.2) == []
    e.now.advance(601)                                                      # type: ignore[attr-defined]
    e.feed(on_air("OH2ABC", message_info("ALL", "?APRS?")))                 # (a message with that text is no query)
    await heard(e, 3)
    await idle_for(0.4)
    assert await said(e, 1, 0.2) == []
    e.feed(on_air("OH2ABC", b"?APRS?V60.17,24.94,0010"))
    await heard(e, 4)
    await idle_for(0.4)
    assert len(await said(e, 1, 2.0)) == 1
    await e.stop()


async def test_a_query_to_somebody_else_is_not_answered(tmp_path: Path) -> None:
    e = await started(tmp_path)
    e.feed(on_air("OH2RDG", message_info("OH2XYZ", "?APRSP")))
    await heard(e, 1)
    assert await said(e, 1, 0.3) == []
    await e.stop()


# ---- the status is not tied to the beacon -------------------------------------------------------------------------------------------------------

async def test_the_beacon_is_not_followed_by_the_status_report(tmp_path: Path) -> None:
    e = await started(tmp_path, station_status="On the road")
    e.feed(on_air("OH2ABC", b">hello"))                                     # (a KISS frame heard: the TNC is in KISS mode and takes frames, the status waited for that)
    await heard(e, 1)
    await until(lambda: e.ctl.rigstatus.last_text == "On the road")          # (said() blocks the loop: the status is on the line before it is read)
    [status] = await said(e)
    assert status.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:>211200zOn the road"
    assert e.ctl.beacon.send_now()
    [beacon] = await said(e)
    assert beacon.info.startswith(b"=6010.20N")
    assert await said(e, 1, 0.3) == [], "no status after the beacon"
    assert [p.kind for p in reversed(await e.packets()) if p.direction == "out"] == ["status", "position"]
    await e.stop()


# ---- the board -----------------------------------------------------------------------------------------------------------------------------------

async def test_a_bulletin_is_on_the_board_in_the_database_and_not_acked_or_overheard(tmp_path: Path) -> None:
    e = await started(tmp_path)
    e.feed(on_air("OH2XYZ", message_info("BLN1", "Road closed at Kaivopuisto", "5")))
    e.feed(on_air("OH2XYZ", message_info("BLN3HAMS", "Net tonight 20:00")))
    e.feed(on_air("OH2ABC", message_info("QST", "Club news")))
    await heard(e, 3)
    await until(lambda: len(e.ctl.bulletins.records()) == 3)
    assert await said(e, 1, 0.3) == [], "nothing is acked"
    assert sorted((b.sender, b.slot, b.kind, b.group) for b in e.ctl.bulletins.records()) == [
        ("OH2ABC", "QST", "group", ""), ("OH2XYZ", "BLN1", "bulletin", ""), ("OH2XYZ", "BLN3HAMS", "group", "HAMS")]
    assert e.ctl.messaging.records() == [] and await e.ctl.messagelog.recent(overheard=True) == []
    await e.settled()
    assert sorted(b.key for b in await e.ctl.bulletinlog.all()) == ["OH2ABC/QST", "OH2XYZ/BLN1", "OH2XYZ/BLN3HAMS"]
    await e.stop()


async def test_a_restart_finds_the_board_and_nothing_ages_out(tmp_path: Path) -> None:
    first = await started(tmp_path)
    first.feed(on_air("OH2XYZ", message_info("BLN1", "Road closed")))
    await until(lambda: len(first.ctl.bulletins.records()) == 1)
    await first.stop()
    second = Env(tmp_path, clock=first.now)
    await second.start()
    assert [b.key for b in second.ctl.bulletins.records()] == ["OH2XYZ/BLN1"]
    second.now.advance(30 * 86400)                                          # type: ignore[attr-defined]
    await idle_for(0.2)
    assert [b.key for b in second.ctl.bulletins.records()] == ["OH2XYZ/BLN1"]
    await second.stop()


async def test_the_daily_prune_removes_no_bulletin_however_old(tmp_path: Path) -> None:
    e = await started(tmp_path)
    old = BulletinRecord("OH2XYZ", "BLNA", "", "announcement", "ancient", utc(2026, 9, 1), utc(2026, 9, 1))
    new = BulletinRecord("OH2ABC", "BLNA", "", "announcement", "yesterday", e.now() - timedelta(days=1), e.now() - timedelta(days=1))
    e.ctl.bulletinlog.save(old)
    e.ctl.bulletinlog.save(new)
    await e.settled()
    await e.ctl.prune()
    assert sorted(b.text for b in await e.ctl.bulletinlog.all()) == ["ancient", "yesterday"]
    await e.stop()


# ---- ?APRSH and QRU, through the whole daemon -----------------------------------------------------------------------------------------------------

async def test_aprsh_tells_from_the_packet_log_when_the_station_was_heard(tmp_path: Path) -> None:
    e = await quick_start(tmp_path, messaging=True)
    for count, wait in enumerate((70 * 60, 0, 0), start=1):                     # (one packet, seventy minutes pass, two more)
        e.feed(on_air("OH2PU-9", b">hello", path="OH2RCH-2*"))
        await heard(e, count)
        e.now.advance(wait)                                                     # type: ignore[attr-defined]
    assert e.ctl.packetlog.db is not None
    await e.ctl.packetlog.db.barrier()
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "?APRSH OH2PU-9")))
    await heard(e, 4)
    [frame] = await said(e)
    assert frame.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG   :OH2PU-9 HEARD: 2 1 . . . . . ."
    await e.stop()


async def test_a_message_to_qru_is_answered_acked_and_not_kept_while_we_serve_a_group_and_is_overheard_otherwise(tmp_path: Path) -> None:
    e = await quick_start(tmp_path, messaging=True, own=True, unpaced=True)
    e.feed(on_air("OH2RDG", message_info("QRU", "INFO", "5"), path="OH2RCH-2*"))
    await heard(e, 1)
    assert await said(e, 1, 0.3) == []
    await until(lambda: len(e.ctl.messaging.records()) == 1)
    assert [(m.state, m.to_call, m.text) for m in e.ctl.messaging.records()] == [("overheard", "QRU", "INFO")], "no group is served: it is a message to another station"
    e.ctl.ownobjects.set("PUB", "object", 60.17, 24.94, "/", "r", "Pub", qru_group="FOOD", on_request=True)
    e.now.advance(60)                                                           # type: ignore[attr-defined]
    e.feed(on_air("OH2RDG", message_info("QRU", "INFO", "6"), path="OH2RCH-2*"))
    await heard(e, 2)
    frames = await said(e, 2)
    assert sorted(f.tnc2() for f in frames) == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG   :ack6", "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG   :de OH2GBA:FOOD(1) Max 5@50km"]
    await idle_for(0.1)
    assert len(e.ctl.messaging.records()) == 1 and await said(e, 1, 0.3) == [], "the object is on request: it is never beaconed"
    await e.stop()
