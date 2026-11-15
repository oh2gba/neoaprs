"""The preferences of the stations (neoaprs/services/prefbook.py) on a real message log and database thread: a path for each station, and RF only, either of them, written through, read again by the
next start, the checks, and what is told; and the path by radio: what a station is given is the path set on the radio the frame goes out on, a call that names no radio means radio 1."""
import asyncio
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs.config import Config
from neoaprs.message import MessagingError
from neoaprs.messagelog import MessageLog
from neoaprs.pref import Pref
from neoaprs.radiospec import FM_ID, HF_ID, RadioSpec
from neoaprs.route import Deliveries, route_of
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


async def test_radio_1_of_any_kind_goes_by_the_path_its_kind_recommends_while_it_has_none_of_its_own(rig: Rig) -> None:
    """A new installation's radio 1 may be of any kind: a LoRa board added first goes by LoRa's WIDE1-1 as a LoRa radio of any other id does, an FM radio 1 by the station's symbol's, as always."""
    rig.config = replace(rig.config, radios=(RadioSpec(FM_ID, "lora", "lora-tcp", "", True, 1), RadioSpec(3, "lora", "lora-tcp", "", True, 2)))
    assert rig.config.path_calls(FM_ID) == rig.config.path_calls(3) == ("WIDE1-1",) and rig.book.path_for("OH2RDG") == rig.book.path_for("OH2RDG", radio_id=3) == ("WIDE1-1",)
    rig.config = replace(rig.config, radios=(RadioSpec(FM_ID, "fm", "kiss", "", True, 1),))
    symbol = tuple(rig.config.recommended_path.split(","))
    assert symbol != ("WIDE1-1",) and rig.config.path_calls(FM_ID) == rig.config.beacon_path_calls == rig.book.path_for("OH2RDG") == symbol, "an FM radio 1: the station's symbol's"


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
    assert rig.book.path_for("OH2RDG") == ("WIDE2-2",) and rig.book.path_for("OH2RDG", 3) == ("WIDE2-2",)
    rig.config = replace(rig.config, station_symbol_code=">")
    assert rig.book.path_for("OH2RDG") == ("WIDE1-1", "WIDE2-1")
    rig.config = replace(rig.config, beacon_path="WIDE2-1")
    assert rig.book.path_for("OH2RDG") == ("WIDE2-1",), "a path that was set stays"


# ---- the path by radio ---------------------------------------------------------------------------------------------------------------------------------------

SECOND_FM = 3                                  # a second FM radio, which carries a path of its own
UNKNOWN = 9                                    # a radio the settings do not have


class Paths:
    """A `PathLog` in memory, as the table station_path will be reached: what it keeps, and whether it says a write was kept."""

    def __init__(self, rows: dict[tuple[str, int], str] | None = None, open: bool = True) -> None:
        self.rows = dict(rows or {})
        self.open = open

    async def paths(self) -> dict[str, dict[int, str]]:
        found: dict[str, dict[int, str]] = {}
        for (call, radio), path in self.rows.items():
            found.setdefault(call, {})[radio] = path
        return found

    async def save_path(self, call: str, radio: int, path: str) -> bool:
        if self.open:
            self.rows[call, radio] = path
        return self.open

    async def forget_path(self, call: str, radio: int) -> bool:
        if self.open:
            del self.rows[call, radio]
        return self.open


def three_radios(config: Config, path: str = "WIDE2-1") -> Config:
    """The settings with radios 1 and 2 as they are and a second FM radio, radio 3, whose own path is `path` (the stored radios of any number: a radio 3 already there is replaced, never added twice)."""
    return replace(config, radios=(*(spec for spec in config.radios if spec.id != SECOND_FM), RadioSpec(SECOND_FM, "fm", "kiss", "", True, 3, settings={"path": path})))


class RadioRig(Rig):
    def __init__(self, log: MessageLog, paths: Paths | None, heard: Deliveries | None = None, **changes: object) -> None:
        super().__init__(log, **changes)
        self.config = three_radios(self.config)
        self.paths = paths
        self.book = PrefBook(log, lambda: self.config, lambda call: heard, FixedClock(), paths=paths)
        self.book.changed.connect(lambda call, pref: self.told.append((call, pref)))
        self.paths_told: list[tuple[str, int]] = []
        self.book.path_changed.connect(lambda call, radio_id: self.paths_told.append((call, radio_id)))


