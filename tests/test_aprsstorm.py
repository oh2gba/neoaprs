"""Storm data (neoaprs/aprsstorm.py): APRS101 chapter 12, in the units of the rest of the program."""
import pytest

from neoaprs.aprsstorm import Storm, split_storm, storm_text


def test_the_specs_hurricane_brenda() -> None:
    rest, storm = split_storm("/HC/150^200/0980>090&030%040")                       # (after the course and speed 088/036, which are the position's)
    assert rest == "" and storm == Storm("HC", 277.8, 370.4, 980, 166.7, 55.6, 74.1)


def test_the_radius_of_whole_gale_winds_is_optional_and_text_after_the_data_is_the_comment() -> None:
    rest, storm = split_storm("/TS/050^065/1002>060&020 moving north")
    assert rest == "moving north" and storm == Storm("TS", 92.6, 120.4, 1002, 111.1, 37.0, None)


def test_the_type_is_enough() -> None:
    assert split_storm("/TD") == ("", Storm("TD"))
    assert split_storm("/TD/0990") == ("", Storm("TD", pressure_hpa=990))


@pytest.mark.parametrize("text", ["", "storm", "/TSunami", "/XX/050", "TS/050", " /HC/050"])
def test_text_that_is_no_storm_data_is_left_alone(text: str) -> None:
    assert split_storm(text) == (text, None)


def test_a_field_with_too_many_digits_ends_the_data() -> None:
    assert split_storm("/HC/15000") == ("/15000", Storm("HC"))


def test_the_storm_in_words() -> None:
    assert storm_text(Storm("HC", 277.8, 370.4, 980, 166.7, 55.6, 74.1)) == (
        "hurricane, wind 278 km/h, gusts 370 km/h, 980 hPa, hurricane winds to 167 km, storm winds to 56 km, gale winds to 74 km")
    assert storm_text(Storm("TD")) == "tropical depression"
