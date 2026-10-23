"""The beacon (neoaprs/services/beacon.py) on a Tnc that is a stub and a clock the test holds: the frame the settings make, byte for byte, and the timer (the first delay, the interval, the skip while
the TNC is not connected, a changed interval)."""
import asyncio
import logging
from dataclasses import replace
from datetime import timedelta

import pytest

from neoaprs import ax25
from neoaprs.aprsparse import parse
from neoaprs.aprsposition import parse_position
from neoaprs.config import Config
from neoaprs.geo import distance_km
from neoaprs.packet import Status
from neoaprs.services.beacon import Beacon, BeaconError, dao_text, phg_text, uncompressed_position
from neoaprs.source import Source, unusable_because
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR, until


class StubTnc:
    """The part of the Tnc the beacon uses: a state, and the frames it was given."""

    def __init__(self, state: Source.State = Source.State.CONNECTED) -> None:
        self.state = state
        self.sent: list[ax25.Frame] = []
        self.takes = True
        self.asked = 0

    @property
    def usable(self) -> bool:
        return self.state is Source.State.CONNECTED

    def why_unusable(self) -> str:
        return unusable_because(self.state)

    def send_frame(self, frame: ax25.Frame) -> bool:
        self.asked += 1
        if self.takes:
            self.sent.append(frame)
        return self.takes


class Rig:
    def __init__(self, **changes: object) -> None:
        self.config: Config = replace(ON_AIR, **changes)             # type: ignore[arg-type]
        self.tnc = StubTnc()
        self.clock = FixedClock()
        self.beacon = Beacon(self.tnc, lambda: self.config, self.clock, first_delay_sec=30.0, tick_sec=0.01, retry_sec=5.0)

    def set(self, **changes: object) -> None:
        self.config = replace(self.config, **changes)                  # type: ignore[arg-type]


# ---- the frame -----------------------------------------------------------------------------------------------------------------------------------

def test_the_default_beacon_is_the_uncompressed_position_with_the_comment_to_the_experimental_tocall_by_way_of_wide() -> None:
    frame = Rig().beacon.frame()
    assert frame.info == b"=6010.20N/02456.40E-NeoAPRS"
    assert (str(frame.destination), str(frame.source), frame.path_text, frame.is_ui) == ("APZNEO", "OH2GBA", "WIDE1-1,WIDE2-1", True)
    assert frame.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=6010.20N/02456.40E-NeoAPRS"
    assert ax25.decode(ax25.encode(frame)) == frame, "it is a frame that goes over the air and comes back"


def test_the_frame_follows_the_settings() -> None:
    frame = Rig(station_call="OH2GBA-9", beacon_path="", beacon_destination="APRS", station_symbol_table="\\", station_symbol_code=">", station_comment="").beacon.frame()
    assert frame.tnc2() == "OH2GBA-9>APRS:=6010.20N\\02456.40E>"
    assert Rig(beacon_path="WIDE2-2").beacon.frame().path_text == "WIDE2-2"


@pytest.mark.parametrize("lat, lon, text", [
    (60.17, 24.94, b"6010.20N/02456.40E-"), (-33.8688, 151.2093, b"3352.13S/15112.56E-"), (0.0, 0.0, b"0000.00N/00000.00E-"), (90.0, -180.0, b"9000.00N/18000.00W-"),
    (-90.0, 180.0, b"9000.00S/18000.00E-"), (59.999999, 24.999999, b"6000.00N/02500.00E-"), (60.1699999, 24.9400001, b"6010.20N/02456.40E-"), (-0.00001, -0.00001, b"0000.00N/00000.00E-"),
    (60.005, 5.0, b"6000.30N/00500.00E-"), (-0.5, -0.0083333, b"0030.00S/00000.50W-")])
def test_the_position_is_rounded_to_the_hundredth_of_a_minute_and_never_ambiguous(lat: float, lon: float, text: bytes) -> None:
    assert uncompressed_position(lat, lon, "/", "-") == text
    assert len(text) == 19 and b" " not in text


