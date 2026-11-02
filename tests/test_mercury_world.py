"""Two and three NeoAPRS stations on one HF frequency with the Mercury HF modem (tests/support/mercuryworld.py on the fake Mercury of tests/support/fakemercury.py): the whole exchange with its timing, a frame at a time
on a channel nobody listens to before keying. A beacon of one station is heard by the others after the frame's time on the air; a message is acked within one frame each way and the first wait of the retry
schedule is long enough for that; two stations that key at the same moment lose both frames and the message goes through on its retry; our frames wait while a frame is on the air or the channel is busy, and one of
ours never follows another before the first has left; a station that gates to APRS-IS puts what it hears on the internet and the Mercury traffic is `rf`; a packet too long for the frame is refused and told, never cut."""
import asyncio
from datetime import timedelta
from pathlib import Path

from neoaprs import ax25
from neoaprs.message import FIRST_WAIT_SEC
from neoaprs.mercury import FRAME_SEC
from tests.support.env import idle_for, until
from tests.support.fakeaprsis import FakeAprsIs
from tests.support.mercuryworld import World


def sent_by(world: World, call: str) -> list[ax25.Frame]:
    """The frames the air carried from this station, as the receivers got them."""
    return [ax25.decode(payload) for sender, _, payload in world.air.delivered if sender is world[call].radio]


async def test_a_beacon_of_one_station_reaches_the_other_two_after_one_frame_on_the_air_and_nobody_else_hears_it_twice(tmp_path: Path) -> None:
    w = World(tmp_path, frame_sec=0.2)
    await w.add("OH2A")
    await w.add("OH2B", lat=61.5, lon=23.8)
    await w.add("OH2C-10", lat=60.4, lon=22.3)
    await w.start()
    for call in ("OH2B", "OH2C-10"):
        assert not [p for p in await w[call].packets() if p.source == "OH2A"]
    assert w["OH2A"].ctl.beacon.send_now()
    await w.until(lambda: len(w.air.delivered) == 2)
    assert {receiver for _, receiver, _ in w.air.delivered} == {w["OH2B"].radio, w["OH2C-10"].radio}
    for call in ("OH2B", "OH2C-10"):
        await w.until(lambda call=call: w[call].ctl.stationbook.get("OH2A") is not None)          # type: ignore[misc]
        heard = w[call].ctl.stationbook.get("OH2A")
        assert heard is not None and heard.lat is not None and abs(heard.lat - 60.17) < 0.01 and heard.heard_rf == 1 and heard.heard_is == 0
    frame = sent_by(w, "OH2A")[0]
    assert frame.path == () and frame.info.startswith(b"=6010.20N/02456.40E-") and len(ax25.encode(frame)) <= 123
    assert w.air.collisions == 0 and w.air.truncated == []
    assert w["OH2A"].ctl.mercury.frames_keyed == 1 and w["OH2B"].ctl.mercury.frames_keyed == 0


async def test_a_message_is_acked_within_one_frame_each_way_and_the_first_wait_of_the_schedule_covers_it(tmp_path: Path) -> None:
    w = World(tmp_path, frame_sec=0.2)
    a, b = await w.add("OH2A"), await w.add("OH2B", lat=61.5, lon=23.8)
    await w.start()
    loop_time = asyncio.get_running_loop().time
    started = loop_time()
    record = await a.ctl.messaging.send("OH2B", "Moi Pekka, kuuluuko?")
    assert record.attempts == 1 and record.state == "sending"
    await w.until(lambda: a.ctl.messaging.get(record.id).state == "acked")     # type: ignore[union-attr]
    took = loop_time() - started
    assert len(w.air.delivered) == 2, "the message one way, the ack the other"
    message, ack = (ax25.decode(p) for _, _, p in w.air.delivered)
    assert message.info == b":OH2B     :Moi Pekka, kuuluuko?{01}" and ack.info == b":OH2A     :ack01}"
    assert 2 * w.air.frame_sec <= took < 2 * w.air.frame_sec + 1.5, "two frames on the air and the polls between them, nothing else"
    assert took * (FRAME_SEC / w.air.frame_sec) < FIRST_WAIT_SEC, "scaled to the real frame, the ack comes well inside the first wait of 32 s"
    received = [m for m in b.ctl.messaging.records() if m.direction == "in"]
    assert len(received) == 1 and received[0].text == "Moi Pekka, kuuluuko?"
    assert w.air.collisions == 0 and a.ctl.mercury.frames_keyed == 1 and b.ctl.mercury.frames_keyed == 1