def test_the_second_fm_radio_is_replaced_in_settings_that_already_have_it() -> None:
    """D1a's settings carry their radios into a copy (`replace`): the helper must not add radio 3 twice, or `config.radio(3)` would be the first of two."""
    made = three_radios(three_radios(replace(ON_AIR), path="WIDE1-1"), path="WIDE2-2")
    assert [spec.id for spec in made.radios].count(SECOND_FM) == 1 and made.radio(SECOND_FM) is not None and made.radio(SECOND_FM).value("path") == "WIDE2-2"  # type: ignore[union-attr]


async def test_the_path_a_station_is_given_is_the_one_set_on_the_radio_in_force(rig: Rig) -> None:
    r = RadioRig(rig.log, Paths())
    assert await r.book.set_path("OH2RDG", "OH2RCH-2") == ("OH2RCH-2",)
    assert await r.book.set_path("OH2RDG", "OH2RDS,WIDE2-1", SECOND_FM) == ("OH2RDS", "WIDE2-1")
    assert r.book.path_for("OH2RDG", radio_id=FM_ID) == ("OH2RCH-2",) and r.book.path_for("OH2RDG", None, SECOND_FM) == ("OH2RDS", "WIDE2-1")
    assert r.book.path_on("OH2RDG", FM_ID) == ("OH2RCH-2",) and r.book.path_on("OH2RDG", SECOND_FM) == ("OH2RDS", "WIDE2-1") and r.book.path_on("OH2RDG", HF_ID) is None
    assert r.book.paths(SECOND_FM) == {"OH2RDG": ("OH2RDS", "WIDE2-1")} and r.book.paths(HF_ID) == {}
    await r.book.set_path("OH2PU-9", "DIRECT", SECOND_FM)
    assert r.book.path_for("OH2PU-9", 1, SECOND_FM) == () and r.book.path_for("OH2PU-9") == ("WIDE1-1", "WIDE2-1"), "direct on the second radio, the beacon path on radio 1, where it has none"


async def test_a_call_that_names_no_radio_means_radio_1_as_before(rig: Rig) -> None:
    r = RadioRig(rig.log, Paths())
    await r.book.set_path("OH2RDG", "OH2RDS", SECOND_FM)
    await r.book.set_path("OH2RDG", "OH2RCH-2")
    assert r.book.path_for("OH2RDG") == r.book.path_for("OH2RDG", 2) == r.book.path_for("OH2RDG", None, FM_ID) == ("OH2RCH-2",)
    assert r.book.all() == {"OH2RDG": Pref(("OH2RCH-2",))} and r.book.paths() == {"OH2RDG": ("OH2RCH-2",)}, "the entry's path, which the page is told, is radio 1's"
    assert await rig.log.prefs() == {"OH2RDG": ("OH2RCH-2", False, None)} and r.paths is not None and r.paths.rows == {("OH2RDG", SECOND_FM): "OH2RDS"}
    await r.book.clear_path("OH2RDG")
    assert r.book.path_for("OH2RDG") == ("WIDE1-1", "WIDE2-1") and r.book.path_for("OH2RDG", None, SECOND_FM) == ("OH2RDS",), "clearing radio 1's leaves the other radio's"


async def test_a_station_with_no_path_on_a_radio_gets_that_radios_own_path(rig: Rig) -> None:
    r = RadioRig(rig.log, Paths(), beacon_path="WIDE1-1,WIDE2-2", station_symbol_table="/", station_symbol_code="-")
    assert r.book.path_for("OH2RDG", None, SECOND_FM) == ("WIDE2-1",), "the second FM radio's own path"
    assert r.book.path_for("OH2RDG") == ("WIDE1-1", "WIDE2-2"), "radio 1's is beacon/path"
    assert r.book.path_for("OH2RDG", None, HF_ID) == ("WIDE1-1", "WIDE2-2"), "a radio of a kind without a path setting: as before (whether its frame may carry it is the fit's to say)"
    assert r.book.path_for("OH2RDG", None, UNKNOWN) == ("WIDE1-1", "WIDE2-2"), "a radio the settings do not have: as before"
    r.config = three_radios(replace(r.config), path="")
    assert r.book.path_for("OH2RDG", None, SECOND_FM) == ("WIDE2-2",), "an empty path of a radio is the recommended path of the station's symbol"
    r.config = three_radios(replace(r.config), path="DIRECT")
    assert r.book.path_for("OH2RDG", None, SECOND_FM) == ()


