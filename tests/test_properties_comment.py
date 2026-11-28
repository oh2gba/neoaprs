"""Properties of what a position comment carries: weather, telemetry, storm data, the data
extensions and DAO, locators and frequencies. Each splitter takes any text without raising, gives
back the rest of its text, and what it reads stays in its domain; base-91 telemetry and a locator
round-trip.
"""

import math

from hypothesis import given
from hypothesis import strategies as st

from neoaprs.aprsextension import (
    extension_lines,
    split_bearing,
    split_dao,
    split_extension,
    split_sign,
    with_dao,
)
from neoaprs.aprsfreq import frequency_text, name_frequency, named_frequency, split_frequency
from neoaprs.aprslocator import grid_centre, grid_of, split_beacon, split_locator
from neoaprs.aprsstorm import split_storm, storm_text
from neoaprs.aprstelemetry import (
    VALUE_LIMIT,
    TelemetryDefinition,
    apply_definition,
    describe,
    parse_telemetry,
    split_comment_telemetry,
)
from neoaprs.aprsweather import parse_report, parse_weather, weather_text
from neoaprs.units import base91_text
from tests.support.damaged import AFTER_IDENTIFIER, mutated, mutated_text

WEATHER = [
    "220/004g005t077r000p000P000h50b09900wRSW",
    "c220s004g005t-05r001p002P003h00b10132L456s1.5#123 comment",
    "090/010g015t045h85b10284l123",
    ".../...g...t...r...p...P...h..b.....",
    "   /   g   t 32",
]
TELEMETRY = [
    "T#005,199,000,255,073,123,01101001",
    "T#MIC,001,002,003,004,005,00000000",
    "T#MIC001,-2.5,.5,7.,1e3",
    "T#012,010,020,030,040,050,10101010Balloon",
    "T#005,",
]
COMMENT_TELEMETRY = ["|!!!!|", '|ss11223344{{!"|hello', "x |!!!\"#$%&'()*+,| y", "|ab|"]
DEFINITIONS = [
    "PARM.Battery,Temp,Light,A4,A5,B1,B2,B3,B4,B5,B6,B7,B8",
    "UNIT.V,deg.C,lux,,,on,on",
    "EQNS.0,0.075,0,0,0.5,-64,1e9,-1e9,0.1,0,1,0,0,1,0",
    "BITS.10110000,Weather balloon",
    "EQNS.0,1,0,x,1,0",
]
STORM = ["/HC/150^200/0980>090&030%040", "/TS/045^060/0995 Cyclone", "/TD", "/HC/150^200/0980>090&030%040extra"]
EXTENSIONS = ["PHG5132/comment", "PHG7~30", "RNG0050 net", "DFS2360", "PHG51320/x", "5L/1201"]
BEARINGS = ["/088/036/270/729", "/360/100", "/000/999 text"]
DAO = ["!W52! text", "text !wB(!", "!w  ! x !A12!", "!W5 !"]
LOCATORS = ["IO91SX/G hello", "KP20le/- net", "IO91/G", "JJ00aa\\n x", "RR99xx/!"]
FREQUENCIES = [
    "146.520MHz T100 R50k some text",
    "/146.94 MHz C107 -060 R25m",
    "A12.345MHz",
    "10.368GHz",
    "443.050MHz D023 +500 1750 444.150rx",
    "146.520MHz Toff",
]
TEXT = st.text(max_size=60)


def finite_or_none(*values: float | None) -> bool:
    return all(v is None or math.isfinite(v) for v in values)


@given(TEXT | mutated_text(WEATHER + list(AFTER_IDENTIFIER)))
def test_weather_fields_stay_in_their_domain(text: str) -> None:
    """parse_weather of any text gives fields in their domain and its raw text plus the rest is the text."""
    weather, rest = parse_weather(text)
    assert text.endswith(rest)
    if weather is None:
        return
    assert weather.raw + rest == text
    assert weather.wind_dir is None or 0 <= weather.wind_dir <= 360
    assert weather.humidity is None or 1 <= weather.humidity <= 100
    for value in (
        weather.wind_kmh,
        weather.gust_kmh,
        weather.rain_1h_mm,
        weather.rain_24h_mm,
        weather.rain_today_mm,
        weather.snow_mm,
        weather.pressure_hpa,
    ):
        assert value is None or (math.isfinite(value) and value >= 0)
    assert finite_or_none(weather.temp_c)
    weather_text(weather)


