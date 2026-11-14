"""The signal of what is heard (neoaprs/reading.py): a reading is tied to its frame where the frame is made. Mercury's SN line comes before its frame on another connection, and the next frame takes it once and
only within PAIR_SEC, so two frames close together each get their own and a frame whose SN never came gets none; a radio type gives only the readings it says (Mercury the SNR, a KISS TNC none, the Dummy HF
radio a made-up SNR in Mercury's range); a station's last reading is that of the latest packet heard direct from it."""
import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs import ax25, dummyline
from neoaprs.aprsparse import parse
from neoaprs.dummyhfscene import SNR_RANGE_DB, STATIONS, HfScene
from neoaprs.dummyline import DUMMY_PATH
from neoaprs.dummyscene import Scene
from neoaprs.mercury import ControlEvent
from neoaprs.packet import Packet
from neoaprs.reading import NO_READING, PAIR_SEC, Pending, Reading
from neoaprs.station import Station
from neoaprs.stationbook import StationBook
from neoaprs.stationnotes import note_heard
from neoaprs.tnc import Tnc
from neoaprs.tncprofile import DUMMY, DUMMY_HF, KISS_TCP, MERCURY, PROFILES
from tests.support.clock import FixedClock
from tests.support.env import until_started
from tests.support.wireworld import T0
from tests.test_mercury_modem import modem
from tests.test_tnc import Rigs, kiss_of, stops_rigs, ui_frame


@pytest.fixture
def rig() -> Rigs:
    return Rigs()


def test_a_reading_said_before_its_frame_is_taken_by_that_frame_once_and_only_within_the_pair_time() -> None:
    pending = Pending()
    pending.put(Reading(snr=-2.5), 10.0)
    assert pending.take(10.05) == Reading(snr=-2.5)
    assert pending.take(10.06) == NO_READING, "taken once: the next frame does not get it again"
    pending.put(Reading(snr=3.0), 20.0)
    assert pending.take(20.0 + PAIR_SEC + 0.01) == NO_READING, "a reading whose frame never came is not given to a frame that comes later"
    assert pending.take(20.0 + PAIR_SEC + 0.02) == NO_READING
    pending.put(Reading(snr=1.0), 30.0)
    pending.put(Reading(snr=4.0), 30.5)
    assert pending.take(30.6) == Reading(snr=4.0), "a second reading before a frame: the first one's frame did not come"
    pending.put(Reading(snr=1.0), 40.0)
    pending.clear()
    assert pending.take(40.1) == NO_READING


def test_a_radio_type_gives_only_the_readings_it_says() -> None:
    assert MERCURY.readings == ("snr",) and DUMMY_HF.readings == ("snr",)
    assert all(p.readings == () for p in PROFILES), "the FM radio's types (KISS TNCs, the Dummy radio) measure nothing"
    both = Reading(snr=7.25, rssi=-112.0)
    assert both.only(("snr",)) == Reading(snr=7.25) and both.only(()) == NO_READING and both.only(("snr", "rssi")) == both, "a type that gives the RSSI needs nothing more than to say so"


@stops_rigs
async def test_two_frames_close_together_each_get_the_snr_mercury_said_for_it_and_a_frame_with_none_said_gets_none(rig: Rigs, tmp_path: Path) -> None:
    r = await rig(profile=MERCURY)
    m = modem(tmp_path, program=False)
    r.tnc.modem = m
    heard: list[Packet] = []
    r.tnc.packet.connect(heard.append)
    m._event(ControlEvent("snr", value=-2.5))                                    # (Mercury: SN first on the control port, then the frame on the broadcast port, 0 to 100 ms later)
    r.radio.feed(kiss_of(ui_frame("OH2AAA")))
    await until_started(lambda: len(heard) == 1)
    m._event(ControlEvent("snr", value=6.1))                                     # (the next frame right after it, a few milliseconds later)
    r.radio.feed(kiss_of(ui_frame("OH2BBB")))
    await until_started(lambda: len(heard) == 2)
    r.radio.feed(kiss_of(ui_frame("OH2CCC")))                                    # (a frame whose SN did not come)
    await until_started(lambda: len(heard) == 3)
    assert [(p.source, p.snr, p.rssi) for p in heard] == [("OH2AAA", -2.5, None), ("OH2BBB", 6.1, None), ("OH2CCC", None, None)]
    assert m.snr == 6.1, "the status line keeps the latest the modem said"


@stops_rigs
async def test_a_reading_that_waited_longer_than_the_pair_time_is_not_the_frames(rig: Rigs, tmp_path: Path) -> None:
    r = await rig(profile=MERCURY)
    m = modem(tmp_path, program=False)
    r.tnc.modem = m
    heard: list[Packet] = []
    r.tnc.packet.connect(heard.append)
    m._event(ControlEvent("snr", value=-2.5))
    m._reading._at -= PAIR_SEC + 0.5                                             # (said a while ago: a frame Mercury decoded and did not hand over, an ARQ frame or one of another size)
    r.radio.feed(kiss_of(ui_frame("OH2AAA")))
    await until_started(lambda: len(heard) == 1)
    assert heard[0].snr is None