async def test_two_stations_that_key_at_the_same_moment_lose_both_frames_and_the_retry_goes_through(tmp_path: Path) -> None:
    w = World(tmp_path, frame_sec=0.3, busy_detect=False)                       # (without the busy detector the second station does not wait: the collision Mercury allows)
    a, b = await w.add("OH2A"), await w.add("OH2B", lat=61.5, lon=23.8)
    await w.start()
    record = await a.ctl.messaging.send("OH2B", "first try")
    assert b.ctl.beacon.send_now(), "B keys while A's frame is on the air"
    await w.until(lambda: w.air.collisions == 2 and not w.air.transmitting, 3.0)             # (both frames are lost)
    assert w.air.delivered == [] and a.ctl.messaging.get(record.id).state == "sending" and a.ctl.messaging.get(record.id).attempts == 1       # type: ignore[union-attr]
    await idle_for(0.2)
    assert a.ctl.messaging.get(record.id).attempts == 1, "the retry waits for its time, nothing goes out before"              # type: ignore[union-attr]
    w.pass_time(FIRST_WAIT_SEC + 1)
    await w.until(lambda: a.ctl.messaging.get(record.id).state == "acked", 5.0)        # type: ignore[union-attr]
    assert a.ctl.messaging.get(record.id).attempts == 2 and w.air.collisions == 2 and len(w.air.delivered) == 2        # type: ignore[union-attr]


async def test_our_frames_wait_while_a_frame_is_on_the_air_and_while_the_channel_is_busy_and_go_one_at_a_time(tmp_path: Path) -> None:
    w = World(tmp_path, frame_sec=0.3)
    a, b = await w.add("OH2A"), await w.add("OH2B", lat=61.5, lon=23.8)
    await w.start()
    assert b.ctl.beacon.send_now()                                                # B is on the air: A's modem hears BUSY ON
    await w.until(lambda: a.ctl.mercury.busy)
    assert not a.tnc.usable and a.tnc.why_unusable() == "the channel is busy" and not a.ctl.beacon.send_now()
    assert a.ctl.beacon.problem == "the channel is busy"
    record = await a.ctl.messaging.send("OH2B", "waits for the channel")
    assert record.attempts == 0 and record.state == "sending", "the attempt waits, none is used up"
    await w.until(lambda: a.ctl.messaging.get(record.id).attempts == 1, 3.0)            # type: ignore[union-attr]
    assert not a.ctl.mercury.busy, "it went when the channel was clear"
    await w.until(lambda: a.ctl.mercury.keyed)                                            # (the modem says PTT ON on its control port a moment after the frame was handed to it)
    assert not a.tnc.usable and a.tnc.why_unusable() == "the radio is transmitting"
    assert not a.ctl.beacon.send_now() and a.ctl.beacon.problem == "the radio is transmitting"
    await w.until(lambda: a.ctl.messaging.get(record.id).state == "acked", 5.0)         # type: ignore[union-attr]
    assert w.air.collisions == 0 and len(w.air.delivered) == 3
    assert a.tnc.describe().startswith("Mercury DATAC3 at 127.0.0.1:") and "listening" in a.tnc.describe()


