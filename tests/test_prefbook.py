"""The preferences of the stations (neoaprs/services/prefbook.py) on a real message log and database thread: a path for each station, and RF only, either of them, written through, read again by the
next start, the checks, and what is told."""
import asyncio
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs.message import MessagingError
from neoaprs.messagelog import MessageLog
from neoaprs.pref import Pref
from neoaprs.services.prefbook import PrefBook
from neoaprs.store import DB_NAME
from tests.support.env import ON_AIR
from tests.support.clock import FixedClock
from tests.support.storedb import keep_old_attempts, store_at


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
    assert rig.book.all() == {} and rig.book.paths() == {}
    assert rig.book.path_for("OH2RDG") == ("WIDE1-1", "WIDE2-1")


async def test_a_path_and_rf_only_are_kept_by_the_call_and_read_back_by_the_next_start(rig: Rig, restart: Callable[[], Rig]) -> None:
    assert await rig.book.set_path(" oh2rdg ", "oh2rch-2, wide2-1") == ("OH2RCH-2", "WIDE2-1")
    await rig.book.set_rf_only("OH2PU-9", True)
    assert await rig.book.set_path("OH2XYZ", "DIRECT") == ()
    assert rig.book.all() == {"OH2RDG": Pref(("OH2RCH-2", "WIDE2-1")), "OH2PU-9": Pref(None, True), "OH2XYZ": Pref(())}
    assert rig.book.path_for("oh2rdg") == ("OH2RCH-2", "WIDE2-1")
    assert rig.book.path_for("OH2XYZ") == (), "empty is direct"
    assert rig.book.path_for("OH2RDG-7") == ("WIDE1-1", "WIDE2-1"), "another SSID is another station"
    assert rig.book.paths() == {"OH2RDG": ("OH2RCH-2", "WIDE2-1"), "OH2XYZ": ()}
    assert await rig.log.prefs() == {"OH2RDG": ("OH2RCH-2,WIDE2-1", False, None), "OH2PU-9": (None, True, None), "OH2XYZ": ("", False, None)}
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


async def test_an_empty_path_takes_the_stations_own_away_and_direct_is_said_with_the_word(rig: Rig) -> None:
    await rig.book.set_path("OH2RDG", "WIDE2-2")
    assert await rig.book.set_path("OH2RDG", "  ") == () and rig.book.all() == {} and rig.told[-1] == ("OH2RDG", None), "empty is automatic again, not no digipeaters"
    assert await rig.book.set_path("OH2RDG", "direct") == () and rig.book.paths() == {"OH2RDG": ()}
    with pytest.raises(MessagingError, match="DIRECT"):
        await rig.book.set_path("OH2RDG", "DIRECT,WIDE1-1")


async def test_an_empty_path_is_a_path_of_its_own_direct_and_not_the_default(rig: Rig) -> None:
    assert await rig.book.set_path("OH2RDG", "DIRECT") == ()
    assert rig.book.path_for("OH2RDG") == () and rig.book.path_for("OH2XYZ") == ("WIDE1-1", "WIDE2-1")
    assert rig.book.paths() == {"OH2RDG": ()}
    rig.config = replace(rig.config, beacon_path="DIRECT")
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


async def test_a_station_that_is_not_a_call_can_have_no_path_and_no_rf_only(rig: Rig) -> None:
    for action in (rig.book.set_path("Big Storm", "WIDE1-1"), rig.book.set_rf_only("Big Storm", True)):
        with pytest.raises(MessagingError, match="call"):
            await action
    assert rig.book.path_for("STORM") == ("WIDE1-1", "WIDE2-1") and rig.book.all() == {}


async def test_clearing_one_part_keeps_the_other_and_clearing_the_last_removes_the_entry(rig: Rig, restart: Callable[[], Rig]) -> None:
    await rig.book.set_path("OH2RDG", "WIDE2-1")
    await rig.book.set_rf_only("OH2RDG", True)
    await rig.book.clear_path("OH2RDG")
    assert rig.book.all() == {"OH2RDG": Pref(None, True)} and await rig.log.prefs() == {"OH2RDG": (None, True, None)}
    assert rig.book.path_for("OH2RDG") == ("WIDE1-1", "WIDE2-1", "RFONLY")
    await rig.book.set_path("OH2RDG", "DIRECT")
    await rig.book.set_rf_only("OH2RDG", False)
    assert rig.book.all() == {"OH2RDG": Pref(())} and await rig.log.prefs() == {"OH2RDG": ("", False, None)}, "an empty path is something"
    await rig.book.clear_path("OH2RDG")
    assert rig.book.all() == {} and await rig.log.prefs() == {}, "nothing left in it: the row is deleted"
    again = restart()
    await again.book.load()
    assert again.book.all() == {}