async def test_the_path_lately_heard_comes_before_a_radios_own_path_and_after_the_one_set_on_it(rig: Rig) -> None:
    clock = FixedClock()
    heard = Deliveries()
    for _ in range(2):
        heard.note(route_of(("OH2RCH-2*",)), 1, clock())
    r = RadioRig(rig.log, Paths(), heard)
    assert r.book.path_for("OH2RDG", 1, SECOND_FM) == ("OH2RCH-2",) == r.book.path_for("OH2RDG", 1), "the first attempts go by the path that reached us"
    assert r.book.path_for("OH2RDG", None, SECOND_FM) == ("WIDE2-1",), "no attempt named: the radio's own"
    await r.book.set_path("OH2RDG", "OH2RDS", SECOND_FM)
    assert r.book.path_for("OH2RDG", 1, SECOND_FM) == ("OH2RDS",) and r.book.path_for("OH2RDG", 1) == ("OH2RCH-2",), "a path set on a radio wins on that radio alone"


async def test_rf_only_is_the_stations_on_every_radio(rig: Rig) -> None:
    r = RadioRig(rig.log, Paths())
    await r.book.set_rf_only("OH2RDG", True)
    await r.book.set_path("OH2RDG", "OH2RDS", SECOND_FM)
    assert r.book.path_for("OH2RDG", None, SECOND_FM) == ("OH2RDS", "RFONLY") and r.book.path_for("OH2RDG") == ("WIDE1-1", "WIDE2-1", "RFONLY")
    await r.book.set_path("OH2RDG", ",".join(f"OH2D{n}" for n in range(8)), SECOND_FM)
    with pytest.raises(MessagingError, match="path too long for RF only"):
        r.book.path_for("OH2RDG", None, SECOND_FM)
    assert r.book.path_for("OH2RDG") == ("WIDE1-1", "WIDE2-1", "RFONLY"), "on radio 1 it still fits"


async def test_the_paths_of_the_other_radios_are_kept_through_the_path_log_and_read_by_the_next_start(rig: Rig) -> None:
    paths = Paths({("OH2OLD", SECOND_FM): "OH2RCH-2,WIDE2-1", ("OH2OLD", FM_ID): "IGNORED", ("OH2DIR", SECOND_FM): ""})
    r = RadioRig(rig.log, paths)
    await r.book.load()
    assert r.book.paths(SECOND_FM) == {"OH2OLD": ("OH2RCH-2", "WIDE2-1"), "OH2DIR": ()} and r.book.paths() == {}, "radio 1's path is the entry's own, which the message log gives"
    await r.book.set_path("oh2rdg", "oh2rds , wide2-1", SECOND_FM)
    await r.book.clear_path("OH2OLD", SECOND_FM)
    await r.book.set_path("OH2DIR", "", SECOND_FM)                            # (an empty path takes it away, as on radio 1)
    await r.book.clear_path("OH2GONE", SECOND_FM)                             # (none to clear: no error, nothing written)
    assert paths.rows == {("OH2OLD", FM_ID): "IGNORED", ("OH2RDG", SECOND_FM): "OH2RDS,WIDE2-1"}
    assert r.paths_told == [("OH2RDG", SECOND_FM), ("OH2OLD", SECOND_FM), ("OH2DIR", SECOND_FM)], "each path that changed is told once, with its radio; clearing none tells nothing"
    again = RadioRig(rig.log, paths)
    await again.book.load()
    assert again.book.paths(SECOND_FM) == {"OH2RDG": ("OH2RDS", "WIDE2-1")} == r.book.paths(SECOND_FM)
    assert r.told == [] and r.book.all() == {}, "the entries, which the page is told, say radio 1's path: nothing of them changed"


async def test_without_a_path_log_a_path_on_another_radio_is_refused_and_radio_1s_is_kept_as_before(rig: Rig) -> None:
    r = RadioRig(rig.log, None)
    with pytest.raises(MessagingError, match="the path on radio 3 could not be kept"):
        await r.book.set_path("OH2RDG", "OH2RDS", SECOND_FM)
    await r.book.clear_path("OH2RDG", SECOND_FM)                              # (nothing there: nothing to refuse)
    await r.book.load()
    assert r.book.paths(SECOND_FM) == {} and r.book.path_for("OH2RDG", None, SECOND_FM) == ("WIDE2-1",)
    assert await r.book.set_path("OH2RDG", "OH2RCH-2") == ("OH2RCH-2",) and await rig.log.prefs() == {"OH2RDG": ("OH2RCH-2", False, None)}