@stops_rigs
async def test_a_kiss_tnc_gives_no_reading_even_with_a_modem_beside_it(rig: Rigs, tmp_path: Path) -> None:
    r = await rig(profile=replace(MERCURY, key="mercury-no-readings", readings=()))
    m = modem(tmp_path, program=False)
    r.tnc.modem = m
    heard: list[Packet] = []
    r.tnc.packet.connect(heard.append)
    m._event(ControlEvent("snr", value=-2.5))
    r.radio.feed(kiss_of(ui_frame("OH2AAA")))
    await until_started(lambda: len(heard) == 1)
    assert heard[0].snr is None, "a type that says it gives no reading has none, whatever was said"
    r.tnc.profile = KISS_TCP
    m._event(ControlEvent("snr", value=-2.5))
    r.radio.feed(kiss_of(ui_frame("OH2BBB")))
    await until_started(lambda: len(heard) == 2)
    assert heard[1].snr is None, "a KISS TNC's line has no modem to ask"


def test_the_dummy_hf_scene_makes_up_a_believable_snr_for_each_station_the_farther_the_weaker() -> None:
    scene, again = HfScene(None, T0), HfScene(None, T0)
    readings: dict[str, list[float]] = {}
    for station in STATIONS:
        frame = ax25.Frame(ax25.Address("APRS"), ax25.Address.parse(station.call), (), info=b">x")
        for _ in range(50):
            reading = scene.reading_of(frame)
            assert reading.rssi is None and reading.snr is not None and reading == again.reading_of(frame), "Mercury gives no RSSI; the same for the same seed"
            readings.setdefault(station.call, []).append(reading.snr)
    low, high = SNR_RANGE_DB
    assert all(low <= snr <= high and round(snr, 1) == snr for values in readings.values() for snr in values)
    mean = {call: sum(values) / len(values) for call, values in readings.items()}
    assert mean["Q3TKU"] > mean["Q4HAM"] > mean["Q6WAW"] and len({round(v) for v in readings["Q3TKU"]}) > 1, "Turku is near, Warsaw far, and a frame fades from the next"
    assert Scene((60.17, 24.94), T0).reading_of(ax25.Frame(ax25.Address("APRS"), ax25.Address.parse("Q3TKU"), (), info=b">x")) == NO_READING


@pytest.mark.parametrize("profile", [DUMMY_HF, DUMMY])
async def test_the_dummy_hf_radio_hears_its_stations_with_an_snr_and_the_dummy_radio_with_none(profile: object, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dummyline, "TICK_SEC", 0.01)
    clock = FixedClock(T0)
    tnc = Tnc(profile=profile, port=DUMMY_PATH, clock=clock)                   # type: ignore[arg-type]
    heard: list[Packet] = []
    tnc.packet.connect(heard.append)
    await tnc.start()
    try:
        for _ in range(60):
            clock.advance(5)
            await asyncio.sleep(0.02)
            if len(heard) >= 3:
                break
    finally:
        await tnc.stop()
    assert len(heard) >= 3
    if profile is DUMMY_HF:
        assert all(p.snr is not None and p.rssi is None and p.radio == "hf" for p in heard)
    else:
        assert all(p.snr is None and p.rssi is None for p in heard)


def test_a_station_keeps_the_reading_of_the_latest_packet_heard_direct_from_it() -> None:
    def heard(snr: float | None, path: tuple[str, ...] = (), minutes: int = 0) -> Packet:
        at = T0.replace(minute=minutes)
        return Packet(at, "in", b"", "Q3TKU", "APRS", path, b">x", parse(b">x", "Q3TKU", "APRS", at), radio="hf", snr=snr)
    station = Station("Q3TKU", first_heard=T0, last_heard=T0)
    note_heard(station, heard(-2.5, minutes=1))
    assert (station.snr, station.rssi, station.signal_at) == (-2.5, None, T0.replace(minute=1))
    note_heard(station, heard(None, minutes=2))
    assert (station.snr, station.signal_at) == (-2.5, T0.replace(minute=1)), "a packet without a reading leaves the last one, with its own time"
    note_heard(station, replace(heard(9.0, ("OH2RCH-2*",), minutes=3), radio="fm"))
    assert station.snr == -2.5, "a digipeater's copy is the digipeater's signal"
    note_heard(station, replace(heard(4.0, minutes=4), rssi=-101.0))
    assert (station.snr, station.rssi, station.signal_at) == (4.0, -101.0, T0.replace(minute=4))


def test_an_object_or_item_keeps_no_reading_its_reporter_s_signal_is_the_reporter_s() -> None:
    for info, name in ((b";NET      *141200z6027.11N/02216.00E-Club net", "NET"), (b")FIELD!6027.11N/02216.00E-", "FIELD")):
        packet = Packet(T0, "in", b"", "Q3TKU", "APRS", (), info, parse(info, "Q3TKU", "APRS", T0), radio="hf", snr=6.1)
        book = StationBook(lambda: T0)
        book.take(packet)
        stations = {s.call: s for s in book.stations()}
        assert (stations["Q3TKU"].snr, stations["Q3TKU"].signal_at) == (6.1, T0)
        assert (stations[name].kind, stations[name].snr, stations[name].rssi, stations[name].signal_at) == ("object" if info[:1] == b";" else "item", None, None, None)