def test_the_uncompressed_position_reads_back_in_the_parser_within_a_hundredth_of_a_minute() -> None:
    for lat, lon in ((60.17, 24.94), (-33.8688, 151.2093), (0.0123, -0.0456), (89.99, 179.99)):
        info = Rig(station_lat=lat, station_lon=lon).beacon.frame().info
        position = parse_position(info[1:], FixedClock()(), messaging=True)
        assert position.lat == pytest.approx(lat, abs=1 / 6000 / 2 + 1e-9) and position.lon == pytest.approx(lon, abs=1 / 6000 / 2 + 1e-9)
        assert position.ambiguity == 0 and position.messaging and not position.compressed and position.comment == "NeoAPRS"


@pytest.mark.parametrize("table, code", [("/", "-"), ("\\", ">"), ("5", "k"), ("T", "&")])
def test_the_compressed_beacon_reads_back_within_a_metre(table: str, code: str) -> None:
    for lat, lon in ((60.17, 24.94), (-33.8688, 151.2093), (89.9, -179.9)):
        info = Rig(beacon_compressed=True, station_lat=lat, station_lon=lon, station_symbol_table=table, station_symbol_code=code).beacon.frame().info
        assert info[:1] == b"=" and len(info) == 1 + 13 + len("NeoAPRS") and info.endswith(b"NeoAPRS")
        position = parse_position(info[1:], FixedClock()(), messaging=True)
        assert distance_km(lat, lon, position.lat, position.lon) * 1000 < 1.0
        assert (position.symbol_table, position.symbol_code, position.comment, position.compressed, position.messaging) == (table, code, "NeoAPRS", True, True)


@pytest.mark.parametrize("changes", [
    {"station_comment": "x" * 44}, {"station_comment": "åäö"}, {"beacon_destination": "A B"}, {"beacon_path": "WIDE1-1,BAD CALL"},
    {"beacon_path": ",".join(["WIDE1-1"] * 9)}, {"station_lat": 91.0}, {"station_lon": -181.0}, {"station_symbol_table": "!!"}, {"station_symbol_code": " "}])
def test_settings_that_make_no_frame_are_an_error_and_nothing_is_sent(changes: dict[str, object], caplog: pytest.LogCaptureFixture) -> None:
    rig = Rig(**changes)
    with pytest.raises(BeaconError):
        rig.beacon.frame()
    caplog.set_level(logging.WARNING, "neoaprs.beacon")
    assert not rig.beacon.send_now()
    assert rig.tnc.sent == [] and rig.beacon.last_sent is None and "no beacon" in rig.beacon.problem
    assert any("no beacon sent" in r.getMessage() for r in caplog.records)


# ---- the PHG extension and DAO ---------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("power, height, gain, direction, text", [
    (2, 3, 2, "omni", "PHG1020"),                      # a small station: 2 W (p 1.4 -> 1), 3 m = 9.8 ft (h 0), 2 dB, omni
    (25, 12, 3, "N", "PHG5238"),                       # 25 W (5), 12 m = 39.4 ft (h 2), 3 dB, 360 degrees north (8)
    (25, 6, 3, "E", "PHG5132"),                        # the specification's example: 25 W, 20 ft, 3 dB, 90 degrees east
    (0, 0, 0, "omni", "PHG0000"), (9999, 9999, 9, "NW", "PHG9997"), (81, 100, 0, "NE", "PHG9501"), (80, 100, 0, "SW", "PHG9505")])
def test_the_phg_extension_is_power_height_gain_and_directivity(power: int, height: int, gain: int, direction: str, text: str) -> None:
    assert phg_text(power, height, gain, direction) == text