async def test_what_is_told_is_each_set_and_each_clearing_that_changed_something(rig: Rig) -> None:
    await rig.book.set_path("OH2RDG", "WIDE2-1")
    await rig.book.set_path("OH2RDG", "WIDE2-1")                      # (set again: told again, the page is waiting for the answer)
    await rig.book.set_rf_only("OH2RDG", True)
    await rig.book.set_rf_only("OH2RDG", False)
    await rig.book.set_rf_only("OH2RDG", False)                       # (nothing to clear: not told)
    await rig.book.clear_path("OH2RDG")
    await rig.book.clear_path("OH2RDG")
    await rig.book.clear_path("NOBODY")
    assert rig.told == [("OH2RDG", Pref(("WIDE2-1",))), ("OH2RDG", Pref(("WIDE2-1",))), ("OH2RDG", Pref(("WIDE2-1",), True)), ("OH2RDG", Pref(("WIDE2-1",))), ("OH2RDG", None)]


async def test_two_changes_at_once_for_one_station_both_land(rig: Rig) -> None:
    await asyncio.gather(rig.book.set_path("OH2RDG", "WIDE2-1"), rig.book.set_rf_only("OH2RDG", True))
    assert rig.book.all() == {"OH2RDG": Pref(("WIDE2-1",), True)} and await rig.log.prefs() == {"OH2RDG": ("WIDE2-1", True, None)}


async def test_a_database_that_is_not_open_keeps_nothing_and_the_caller_is_told() -> None:
    closed = Rig(MessageLog())
    with pytest.raises(MessagingError, match="the database is not open"):
        await closed.book.set_path("OH2RDG", "WIDE2-1")
    with pytest.raises(MessagingError, match="the database is not open"):
        await closed.book.set_rf_only("OH2RDG", True)
    await closed.book.clear_path("OH2RDG")                            # (nothing there to clear: nothing to write)
    assert closed.book.all() == {} and closed.told == []


# ---- the attempts of an older version

async def test_a_count_of_attempts_kept_by_an_older_version_is_ignored_and_a_row_with_only_that_says_nothing(rig: Rig, restart: Callable[[], Rig]) -> None:
    assert rig.log.db is not None
    await keep_old_attempts(rig.log.db, "EMAIL-2", 2)
    await keep_old_attempts(rig.log.db, "OH2RDG", 3, "WIDE2-1")
    again = restart()
    await again.book.load()
    assert again.book.all() == {"OH2RDG": Pref(("WIDE2-1",))}, "the row of the count alone is no entry, and the other has only its path"
    assert await again.log.prefs() == {"OH2RDG": ("WIDE2-1", False, None)}


# ---- RF only

async def test_rf_only_is_set_kept_read_back_by_the_next_start_and_cleared(rig: Rig, restart: Callable[[], Rig]) -> None:
    assert rig.book.path_for("OH2RDG") == ("WIDE1-1", "WIDE2-1")
    await rig.book.set_rf_only("oh2rdg", True)
    assert rig.book.all() == {"OH2RDG": Pref(rf_only=True)} and await rig.log.prefs() == {"OH2RDG": (None, True, None)}
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
    await rig.book.set_path("OH2RDG", "DIRECT")
    assert rig.book.path_for("OH2RDG") == ("RFONLY",)
    await rig.book.set_path("OH2RDG", "OH2RCH-2,NOGATE")
    assert rig.book.path_for("OH2RDG") == ("OH2RCH-2", "NOGATE"), "NOGATE says it already"
    await rig.book.set_path("OH2RDG", "RFONLY,OH2RCH-2")
    assert rig.book.path_for("OH2RDG") == ("RFONLY", "OH2RCH-2"), "a path that has RFONLY already gets no second"


async def test_rf_only_sits_beside_the_path_and_the_entry_goes_when_the_last_of_them_does(rig: Rig) -> None:
    await rig.book.set_path("OH2RDG", "WIDE2-1")
    await rig.book.set_rf_only("OH2RDG", True)
    assert rig.book.all() == {"OH2RDG": Pref(("WIDE2-1",), True)}
    await rig.book.clear_path("OH2RDG")
    assert rig.book.all() == {"OH2RDG": Pref(rf_only=True)}, "RF only keeps the entry"
    await rig.book.set_path("OH2RDG", "WIDE2-2")
    await rig.book.set_rf_only("OH2RDG", False)
    assert rig.book.all() == {"OH2RDG": Pref(("WIDE2-2",))}
    await rig.book.set_rf_only("OH2RDG", False)                              # (already off: nothing to tell)
    assert rig.told[-1] == ("OH2RDG", Pref(("WIDE2-2",))) and len(rig.told) == 5


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


async def test_a_station_without_a_path_gets_the_recommended_path_of_the_symbol_as_the_fallback(rig: Rig) -> None:
    rig.config = replace(rig.config, beacon_path="", station_symbol_table="/", station_symbol_code="-")
    assert rig.book.path_for("OH2RDG") == ("WIDE2-1",) and rig.book.path_for("OH2RDG", 3) == ("WIDE2-1",)
    rig.config = replace(rig.config, station_symbol_code=">")
    assert rig.book.path_for("OH2RDG") == ("WIDE1-1", "WIDE2-1")
    rig.config = replace(rig.config, beacon_path="WIDE2-2")
    assert rig.book.path_for("OH2RDG") == ("WIDE2-2",), "a path that was set stays"
