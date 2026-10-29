"""The settings of the base map (`map/radius_km`, `map/maxzoom`, `map/source`) and `map/station_hours`: their ranges, the forms a source may have, and that a wrong value names its key."""
from dataclasses import replace

import pytest

from neoaprs.config import DEFAULT_STATION_HOURS, DEFAULTS, STATION_HOURS, Config


def test_the_defaults_are_150_km_zoom_12_and_the_latest_daily_build() -> None:
    assert (DEFAULTS.map_radius_km, DEFAULTS.map_maxzoom, DEFAULTS.map_source) == (150, 12, "")


@pytest.mark.parametrize(("key", "good", "bad"), [("map/radius_km", ["10", "150", "1000", " 60 "], ["9", "1001", "0", "-5", "far", "1.5", ""]),
                                                   ("map/maxzoom", ["6", "12", "15"], ["5", "16", "high", ""])])
def test_the_radius_and_the_zoom_are_whole_numbers_in_their_ranges(key: str, good: list[str], bad: list[str]) -> None:
    for text in good:
        assert Config.check(key, text) == text.strip()
    for text in bad:
        with pytest.raises(ValueError, match=key):
            Config.check(key, text)


@pytest.mark.parametrize("text", ["", "https://build.protomaps.com/20261022.pmtiles", "http://127.0.0.1:8000/planet.pmtiles", "/maps/planet.pmtiles", "C:\\maps\\planet.pmtiles", "planet.pmtiles",
                                  "/data/My Maps/planet.pmtiles", "C:\\Users\\John Doe\\planet.pmtiles"])
def test_a_source_is_empty_a_web_address_or_a_path(text: str) -> None:
    assert Config.check("map/source", text) == text


@pytest.mark.parametrize("text", ["--help", "-o", "ftp://host/x.pmtiles", "s3://bucket/x.pmtiles", "https://host/two words.pmtiles", "x" * 501, "line\nbreak", "tab\there.pmtiles", "bell\x07.pmtiles", "nbsp\u00a0here.pmtiles", "- spaced option"])
def test_a_source_that_is_an_option_another_kind_of_address_or_not_printable_is_refused(text: str) -> None:
    with pytest.raises(ValueError, match="map/source"):
        Config.check("map/source", text)


def test_the_time_a_station_stays_on_the_map_is_1_3_6_12_or_24_hours_and_3_by_default() -> None:
    assert STATION_HOURS == (1, 3, 6, 12, 24) and DEFAULTS.map_station_hours == 3 == DEFAULT_STATION_HOURS and Config.from_data({}).map_station_hours == 3
    for hours in STATION_HOURS:
        assert Config.check("map/station_hours", f" {hours} ") == str(hours)
        assert Config.parse("map/station_hours", str(hours)) == hours
    for text in ["0", "2", "4", "48", "-3", "three", "1.5", ""]:
        with pytest.raises(ValueError, match="map/station_hours"):
            Config.check("map/station_hours", text)
    with pytest.raises(ValueError, match="map/station_hours: 2 is not one of 1, 3, 6, 12, 24"):
        Config.checked(DEFAULTS, {"map/station_hours": "2"})
    assert Config.checked(DEFAULTS, {"map/station_hours": "12"}).map_station_hours == 12


def test_a_stored_time_on_the_map_that_is_no_choice_falls_back_to_3_hours_and_a_choice_stays() -> None:
    assert Config.from_data({"map/station_hours": "5"}).map_station_hours == 3
    assert Config.from_data({"map/station_hours": "24"}).map_station_hours == 24
    assert Config.from_data({"map/station_hours": "24"}).to_data()["map/station_hours"] == "24"


def test_a_save_puts_the_values_in_force_and_a_bad_one_changes_nothing() -> None:
    config = Config.checked(DEFAULTS, {"map/radius_km": "40", "map/maxzoom": "14"})
    assert (config.map_radius_km, config.map_maxzoom) == (40, 14)
    with pytest.raises(ValueError, match="map/radius_km"):
        Config.checked(config, {"map/maxzoom": "10", "map/radius_km": "5000"})
    assert replace(config).map_maxzoom == 14
    assert config.to_data()["map/radius_km"] == "40" and Config.from_data(config.to_data()) == config


def test_a_stored_value_that_is_wrong_falls_back_to_the_default() -> None:
    config = Config.from_data({"map/radius_km": "huge", "map/maxzoom": "99", "map/source": "--help"})
    assert (config.map_radius_km, config.map_maxzoom, config.map_source) == (150, 12, "")