@pytest.mark.parametrize("watts, code", [(0, 0), (1, 1), (2, 1), (3, 2), (4, 2), (6, 2), (7, 3), (9, 3), (16, 4), (25, 5), (36, 6), (49, 7), (64, 8), (81, 9), (100, 9), (9999, 9)])
def test_the_power_code_is_the_square_root_of_the_watts_rounded(watts: int, code: int) -> None:
    assert phg_text(watts, 0, 0, "omni") == f"PHG{code}000"


@pytest.mark.parametrize("feet, code", [(10, 0), (14, 0), (15, 1), (20, 1), (28, 1), (30, 2), (40, 2), (80, 3), (160, 4), (320, 5), (640, 6), (1280, 7), (2560, 8), (5120, 9), (100000, 9)])
def test_the_height_code_is_the_logarithm_of_the_height_in_tens_of_feet_rounded(feet: int, code: int) -> None:
    assert phg_text(1, round(feet / 3.2808, 3), 0, "omni")[4] == str(code)


def test_the_directivity_digit_runs_clockwise_from_omni_through_north_east_to_north() -> None:
    assert [phg_text(1, 0, 0, d)[-1] for d in ("omni", "NE", "E", "SE", "S", "SW", "W", "NW", "N")] == list("012345678")


def test_the_beacon_has_the_phg_right_after_the_symbol_and_before_the_comment() -> None:
    frame = Rig(beacon_power_w=2, beacon_antenna_height_m=3, beacon_antenna_gain_db=2).beacon.frame()
    assert frame.info == b"=6010.20N/02456.40E-PHG1020NeoAPRS"
    assert frame.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=6010.20N/02456.40E-PHG1020NeoAPRS"
    assert Rig(beacon_power_w=25, beacon_antenna_height_m=12, beacon_antenna_gain_db=3, beacon_antenna_direction="N", station_comment="").beacon.frame().info == b"=6010.20N/02456.40E-PHG5238"
    assert ax25.decode(ax25.encode(frame)) == frame


def test_a_compressed_position_has_no_data_extension_so_no_phg_is_sent() -> None:
    compressed = Rig(beacon_compressed=True).beacon.frame()
    with_power = Rig(beacon_compressed=True, beacon_power_w=25, beacon_antenna_height_m=6, beacon_antenna_gain_db=3, beacon_antenna_direction="E").beacon.frame()
    assert with_power == compressed and b"PHG" not in with_power.info and with_power.info.endswith(b"NeoAPRS")
    assert Rig(beacon_compressed=True, beacon_power_w=25, beacon_dao=True).beacon.frame() == compressed


def test_without_a_power_there_is_no_phg_whatever_the_rest_says() -> None:
    plain = Rig().beacon.frame()
    assert plain.info == b"=6010.20N/02456.40E-NeoAPRS"
    assert Rig(beacon_power_w=None, beacon_antenna_height_m=30, beacon_antenna_gain_db=9, beacon_antenna_direction="S").beacon.frame() == plain
    assert Rig(beacon_power_w=0).beacon.frame().info == b"=6010.20N/02456.40E-PHG0000NeoAPRS", "a power of 0 is a power: only an empty one means no PHG"


def test_the_phg_is_read_back_by_the_parser_as_the_extension_and_not_the_comment() -> None:
    info = Rig(beacon_power_w=25, beacon_antenna_height_m=6, beacon_antenna_gain_db=3, beacon_antenna_direction="E").beacon.frame().info
    position = parse_position(info[1:], FixedClock()(), messaging=True)
    assert (position.lat, position.lon) == pytest.approx((60.17, 24.94), abs=1e-4) and position.comment == "NeoAPRS"
    assert position.extensions is not None and position.extensions.phg is not None
    assert (position.extensions.phg.power_w, position.extensions.phg.gain_db, position.extensions.phg.direction_deg) == (25, 3, 90)


