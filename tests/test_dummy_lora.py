"""The Dummy LoRa radio, the proof that a third kind of radio is a description, a driver and its texts (plan §2 and step 7; neoaprs/radiotypes/dummylora.py, neoaprs/dummylorascene.py, neoaprs/dummyworlds.py,
neoaprs/tnc2line.py): TNC2 text read into AX.25 frames and written back, the LoRa packet's header and its 255 bytes, a board's lines cut and read with what is no packet told apart; the type of the kind `lora`
with the limits and the choices of LoRa; a world of made-up stations round the station on the Q prefix, the iGate that repeats WIDE1-1, the home station that answers a message, each frame with an SNR and a
strength in what a board measures, a world of its own for each radio; the line that hears that world in text and puts what we send on its made-up air in text; and a daemon with a Dummy LoRa radio added from
the page beside the FM radio: it runs, its stations are heard on it with their readings, its beacon and a message go out on it in text, the message is acked, and the topic `radios` tells its row."""
import asyncio
import logging
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs import ax25, dummyline
from neoaprs.aprsmessage import parse_message
from neoaprs.clock import utc
from neoaprs.dummyscene import call_of
from neoaprs.dummylorascene import ACK_AFTER_SEC, HELLO, IGATE, RSSI_RANGE_DBM, SNR_RANGE_DB, LoraScene, board_air, board_line
from neoaprs.dummylorascene import calls as lora_calls
from neoaprs.dummyworlds import DummyLoraPort, made_up_calls
from neoaprs.dummyframes import air
from neoaprs.radiorules import LORA, rules_of
from neoaprs.radiotype import Allowed, Can, Limits
from neoaprs.radiotypes import DEFAULT_TYPE, kind_fields, recommended_path, type_of, types_of
from neoaprs.services.radioset import fit_frame
from neoaprs.source import Source
from neoaprs.tnc import Tnc
from neoaprs.tnc2line import HEADER, MAX_LINE, MAX_PACKET, MAX_TEXT, LineReader, Tnc2Error, air_of, fits, frame_of, from_air, read_line, text_of
from neoaprs.tncdriver import PROFILES, TncDriver
from neoaprs.tncprofile import DUMMY_LORA
from tests.support.clock import FixedClock
from tests.support.env import Env, until_started
from tests.test_dummy import refuse_the_world
from tests.test_radios_wire import added

START = utc(2026, 11, 15, 12, 0, 0)
HELSINKI = (60.17, 24.94)
ME = "OH2GBA"


@pytest.fixture
def fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dummyline, "TICK_SEC", 0.01)


def play(scene: LoraScene, seconds: int, step: int = 5) -> list[tuple[int, ax25.Frame]]:
    return [(t, f) for t in range(0, seconds + 1, step) for f in scene.due(START + timedelta(seconds=t))]


def from_us(info: bytes, path: str = "WIDE1-1") -> ax25.Frame:
    return air(ME, info, path, "APNX01")


# ---- TNC2 text

def test_a_packets_text_is_read_into_the_frame_it_is_and_written_back_byte_for_byte() -> None:
    for text in (b"OH2GBA-7>APLRT1,WIDE1-1:!6010.00N/02456.00E>", b"Q9TRK-7>APLRT1,Q9LRG-10*:=/0)dITh.'>9O[LoRa tracker", b"OH2GBA>APRS::Q9KOT    :Hello{12", b"A>B:",
                 "Q9BKE-12>APLRT1:>Pyöräilemässä".encode()):
        frame = frame_of(text)
        assert text_of(frame) == text and ax25.decode(ax25.encode(frame)) == frame, text
    frame = frame_of(b"Q1ABC>APRS,Q2DIG,Q7DIG*,WIDE2-1:>status")
    assert [a.repeated for a in frame.path] == [True, True, False], "AX.25 marks every digipeater up to the starred one"
    assert text_of(frame) == b"Q1ABC>APRS,Q2DIG,Q7DIG*,WIDE2-1:>status", "TNC2 text stars only the last one"
    assert frame_of("Q9BKE-12>APLRT1:>Pyöräilemässä".encode()).info == ">Pyöräilemässä".encode(), "the information field is the bytes it came as (UTF-8 here), never decoded"


