"""The preferences of the stations (neoaprs/services/prefbook.py) on a real message log and database thread: a path, a timeout and a count of attempts for each station, any of them, written through, read again by the
next start, the checks, and what is told."""
import asyncio
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs.config import DEFAULTS
from neoaprs.message import MessagingError
from neoaprs.messagelog import MessageLog
from neoaprs.pref import Pref
from neoaprs.services.prefbook import PrefBook
from neoaprs.store import DB_NAME
from tests.support.env import ON_AIR
from tests.support.clock import FixedClock
from tests.support.storedb import store_at


class Rig:
    def __init__(self, log: MessageLog, **changes: object) -> None:
        self.config = replace(ON_AIR, **changes)                     # type: ignore[arg-type]
        self.log = log
        self.book = PrefBook(log, lambda: self.config)
        self.told: list[tuple[str, Pref | None]] = []
        self.book.changed.connect(lambda call, pref: self.told.append((call, pref)))


@pytest.fixture
async def rig(tmp_path: Path) -> Rig:
    clock = FixedClock()
    store = await store_at(tmp_path / DB_NAME, clock)
    assert store.db is not None
    r = Rig(MessageLog(store.db, clock))
    await r.book.load()
    return r


@pytest.fixture
def restart(rig: Rig) -> Callable[[], Rig]:
    """A second book on the same database, as after a restart of the daemon."""
    def make() -> Rig:
        return Rig(rig.log)
    return make


async def test_a_station_has_the_defaults_until_it_is_given_something(rig: Rig) -> None:
    assert rig.book.all() == {} and rig.book.paths() == {} and rig.book.never_hidden() == frozenset()
    assert rig.book.path_for("OH2RDG") == ("WIDE1-1", "WIDE2-1") and rig.book.timeout_for("OH2RDG") is None


async def test_a_path_and_a_timeout_are_kept_by_the_call_and_read_back_by_the_next_start(rig: Rig, restart: Callable[[], Rig]) -> None:
    assert await rig.book.set_path(" oh2rdg ", "oh2rch-2, wide2-1") == ("OH2RCH-2", "WIDE2-1")
    assert await rig.book.set_timeout("oh2rdg", 45) == 45
    assert await rig.book.set_timeout("OH2PU-9", 0) == 0
    assert await rig.book.set_path("OH2XYZ", "") == ()
    assert rig.book.all() == {"OH2RDG": Pref(("OH2RCH-2", "WIDE2-1"), 45), "OH2PU-9": Pref(None, 0), "OH2XYZ": Pref((), None)}
    assert rig.book.path_for("oh2rdg") == ("OH2RCH-2", "WIDE2-1") and rig.book.timeout_for("oh2rdg") == 45
    assert rig.book.path_for("OH2PU-9") == ("WIDE1-1", "WIDE2-1") and rig.book.timeout_for("OH2PU-9") == 0, "a timeout alone leaves the path the default"
    assert rig.book.path_for("OH2XYZ") == () and rig.book.timeout_for("OH2XYZ") is None, "a path alone leaves the timeout the default; empty is direct"
    assert rig.book.path_for("OH2RDG-7") == ("WIDE1-1", "WIDE2-1") and rig.book.timeout_for("OH2RDG-7") is None, "another SSID is another station"
    assert rig.book.paths() == {"OH2RDG": ("OH2RCH-2", "WIDE2-1"), "OH2XYZ": ()} and rig.book.never_hidden() == frozenset({"OH2PU-9"})
    assert await rig.log.prefs() == {"OH2RDG": ("OH2RCH-2,WIDE2-1", 45, None, False), "OH2PU-9": (None, 0, None, False), "OH2XYZ": ("", None, None, False)}
    again = restart()
    await again.book.load()
    assert again.book.all() == rig.book.all()


