"""The beacon of a moving station (neoaprs/services/beacon.py with services/mobilebeacon.py and neoaprs/smartbeacon.py) on a Tnc that is a stub, a GPS that is a stand-in and a clock the test holds: the compressed frame byte for
byte, the start beacon, the beacons by time at three speeds, the turn, no beacon without a fix, a request, `?APRSP`, and the timer's usual care (a radio that is away, a frame that is refused)."""
import logging
from datetime import timedelta

import pytest

from neoaprs import ax25
from neoaprs.aprsposition import parse_position
from neoaprs.clock import utc
from neoaprs.config import BEACON_OFF
from neoaprs.services.beacon import Beacon, BeaconError, NoFix
from neoaprs.services.queries import Queries
from neoaprs.source import Source
from neoaprs.stationbook import StationBook
from tests.support.env import idle_for, remember_stop, until
from tests.support.gps import FakeFixes, fix_at
from tests.support.rig import ServiceRig

# 60.43 N, 24.145 E, 54 km/h, 270 degrees, 31.4 m, as the compressed position of a car (symbol `>`)
KNOWN_INFO = b"=//w5#TW?M>eM[/A=000103NeoAPRS"


class Rig(ServiceRig):
    def __init__(self, fix: bool = True, **changes: object) -> None:
        super().__init__(**{"gps_source": "gpsd", "station_symbol_code": ">", "beacon_interval_min": 30, **changes})
        self.gps = FakeFixes()
        self.beacon = Beacon(self.tnc, lambda: self.config, self.clock, first_delay_sec=30.0, tick_sec=0.01, retry_sec=5.0, gps=self.gps)
        if fix:
            self.move(speed=54.0, course=270)

    def move(self, speed: float | None = 54.0, course: int | None = 270, **changes: object) -> None:
        """The GPS gives a fix now, with this speed and course."""
        self.gps.fix = fix_at(self.clock(), speed_kmh=speed, course_deg=course, **changes)             # type: ignore[arg-type]

    def tick(self) -> None:
        self.beacon._tick()


# ---- the frame

def test_the_frame_of_a_known_fix_is_these_bytes() -> None:
    rig = Rig()
    frame = rig.beacon.frame()
    assert frame.info == KNOWN_INFO and len(frame.info) == 1 + 13 + 9 + 7
    assert frame.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=//w5#TW?M>eM[/A=000103NeoAPRS" and frame.is_ui
    assert ax25.decode(ax25.encode(frame)) == frame


def test_the_frame_reads_back_as_a_compressed_position_with_the_course_speed_altitude_and_comment() -> None:
    p = parse_position(Rig().beacon.frame().info[1:], utc(2026, 10, 21, 12), messaging=True)
    assert p.compressed and p.messaging and (p.symbol_table, p.symbol_code) == ("/", ">")
    assert (p.lat, p.lon) == (pytest.approx(60.43, abs=3e-6), pytest.approx(24.145, abs=3e-6))
    assert p.course_deg in (268, 272) and p.speed_kmh == pytest.approx(54.0, rel=0.04) and p.altitude_m == pytest.approx(31.4, abs=0.31) and p.comment == "NeoAPRS"


def test_the_home_position_of_the_settings_is_not_in_the_frame_and_need_not_be_set() -> None:
    rig = Rig(station_lat=None, station_lon=None)
    assert rig.beacon.frame().info == KNOWN_INFO
    assert Rig(station_lat=10.0, station_lon=10.0).beacon.frame().info == KNOWN_INFO


def test_there_is_no_phg_in_a_mobile_beacon_and_a_long_comment_is_cut_not_refused() -> None:
    with_power = Rig(beacon_power_w=25, beacon_antenna_height_m=6, beacon_antenna_gain_db=3, station_comment="x" * 43)
    info = with_power.beacon.frame().info
    assert b"PHG" not in info and info.endswith(b"/A=000103" + b"x" * 31) and len(info[14:]) == 40, "the 36 characters of a comment with PHG do not apply, and 40 is the most a compressed report may have"
    no_altitude = Rig(station_comment="y" * 43)
    no_altitude.move(altitude_m=None)
    assert no_altitude.beacon.frame().info[14:] == b"y" * 40