@pytest.mark.parametrize("lat, lon, position, dao", [
    (60.1738, 24.9433, b"6010.42N/02456.59E-", "!W88!"), (-33.8688, 151.2093, b"3352.12S/15112.55E-", "!W88!"), (60.17, 24.94, b"6010.20N/02456.40E-", "!W00!"),
    (60.1741, 24.9406, b"6010.44N/02456.43E-", "!W66!"), (0.0, 0.0, b"0000.00N/00000.00E-", "!W00!"), (-0.00001, -0.00001, b"0000.00S/00000.00W-", "!W11!"),
    (59.999999, 24.999999, b"6000.00N/02500.00E-", "!W00!"), (60.1749, 24.9999999, b"6010.49N/02500.00E-", "!W40!"), (60.1749999, 24.9999999, b"6010.50N/02500.00E-", "!W00!"), (-90.0, 180.0, b"9000.00S/18000.00E-", "!W00!")])
def test_dao_is_the_digit_after_the_hundredths_of_the_minutes_of_the_latitude_and_the_longitude(lat: float, lon: float, position: bytes, dao: str) -> None:
    assert uncompressed_position(lat, lon, "/", "-", dao=True) == position
    assert dao_text(lat, lon) == dao


def test_the_beacon_ends_in_dao_when_asked_and_the_position_with_the_dao_is_finer_than_without() -> None:
    lat, lon = 60.1738, 24.9433
    frame = Rig(station_lat=lat, station_lon=lon, beacon_dao=True).beacon.frame()
    assert frame.info == b"=6010.42N/02456.59E-NeoAPRS!W88!"
    assert Rig(station_lat=lat, station_lon=lon).beacon.frame().info == b"=6010.43N/02456.60E-NeoAPRS"
    position = parse_position(frame.info[1:-5], FixedClock()(), messaging=True)
    x, y = int(frame.info[-3:-2]), int(frame.info[-2:-1])
    assert position.lat + x / 60000 == pytest.approx(lat, abs=1e-8) and position.lon + y / 60000 == pytest.approx(lon, abs=1e-8)
    assert distance_km(lat, lon, position.lat, position.lon) * 1000 < 20.0
    assert distance_km(lat, lon, position.lat + x / 60000, position.lon + y / 60000) * 1000 < 1.0


def test_dao_comes_after_the_comment_and_the_phg_before_it_and_neither_changes_the_other() -> None:
    both = Rig(beacon_power_w=2, beacon_antenna_gain_db=2, beacon_dao=True, station_lat=60.1738, station_lon=24.9433).beacon.frame()
    assert both.info == b"=6010.42N/02456.59E-PHG1020NeoAPRS!W88!"
    assert Rig(beacon_dao=True, station_comment="").beacon.frame().info == b"=6010.20N/02456.40E-!W00!"
    assert Rig(beacon_dao=True, station_comment="x" * 43).beacon.frame().info.endswith(b"x" * 43 + b"!W00!"), "the DAO comes on top of the limit of the comment"
    assert Rig(beacon_dao=True, station_comment="x" * 36, beacon_power_w=1).beacon.frame().info.endswith(b"PHG1000" + b"x" * 36 + b"!W00!")


@pytest.mark.parametrize("changes, longest", [
    ({}, 43), ({"beacon_power_w": 5}, 36), ({"beacon_compressed": True}, 40), ({"beacon_compressed": True, "beacon_power_w": 5}, 40), ({"beacon_dao": True}, 43), ({"beacon_dao": True, "beacon_power_w": 5}, 36)])
def test_the_comment_may_be_43_36_or_40_characters_for_what_the_beacon_sends_and_no_more(changes: dict[str, object], longest: int) -> None:
    assert Rig(station_comment="x" * longest, **changes).beacon.frame().info.count(b"x") == longest
    with pytest.raises(BeaconError, match=rf"station/comment: {longest + 1} characters is more than the {longest} allowed"):
        Rig(station_comment="x" * (longest + 1), **changes).beacon.frame()