async def test_a_station_has_the_beacon_path_until_it_is_given_one_of_its_own(rig: Rig) -> None:
    assert rig.book.path_for("OH2RDG") == ("WIDE1-1", "WIDE2-1")
    assert await rig.book.set_path("oh2rdg", " oh2rch-2 , wide2-1 ") == ("OH2RCH-2", "WIDE2-1")
    assert rig.book.path_for("OH2RDG") == ("OH2RCH-2", "WIDE2-1") and rig.book.path_for("oh2rdg") == ("OH2RCH-2", "WIDE2-1")
    assert rig.book.path_for("OH2RDG-7") == ("WIDE1-1", "WIDE2-1"), "a station with another SSID is another station"
    assert rig.book.path_for("not a call") == ("WIDE1-1", "WIDE2-1")
    rig.config = replace(rig.config, beacon_path="WIDE2-2")
    assert rig.book.path_for("OH2RDG-7") == ("WIDE2-2",) and rig.book.path_for("OH2RDG") == ("OH2RCH-2", "WIDE2-1")
    await rig.book.clear_path("OH2RDG")
    assert rig.book.path_for("OH2RDG") == ("WIDE2-2",)
    await rig.book.clear_path("OH2RDG")                                       # (no path to clear: no error)


async def test_an_empty_path_is_a_path_of_its_own_direct_and_not_the_default(rig: Rig) -> None:
    assert await rig.book.set_path("OH2RDG", "") == ()
    assert rig.book.path_for("OH2RDG") == () and rig.book.path_for("OH2XYZ") == ("WIDE1-1", "WIDE2-1")
    assert rig.book.paths() == {"OH2RDG": ()}
    rig.config = replace(rig.config, beacon_path="")
    await rig.book.set_path("OH2XYZ", "WIDE1-1")
    assert rig.book.path_for("OH2XYZ") == ("WIDE1-1",) and rig.book.path_for("OH2RDG") == ()


@pytest.mark.parametrize("call, path, reason", [("", "WIDE1-1", "call"), ("TOOLONGCALL", "", "call"), ("OH2RDG", "WIDE 1", "call"), ("OH2RDG", "WIDE1-16", "SSID"),
                                                ("OH2RDG", ",".join(["WIDE1-1"] * 9), "more than the 8")])
async def test_a_path_is_checked_as_the_beacon_path_is_and_a_bad_one_changes_nothing(rig: Rig, call: str, path: str, reason: str) -> None:
    with pytest.raises(MessagingError, match=reason):
        await rig.book.set_path(call, path)
    assert rig.book.all() == {} and await rig.log.prefs() == {}


async def test_up_to_eight_digipeaters_are_a_path(rig: Rig) -> None:
    assert len(await rig.book.set_path("OH2RDG", ",".join(f"RELAY-{n}" for n in range(1, 9)))) == 8


async def test_a_station_that_is_not_a_call_can_have_a_timeout_but_not_a_path(rig: Rig) -> None:
    await rig.book.set_timeout("STORM", 30)                           # (an object's name)
    await rig.book.set_timeout(" Big Storm ", 0)
    assert rig.book.all() == {"STORM": Pref(None, 30), "Big Storm": Pref(None, 0)} and rig.book.timeout_for("STORM") == 30 and rig.book.timeout_for("Big Storm") == 0
    with pytest.raises(MessagingError, match="call"):
        await rig.book.set_path("Big Storm", "WIDE1-1")
    assert rig.book.path_for("STORM") == ("WIDE1-1", "WIDE2-1")


async def test_clearing_one_part_keeps_the_other_and_clearing_the_last_removes_the_entry(rig: Rig, restart: Callable[[], Rig]) -> None:
    await rig.book.set_path("OH2RDG", "WIDE2-1")
    await rig.book.set_timeout("OH2RDG", 90)
    await rig.book.clear_path("OH2RDG")
    assert rig.book.all() == {"OH2RDG": Pref(None, 90)} and await rig.log.prefs() == {"OH2RDG": (None, 90, None, False)}
    assert rig.book.path_for("OH2RDG") == ("WIDE1-1", "WIDE2-1")
    await rig.book.set_path("OH2RDG", "")
    await rig.book.clear_timeout("OH2RDG")
    assert rig.book.all() == {"OH2RDG": Pref((), None)} and await rig.log.prefs() == {"OH2RDG": ("", None, None, False)}, "an empty path is something"
    await rig.book.clear_path("OH2RDG")
    assert rig.book.all() == {} and await rig.log.prefs() == {}, "nothing left in it: the row is deleted"
    again = restart()
    await again.book.load()
    assert again.book.all() == {}