def test_a_text_that_cannot_be_an_ax25_frame_is_refused_with_its_reason() -> None:
    for text, why in ((b"OH2ABCDE>APRS:x", "1 to 6 characters"), (b"OH2GBA-16>APRS:x", "SSID above 15"), (b"OH2GBA*>APRS:x", "only a digipeater"), (b"A>B,1,2,3,4,5,6,7,8,9:x", "at most 8"),
                      (b"no packet here", "no SRC>DST")):
        with pytest.raises(Tnc2Error, match=why):
            frame_of(text)


def test_a_lora_packet_is_the_header_and_the_text_and_at_most_255_bytes() -> None:
    frame = from_us(b"!6010.00N/02456.00E-")
    packet = air_of(frame)
    assert packet == b"<\xff\x01" + text_of(frame) and packet.startswith(HEADER) and from_air(packet) == frame and fits(packet)
    with pytest.raises(Tnc2Error, match="does not begin with the header"):
        from_air(text_of(frame))
    long = from_us(b">" + b"x" * (MAX_PACKET - len(air_of(from_us(b">")))))
    assert len(air_of(long)) == MAX_PACKET and fits(air_of(long)) and not fits(air_of(from_us(long.info + b"x")))


def test_a_boards_lines_are_cut_at_each_line_feed_and_told_apart_into_packets_packets_that_are_none_and_its_own_lines() -> None:
    reader = LineReader()
    assert reader.feed(b"Q9KOT>APLRT1,WIDE1-1:=6011.71N/02449.36E-Hom") == [], "a piece of a line waits for the rest"
    lines = reader.feed(b"e\r\n\r\n[LoRa] RSSI -104 dBm\nOH2ABCDE>APRS:too long a call\r\nQ9TRK-7>APLRT1:>ok\n")
    assert [line.text for line in lines] == [b"Q9KOT>APLRT1,WIDE1-1:=6011.71N/02449.36E-Home", b"[LoRa] RSSI -104 dBm", b"OH2ABCDE>APRS:too long a call", b"Q9TRK-7>APLRT1:>ok"]
    packet, log, refused, last = lines
    assert packet.frame is not None and str(packet.frame.source) == "Q9KOT" and packet.why == ""
    assert log.frame is None and log.why == "", "a line of the board's own is no packet and no fault"
    assert refused.frame is None and "not an AX.25 address" in refused.why
    assert last.frame is not None and last.frame.info == b">ok"
    assert read_line(b"Q9KOT>APRS:x").frame is not None and len(LineReader().feed(b"x" * 5000)) == 1, "a line that never ends is cut off, not held for ever"


def test_a_line_longer_than_any_lora_packet_is_no_packet_and_the_rest_of_a_line_cut_off_is_no_line_of_its_own() -> None:
    head = b"OH2GBA>APZNEO:>"
    assert MAX_TEXT == MAX_PACKET - len(HEADER) == 252
    assert read_line(head + b"x" * (MAX_TEXT - len(head))).frame is not None, "252 bytes of text are a packet"
    over = read_line(head + b"x" * (MAX_TEXT + 1 - len(head)))
    assert over.frame is None and "longer than any LoRa packet" in over.why
    reader = LineReader()
    long = head + b"y" * (1100 - len(head))
    lines = [line for i in range(0, len(long), 100) for line in reader.feed(long[i:i + 100])] + reader.feed(b"\r\nQ9KOT>APLRT1:>after\n")
    assert [(len(line.text), line.frame is None, "longer than any LoRa packet" in line.why) for line in lines] == [(MAX_LINE, True, True), (len(b"Q9KOT>APLRT1:>after"), False, False)], \
        "the cut line is refused once, its rest is dropped up to its line feed, and the next line is read"
    whole = LineReader().feed(long + b"\nQ9KOT>APLRT1:>after\n")
    assert [line.frame is None for line in whole] == [True, False] and len(whole[0].text) == MAX_LINE, "the same when the line comes whole"


# ---- the type