@given(st.binary(max_size=60) | mutated([b"_10090556" + w.encode() for w in WEATHER]))
def test_a_positionless_weather_report_never_raises(info: bytes) -> None:
    """parse_report of any bytes gives a Weather or None."""
    parse_report(info)


@given(TEXT | mutated_text(TELEMETRY))
def test_a_telemetry_report_stays_in_its_domain(info: str) -> None:
    """parse_telemetry of any text gives None or one to five finite values and at most eight bits."""
    report = parse_telemetry(info)
    if report is None:
        return
    assert 1 <= len(report.analog) <= 5
    assert all(math.isfinite(v) and abs(v) <= VALUE_LIMIT for v in report.analog)
    assert len(report.bits) <= 8 and set(report.bits) <= {"0", "1"}
    assert report.sequence is None or 0 <= report.sequence <= 99999


@given(
    st.integers(min_value=0, max_value=999),
    st.lists(st.integers(min_value=0, max_value=255), min_size=5, max_size=5),
    st.text(alphabet="01", min_size=8, max_size=8),
)
def test_a_telemetry_report_parses_back(sequence: int, analog: list[int], bits: str) -> None:
    """A report written as the spec writes it parses back to its sequence, values and bits."""
    report = parse_telemetry(f"T#{sequence:03d},{','.join(f'{v:03d}' for v in analog)},{bits}")
    assert report is not None
    assert (report.sequence, report.analog, report.bits) == (sequence, [float(v) for v in analog], bits)


@given(st.lists(st.integers(min_value=0, max_value=91 * 91 - 1), min_size=2, max_size=7), st.text(max_size=10))
def test_base91_telemetry_round_trips(values: list[int], comment: str) -> None:
    """|ss11..| written from numbers splits back into the same sequence, values and bits."""
    text, report = split_comment_telemetry(
        "|" + b"".join(base91_text(v, 2) for v in values).decode() + "|" + comment.replace("|", "")
    )
    assert report is not None and text == comment.replace("|", "").strip()
    assert report.sequence == values[0]
    assert report.analog == [float(v) for v in values[1:6]]
    if len(values) == 7:
        assert report.bits == "".join("1" if values[6] >> i & 1 else "0" for i in range(8))


@given(TEXT | mutated_text(COMMENT_TELEMETRY))
def test_base91_telemetry_in_any_comment_never_raises(text: str) -> None:
    """split_comment_telemetry of any text gives a comment and None or a report."""
    split_comment_telemetry(text)


@given(st.lists(TEXT | mutated_text(DEFINITIONS), max_size=4), TEXT | mutated_text(TELEMETRY))
def test_definitions_and_reports_describe_to_finite_values(messages: list[str], info: str) -> None:
    """Any definition messages applied to any report give finite values."""
    definition = TelemetryDefinition()
    for text in messages:
        definition = apply_definition(definition, text) or definition
    assert all(abs(n) <= VALUE_LIMIT for triple in definition.coefficients for n in triple)
    report = parse_telemetry(info)
    if report is not None:
        view = describe(report, definition)
        assert all(math.isfinite(c.value) for c in view.channels)


@given(TEXT | mutated_text(STORM))
def test_storm_data_stays_in_its_domain(text: str) -> None:
    """split_storm of any text gives None or storm data with fields of zero or more."""
    rest, storm = split_storm(text)
    if storm is None:
        assert rest == text
        return
    assert storm.storm_type in ("TS", "HC", "TD")
    for value in (
        storm.wind_kmh,
        storm.gust_kmh,
        storm.pressure_hpa,
        storm.hurricane_radius_km,
        storm.storm_radius_km,
        storm.gale_radius_km,
    ):
        assert value is None or value >= 0
    assert storm_text(storm)