@pytest.mark.parametrize("comment", ["a|b", "a~b", "Hyvää", "tab\t"])
def test_the_frame_is_refused_for_a_comment_that_is_not_printable_ascii_without_the_switch_characters(comment: str) -> None:
    with pytest.raises(BeaconError, match="station/comment"):
        Rig(station_comment=comment).beacon.frame()


def test_a_beacon_that_cannot_be_built_is_not_sent_and_says_why(caplog: pytest.LogCaptureFixture) -> None:
    rig = Rig(station_comment="x" * 40, beacon_power_w=5)               # (a hand-made Config: the settings check would have refused the pair)
    with caplog.at_level(logging.WARNING, logger="neoaprs.beacon"):
        assert not rig.beacon.send_now()
    assert rig.tnc.sent == [] and "40 characters is more than the 36 allowed with the PHG" in rig.beacon.problem and any("no beacon sent" in r.getMessage() for r in caplog.records)


def test_a_frame_with_an_information_field_over_256_bytes_is_refused() -> None:
    rig = Rig()
    with pytest.raises(BeaconError, match="more than the 256"):
        rig.beacon._frame_of(b"=" + b"x" * 256)
    assert len(rig.beacon._frame_of(b"=" + b"x" * 255).info) == 256


def test_the_compressed_form_has_no_dao() -> None:
    assert Rig(beacon_compressed=True, beacon_dao=True).beacon.frame() == Rig(beacon_compressed=True).beacon.frame()


# ---- on request ----------------------------------------------------------------------------------------------------------------------------------

def test_send_now_sends_the_frame_and_notes_when_and_why() -> None:
    rig = Rig()
    assert rig.beacon.send_now() and rig.tnc.sent == [rig.beacon.frame()]
    assert (rig.beacon.last_sent, rig.beacon.last_reason, rig.beacon.problem) == (rig.clock(), "request", "")
    rig.clock.advance(90)
    assert rig.beacon.send_now("interval") and len(rig.tnc.sent) == 2 and (rig.beacon.last_sent, rig.beacon.last_reason) == (rig.clock(), "interval")


def test_send_now_while_the_tnc_is_not_connected_sends_nothing_and_says_why() -> None:
    for state in (Source.State.WAITING, Source.State.CONNECTING, Source.State.STOPPED):
        rig = Rig()
        rig.tnc.state = state
        assert not rig.beacon.send_now()
        assert rig.tnc.sent == [] and rig.beacon.last_sent is None and "not connected" in rig.beacon.problem


def test_send_now_when_the_tnc_will_not_take_the_frame_is_false_and_notes_nothing() -> None:
    rig = Rig()
    rig.tnc.takes = False
    assert not rig.beacon.send_now() and rig.beacon.last_sent is None and "did not take" in rig.beacon.problem
    rig.tnc.takes = True
    assert rig.beacon.send_now() and rig.beacon.problem == ""


# ---- the status frame (when it is sent is services/rigstatus.py) ---------------------------------------------------------------------------------

def test_the_status_frame_is_the_text_with_the_day_hour_and_minute_in_utc_by_the_destination_and_path_of_the_beacon() -> None:
    rig = Rig()
    frame = rig.beacon.status_frame("On the road, QRV 145.500")
    assert frame is not None and frame.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:>211200zOn the road, QRV 145.500" and frame.is_ui
    assert ax25.decode(ax25.encode(frame)) == frame
    rig.clock.advance(86400 * 3 + 3600 * 12 + 60 * 7)
    again = rig.beacon.status_frame("On the road, QRV 145.500")
    assert again is not None and again.info == b">250007zOn the road, QRV 145.500", "day 25, 00:07"
    assert isinstance(parse(again.info, "OH2GBA", "APZNEO", rig.clock()), Status)