def test_the_dummy_lora_type_is_of_the_kind_lora_with_the_limits_and_the_choices_of_lora_and_nothing_to_find_or_tune() -> None:
    t = type_of("dummy-lora")
    assert (t.kind, t.transport, t.driver, t.profile, t.text, t.dummy) == ("lora", "dummy", "tnc", "dummy-lora", "radio.type.dummy-lora", True)
    assert types_of("lora")[-1] == t and DEFAULT_TYPE["lora"] == "lora-tcp", "the Dummy is last of its kind; a new LoRa radio is the board on the network (tests/test_lora_types.py)"
    assert t.limits == Limits(250, 30, 300, 20, 252, max_kiss=256), "a frame of 250 bytes, 252 of text and 256 in KISS, the timed beacon from 30 minutes with a pause of up to 300 s, up to 20 s before a retry"
    hf = type_of("mercury").limits
    assert (t.limits.beacon_min_min, t.limits.beacon_jitter_sec, t.limits.retry_jitter_sec) >= (hf.beacon_min_min, hf.beacon_jitter_sec, hf.retry_jitter_sec), \
        "its timed beacon goes no more often than an HF radio's (a moving station's SmartBeaconing, which HF has not, goes by its own rates)"
    assert t.allowed == Allowed(paths=True, digipeat=False, smart_beacon=True, gateway_heard=True, shared_channel=False), "no digipeating by us: the network's iGates repeat WIDE1-1"
    assert t.can == Can(False, False, False, False, False, False, False)
    assert [f.key for f in t.fields] == [f.key for f in kind_fields("lora") if f.key in ("beacon", "path", "digipeat")] == ["beacon", "path"], "no digipeater to turn on"
    assert t.recommended_path == recommended_path("lora") == "WIDE1-1" and recommended_path("fm") == recommended_path("hf") == "", "FM and HF go by the station's symbol"
    assert rules_of(t) == LORA == DUMMY_LORA.rules and PROFILES[t.profile] is DUMMY_LORA and DUMMY_LORA.readings == ("snr", "rssi") and (DUMMY_LORA.max_frame, DUMMY_LORA.max_text) == (250, MAX_TEXT)


# ---- the world

def test_the_stations_are_on_the_q_prefix_round_the_station_and_the_igate_repeats_what_asks_for_wide1_1() -> None:
    frames = play(LoraScene(HELSINKI, START), 1200)
    calls = {str(f.source) for _, f in frames}
    assert calls == {IGATE, "Q9KOT", "Q9TRK-7", "Q9BKE-12"} and all(c.startswith("Q") for c in calls)
    firsts = {str(f.source): t for t, f in reversed(frames)}
    assert max(firsts.values()) <= 45, "every station is heard within the first minute"
    for _, frame in frames:
        assert len(board_air(frame) or b"") <= MAX_PACKET and from_air(board_air(frame) or b"") == frame
        if frame.path and frame.path[0].repeated:
            assert str(frame.path[0]) == IGATE + "*" and frame.path[1:] == (), "the iGate takes the place of WIDE1-1"
        elif str(frame.source) != IGATE:
            assert frame.path == (ax25.Address("WIDE1", 1),)
    repeats = [f for _, f in frames if f.path and f.path[0].repeated]
    assert {str(f.source) for f in repeats} == calls - {IGATE}, "each station's frames come again from the iGate"
    positions = [f for _, f in frames if f.info[:1] == b"="]
    assert positions and any("Pyöräilemässä".encode() in f.info for f in positions)


def test_each_frame_has_an_snr_and_a_strength_a_board_measures_the_repeat_the_igates() -> None:
    scene = LoraScene(HELSINKI, START)
    for _, frame in play(scene, 1200):
        reading = scene.reading_of(frame)
        assert reading.snr is not None and reading.rssi is not None
        assert SNR_RANGE_DB[0] <= reading.snr <= SNR_RANGE_DB[1] and RSSI_RANGE_DBM[0] <= reading.rssi <= RSSI_RANGE_DBM[1]
        if frame.path and frame.path[0].repeated:
            assert reading.rssi >= -90, "a repeat comes from the iGate on the hill, stronger than the trackers"


