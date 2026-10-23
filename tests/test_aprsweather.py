"""The weather decoder (neoaprs/aprsweather.py): the conversions to metric, where the fields end and the comment begins, what is missing, the line a summary says, and the weather of a packet. The decoded cases of the
dispatcher (real reports and the spec's examples) are in tests/fixtures/aprs/cases.json."""
from datetime import UTC, datetime

import pytest

from neoaprs.aprsparse import parse
from neoaprs.aprsweather import Weather, parse_report, parse_weather, weather_text
from neoaprs.packet import ItemReport, ObjectReport, Other, Packet, Position, Status, ThirdParty
from neoaprs.packetcodec import decode_decoded, encode_decoded

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
REAL = "107/001g001t050r001p016P013h85b10284"


def weather(text: str) -> Weather:
    found, _ = parse_weather(text)
    assert found is not None
    return found


@pytest.mark.parametrize(("field", "name", "value"), [
    ("g010", "gust_kmh", 16.1), ("c000s010", "wind_kmh", 16.1), ("t032", "temp_c", 0.0), ("t212", "temp_c", 100.0), ("t-40", "temp_c", -40.0), ("t000", "temp_c", -17.8), ("t-05", "temp_c", -20.6),
    ("r100", "rain_1h_mm", 25.4), ("p016", "rain_24h_mm", 4.1), ("P013", "rain_today_mm", 3.3), ("r001", "rain_1h_mm", 0.3), ("h85", "humidity", 85), ("h01", "humidity", 1), ("h00", "humidity", 100),
    ("b10284", "pressure_hpa", 1028.4), ("b09900", "pressure_hpa", 990.0), ("L072", "luminosity", 72), ("L999", "luminosity", 999), ("l000", "luminosity", 1000), ("l123", "luminosity", 1123),
    ("#042", "rain_counter", 42), ("c220", "wind_dir", 220), ("c360", "wind_dir", 360), ("c000", "wind_dir", 0),
])
def test_a_field_is_converted_to_metric(field: str, name: str, value: float) -> None:
    assert getattr(weather(field), name) == pytest.approx(value, abs=0.05)


def test_snow_is_the_s_that_follows_the_wind_speed() -> None:
    assert weather("c220s004g005t077s002").snow_mm == pytest.approx(50.8) and weather("c220s004g005t077s002").wind_kmh == pytest.approx(6.4)
    assert weather("220/004g005t077r000p000P000h90b10100s010").snow_mm == pytest.approx(254.0)
    only = weather("c220s004")
    assert only.wind_kmh == pytest.approx(6.4) and only.snow_mm is None


def test_the_wind_of_a_position_takes_two_or_three_digits_of_direction() -> None:
    assert (weather("107/001").wind_dir, weather("96/001").wind_dir, weather("96/001").wind_kmh) == (107, 96, pytest.approx(1.6))


def test_the_fields_end_at_the_first_character_that_is_not_one_and_the_rest_is_the_comment() -> None:
    parsed, rest = parse_weather(REAL + " RX Igate & WX station")
    assert parsed is not None and parsed.raw == REAL and rest == " RX Igate & WX station"
    assert parse_weather("t050b10285Inkoo")[1] == "Inkoo"                                          # a comment glued to the data
    assert parse_weather("t050h79Lahti")[1] == "Lahti"                                             # a word that begins with a field letter but has no digits is a comment
    assert parse_weather("t050t060")[1] == "t060"                                                  # a field twice: the second is not a field
    assert parse_weather("t05")[1] == "t05" and parse_weather("t05")[0] is None                    # too short: no field at all
    assert parse_weather("g005t077wRSW")[1] == "wRSW"


@pytest.mark.parametrize("text", ["", "Hello there", "wRSW", "x220", ".../...", "g...t...h..b....."])
def test_text_without_a_value_is_no_weather(text: str) -> None:
    assert parse_weather(text)[0] is None


def test_every_field_missing_is_no_weather_but_the_fields_are_not_the_comment() -> None:
    assert parse_weather(".../...g...t...r...p...P...h..b.....") == (None, "")
    assert parse_weather(".../...g...t...r...p...P...h..b.....XYZ") == (None, "XYZ")


def test_dots_or_spaces_are_a_missing_field_and_the_others_still_count() -> None:
    w = weather("220/...g   t060r...p...P...h..b10130")
    assert (w.wind_dir, w.wind_kmh, w.gust_kmh, w.temp_c, w.rain_1h_mm, w.humidity, w.pressure_hpa) == (220, None, None, pytest.approx(15.6, abs=0.05), None, None, 1013.0)


def test_a_direction_over_360_is_none() -> None:
    assert weather("999/004").wind_dir is None and weather("999/004").wind_kmh == pytest.approx(6.4)