@given(TEXT | mutated_text(EXTENSIONS + list(AFTER_IDENTIFIER)), st.booleans())
def test_a_data_extension_stays_in_its_domain(text: str, area: bool) -> None:
    """split_extension of any text gives finite values, a direction of 45 to 360 degrees or none."""
    ext, rest = split_extension(text, area)
    assert text.endswith(rest)
    if ext is None:
        return
    if ext.phg:
        assert ext.phg.power_w >= 0 and math.isfinite(ext.phg.range_km) and math.isfinite(ext.phg.height_m)
        assert ext.phg.direction_deg in (None, 45, 90, 135, 180, 225, 270, 315, 360)
    if ext.dfs:
        assert math.isfinite(ext.dfs.height_m)
    if ext.area:
        assert ext.area.lat_offset_deg >= 0 and math.isfinite(ext.area.lon_offset_deg)
    assert finite_or_none(ext.range_km)
    assert extension_lines(ext)


@given(TEXT | mutated_text(BEARINGS + EXTENSIONS))
def test_a_df_bearing_and_a_signpost_stay_in_their_domain(text: str) -> None:
    """split_bearing gives a bearing 0 to 359 and hits 0 to 9; split_sign one to three characters."""
    bearing, rest = split_bearing(text)
    assert text.endswith(rest)
    if bearing is not None:
        assert 0 <= bearing.bearing_deg < 360 and 0 <= bearing.hits <= 9 and math.isfinite(bearing.range_km)
    _, sign = split_sign(text)
    assert sign is None or 1 <= len(sign) <= 3


@given(TEXT | mutated_text(DAO), st.floats(min_value=-90, max_value=90), st.floats(min_value=-180, max_value=180))
def test_dao_keeps_a_place_on_the_earth(text: str, lat: float, lon: float) -> None:
    """with_dao of any comment's DAO keeps the place on the Earth and moves it less than 0.01 minute."""
    _, extra = split_dao(text)
    if extra is not None:
        assert all(0 <= m < 0.01 for m in extra)
    new_lat, new_lon = with_dao(lat, lon, extra)
    assert -90 <= new_lat <= 90 and -180 <= new_lon <= 180
    assert abs(new_lat - lat) < 0.01 / 60 and abs(new_lon - lon) < 0.01 / 60


@given(st.floats(min_value=-90, max_value=90), st.floats(min_value=-180, max_value=180))
def test_a_locator_holds_its_place(lat: float, lon: float) -> None:
    """grid_of then grid_centre gives a place within half a subsquare, and the same grid again."""
    grid = grid_of(lat, lon)
    centre_lat, centre_lon = grid_centre(grid)
    assert abs(centre_lat - lat) <= 1 / 48 + 1e-9 and abs(centre_lon - lon) <= 1 / 24 + 1e-9
    assert grid_of(centre_lat, centre_lon) == grid


@given(TEXT | mutated_text(LOCATORS))
def test_a_locator_in_any_text_is_on_the_earth(text: str) -> None:
    """split_locator and split_beacon of any text give None or a locator whose centre is on the Earth."""
    found = [split_locator(text)[0], (split_beacon(text) or (None, ""))[0]]
    for locator in found:
        if locator is not None:
            assert -90 <= locator.lat <= 90 and -180 <= locator.lon <= 180


@given(TEXT | mutated_text(FREQUENCIES))
def test_a_frequency_in_any_text_is_finite(text: str) -> None:
    """split_frequency and named_frequency of any text give None or finite frequencies of zero or more."""
    rest, frequency = split_frequency(text)
    found = [frequency, named_frequency(text[:9], frequency, rest)[0]]
    for f in found:
        if f is not None:
            assert math.isfinite(f.mhz) and f.mhz >= 0
            assert f.rx_mhz is None or math.isfinite(f.rx_mhz)
            assert f.range_km is None or f.range_km >= 0
            assert frequency_text(f)
    mhz = name_frequency(text)
    assert mhz is None or math.isfinite(mhz)


def test_a_kelvin_sign_names_no_microwave_band() -> None:
    """A Kelvin sign before a frequency is text, not band K."""
    assert split_frequency("K12.345MHz") == ("K12.345MHz", None)