def test_the_status_text_is_ascii_of_at_most_55_characters_and_an_empty_status_makes_no_frame() -> None:
    assert Rig().beacon.status_frame("") is None
    frame = Rig().beacon.status_frame("Hello " + "x" * 49)
    assert frame is not None and len(frame.info) == 1 + 7 + 55
    decoded = parse(frame.info, "OH2GBA", "APZNEO", FixedClock()())
    assert isinstance(decoded, Status) and decoded.text == "Hello " + "x" * 49 and decoded.timestamp is not None
    for text, why in (("x" * 56, "56 characters"), ("a|b", "'|'"), ("a~b", "'~'"), ("Hyvää päivää", "ASCII")):
        with pytest.raises(BeaconError, match=why):
            Rig().beacon.status_frame(text)


def test_the_beacon_sends_no_status_report_after_itself_whatever_station_status_says() -> None:
    rig = Rig(station_status="QRV")
    assert rig.beacon.send_now()
    rig.clock.advance(1800)
    assert rig.beacon.send_now("interval")
    assert [f.info[:1] for f in rig.tnc.sent] == [b"=", b"="]


def test_settings_that_make_no_frame_make_no_status_frame() -> None:
    with pytest.raises(BeaconError):
        Rig(station_call="TOOLONGCALL").beacon.status_frame("QRV")


# ---- the timer -----------------------------------------------------------------------------------------------------------------------------------

async def quiet(rig: Rig, ticks: int = 8) -> None:
    await asyncio.sleep(rig.beacon.tick_sec * ticks)


async def test_the_first_beacon_is_thirty_seconds_after_the_start_and_then_one_every_interval() -> None:
    rig = Rig(beacon_interval_min=2)
    await rig.beacon.start()
    try:
        started = rig.clock()
        assert rig.beacon.next_due == started + timedelta(seconds=30)
        rig.clock.advance(29)
        await quiet(rig)
        assert rig.tnc.sent == []
        rig.clock.advance(1)
        await until(lambda: len(rig.tnc.sent) == 1)
        assert (rig.beacon.last_sent, rig.beacon.last_reason) == (rig.clock(), "interval") and rig.beacon.next_due == rig.clock() + timedelta(minutes=2)
        rig.clock.advance(119)
        await quiet(rig)
        assert len(rig.tnc.sent) == 1
        rig.clock.advance(1)
        await until(lambda: len(rig.tnc.sent) == 2)
        await quiet(rig)
        assert len(rig.tnc.sent) == 2, "one beacon for one interval, however late the tick"
    finally:
        await rig.beacon.stop()


async def test_a_beacon_on_request_moves_the_next_one_an_interval_on() -> None:
    rig = Rig(beacon_interval_min=10)
    await rig.beacon.start()
    try:
        rig.clock.advance(100)
        assert rig.beacon.send_now()
        assert rig.beacon.next_due == rig.clock() + timedelta(minutes=10)
        rig.clock.advance(599)
        await quiet(rig)
        assert len(rig.tnc.sent) == 1
    finally:
        await rig.beacon.stop()