def test_the_conversions_of_the_real_report() -> None:
    w = weather(REAL)
    assert w == Weather(107, 1.6, 1.6, 10.0, 85, 1028.4, 0.3, 4.1, 3.3, raw=REAL)


def test_the_summary_says_only_the_fields_that_are_there() -> None:
    assert weather_text(weather(REAL)) == "wind 107° 2 km/h gusts 2, 10.0 °C, 85 %, 1028.4 hPa, rain 0.3 mm/h, 24 h 4.1 mm, today 3.3 mm"
    assert weather_text(weather("t-05")) == "-20.6 °C"
    assert weather_text(weather("g010")) == "wind gusts 16 km/h"
    assert weather_text(weather("c090s000L072")) == "wind 90° 0 km/h, 72 W/m²"
    assert weather_text(weather("p016")) == "rain 24 h 4.1 mm"


def test_a_positionless_report_has_its_time_and_then_the_fields() -> None:
    w = parse_report(b"_10090556c220s004g005t077r000p000P000h50b09900wRSW")
    assert w is not None and (w.wind_dir, w.temp_c, w.pressure_hpa) == (220, 25.0, 990.0)
    assert parse_report(b"_1009055") is None and parse_report(b"_10090556") is None and parse_report(b"!4903.50N/07201.75W_220/004") is None


def test_the_packet_says_whose_weather_and_the_summary_has_it() -> None:
    info = b"@210945z6024.43N/02352.73E_" + REAL.encode() + b" RX Igate & WX station"
    decoded = parse(info, "OH2MUI", "APRX29", NOW)
    packet = Packet(NOW, "in", b"", "OH2MUI", "APRX29", (), info, decoded)
    assert packet.weather_report == ("OH2MUI", weather(REAL))
    assert packet.summary == "position 60.4072 23.8788 /_ weather: wind 107° 2 km/h gusts 2, 10.0 °C, 85 %, 1028.4 hPa, rain 0.3 mm/h, 24 h 4.1 mm, today 3.3 mm - RX Igate & WX station"
    positionless = Packet(NOW, "in", b"", "OH2MUI", "APRX29", (), b"_10090556t050", parse(b"_10090556t050", "OH2MUI", "APRX29", NOW))
    assert positionless.weather_report == ("OH2MUI", weather("t050")) and positionless.summary == "weather: 10.0 °C"
    assert Packet(NOW, "in", b"", "OH2MUI", "APRX29", (), b"", Other("weather", "_x")).weather_report is None
    assert Packet(NOW, "in", b"", "OH2MUI", "APRX29", (), b"", Status("hi")).weather_report is None


def test_an_object_or_item_with_weather_is_the_weather_of_its_own_name_and_a_killed_one_has_none() -> None:
    position = Position(60.0, 24.0, "/", "_", weather=weather("t050"))
    assert Packet(NOW, "in", b"", "OH2MUI", "APRS", (), b"", ObjectReport("WXPOST", True, position)).weather_report == ("WXPOST", weather("t050"))
    assert Packet(NOW, "in", b"", "OH2MUI", "APRS", (), b"", ItemReport("WXITEM", True, position)).weather_report == ("WXITEM", weather("t050"))
    assert Packet(NOW, "in", b"", "OH2MUI", "APRS", (), b"", ObjectReport("WXPOST", False, position)).weather_report is None


def test_the_weather_of_a_third_party_packet_is_the_sender_inside() -> None:
    position = Position(60.0, 24.0, "/", "_", weather=weather("t050"))
    packet = Packet(NOW, "in", b"", "OH7JHF-1", "APRS", ("TCPIP",), b"", position, ThirdParty("OH2MUI", "APRS"))
    assert packet.weather_report == ("OH2MUI", weather("t050"))


def test_the_weather_survives_the_json_of_the_packet_table_and_a_row_from_before_has_none() -> None:
    position = Position(60.0, 24.0, "/", "_", "RX Igate", weather=weather(REAL))
    assert decode_decoded(encode_decoded(position)) == position
    other = Other("weather", "_10090556t050", weather("t050"))
    assert decode_decoded(encode_decoded(other)) == other
    before = '{"type":"position","lat":60.0,"lon":24.0,"symbol_table":"/","symbol_code":"_","comment":"t050","course_deg":null,"speed_kmh":null,"altitude_m":null,"timestamp":null,"messaging":false,"compressed":false,"ambiguity":0}'
    assert decode_decoded(before) == Position(60.0, 24.0, "/", "_", "t050")
    assert decode_decoded('{"type":"other","kind":"weather","text":"_x"}') == Other("weather", "_x")