def test_a_fix_without_speed_or_course_is_the_blank_form() -> None:
    rig = Rig(fix=False)
    rig.move(speed=None, course=None)
    info = rig.beacon.frame().info
    assert info[10:14] == b"> sT" and info[14:] == b"/A=000103NeoAPRS", "after the symbol code: a space and the fillers, then the altitude"


def test_the_comment_that_is_not_ascii_or_has_a_switch_character_makes_no_beacon() -> None:
    for comment in ("a|b", "a~b"):
        with pytest.raises(BeaconError):
            Rig(station_comment=comment).beacon.frame()


def test_the_beacon_of_a_station_that_stays_is_the_plain_position_whether_or_not_a_gps_is_there() -> None:
    rig = Rig(gps_source="off")
    assert rig.beacon.frame().info == b"=6010.20N/02456.40E>NeoAPRS"


@pytest.mark.parametrize("source", ["gpsd", "serial"])
def test_the_gps_source_alone_makes_the_beacon_a_moving_stations(source: str) -> None:
    rig = Rig(gps_source=source)
    assert rig.config.mobile and rig.beacon.frame().info == KNOWN_INFO
    rig.set(gps_source="off")
    assert not rig.config.mobile and rig.beacon.frame().info == b"=6010.20N/02456.40E>NeoAPRS"


# ---- no fix, no beacon

def test_with_no_fix_there_is_no_frame_and_the_home_position_is_not_put_in_its_place() -> None:
    rig = Rig(fix=False)
    with pytest.raises(NoFix, match="no position fix"):
        rig.beacon.frame()
    assert issubclass(NoFix, BeaconError)