async def test_what_is_told_is_each_set_and_each_clearing_that_changed_something(rig: Rig) -> None:
    await rig.book.set_path("OH2RDG", "WIDE2-1")
    await rig.book.set_path("OH2RDG", "WIDE2-1")                      # (set again: told again, the page is waiting for the answer)
    await rig.book.set_timeout("OH2RDG", 10)
    await rig.book.clear_timeout("OH2RDG")
    await rig.book.clear_timeout("OH2RDG")                            # (nothing to clear: not told)
    await rig.book.clear_path("OH2RDG")
    await rig.book.clear_path("OH2RDG")
    await rig.book.clear_path("NOBODY")
    await rig.book.clear_timeout("NOBODY")
    assert rig.told == [("OH2RDG", Pref(("WIDE2-1",), None)), ("OH2RDG", Pref(("WIDE2-1",), None)), ("OH2RDG", Pref(("WIDE2-1",), 10)), ("OH2RDG", Pref(("WIDE2-1",), None)), ("OH2RDG", None)]


@pytest.mark.parametrize("minutes", [-1, 10081, 100000])
async def test_a_timeout_out_of_range_is_refused_and_changes_nothing(rig: Rig, minutes: int) -> None:
    with pytest.raises(MessagingError, match="between 0 and 10080"):
        await rig.book.set_timeout("OH2RDG", minutes)
    assert rig.book.all() == {} and rig.told == [] and await rig.log.prefs() == {}


async def test_the_whole_range_is_a_timeout(rig: Rig) -> None:
    await rig.book.set_timeout("OH2RDG", 0)
    await rig.book.set_timeout("OH2RDG", 10080)
    assert rig.book.timeout_for("OH2RDG") == 10080 and rig.book.never_hidden() == frozenset()


@pytest.mark.parametrize("call", ["", "   ", "TOOLONGNAMEFORANOBJECT", "tab\there"])
async def test_a_name_that_is_neither_a_call_nor_an_objects_is_refused(rig: Rig, call: str) -> None:
    for action in (rig.book.set_timeout(call, 5), rig.book.clear_timeout(call)):
        with pytest.raises(MessagingError, match="not a call or the name of an object"):
            await action
    assert rig.book.timeout_for(call) is None and rig.book.all() == {} and rig.told == []


async def test_two_changes_at_once_for_one_station_both_land(rig: Rig) -> None:
    await asyncio.gather(rig.book.set_path("OH2RDG", "WIDE2-1"), rig.book.set_timeout("OH2RDG", 20))
    assert rig.book.all() == {"OH2RDG": Pref(("WIDE2-1",), 20)} and await rig.log.prefs() == {"OH2RDG": ("WIDE2-1", 20, None, False)}


async def test_a_database_that_is_not_open_keeps_nothing_and_the_caller_is_told() -> None:
    closed = Rig(MessageLog())
    with pytest.raises(MessagingError, match="the database is not open"):
        await closed.book.set_path("OH2RDG", "WIDE2-1")
    with pytest.raises(MessagingError, match="the database is not open"):
        await closed.book.set_timeout("OH2RDG", 5)
    with pytest.raises(MessagingError, match="the database is not open"):
        await closed.book.set_attempts("OH2RDG", 2)
    await closed.book.clear_timeout("OH2RDG")                         # (nothing there to clear: nothing to write)
    await closed.book.clear_attempts("OH2RDG")
    assert closed.book.all() == {} and closed.told == []


# ---- the attempts

async def test_a_station_has_the_setting_attempts_until_it_is_given_a_count_of_its_own(rig: Rig, restart: Callable[[], Rig]) -> None:
    assert rig.book.attempts_for("EMAIL-2") == DEFAULTS.messages_attempts == 6
    assert await rig.book.set_attempts(" email-2 ", 2) == 2
    assert rig.book.attempts_for("EMAIL-2") == 2 and rig.book.attempts_for("email-2") == 2
    assert rig.book.attempts_for("EMAIL-3") == 6 and rig.book.attempts_for("OH2RDG") == 6, "another SSID or another station has the setting"
    assert rig.book.attempts_for("not a call at all, with spaces and more than nine characters") == 6
    rig.config = replace(rig.config, messages_attempts=4)
    assert rig.book.attempts_for("OH2RDG") == 4 and rig.book.attempts_for("EMAIL-2") == 2, "the setting counts for a station that has none of its own"
    assert rig.book.all() == {"EMAIL-2": Pref(None, None, 2)} and rig.book.paths() == {} and rig.book.never_hidden() == frozenset()
    assert rig.book.path_for("EMAIL-2") == ("WIDE1-1", "WIDE2-1") and rig.book.timeout_for("EMAIL-2") is None, "attempts alone leave the path and the timeout the default"
    assert await rig.log.prefs() == {"EMAIL-2": (None, None, 2, False)}
    again = restart()
    await again.book.load()
    assert again.book.all() == rig.book.all()