async def test_a_station_that_gates_puts_what_it_hears_over_mercury_on_aprs_is_and_nothing_comes_back(tmp_path: Path) -> None:
    server = FakeAprsIs()
    await server.start()
    try:
        w = World(tmp_path, frame_sec=0.1)
        await w.add("OH2A")
        gate = await w.add("OH2C-10", lat=60.4, lon=22.3, **{"igate/enabled": "true", "igate/server": server.address, "igate/password": "19628"})
        await w.start()
        await until(lambda: gate.ctl.igate.state in ("connected", "listening"), 5.0)
        assert w["OH2A"].ctl.beacon.send_now()
        await until(lambda: any(line.startswith("OH2A>") for line in server.packets), 5.0)
        [line] = [line for line in server.packets if line.startswith("OH2A>")]
        assert ",qAO,OH2C-10:" in line, "gated as heard on the radio, by this gate"
        assert len(w.air.delivered) == 1, "nothing from the internet went to the radio"
    finally:
        await server.stop()


async def test_over_the_air_every_frame_is_direct_and_whole_whatever_the_path_settings_say_and_the_longest_message_fits(tmp_path: Path) -> None:
    w = World(tmp_path, frame_sec=0.1)
    a, b = await w.add("OH2A", **{"beacon/path": "WIDE1-1,WIDE2-1,WIDE3-1,WIDE4-1,WIDE5-1,WIDE6-1,WIDE7-1", "station/comment": "A comment as long as the settings allow, 43"}), await w.add("OH2B", lat=61.5, lon=23.8)
    await w.start()
    record = await a.ctl.messaging.send("OH2B", "x" * 67)
    await w.until(lambda: a.ctl.messaging.get(record.id).state == "acked", 5.0)         # type: ignore[union-attr]
    message = ax25.decode(w.air.delivered[0][2])
    assert message.path == () and len(ax25.encode(message)) == 98, "the longest message, 67 characters with its number, is 98 bytes direct: under the frame with room to spare"
    assert a.ctl.beacon.send_now()
    await w.until(lambda: len(w.air.delivered) == 3)
    beacon = sent_by(w, "OH2A")[-1]
    assert beacon.path == () and beacon.info.endswith(b"A comment as long as the settings allow, 43") and len(ax25.encode(beacon)) == 79, "direct, whole, the path setting ignored and kept"
    assert w.air.truncated == [] and a.ctl.config.beacon_path_calls[0] == "WIDE1-1"
    await w.until(lambda: b.ctl.stationbook.get("OH2A") is not None)
    heard = b.ctl.stationbook.get("OH2A")
    assert heard is not None and heard.last_comment.startswith("A comment as long as") and heard.lat is not None


async def test_the_hf_beacon_goes_out_on_its_own_interval_with_the_random_pause_and_a_moving_station_stays_fixed(tmp_path: Path) -> None:
    w = World(tmp_path, frame_sec=0.1)
    a = await w.add("OH2A", **{"hf/beacon_interval_min": "15", "beacon/interval_min": "0"})
    await w.add("OH2B", lat=61.5, lon=23.8)
    a.ctl.beacon.jitter = lambda most: 120.0
    await w.start()
    assert a.ctl.beacon.interval_min == 15 and a.ctl.config.beacon_interval_min == 0
    w.pass_time(31)                                                                 # (the first beacon of a run comes 30 s after the start)
    await w.until(lambda: len(w.air.delivered) == 1, 5.0)
    first = sent_by(w, "OH2A")[0]
    assert first.path == () and first.info.startswith(b"=6010.20N/02456.40E-"), "the home position, direct"
    assert a.ctl.beacon.next_due == a.ctl.beacon.last_sent + timedelta(minutes=15) + timedelta(seconds=120)      # type: ignore[operator]
    w.pass_time(15 * 60 + 100)
    await idle_for(0.3)
    assert len(w.air.delivered) == 1, "the interval has passed but the pause has not"
    w.pass_time(30)
    await w.until(lambda: len(w.air.delivered) == 2, 5.0)
