"""The data extensions after the symbol of a position: PHG (and the range its formula gives), RNG, DFS, the bearing of a DF report and an area object's descriptor."""
import pytest

from neoaprs.aprsextension import Extensions, extension_lines, phg_range_km, split_bearing, split_dao, split_extension, with_dao


def test_phg_is_the_specs_example() -> None:
    ext, rest = split_extension("PHG5132Hello", False)
    assert rest == "Hello" and ext is not None and ext.phg is not None
    phg = ext.phg
    assert (phg.power_w, phg.gain_db, phg.direction_deg) == (25, 3, 90)
    assert phg.height_m == pytest.approx(6.1, abs=0.05)                  # 20 feet
    assert phg.range_km == pytest.approx(8 * 1.609, abs=0.2)             # "about 8 miles" says the specification


def test_the_probes_form_of_phg_is_read_and_its_rate_dropped() -> None:
    ext, rest = split_extension("PHG72604/ Pepperell", False)             # APRS 1.2: 4 beacons an hour, then the mandatory "/"
    assert rest == " Pepperell" and ext is not None and ext.phg is not None and ext.phg.power_w == 49
    ext, rest = split_extension("PHG7260A/x", False)                      # A is 10 an hour
    assert rest == "x" and ext is not None and ext.phg is not None
    assert split_extension("PHG72604 x", False)[1] == "4 x"                # without the "/" the digit is text


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
    assert (ext.area.shape, ext.area.colour) == ("filled ellipse", "cyan")
    assert (ext.area.lat_offset_deg, ext.area.lon_offset_deg) == (pytest.approx(4 / 60), pytest.approx(4 / 60))      # the spec's example: 4 minutes each way (10 * 10 / 1500 degrees)
    ext, _ = split_extension("8101310", True)                              # the "/" before the colour digit is a 1: colours 10 to 15
    assert ext is not None and ext.area is not None and (ext.area.shape, ext.area.colour) == ("filled triangle", "dim violet")
    assert split_extension("0/3/04", True) == (None, "0/3/04")
    assert split_extension("PHG5132", True) == (None, "PHG5132")           # (an area symbol takes only an area descriptor)
    assert split_extension("710/310", False) == (None, "710/310")
    ext, _ = split_extension("205/506", True)                              # the offsets are square roots of the degrees times 1500: 5 is 25/1500, 6 is 36/1500
    assert ext is not None and ext.area is not None and (ext.area.lat_offset_deg, ext.area.lon_offset_deg) == (pytest.approx(25 / 1500), pytest.approx(36 / 1500))


def test_the_lines_say_each_extension_once() -> None:
    ext, _ = split_extension("PHG5132", False)
    assert ext is not None
    assert extension_lines(ext) == ["PHG 25 W, 6 m, 3 dB, 90°, range 13 km"]
    omni, _ = split_extension("PHG5130", False)
    assert omni is not None and extension_lines(omni)[0].count("omni") == 1
    assert extension_lines(Extensions(range_km=80.47)) == ["range 80 km"]
    assert extension_lines(Extensions()) == []


# ---- !DAO! (APRS 1.2, chapter 5)

@pytest.mark.parametrize(("text", "rest", "extra"), [
    ("Comment !W12!", "Comment", (0.001, 0.002)),                    # human readable: thousandths of a minute
    ("!W12!Comment", "Comment", (0.001, 0.002)),
    ("!W 5! x", "x", (0.0, 0.005)),                                  # a blank adds nothing
    ("!w!!!", "", (0.0, 0.0)),                                       # base-91: "!" is 0
    ("!w5L!", "", (20 * 1.1 / 10000, 43 * 1.1 / 10000)),
    ("!w{{!", "", (90 * 1.1 / 10000, 90 * 1.1 / 10000)),
    ("!wAB! then !W34!", "then", (0.003, 0.004)),                    # the last counts
])
def test_dao_is_taken_out_of_the_comment_with_the_minutes_it_adds(text: str, rest: str, extra: tuple[float, float]) -> None:
    left, found = split_dao(text)
    assert left == rest and found == (pytest.approx(extra[0]), pytest.approx(extra[1]))


@pytest.mark.parametrize("text", ["", "Hello!", "!WAB!", "!w12", "!1AB!", "W12!", "!W123!", "a!b!c"])
def test_a_comment_without_dao_is_left_as_it_is(text: str) -> None:
    assert split_dao(text) == (text, None)


def test_dao_adds_away_from_the_equator_and_the_meridian() -> None:
    assert with_dao(60.0, 24.0, (0.006, 0.006)) == (pytest.approx(60.0001), pytest.approx(24.0001))
    assert with_dao(-60.0, -24.0, (0.006, 0.006)) == (pytest.approx(-60.0001), pytest.approx(-24.0001))
    assert with_dao(60.0, 24.0, None) == (60.0, 24.0)