async def test_attempts_sit_beside_a_path_and_a_timeout_and_the_entry_goes_when_the_last_of_the_three_does(rig: Rig) -> None:
    await rig.book.set_path("OH2RDG", "WIDE2-1")
    await rig.book.set_timeout("OH2RDG", 90)
    await rig.book.set_attempts("OH2RDG", 3)
    assert rig.book.all() == {"OH2RDG": Pref(("WIDE2-1",), 90, 3)} and await rig.log.prefs() == {"OH2RDG": ("WIDE2-1", 90, 3, False)}
    await rig.book.set_path("OH2RDG", "")                                    # (a path set again keeps the others)
    await rig.book.set_timeout("OH2RDG", 5)
    assert rig.book.all() == {"OH2RDG": Pref((), 5, 3)}
    await rig.book.clear_path("OH2RDG")
    await rig.book.clear_timeout("OH2RDG")
    assert rig.book.all() == {"OH2RDG": Pref(None, None, 3)}, "the attempts keep the entry"
    await rig.book.clear_attempts("OH2RDG")
    assert rig.book.all() == {} and await rig.log.prefs() == {}, "nothing left in it: the row is deleted"
    assert rig.told[-1] == ("OH2RDG", None)


async def test_clearing_the_attempts_gives_back_the_setting_and_clearing_none_is_no_error(rig: Rig) -> None:
    await rig.book.set_attempts("OH2RDG", 1)
    await rig.book.set_timeout("OH2RDG", 30)
    await rig.book.clear_attempts("OH2RDG")
    assert rig.book.attempts_for("OH2RDG") == 6 and rig.book.all() == {"OH2RDG": Pref(None, 30, None)}
    told = len(rig.told)
    await rig.book.clear_attempts("OH2RDG")
    await rig.book.clear_attempts("NOBODY")
    assert len(rig.told) == told, "nothing to clear: not told"


@pytest.mark.parametrize("attempts", [-1, 0, 11, 100])
async def test_attempts_out_of_range_are_refused_and_change_nothing(rig: Rig, attempts: int) -> None:
    with pytest.raises(MessagingError, match="between 1 and 10"):
        await rig.book.set_attempts("OH2RDG", attempts)
    assert rig.book.all() == {} and rig.told == [] and await rig.log.prefs() == {}


@pytest.mark.parametrize("attempts", [1, 2, 6, 10])
async def test_the_whole_range_is_a_count_of_attempts(rig: Rig, attempts: int) -> None:
    await rig.book.set_attempts("OH2RDG", attempts)
    assert rig.book.attempts_for("OH2RDG") == attempts


async def test_a_name_that_is_not_a_call_can_have_attempts_and_a_bad_one_is_refused(rig: Rig) -> None:
    await rig.book.set_attempts("STORM", 3)
    assert rig.book.attempts_for("STORM") == 3
    with pytest.raises(MessagingError, match="not a call or the name of an object"):
        await rig.book.set_attempts("", 3)
    with pytest.raises(MessagingError, match="not a call or the name of an object"):
        await rig.book.clear_attempts("TOOLONGNAMEFORANOBJECT")


async def test_attempts_set_at_once_with_a_path_both_land(rig: Rig) -> None:
    await asyncio.gather(rig.book.set_path("OH2RDG", "WIDE2-1"), rig.book.set_attempts("OH2RDG", 2))
    assert rig.book.all() == {"OH2RDG": Pref(("WIDE2-1",), None, 2)}


# ---- RF only