def test_the_home_station_acks_a_message_and_answers_once_and_a_frame_of_ours_that_asks_for_wide1_1_is_repeated() -> None:
    scene = LoraScene(HELSINKI, START)
    play(scene, 60)
    now = START + timedelta(seconds=60)
    scene.react(from_us(b":Q9KOT    :Hello there{7"), now)
    scene.react(from_us(b":Q9KOT    :Hello there{7"), now)                    # (a retry: acked again, not answered again)
    scene.react(from_us(b":Q9TRK-7  :Anyone{8"), now)                       # (a tracker takes no messages)
    scene.react(from_us(b"!6010.00N/02456.00E-", "WIDE2-2"), now)            # (the iGate repeats WIDE1-1 only)
    later = [f for t in range(1, 30) for f in scene.due(now + timedelta(seconds=t))]
    acks = [f for f in later if f.source == ax25.Address.parse("Q9KOT") and f.info.startswith(b":OH2GBA   :ack7")]
    answers = [parse_message(f.info[1:]) for f in later if f.source == ax25.Address.parse("Q9KOT") and b":ack" not in f.info and f.info[:1] == b":"]
    assert len(acks) == 2 and [a.text for a in answers] == [HELLO] and not any(b"ack8" in f.info for f in later)
    ours = [f for f in later if f.source == ax25.Address.parse(ME)]
    assert len(ours) == 3 and all(str(f.path[0]) == IGATE + "*" and f.info[:1] == b":" for f in ours), "our three messages came back from the iGate, the position on WIDE2-2 did not"
    assert ACK_AFTER_SEC >= 4, "a frame of two to four seconds each way"


def test_each_radio_has_a_world_of_its_own_by_its_seed_and_the_same_one_at_every_start() -> None:
    one, three = LoraScene(HELSINKI, START, seed=1), LoraScene(HELSINKI, START, seed=3)
    calls = lambda scene: {str(f.source) for _, f in play(scene, 300)}      # noqa: E731
    assert calls(one) == {IGATE, "Q9KOT", "Q9TRK-7", "Q9BKE-12"} and calls(three) == {"Q1LRG-10", "Q1KOT", "Q1TRK-7", "Q1BKE-12"}
    again = LoraScene(HELSINKI, START, seed=3)
    assert [text_of(f) for _, f in play(again, 900)] == [text_of(f) for _, f in play(LoraScene(HELSINKI, START, seed=3), 900)]


# ---- the line

async def test_the_line_hears_the_world_in_text_hands_the_tnc_the_frames_and_puts_what_we_send_on_the_air_in_text(fast: None, monkeypatch: pytest.MonkeyPatch) -> None:
    tried = refuse_the_world(monkeypatch)
    clock = FixedClock(START)
    tnc = Tnc(profile=DUMMY_LORA, port=dummyline.DUMMY_PATH, clock=clock)
    tnc.radio_id = 4
    heard: list[tuple[str, str, int | None, float | None, float | None]] = []
    tnc.packet.connect(lambda p: heard.append((p.direction, p.source, p.radio_id, p.snr, p.rssi)))
    await tnc.start()
    assert tnc.state is Source.State.CONNECTED and tnc.usable and tnc.is_dummy and tnc.max_frame == 250
    assert tnc.describe().startswith("dummy LoRa radio, made-up traffic,"), "the status line names the kind"
    port = tnc._port
    assert isinstance(port, DummyLoraPort)
    for _ in range(12):
        clock.advance(5)
        await asyncio.sleep(0.03)
    assert tnc.send_frame(from_us(b":Q2KOT    :Hello{5"))
    assert not tnc.send_frame(from_us(b">" + b"x" * 240)), "a frame over the 250 bytes of LoRa is not sent"
    long_text = air("OH2GBA-15", b">" + b"x" * 219, "WIDE1-1,WIDE2-1", "APNX01")
    assert (len(ax25.encode(long_text)), len(air_of(long_text))) == (250, 256)
    assert not tnc.send_frame(long_text), "a frame of 250 bytes whose text is 253 is not sent: the packet would be 256"
    assert any("not sent: 253 bytes of text, the radio carries 252" in line for line in tnc.lines)
    for _ in range(10):
        clock.advance(2)
        await asyncio.sleep(0.03)
    await tnc.stop()
    assert list(port.transmitted)[:1] == [HEADER + b"OH2GBA>APNX01,WIDE1-1::Q2KOT    :Hello{5"], "what we sent went on the made-up air in text with the header"
    assert len(port.transmitted) == 1 and [p for d, *p in heard if d == "out"] == [[ME, 4, None, None]], "and nothing that does not fit was reported sent"
    calls = {s for d, s, _, _, _ in heard if d == "in"}
    assert {call_of("Q9LRG-10", 4), call_of("Q9KOT", 4), call_of("Q9TRK-7", 4)} == {"Q2LRG-10", "Q2KOT", "Q2TRK-7"} <= calls, "the world of radio 4"
    assert all(r == 4 for _, _, r, _, _ in heard) and all(snr is not None and rssi is not None for d, _, _, snr, rssi in heard if d == "in")
    assert tnc.stats.rejected == 0 and tried == []


