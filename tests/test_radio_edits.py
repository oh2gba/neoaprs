"""The checks of neoaprs/radioedits.py without a daemon: a radio's place is a whole number the
database holds."""
import pytest

from neoaprs.config import DEFAULTS
from neoaprs.radioedits import MAX_POSITION, changed_radio
from neoaprs.radiospec import FM_ID, RadioError


@pytest.mark.parametrize("position", [0, -1, MAX_POSITION + 1, 10**6 * MAX_POSITION, 2**63, True, "2"])
def test_a_place_that_is_no_whole_number_from_1_to_the_last_is_refused(position: object) -> None:
    with pytest.raises(RadioError, match=f"radio/1/position: a whole number from 1 to {MAX_POSITION}"):
        changed_radio(DEFAULTS, FM_ID, {"position": position})


def test_the_last_place_is_taken() -> None:
    assert changed_radio(DEFAULTS, FM_ID, {"position": MAX_POSITION}).position == MAX_POSITION == 2**31 - 1