async def test_rf_only_is_set_kept_read_back_by_the_next_start_and_cleared(rig: Rig, restart: Callable[[], Rig]) -> None:
    assert rig.book.path_for("OH2RDG") == ("WIDE1-1", "WIDE2-1")
    await rig.book.set_rf_only("oh2rdg", True)
    assert rig.book.all() == {"OH2RDG": Pref(rf_only=True)} and await rig.log.prefs() == {"OH2RDG": (None, None, None, True)}
    assert rig.told == [("OH2RDG", Pref(rf_only=True))]
    again = restart()
    await again.book.load()
    assert again.book.all() == {"OH2RDG": Pref(rf_only=True)} and again.book.path_for("OH2RDG") == ("WIDE1-1", "WIDE2-1", "RFONLY")
    assert again.book.path_for("OH2XYZ") == ("WIDE1-1", "WIDE2-1"), "the others are not RF only"
    await rig.book.set_rf_only("OH2RDG", False)
    assert rig.book.all() == {} and await rig.log.prefs() == {}, "nothing left in it: the row is deleted"
    assert rig.told[-1] == ("OH2RDG", None) and rig.book.path_for("OH2RDG") == ("WIDE1-1", "WIDE2-1")


async def test_rf_only_goes_after_the_stations_own_path_and_direct_with_rf_only_is_just_rfonly(rig: Rig) -> None:
    await rig.book.set_path("OH2RDG", "OH2RCH-2,WIDE2-1")
    await rig.book.set_rf_only("OH2RDG", True)
    assert rig.book.path_for("OH2RDG") == ("OH2RCH-2", "WIDE2-1", "RFONLY")
    await rig.book.set_path("OH2RDG", "")
    assert rig.book.path_for("OH2RDG") == ("RFONLY",)
    await rig.book.set_path("OH2RDG", "OH2RCH-2,NOGATE")
    assert rig.book.path_for("OH2RDG") == ("OH2RCH-2", "NOGATE"), "NOGATE says it already"
    await rig.book.set_path("OH2RDG", "RFONLY,OH2RCH-2")
    assert rig.book.path_for("OH2RDG") == ("RFONLY", "OH2RCH-2"), "a path that has RFONLY already gets no second"


async def test_rf_only_sits_beside_the_other_parts_and_the_entry_goes_when_the_last_of_them_does(rig: Rig) -> None:
    await rig.book.set_attempts("OH2RDG", 3)
    await rig.book.set_rf_only("OH2RDG", True)
    assert rig.book.all() == {"OH2RDG": Pref(None, None, 3, True)}
    await rig.book.clear_attempts("OH2RDG")
    assert rig.book.all() == {"OH2RDG": Pref(rf_only=True)}, "RF only keeps the entry"
    await rig.book.set_timeout("OH2RDG", 5)
    await rig.book.set_rf_only("OH2RDG", False)
    assert rig.book.all() == {"OH2RDG": Pref(None, 5)}
    await rig.book.set_rf_only("OH2RDG", False)                              # (already off: nothing to tell)
    assert rig.told[-1] == ("OH2RDG", Pref(None, 5)) and len(rig.told) == 5


async def test_the_email_gateway_can_never_be_rf_only_and_the_reason_is_told(rig: Rig) -> None:
    with pytest.raises(MessagingError, match="EMAIL-2 cannot be RF only: the email gateway is on the internet"):
        await rig.book.set_rf_only("email-2", True)
    assert rig.book.all() == {} and rig.told == [] and await rig.log.prefs() == {}
    await rig.book.set_rf_only("EMAIL-2", False)                             # (off is no error)
    assert rig.told == []


@pytest.mark.parametrize("call", ["", "OH2 RDG", "TOOLONGCALL"])
async def test_rf_only_is_for_a_call_and_a_name_that_is_none_is_refused(rig: Rig, call: str) -> None:
    with pytest.raises(MessagingError):
        await rig.book.set_rf_only(call, True)
    assert rig.book.all() == {}


async def test_a_path_that_rfonly_would_make_longer_than_eight_is_refused_with_the_reason(rig: Rig) -> None:
    eight = ",".join(f"OH2RC{n}" for n in range(8))
    await rig.book.set_path("OH2RDG", eight)
    assert rig.book.path_for("OH2RDG") == tuple(eight.split(","))
    await rig.book.set_rf_only("OH2RDG", True)
    with pytest.raises(MessagingError, match="path too long for RF only"):
        rig.book.path_for("OH2RDG")
    await rig.book.set_path("OH2RDG", ",".join(eight.split(",")[:7]))
    assert len(rig.book.path_for("OH2RDG")) == 8 and rig.book.path_for("OH2RDG")[-1] == "RFONLY"