def test_a_frame_longer_than_a_lora_packet_is_not_put_on_the_air_and_one_that_fits_is_heard_as_sent() -> None:
    assert board_air(from_us(b">" + b"x" * 240)) is None
    frame = from_us(b">short")
    assert board_line(board_air(frame) or b"") == text_of(frame) + b"\r\n" and board_line(text_of(frame)) == b"", "a packet without the header is not handed on"


def test_our_frame_is_cut_to_the_text_a_lora_packet_carries_and_only_its_comment_is_cut() -> None:
    frame = air("OH2GBA-15", b"!6010.00N/02456.00E-" + b"c" * 200, "WIDE1-1,WIDE2-1", "APNX01")
    assert len(ax25.encode(frame)) == 250 and len(text_of(frame)) == 253
    assert fit_frame(frame, 250) is frame, "the AX.25 frame alone fits"
    fitted = fit_frame(frame, 250, MAX_TEXT)
    assert len(text_of(fitted)) == MAX_TEXT and fitted.info == frame.info[:-1] and fits(air_of(fitted))
    with pytest.raises(ValueError, match="of text the radio carries"):
        fit_frame(air("OH2GBA-15", b"!6010.00N/02456.00E-", "WIDE1-1", "APNX01"), None, 30)


def test_each_dummy_world_names_the_calls_it_makes_up_for_its_radio() -> None:
    assert made_up_calls("dummy-lora", 3) == lora_calls(3) == {"Q1LRG-10", "Q1KOT", "Q1TRK-7", "Q1BKE-12"} and made_up_calls("dummy-lora", 1) == {IGATE, "Q9KOT", "Q9TRK-7", "Q9BKE-12"}
    assert "Q1KUO" in made_up_calls("dummy-hf", 2) == made_up_calls("dummy-hf", 5), "the Dummy HF radio's cities are the same in every world"
    assert made_up_calls("dummy", 1) == made_up_calls("kiss", 1) == frozenset(), "the Dummy radio's stations are made round the station; a real radio makes none up"


# ---- the daemon