async def test_a_beacon_due_while_the_radio_is_silent_waits_told_once_and_goes_out_on_the_first_tick_after_it_answers(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.beacon")
    rig = Rig(beacon_interval_min=5)
    rig.tnc.state = Source.State.SILENT
    await rig.beacon.start()
    try:
        started = rig.clock()
        rig.clock.advance(30)
        await quiet(rig)
        rig.clock.advance(3 * 300)                                                    # (several intervals of outage: still one beacon, not a queue)
        await quiet(rig)
        assert rig.tnc.sent == [] and rig.beacon.last_sent is None
        assert rig.beacon.next_due == started + timedelta(seconds=30), "left where it was, in the past"
        told = [r for r in caplog.records if "it goes out when the radio is back" in r.getMessage()]
        assert len(told) == 1 and "the radio is silent" in told[0].getMessage(), "told once per outage"
        assert not rig.beacon.send_now() and rig.beacon.problem == "the radio is silent"
        rig.tnc.state = Source.State.CONNECTED
        await until(lambda: len(rig.tnc.sent) == 1)
        await quiet(rig)
        assert len(rig.tnc.sent) == 1 and rig.beacon.last_reason == "interval"
        assert (rig.beacon.last_sent, rig.beacon.next_due) == (rig.clock(), rig.clock() + timedelta(minutes=5))
    finally:
        await rig.beacon.stop()


async def test_a_beacon_due_while_the_tnc_is_not_connected_goes_out_when_it_is_back_and_a_second_outage_is_told_again(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.beacon")
    rig = Rig(beacon_interval_min=5)
    rig.tnc.state = Source.State.WAITING
    await rig.beacon.start()
    try:
        rig.clock.advance(30)
        await quiet(rig)
        assert rig.tnc.sent == []
        rig.tnc.state = Source.State.CONNECTED
        await until(lambda: len(rig.tnc.sent) == 1)
        rig.tnc.state = Source.State.WAITING
        rig.clock.advance(300)
        await quiet(rig)
        assert len(rig.tnc.sent) == 1
        rig.tnc.state = Source.State.CONNECTED
        await until(lambda: len(rig.tnc.sent) == 2)
        told = [r for r in caplog.records if "it goes out when the radio is back" in r.getMessage()]
        assert len(told) == 2 and all("the TNC is not connected" in r.getMessage() for r in told)
    finally:
        await rig.beacon.stop()


async def test_an_outage_shorter_than_the_interval_sends_nothing_extra() -> None:
    rig = Rig(beacon_interval_min=10)
    await rig.beacon.start()
    try:
        rig.clock.advance(30)
        await until(lambda: len(rig.tnc.sent) == 1)
        due = rig.beacon.next_due
        rig.tnc.state = Source.State.SILENT
        rig.clock.advance(240)
        await quiet(rig)
        rig.tnc.state = Source.State.CONNECTED
        await quiet(rig)
        assert len(rig.tnc.sent) == 1 and rig.beacon.next_due == due
        rig.clock.advance(360)
        await until(lambda: len(rig.tnc.sent) == 2)
    finally:
        await rig.beacon.stop()


async def test_a_frame_the_tnc_refuses_is_tried_again_after_retry_sec_and_goes_out_when_it_is_taken() -> None:
    rig = Rig(beacon_interval_min=5)
    rig.tnc.takes = False                                                             # (the Tnc is settling after entering KISS)
    await rig.beacon.start()
    try:
        rig.clock.advance(30)
        await until(lambda: rig.tnc.asked == 1)
        await quiet(rig)
        assert rig.tnc.asked == 1, "not asked again before retry_sec"
        rig.clock.advance(4.9)
        await quiet(rig)
        assert rig.tnc.asked == 1
        rig.tnc.takes = True
        rig.clock.advance(0.1)
        await until(lambda: len(rig.tnc.sent) == 1)
        assert rig.tnc.asked == 2 and (rig.beacon.last_sent, rig.beacon.next_due) == (rig.clock(), rig.clock() + timedelta(minutes=5))
        await quiet(rig)
        assert rig.tnc.asked == 2
    finally:
        await rig.beacon.stop()


async def test_six_refusals_in_a_row_skip_the_interval_and_the_next_is_the_first_boundary_after_now(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.beacon")
    rig = Rig(beacon_interval_min=5)
    rig.tnc.takes = False
    await rig.beacon.start()
    try:
        started = rig.clock()
        rig.clock.advance(30)
        for n in range(1, 6):
            await until(lambda want=n: rig.tnc.asked == want)
            rig.clock.advance(5)
        await until(lambda: rig.tnc.asked == 6)
        await until(lambda: rig.beacon.next_due == started + timedelta(seconds=30 + 300))
        await quiet(rig)
        assert rig.tnc.asked == 6 and rig.tnc.sent == [] and rig.beacon.last_sent is None
        assert any("refused 6 times" in r.getMessage() and "skipped" in r.getMessage() for r in caplog.records)
        rig.tnc.takes = True
        rig.clock.advance(300)
        await until(lambda: len(rig.tnc.sent) == 1)
        assert rig.tnc.asked == 7, "the count starts again with the next interval"
    finally:
        await rig.beacon.stop()


async def test_with_the_interval_at_zero_nothing_is_sent_and_nothing_is_due() -> None:
    rig = Rig()
    await rig.beacon.start()
    try:
        assert rig.beacon.next_due is None
        rig.clock.advance(7200)
        await quiet(rig)
        assert rig.tnc.sent == [] and rig.beacon.next_due is None
    finally:
        await rig.beacon.stop()


async def test_a_new_interval_takes_effect_at_once_and_zero_stops_the_timer() -> None:
    rig = Rig(beacon_interval_min=10)
    await rig.beacon.start()
    try:
        rig.clock.advance(30)
        await until(lambda: len(rig.tnc.sent) == 1)
        sent_at = rig.clock()
        assert rig.beacon.next_due == sent_at + timedelta(minutes=10)
        rig.set(beacon_interval_min=3)
        rig.beacon.settings_changed()
        assert rig.beacon.next_due == sent_at + timedelta(minutes=3), "counted from the latest beacon"
        rig.clock.advance(120)
        rig.set(beacon_interval_min=1)
        rig.beacon.settings_changed()
        await until(lambda: len(rig.tnc.sent) == 2)                                   # (the minute since the last one has passed: due at once)
        rig.set(beacon_interval_min=0)
        rig.beacon.settings_changed()
        assert rig.beacon.next_due is None
        rig.clock.advance(7200)
        await quiet(rig)
        assert len(rig.tnc.sent) == 2
        rig.set(beacon_interval_min=60)
        rig.beacon.settings_changed()
        assert rig.beacon.next_due == rig.beacon.last_sent + timedelta(minutes=60)    # type: ignore[operator]
    finally:
        await rig.beacon.stop()


async def test_the_beacon_that_was_never_sent_is_due_at_once_when_the_interval_is_first_set_late() -> None:
    rig = Rig()
    await rig.beacon.start()
    try:
        rig.clock.advance(3600)
        rig.set(beacon_interval_min=30)
        rig.beacon.settings_changed()
        await until(lambda: len(rig.tnc.sent) == 1)
    finally:
        await rig.beacon.stop()


async def test_a_setting_other_than_the_interval_leaves_the_time_of_the_next_beacon_alone() -> None:
    rig = Rig(beacon_interval_min=5)
    rig.tnc.state = Source.State.WAITING
    await rig.beacon.start()
    try:
        rig.clock.advance(30)
        await quiet(rig)                                                                                  # (the first one is due and waits for the TNC)
        due = rig.beacon.next_due
        rig.set(station_comment="mobile")
        rig.beacon.settings_changed()
        assert rig.beacon.next_due == due
        await quiet(rig)
        assert rig.tnc.sent == [], "saving the settings does not send a beacon"
        rig.tnc.state = Source.State.CONNECTED
        await until(lambda: len(rig.tnc.sent) == 1)
        assert rig.tnc.sent[0].info.endswith(b"mobile"), "the beacon is made when it is sent, from the settings then"
    finally:
        await rig.beacon.stop()


async def test_stop_ends_the_timer_and_start_again_counts_from_the_new_start() -> None:
    rig = Rig(beacon_interval_min=1)
    await rig.beacon.start()
    await rig.beacon.start()                                                                  # (once more changes nothing)
    await rig.beacon.stop()
    assert rig.beacon.next_due is None
    rig.clock.advance(3600)
    await quiet(rig)
    assert rig.tnc.sent == []
    await rig.beacon.start()
    try:
        assert rig.beacon.next_due == rig.clock() + timedelta(seconds=30)
    finally:
        await rig.beacon.stop()
