"""The data extensions after the symbol of a position: PHG (and the range its formula gives), RNG, DFS, the bearing of a DF report and an area object's descriptor."""
import pytest

from neoaprs.aprsextension import Extensions, extension_lines, phg_range_km, split_bearing, split_extension


def test_phg_is_the_specs_example() -> None:
    ext, rest = split_extension("PHG5132Hello", False)
    assert rest == "Hello" and ext is not None and ext.phg is not None
    phg = ext.phg
    assert (phg.power_w, phg.gain_db, phg.direction_deg) == (25, 3, 90)
    assert phg.height_m == pytest.approx(6.1, abs=0.05)                  # 20 feet
    assert phg.range_km == pytest.approx(8 * 1.609, abs=0.2)             # "about 8 miles" says the specification


def test_the_phg_range_formula() -> None:
    assert phg_range_km(25, 20 * 0.3048, 3) == pytest.approx(12.8, abs=0.1)
    assert phg_range_km(0, 6.0, 0) == 0.0


@pytest.mark.parametrize(("code", "direction"), [("0", None), ("1", 45), ("2", 90), ("8", 360), ("9", None)])
def test_the_directivity_codes(code: str, direction: int | None) -> None:
    ext, _ = split_extension(f"PHG513{code}", False)
    assert ext is not None and ext.phg is not None and ext.phg.direction_deg == direction


def test_the_height_code_may_be_any_character_from_zero_up() -> None:
    ext, _ = split_extension("PHG3:20", False)                           # ':' is 10240 feet
    assert ext is not None and ext.phg is not None and ext.phg.height_m == pytest.approx(10240 * 0.3048, abs=0.1)


def test_rng_and_dfs() -> None:
    ext, rest = split_extension("RNG0050x", False)
    assert ext is not None and ext.range_km == pytest.approx(80.47, abs=0.1) and rest == "x"
    ext, rest = split_extension("DFS2360", False)
    assert ext is not None and ext.dfs is not None and rest == ""
    assert (ext.dfs.strength, ext.dfs.gain_db, ext.dfs.direction_deg) == (2, 6, None) and ext.dfs.height_m == pytest.approx(80 * 0.3048, abs=0.1)


@pytest.mark.parametrize("text", ["", "PHG513", "PHGx132", "RNG50", "DFS23", "phg5132", " PHG5132", "Hello"])
def test_text_that_is_no_extension_is_left_alone(text: str) -> None:
    assert split_extension(text, False) == (None, text)


def test_the_bearing_of_a_df_report() -> None:
    bearing, rest = split_bearing("/270/729 DF")
    assert rest == " DF" and bearing is not None
    assert (bearing.bearing_deg, bearing.hits, bearing.quality) == (270, 7, 9) and bearing.range_km == pytest.approx(4 * 1.609, abs=0.1)    # 2^2 miles
    assert split_bearing("/360/000")[0] is not None and (split_bearing("/360/000")[0] or bearing).bearing_deg == 0
    for text in ("/361/729", "/27/729", "270/729", "/270/72"):
        assert split_bearing(text) == (None, text)


def test_an_area_descriptor() -> None:
    ext, rest = split_extension("710/310{100}", True)
    assert rest == "{100}" and ext is not None and ext.area is not None
    assert (ext.area.shape, ext.area.colour, ext.area.lat_offset_deg, ext.area.lon_offset_deg) == ("filled ellipse", "cyan", 1.0, 1.0)
    ext, _ = split_extension("8101310", True)                              # the "/" before the colour digit is a 1: colours 10 to 15
    assert ext is not None and ext.area is not None and (ext.area.shape, ext.area.colour) == ("filled triangle", "dim violet")
    assert split_extension("0/3/04", True) == (None, "0/3/04")
    assert split_extension("PHG5132", True) == (None, "PHG5132")           # (an area symbol takes only an area descriptor)
    assert split_extension("710/310", False) == (None, "710/310")
    ext, _ = split_extension("205/506", True)                              # the offsets are square roots of hundredths of a degree: 5 is 25/100, 6 is 36/100
    assert ext is not None and ext.area is not None and (ext.area.lat_offset_deg, ext.area.lon_offset_deg) == (0.25, 0.36)


def test_the_lines_say_each_extension_once() -> None:
    ext, _ = split_extension("PHG5132", False)
    assert ext is not None
    assert extension_lines(ext) == ["PHG 25 W, 6 m, 3 dB, 90°, range 13 km"]
    omni, _ = split_extension("PHG5130", False)
    assert omni is not None and extension_lines(omni)[0].count("omni") == 1
    assert extension_lines(Extensions(range_km=80.47)) == ["range 80 km"]
    assert extension_lines(Extensions()) == []
