"""The beacon Off (`beacon/interval_min` 0, for a fixed and a moving station alike) on the whole daemon with a fake radio: no automatic beacon and no automatic status report go out whatever is due, and everything else does, because Off is not
RX only (tests/test_receive_only.py): a message and its retries, the ack of a message heard, the answer to a query, our own objects and the fill-in digipeater. The beacon and the status that were held back go out when it is on."""
import asyncio
from dataclasses import replace
from pathlib import Path

from tests.support.air import message_info, on_air, said
from tests.support.env import Env, idle_for, quick_start, until

BUSY = b"!6010.20N/02456.40E-test"
BEACON = "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:="


async def started(tmp_path: Path, **settings: str) -> Env:
    e = await quick_start(tmp_path, beacon=True, messaging=True, rigstatus=True, own=True, unpaced=True, settings={"digi/enabled": "true", "beacon/interval_min": "0", "station/status": "QRV", **settings})
    await e.until_connected()
    return e


async def test_with_the_beacon_off_no_beacon_and_no_status_go_but_a_message_an_ack_an_answer_an_object_and_a_digipeated_packet_do(tmp_path: Path) -> None:
    e = await started(tmp_path)
    sent = await e.ctl.messaging.send("OH2RDG", "Hello")
    e.ctl.ownobjects.set("LEADER", "object", lat=60.17, lon=24.94, symbol_table="/", symbol_code=">")
    e.now.advance(3 * 3600)                                                 # type: ignore[attr-defined]
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "Moi!", "12"), path="OH2RCH-2*"))
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "?APRSP"), path="OH2RCH-2*"))
    e.feed(on_air("OH2XYZ", BUSY, path="WIDE1-1,WIDE2-1"))
    await until(lambda: e.tnc.stats.packets == 3)
    frames: list[str] = []
    wanted = (lambda f: ":Hello{" in f, lambda f: ":ack12" in f, lambda f: f.startswith(BEACON) and "OH2RDG" not in f, lambda f: ";LEADER" in f, lambda f: f.startswith("OH2XYZ>"))
    deadline = asyncio.get_running_loop().time() + 10.0
    while not all(any(w(f) for f in frames) for w in wanted) and asyncio.get_running_loop().time() < deadline:
        frames += [f.tnc2() for f in await said(e, 1, 0.5)]
    frames += [f.tnc2() for f in await said(e, 99, 0.5)]
    assert all(any(w(f) for f in frames) for w in wanted), frames          # (the message, its ack, the answer to ?APRSP with our position, the object, the digipeated copy)
    assert e.ctl.beacon.last_sent is None and e.ctl.rigstatus.last_sent_at is None, "the timers did not send, however much time went by"
    assert not any(":>" in f for f in frames), "no status report"
    record = e.ctl.messaging.get(sent.id)
    assert record is not None and record.attempts >= 1
    await e.stop()


async def test_the_requests_still_send_while_the_beacon_is_off_for_it_is_the_timer_that_is_off(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    e.ctl.rigstatus.poll_sec = 3600
    await e.start()
    await e.until_usable()
    assert await e.ctl.save_config(replace(e.ctl.config, beacon_interval_min=0, station_status="QRV", status_source="text"))
    page = await e.ws()
    await page.until(lambda: len(page.of("status")) >= 1)
    for command in ("beacon_now", "status_now"):
        await page.send({"cmd": command})
    frames: list[str] = []
    deadline = asyncio.get_running_loop().time() + 10.0
    while not (any(f.startswith(BEACON) for f in frames) and any(":>" in f and "QRV" in f for f in frames)) and asyncio.get_running_loop().time() < deadline:
        frames += [f.tnc2() for f in await said(e, 1, 0.5)]
    assert any(f.startswith(BEACON) for f in frames) and any(":>" in f and "QRV" in f for f in frames), frames
    assert not [m for m in page.messages if m.get("type") == "error"], "no refusal"
    await e.stop()


async def test_the_beacon_and_the_status_that_were_held_back_go_when_the_beacon_is_on(tmp_path: Path) -> None:
    e = await started(tmp_path)
    e.now.advance(3 * 3600)                                                 # type: ignore[attr-defined]
    await idle_for(0.3)
    assert await e.heard(1, 0.3) == b""
    assert await e.ctl.save_config(replace(e.ctl.config, beacon_interval_min=30))
    frames: list[str] = []
    deadline = asyncio.get_running_loop().time() + 10.0
    while not (any(f.startswith(BEACON) for f in frames) and any(":>" in f and "QRV" in f for f in frames)) and asyncio.get_running_loop().time() < deadline:
        frames += [f.tnc2() for f in await said(e, 1, 0.5)]
    assert any(f.startswith(BEACON) for f in frames) and any(":>" in f and "QRV" in f for f in frames), frames
    await e.stop()


async def test_a_moving_station_with_the_interval_at_zero_sends_nothing_by_itself(tmp_path: Path) -> None:
    e = await started(tmp_path, **{"gps/source": "gpsd", "gps/host": "127.0.0.1:1"})
    e.now.advance(3 * 3600)                                                 # type: ignore[attr-defined]
    await idle_for(0.3)
    assert e.ctl.beacon.last_sent is None and e.ctl.beacon.next_due is None
    assert not e.ctl.beacon.send_now("request") and e.ctl.beacon.problem != "the beacon is off", "Beacon now is asked for: it fails for the missing fix, not for the beacon being off"
    await e.stop()