async def test_a_dummy_lora_radio_added_from_the_page_runs_hears_its_stations_beacons_and_takes_a_message_in_text_and_is_a_row_of_the_topic(tmp_path: Path, fast: None,
                                                                                                                                            caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="neoaprs")
    e = Env(tmp_path, radio=False, web=True, settings={"station/call": ME, "station/lat": "60.17", "station/lon": "24.94", "messages/alert": "false"})
    await e.start(connected=False)
    page = await e.ws()
    await page.until(lambda: "radios" in page.topics)
    id = await added(page, "dummy-lora")
    radio = e.ctl.radios.get(id)
    assert radio is not None and isinstance(radio.driver, TncDriver) and radio.kind == "lora" and radio.max_frame == 250
    await until_started(lambda: radio.state is Source.State.CONNECTED)
    await page.until(lambda: page.topics["radios"][str(id)]["state"] == "connected")
    row = page.topics["radios"][str(id)]
    assert (row["kind"], row["type"], row["dummy"], row["number"], row["enabled"]) == ("lora", "dummy-lora", True, 1, True)
    assert row["limits"] == {"max_frame": 250, "beacon_min_min": 30} and row["can"] == {**dict.fromkeys(row["can"], False), "transmit": True}
    assert row["allowed"] == {"paths": True, "digipeat": False, "smart_beacon": True, "gateway_heard": True, "shared_channel": False} and row["choices"] == {"beacon": True, "path": "", "digipeat": None}
    world = {call_of(call, id) for call in ("Q9LRG-10", "Q9KOT", "Q9TRK-7")}             # (the bike's first beacon may come after the others are in)
    for _ in range(200):
        e.now.advance(5)                                                         # type: ignore[attr-defined]
        await asyncio.sleep(0.02)
        if world <= {s.call for s in e.ctl.stationbook.stations() if s.heard_on(id).count > 0}:
            break
    heard = [s for s in e.ctl.stationbook.stations() if s.call.startswith("Q")]
    assert heard and all(s.heard_on(id).count > 0 and s.heard_fm == 0 for s in heard), "heard on the LoRa radio, never on the FM one"
    home = next(s for s in heard if s.call.endswith("KOT"))
    assert home.lat is not None and home.snr is not None and home.rssi is not None, "a station heard direct on the LoRa radio has its position and its signal"
    packets = [p for p in await e.packets() if p.direction == "in" and p.source.startswith("Q")]
    assert packets and all(p.radio_id == id and p.via == "dummy" and p.snr is not None and p.rssi is not None for p in packets)
    assert all(ax25.decode(p.raw) == frame_of(text_of(ax25.decode(p.raw))) for p in packets), "the packet's raw is the AX.25 frame we made of the text"
    port = radio.line._port
    assert isinstance(port, DummyLoraPort)
    assert radio.beacon.send_now(), radio.beacon.problem
    assert port.transmitted and port.transmitted[-1].startswith(HEADER + ME.encode() + b">"), "our beacon went out on the LoRa radio in text"
    assert from_air(port.transmitted[-1]).path_text == "WIDE1-1", "with no path of its own, on LoRa's WIDE1-1 (a fixed station's symbol would say WIDE2-2)"
    igate = call_of(IGATE, id)
    for _ in range(40):
        e.now.advance(1)                                                         # type: ignore[attr-defined]
        await asyncio.sleep(0.02)
    back = [ax25.decode(p.raw) for p in await e.packets() if p.direction == "in" and p.source == ME]
    assert any(str(f.path[0]) == igate + "*" and f.info[:1] == b"=" for f in back), "and the iGate repeated it"
    record = await e.ctl.messaging.send(home.call, "Hello over LoRa")
    for _ in range(200):
        e.now.advance(1)                                                         # type: ignore[attr-defined]
        await asyncio.sleep(0.02)
        if (now := e.ctl.messaging.get(record.id)) is not None and now.state == "acked" and any(r.direction == "in" and r.text == HELLO for r in e.ctl.messaging.records()):
            break
    done = e.ctl.messaging.get(record.id)
    assert done is not None and done.state == "acked", done
    assert any(b"::" + home.call.encode().ljust(9) + b":Hello over LoRa{" in p for p in port.transmitted), "the message went out on the LoRa radio in text"
    assert all(from_air(p).path_text == "WIDE1-1" for p in port.transmitted if b"::" in p), "on WIDE1-1, and our ack too"
    assert any(r.direction == "in" and r.text == HELLO and r.from_call == home.call for r in e.ctl.messaging.records()), "and the station's answer came in"
    tracker = await e.ctl.messaging.send(call_of("Q9TRK-7", id), "a tracker takes no messages")
    await page.send({"cmd": "radio_change", "radio": id, "enabled": False})
    await page.until(lambda: not page.topics["radios"][str(id)]["enabled"])
    assert getattr(e.ctl.messaging.get(tracker.id), "state", "") == "cancelled", "a radio that leaves its made-up world takes the messages to it along"
    assert not {s.call for s in e.ctl.stationbook.stations()} & made_up_calls("dummy-lora", id), "and its stations"
    assert "forgot the made-up stations of the Dummy LoRa radio: " in caplog.text
    await e.stop()