def test_with_no_fix_nothing_is_sent_by_the_timer_or_on_request_and_the_beacon_says_why(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.beacon")
    rig = Rig(fix=False)
    rig.gps.why = "the latest GPS fix is 130 s old"
    rig.tick()
    rig.clock.advance(7200)
    rig.tick()
    assert rig.tnc.asked == 0 and rig.beacon.next_due is None
    assert rig.beacon.problem == "no beacon: the latest GPS fix is 130 s old"
    assert not rig.beacon.send_now() and rig.tnc.asked == 0 and rig.beacon.problem == "no beacon: the latest GPS fix is 130 s old"
    told = [r for r in caplog.records if "no beacon" in r.getMessage()]
    assert len(told) == 1, "told once, not at every tick"


def test_a_mobile_beacon_without_any_gps_service_is_no_beacon() -> None:
    rig = Rig(fix=False)
    bare = Beacon(rig.tnc, lambda: rig.config, rig.clock)
    with pytest.raises(NoFix, match="no GPS is set up"):
        bare.frame()
    bare._tick()
    assert rig.tnc.asked == 0


def test_when_the_fix_comes_back_the_beacon_follows_it_and_the_problem_is_gone(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.beacon")
    rig = Rig(fix=False)
    rig.tick()
    assert rig.beacon.problem
    rig.move()
    rig.tick()
    assert rig.beacon.problem == "" and len(rig.tnc.sent) == 1
    assert any("has a fix again" in r.getMessage() for r in caplog.records)


# ---- when it is sent

def test_the_first_fix_is_beaconed_at_once_as_the_start_and_the_next_by_time_is_due_at_the_rate_of_the_speed() -> None:
    rig = Rig()
    rig.tick()
    assert rig.tnc.infos() == [KNOWN_INFO]
    assert rig.beacon.last_reason == "start" and rig.beacon.mobile.last_reason == "start" and rig.beacon.last_sent == rig.clock()
    assert rig.beacon.next_due == rig.clock() + timedelta(seconds=60 * 100 / 54.0)
    rig.tick()
    assert len(rig.tnc.sent) == 1, "once"


# (the preset, a speed, the seconds between two beacons by time at that speed: the slow time when still, the fast time at and above the fast speed, fast_sec * fast_kmh / speed between)
RATES = [("car", 0.0, 1800), ("car", 50.0, 120), ("car", 130.0, 60), ("bicycle", 2.0, 1800), ("bicycle", 15.0, 120), ("bicycle", 40.0, 60),
         ("foot", 1.0, 1800), ("foot", 3.5, 240), ("foot", 10.0, 120), ("boat", 2.0, 1800), ("boat", 20.0, 120), ("boat", 50.0, 60)]


@pytest.mark.parametrize(("travel", "speed", "seconds"), RATES)
def test_the_time_between_beacons_is_the_rate_of_the_speed_for_the_preset(travel: str, speed: float, seconds: int) -> None:
    rig = Rig(fix=False, beacon_travel=travel)
    rig.move(speed=speed, course=90)
    rig.tick()
    assert len(rig.tnc.sent) == 1 and rig.beacon.next_due == rig.clock() + timedelta(seconds=seconds)
    rig.clock.advance(seconds - 1)
    rig.move(speed=speed, course=90)
    rig.tick()
    assert len(rig.tnc.sent) == 1
    rig.clock.advance(1)
    rig.move(speed=speed, course=90)
    rig.tick()
    assert len(rig.tnc.sent) == 2 and rig.beacon.last_reason == "time"
    assert rig.beacon.next_due == rig.clock() + timedelta(seconds=seconds)


# (the preset, a speed in km/h that is 30, 15, 20 or 5 miles per hour, the least turn in degrees there that is not beaconed, the least that is, the seconds a turn waits after the last beacon)
TURNS = [("car", 48.28, 35, 42, 15), ("bicycle", 24.14, 50, 55, 20), ("foot", 8.05, 60, 70, 60), ("boat", 32.19, 30, 36, 30)]


@pytest.mark.parametrize(("travel", "speed", "small", "big", "wait"), TURNS)
def test_a_turn_is_beaconed_from_the_threshold_of_the_preset_and_not_sooner_than_its_turn_time(travel: str, speed: float, small: int, big: int, wait: int) -> None:
    rig = Rig(fix=False, beacon_travel=travel)
    rig.move(speed=speed, course=0)
    rig.tick()
    rig.clock.advance(wait)
    rig.move(speed=speed, course=small)
    rig.tick()
    assert len(rig.tnc.sent) == 1, "a turn below the threshold of the speed is no turn"
    rig.clock.advance(-1)
    rig.move(speed=speed, course=big)
    rig.tick()
    assert len(rig.tnc.sent) == 1, "a turn one second before the turn time is too soon"
    rig.clock.advance(1)
    rig.move(speed=speed, course=big)
    rig.tick()
    assert len(rig.tnc.sent) == 2 and rig.beacon.last_reason == "turn"


def test_a_corner_is_beaconed_at_once_but_not_sooner_than_the_turn_time() -> None:
    rig = Rig(fix=False)
    rig.move(speed=60.0, course=90)
    rig.tick()
    rig.clock.advance(10)
    rig.move(speed=60.0, course=180)
    rig.tick()
    assert len(rig.tnc.sent) == 1, "10 seconds after the last: too soon for a turn"
    rig.clock.advance(5)
    rig.move(speed=60.0, course=180)
    rig.tick()
    assert len(rig.tnc.sent) == 2 and rig.beacon.last_reason == "turn"
    rig.clock.advance(20)
    rig.move(speed=60.0, course=185)
    rig.tick()
    assert len(rig.tnc.sent) == 2, "5 degrees from the turn is not a turn"


def test_a_station_that_stands_still_sends_no_turns_and_one_beacon_in_half_an_hour() -> None:
    rig = Rig(fix=False)
    rig.move(speed=2.0, course=0)
    rig.tick()
    for step in range(1, 120):
        rig.clock.advance(10)
        rig.move(speed=2.0, course=(step * 37) % 360)                         # (a GPS that stands still reports any course)
        rig.tick()
    assert len(rig.tnc.sent) == 1
    rig.clock.advance(700)
    rig.move(speed=2.0, course=5)
    rig.tick()
    assert len(rig.tnc.sent) == 2 and rig.beacon.last_reason == "time"


def test_a_change_of_what_the_station_moves_as_is_in_force_at_the_next_tick() -> None:
    rig = Rig(fix=False)
    rig.move(speed=7.0, course=90)
    rig.tick()
    assert rig.beacon.next_due == rig.clock() + timedelta(seconds=1800), "7 km/h is slow for a car"
    rig.set(beacon_travel="foot")
    rig.tick()
    assert rig.beacon.next_due == rig.clock() + timedelta(seconds=120), "and fast for a walker"


def test_the_interval_of_the_fixed_beacon_is_only_on_or_off_for_a_moving_station() -> None:
    for minutes in (20, 30, 1440):
        rig = Rig(beacon_interval_min=minutes)
        rig.tick()
        assert len(rig.tnc.sent) == 1 and rig.beacon.last_reason == "start", minutes
        rig.clock.advance(112)
        rig.move(speed=54.0, course=270)
        rig.tick()
        assert len(rig.tnc.sent) == 2 and rig.beacon.last_reason == "time", f"{minutes}: SmartBeaconing times it at 54 km/h, not the interval"


def test_with_the_interval_at_zero_the_moving_station_sends_nothing_by_the_timer_or_on_request_and_says_the_beacon_is_off() -> None:
    rig = Rig(beacon_interval_min=0)
    for _ in range(3):
        rig.tick()
        rig.clock.advance(600)
        rig.move(speed=90.0, course=10)                                                 # (a fast station that turns, with a fix: SmartBeaconing would say send)
    assert rig.tnc.sent == [] and rig.beacon.last_sent is None and rig.beacon.next_due is None and rig.beacon.mobile.last is None
    assert not rig.beacon.send_now() and rig.beacon.problem == BEACON_OFF and rig.tnc.sent == []


async def test_switching_a_moving_station_off_and_on_stops_and_resumes_smartbeaconing() -> None:
    rig = Rig()
    await rig.beacon.start()
    try:
        rig.tick()
        assert len(rig.tnc.sent) == 1
        rig.set(beacon_interval_min=0)
        rig.beacon.settings_changed()
        assert rig.beacon.next_due is None
        rig.clock.advance(1800)
        rig.move(speed=90.0, course=100)
        rig.tick()
        assert len(rig.tnc.sent) == 1
        rig.set(beacon_interval_min=30)                                                 # (On from Off stores the first interval, which is not used)
        rig.beacon.settings_changed()
        rig.tick()
        assert len(rig.tnc.sent) == 2 and rig.beacon.last_reason in ("time", "turn")
    finally:
        await rig.beacon.stop()


def test_a_request_sends_the_live_frame_and_the_times_count_from_it() -> None:
    rig = Rig()
    rig.tick()
    rig.clock.advance(30)
    rig.move(speed=54.0, course=270, lat=60.44)
    assert rig.beacon.send_now()
    assert rig.beacon.last_reason == "request" and rig.beacon.mobile.last_reason == "request" and rig.tnc.sent[-1].info != KNOWN_INFO
    assert parse_position(rig.tnc.sent[-1].info[1:], rig.clock()).lat == pytest.approx(60.44, abs=1e-5)
    assert rig.beacon.next_due == rig.clock() + timedelta(seconds=60 * 100 / 54.0)
    rig.clock.advance(100)
    rig.tick()
    assert len(rig.tnc.sent) == 2, "100 seconds after the request: the 111 of the rate are not over"


def test_a_corner_is_measured_from_the_course_of_the_last_beacon_even_when_it_was_a_request() -> None:
    rig = Rig(fix=False)
    rig.move(speed=60.0, course=90)
    assert rig.beacon.send_now()
    rig.clock.advance(20)
    rig.move(speed=60.0, course=200)
    rig.tick()
    assert rig.beacon.last_reason == "turn"


def test_a_fix_is_remembered_with_its_course_for_the_page() -> None:
    rig = Rig()
    rig.tick()
    last = rig.beacon.mobile.last
    assert last is not None and last.at == rig.clock() and last.course_deg == 270


# ---- the radio

def test_a_beacon_that_is_due_while_the_radio_is_away_waits_and_goes_out_with_the_fix_of_then(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.beacon")
    rig = Rig()
    rig.tnc.state = Source.State.WAITING
    rig.tick()
    rig.tick()
    assert rig.tnc.asked == 0 and len([r for r in caplog.records if "it goes out when the radio is back" in r.getMessage()]) == 1
    rig.clock.advance(600)
    rig.move(speed=54.0, course=270, lat=60.5)
    rig.tnc.state = Source.State.CONNECTED
    rig.tick()
    assert len(rig.tnc.sent) == 1 and rig.beacon.last_reason == "start"
    assert parse_position(rig.tnc.sent[0].info[1:], rig.clock()).lat == pytest.approx(60.5, abs=1e-5), "the position of now, not the one of when it fell due"


def test_a_frame_the_tnc_refuses_is_tried_again_and_after_six_refusals_a_minute_later(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.beacon")
    rig = Rig()
    rig.tnc.takes = False
    for _ in range(6):
        rig.tick()
        rig.clock.advance(5)
    assert rig.tnc.asked == 6 and any("tried again in 60 s" in r.getMessage() for r in caplog.records)
    rig.clock.advance(30)
    rig.tick()
    assert rig.tnc.asked == 6, "a minute has not passed since the sixth"
    rig.tnc.takes = True
    rig.clock.advance(60)
    rig.move()
    rig.tick()
    assert len(rig.tnc.sent) == 1


def test_receive_only_sends_nothing_and_says_so() -> None:
    rig = Rig(station_transmit=False)
    rig.tick()
    assert rig.tnc.asked == 0 and rig.beacon.problem
    assert not rig.beacon.send_now()


# ---- a change of the settings

async def test_the_timer_of_a_fixed_beacon_is_planned_again_when_the_station_turns_mobile_and_back() -> None:
    rig = Rig(gps_source="off", beacon_interval_min=10)
    await rig.beacon.start()
    try:
        assert rig.beacon.next_due == rig.clock() + timedelta(seconds=30)
        rig.set(gps_source="gpsd")
        rig.beacon.settings_changed()
        assert rig.beacon.next_due is None, "SmartBeaconing says when, at the next tick"
        await until(lambda: len(rig.tnc.sent) == 1)
        assert rig.beacon.last_reason == "start" and rig.beacon.next_due is not None
        rig.set(gps_source="off")
        rig.beacon.settings_changed()
        assert rig.beacon.next_due == rig.beacon.last_sent + timedelta(minutes=10)         # type: ignore[operator]
    finally:
        await rig.beacon.stop()


async def test_the_real_timer_beacons_on_the_fix_and_the_clock() -> None:
    rig = Rig()
    await rig.beacon.start()
    try:
        await until(lambda: len(rig.tnc.sent) == 1)
        rig.clock.advance(112)
        rig.move()
        await until(lambda: len(rig.tnc.sent) == 2)
        assert rig.beacon.last_reason == "time"
        rig.gps.fix = None
        rig.clock.advance(7200)
        await idle_for(0.1)
        assert len(rig.tnc.sent) == 2
    finally:
        await rig.beacon.stop()


# ---- ?APRSP

class QueryRig(Rig):
    def __init__(self, **changes: object) -> None:
        super().__init__(**changes)
        self.book = StationBook(self.clock)
        self.q = Queries(self.tnc, lambda: self.config, self.beacon, lambda: None, self.book, lambda call: self.config.beacon_path_calls, self.clock, delay=lambda: 0.0)
        remember_stop(self.q.stop)

    def ask(self, text: str) -> None:
        from neoaprs.packet import Message, Packet
        self.q.on_packet(Packet(self.clock(), "in", b"", "OH2RDG", "APZNEO", ("OH2RCH-2*",), b"", Message("OH2GBA", text)))


def test_aprsp_is_answered_with_the_position_as_it_is_now() -> None:
    rig = QueryRig()
    rig.ask("?APRSP")
    assert rig.tnc.infos() == [KNOWN_INFO]
    rig.clock.advance(60)
    rig.move(lat=60.5)
    rig.ask("?APRSP")
    assert parse_position(rig.tnc.infos()[1][1:], rig.clock()).lat == pytest.approx(60.5, abs=1e-5)
    assert rig.beacon.last_sent is None, "an answer is not a beacon: SmartBeaconing is not restarted by it"


def test_aprsp_is_not_answered_without_a_fix_and_the_log_says_why(caplog: pytest.LogCaptureFixture) -> None:
    rig = QueryRig(fix=False)
    with caplog.at_level(logging.WARNING, "neoaprs.queries"):
        rig.ask("?APRSP")
    assert rig.tnc.sent == [] and any("no position fix" in r.getMessage() for r in caplog.records)
