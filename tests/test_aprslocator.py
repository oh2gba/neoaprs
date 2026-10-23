"""Maidenhead locators in a status report, in Mic-E status text and in the locator beacon."""
import pytest

from neoaprs.aprslocator import Locator, grid_centre, split_beacon, split_locator


@pytest.mark.parametrize(("grid", "lat", "lon"), [
    ("IO91", 51.5, -1.0), ("IO91sx", 51.97917, -0.45833), ("IO91SX", 51.97917, -0.45833), ("KP20", 60.5, 25.0), ("AA00", -89.5, -179.0), ("RR99", 89.5, 179.0), ("JJ00aa", 0.02083, 0.04167),
])
def test_the_centre_of_a_square(grid: str, lat: float, lon: float) -> None:
    assert grid_centre(grid) == (pytest.approx(lat, abs=1e-4), pytest.approx(lon, abs=1e-4))


def test_a_locator_with_its_symbol_and_the_text_after_it() -> None:
    loc, rest = split_locator("IO91sx/- My house")
    assert loc == Locator("IO91sx", 51.97917, -0.45833, "/", "-") and rest == "My house"
    loc, rest = split_locator("IO91/G")
    assert loc is not None and (loc.grid, loc.symbol_code, rest) == ("IO91", "G", "")
    loc, _ = split_locator("IO91ab/-")                                    # (the six character form wins over a four character one with the overlay a)
    assert loc is not None and loc.grid == "IO91ab"
    loc, _ = split_locator("IO91\\G")
    assert loc is not None and loc.symbol_table == "\\"


@pytest.mark.parametrize("text", ["", "IO91", "IO91s", "IO91sx", "IO91sx/", "IO91sx/GHello", "io91sx/G", "SS91/G", "IO91sx#G", "IO9/G", "Hello", " IO91sx/G"])
def test_text_that_is_no_locator(text: str) -> None:
    assert split_locator(text) == (None, text)


def test_the_locator_beacon_may_leave_the_symbol_out() -> None:
    found = split_beacon("IO91SX")
    assert found is not None and found[0] == Locator("IO91SX", 51.97917, -0.45833, "/", "G") and found[1] == ""
    found = split_beacon("IO91]  hello")
    assert found is not None and (found[0].grid, found[1]) == ("IO91", "hello")
    found = split_beacon("KP20/- Helsinki")
    assert found is not None and (found[0].symbol_code, found[1]) == ("-", "Helsinki")
    assert split_beacon("hello") is None