async def test_a_path_the_log_could_not_keep_is_not_held_and_a_bad_one_changes_nothing(rig: Rig) -> None:
    paths = Paths({("OH2OLD", SECOND_FM): "OH2RCH-2"}, open=False)
    r = RadioRig(rig.log, paths)
    await r.book.load()
    with pytest.raises(MessagingError, match="could not be kept: the database is not open"):
        await r.book.set_path("OH2RDG", "OH2RDS", SECOND_FM)
    with pytest.raises(MessagingError, match="could not be removed: the database is not open"):
        await r.book.clear_path("OH2OLD", SECOND_FM)
    with pytest.raises(MessagingError):
        await r.book.set_path("OH2RDG", "not a path!", SECOND_FM)
    with pytest.raises(MessagingError):
        await r.book.set_path("not a call", "WIDE1-1", SECOND_FM)
    assert r.book.paths(SECOND_FM) == {"OH2OLD": ("OH2RCH-2",)}


async def test_a_path_set_cleared_or_changed_on_radio_1_is_told_with_its_radio_too_and_a_refused_one_is_not(rig: Rig) -> None:
    r = RadioRig(rig.log, Paths())
    await r.book.set_path("OH2RDG", "OH2RCH-2")
    await r.book.set_rf_only("OH2RDG", True)
    await r.book.set_path("OH2RDG", "OH2RCH-2")                               # (the same again: no change of the path)
    await r.book.clear_path("OH2RDG")
    with pytest.raises(MessagingError):
        await r.book.set_path("OH2RDG", "not a path!")
    assert r.paths_told == [("OH2RDG", FM_ID), ("OH2RDG", FM_ID)]
    closed = RadioRig(rig.log, Paths(open=False))
    with pytest.raises(MessagingError):
        await closed.book.set_path("OH2RDG", "OH2RDS", SECOND_FM)
    assert closed.paths_told == []


class ForgetsAll:
    """D2's message log as it forgets a station (`delete_pref`): the row of station_pref and the station's path on every radio."""

    def __init__(self, log: MessageLog, paths: Paths) -> None:
        self.forget, self.paths = log.forget_pref, paths

    async def __call__(self, call: str) -> bool:
        self.paths.rows = {(c, radio): path for (c, radio), path in self.paths.rows.items() if c != call}
        return await self.forget(call)


@pytest.mark.parametrize("forgets_all", [True, False])
async def test_clearing_the_last_part_of_an_entry_keeps_the_paths_on_the_other_radios(rig: Rig, monkeypatch: pytest.MonkeyPatch, forgets_all: bool) -> None:
    """Whether the message log forgets the station's other paths with its entry (D2's first meaning) or not, they stay, held and kept, and the next start has them; the ones that survived are not written again."""
    paths = Paths()
    r = RadioRig(rig.log, paths)
    await r.book.set_path("OH2RDG", "OH2RDS", SECOND_FM)
    await r.book.set_path("OH2RDG", "OH2RCH-2")
    if forgets_all:
        monkeypatch.setattr(rig.log, "forget_pref", ForgetsAll(rig.log, paths))
    written: list[tuple[str, int]] = []
    save = paths.save_path

    async def counted(call: str, radio: int, path: str) -> bool:
        written.append((call, radio))
        return await save(call, radio, path)
    monkeypatch.setattr(paths, "save_path", counted)
    await r.book.clear_path("OH2RDG")
    assert r.book.all() == {} and r.book.path_on("OH2RDG", SECOND_FM) == ("OH2RDS",)
    assert paths.rows == {("OH2RDG", SECOND_FM): "OH2RDS"} and written == ([("OH2RDG", SECOND_FM)] if forgets_all else [])
    again = RadioRig(rig.log, paths)
    await again.book.load()
    assert again.book.path_for("OH2RDG", None, SECOND_FM) == ("OH2RDS",) and again.book.all() == {}


async def test_a_path_on_another_radio_that_could_not_be_kept_again_is_said_in_the_log_and_no_longer_held(rig: Rig, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    paths = Paths()
    r = RadioRig(rig.log, paths)
    await r.book.set_path("OH2RDG", "OH2RDS", SECOND_FM)
    await r.book.set_rf_only("OH2RDG", True)
    monkeypatch.setattr(rig.log, "forget_pref", ForgetsAll(rig.log, paths))
    paths.open = False
    await r.book.set_rf_only("OH2RDG", False)
    assert r.book.all() == {} and r.book.path_on("OH2RDG", SECOND_FM) is None and r.paths_told[-1] == ("OH2RDG", SECOND_FM)
    assert "the path of OH2RDG on radio 3 was lost" in caplog.text
