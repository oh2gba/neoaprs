"""The alerts set on stations (neoaprs/services/stationalerts.py) on a real station book and real preferences on a database: each of the three (on the air, within N km, heard direct) fires once for each crossing
and not again until it is reset, an alert never fires for what was already true when it was set, our own station and our own objects have none, the internet counts only while it is shown, and an alert is
read back by the next start."""
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs.message import MessagingError
from neoaprs.messagelog import MessageLog
from neoaprs.ownobject import OwnObject
from neoaprs.packet import Packet, Position, Status
from neoaprs.pref import Alert, Fired
from neoaprs.services.prefbook import PrefBook
from neoaprs.services.stationalerts import QUIET, StationAlerts, outside_km
from neoaprs.stationbook import StationBook
from neoaprs.store import DB_NAME
from neoaprs.web.protocol import TOPIC_NAMES
from tests.support.air import on_air
from tests.support.alertcmd import writing_titled
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR, Env, until
from tests.support.storedb import store_at

HOME = (60.17, 24.94)
DEGREE_KM = 111.2                          # (a degree of latitude, near enough: the tests place a station so many km north of us)
VIA_DIGI = ("OH2RCH-2*", "WIDE2-1")
DIRECT = ("WIDE1-1", "WIDE2-1")            # (nothing repeated: heard direct)
QUIET_SEC = QUIET.total_seconds()


def north(km: float) -> Position:
    return Position(lat=HOME[0] + km / DEGREE_KM, lon=HOME[1], symbol_table="/", symbol_code=">")


class Rig:
    def __init__(self, log: MessageLog, clock: FixedClock, **changes: object) -> None:
        self.config = replace(ON_AIR, **changes)                     # type: ignore[arg-type]
        self.clock = clock
        self.book = StationBook(clock)
        self.book.set_me("OH2GBA", *HOME)
        self.prefs = PrefBook(log, lambda: self.config, clock=clock)
        self.alerts = StationAlerts(self.book, self.prefs, lambda: self.config, clock)
        self.fired: list[Fired] = []
        self.book.changed.connect(self.alerts.station_changed)       # (what neoaprs/wiring.py connects)
        self.prefs.changed.connect(self.alerts.pref_changed)
        self.alerts.fired.connect(self.fired.append)

    async def start(self) -> "Rig":
        await self.prefs.load()
        self.alerts.load()
        return self

    def hear(self, call: str = "OH2XYZ", after_sec: float = 60, decoded: object = None, path: tuple[str, ...] = VIA_DIGI, via: str = "rf") -> None:
        self.clock.advance(after_sec)
        self.book.take(Packet(heard_at=self.clock(), direction="in", raw=b"", source=call, destination="APRS", path=path, info=b"", decoded=decoded or Status("on"), via=via))  # type: ignore[arg-type]

    def kinds(self) -> list[tuple[str, str]]:
        return [(f.call, f.kind) for f in self.fired]


@pytest.fixture
async def log(tmp_path: Path) -> MessageLog:
    store = await store_at(tmp_path / DB_NAME, FixedClock())
    assert store.db is not None
    return MessageLog(store.db, FixedClock())


@pytest.fixture
async def rig(log: MessageLog) -> Rig:
    return await Rig(log, FixedClock()).start()


async def test_on_the_air_fires_after_half_an_hour_of_silence_once_and_not_again_until_it_was_silent_again(rig: Rig) -> None:
    rig.hear()
    await rig.alerts.set("oh2xyz", Alert(on_air=True))
    rig.hear(after_sec=60)
    assert rig.fired == [], "heard a minute ago: it was on the air already when the alert was set"
    rig.hear(after_sec=QUIET_SEC)
    assert rig.kinds() == [("OH2XYZ", "on_air")] and rig.fired[0].text == "OH2XYZ is on the air" and rig.fired[0].at == rig.clock()
    rig.hear(after_sec=60)
    rig.hear(after_sec=QUIET_SEC - 1)
    assert len(rig.fired) == 1, "every packet within the half hour is the same time on the air"
    rig.hear(after_sec=QUIET_SEC + 1)
    assert rig.kinds() == [("OH2XYZ", "on_air")] * 2


async def test_a_station_never_heard_fires_at_its_first_packet_and_another_station_never(rig: Rig) -> None:
    await rig.alerts.set("OH2NEW-9", Alert(on_air=True))
    rig.hear("OH2ABC")
    rig.hear("OH2NEW-9")
    rig.hear("OH2NEW-9")
    assert rig.kinds() == [("OH2NEW-9", "on_air")]


async def test_within_fires_when_the_station_comes_in_from_outside_once_and_again_only_after_it_was_well_outside(rig: Rig) -> None:
    rig.hear(decoded=north(22))
    await rig.alerts.set("OH2XYZ", Alert(within_km=10))
    rig.hear(decoded=north(15))
    assert rig.fired == []
    rig.hear(decoded=north(8.24))
    assert rig.kinds() == [("OH2XYZ", "within")] and rig.fired[0].text == "OH2XYZ is 8.2 km from you" and rig.fired[0].km == 8.2
    rig.hear(decoded=north(3))
    rig.hear(decoded=north(10.5))                                       # (beyond 10 km, but not beyond the margin: a position that wanders on the edge)
    rig.hear(decoded=north(9.5))
    assert len(rig.fired) == 1 and outside_km(10) == 11
    rig.hear(decoded=north(25))
    rig.hear(decoded=north(4))
    assert rig.kinds() == [("OH2XYZ", "within")] * 2 and rig.fired[1].text == "OH2XYZ is 4.0 km from you"
    rig.hear(decoded=north(40))
    rig.hear(decoded=north(12))
    assert len(rig.fired) == 2 and rig.fired[1].km == 4.0


async def test_a_station_already_near_when_the_alert_is_set_fires_only_after_it_has_been_outside(rig: Rig) -> None:
    rig.hear(decoded=north(3))
    await rig.alerts.set("OH2XYZ", Alert(within_km=10))
    rig.hear(decoded=north(2))
    assert rig.fired == []
    rig.hear(decoded=north(30))
    rig.hear(decoded=north(2))
    assert rig.kinds() == [("OH2XYZ", "within")]


async def test_within_fires_for_the_first_position_known_when_it_is_near_as_on_the_air_does_for_a_first_packet(rig: Rig) -> None:
    await rig.alerts.set("OH2NEW-9", Alert(within_km=10))                    # (never heard)
    rig.hear("OH2NEW-9", decoded=north(3))
    assert rig.kinds() == [("OH2NEW-9", "within")] and rig.fired[0].km == 3.0
    rig.hear("OH2NEW-9", decoded=north(2))
    assert len(rig.fired) == 1


async def test_within_fires_for_the_first_position_of_a_station_that_had_none_when_the_alert_was_set(rig: Rig) -> None:
    rig.hear("OH2OLD")
    await rig.alerts.set("OH2OLD", Alert(within_km=10))
    rig.hear("OH2OLD", decoded=north(3))
    assert rig.kinds() == [("OH2OLD", "within")]


async def test_within_fires_when_we_come_near_a_station_that_stands_still(rig: Rig) -> None:
    rig.hear(decoded=north(30))
    await rig.alerts.set("OH2XYZ", Alert(within_km=10))
    rig.clock.advance(600)
    rig.book.set_me("OH2GBA", HOME[0] + 25 / DEGREE_KM, HOME[1])          # (the GPS of a moving station: 5 km from it now)
    assert rig.kinds() == [("OH2XYZ", "within")] and rig.fired[0].km == 5.0 and rig.fired[0].at == rig.clock(), "when we came near, not when its position was"


async def test_heard_direct_fires_after_half_an_hour_without_and_not_for_a_packet_by_a_digipeater(rig: Rig) -> None:
    rig.hear(path=VIA_DIGI)
    await rig.alerts.set("OH2XYZ", Alert(direct=True))
    rig.hear(path=VIA_DIGI)
    assert rig.fired == []
    rig.hear(path=DIRECT)
    assert rig.kinds() == [("OH2XYZ", "direct")] and rig.fired[0].text == "OH2XYZ is heard direct"
    rig.hear(path=DIRECT, after_sec=QUIET_SEC - 60)
    rig.hear(path=VIA_DIGI, after_sec=QUIET_SEC)
    assert len(rig.fired) == 1, "heard direct within the half hour: the same crossing"
    rig.hear(path=DIRECT, after_sec=QUIET_SEC)
    assert rig.kinds() == [("OH2XYZ", "direct")] * 2


async def test_the_three_at_once_each_fire_by_themselves_and_nothing_fires_for_a_station_without_one(rig: Rig) -> None:
    rig.hear(decoded=north(30), path=VIA_DIGI)
    rig.hear("OH2ABC", decoded=north(30))
    await rig.alerts.set("OH2XYZ", Alert(on_air=True, within_km=10, direct=True))
    rig.hear(decoded=north(5), path=DIRECT, after_sec=QUIET_SEC)
    rig.hear("OH2ABC", decoded=north(5), path=DIRECT, after_sec=QUIET_SEC)
    assert sorted(rig.kinds()) == [("OH2XYZ", "direct"), ("OH2XYZ", "on_air"), ("OH2XYZ", "within")]


async def test_our_own_station_and_our_own_objects_have_no_alert(rig: Rig) -> None:
    rig.book.own_object(OwnObject("LEADER", "object", 60.2, 24.9, "/", ">", rig.clock(), rig.clock()))
    for call in ("OH2GBA", "oh2gba", "LEADER"):
        with pytest.raises(MessagingError, match="our own"):
            await rig.alerts.set(call, Alert(on_air=True))
    assert rig.prefs.all() == {}


async def test_an_alert_that_watches_nothing_takes_it_away_and_the_entry_goes_when_nothing_else_is_set(rig: Rig) -> None:
    await rig.prefs.set_rf_only("OH2XYZ", True)
    await rig.alerts.set("OH2XYZ", Alert(on_air=True, within_km=25))
    assert rig.prefs.all()["OH2XYZ"].alert == Alert(on_air=True, within_km=25)
    await rig.alerts.set("OH2XYZ", Alert())
    assert rig.prefs.all()["OH2XYZ"].alert is None and rig.alerts.alerts() == {}
    rig.hear()
    assert rig.fired == []
    await rig.prefs.set_rf_only("OH2XYZ", False)
    assert rig.prefs.all() == {}
    with pytest.raises(MessagingError, match="1 to 1000 km"):
        await rig.prefs.set_alert("OH2XYZ", Alert(within_km=0))


async def test_a_packet_from_the_internet_counts_only_while_the_internet_is_shown(log: MessageLog) -> None:
    rig = await Rig(log, FixedClock(), igate_enabled=False).start()
    await rig.alerts.set("OH2NET", Alert(on_air=True))
    rig.hear("OH2NET", path=("TCPIP*", "qAC", "T2FINLAND"), via="is")
    assert rig.fired == []
    rig.config = replace(rig.config, igate_enabled=True)
    rig.alerts.settings_changed(rig.config)
    rig.hear("OH2NET", path=("TCPIP*", "qAC", "T2FINLAND"), via="is", after_sec=QUIET_SEC)
    assert rig.kinds() == [("OH2NET", "on_air")]


async def test_an_alert_is_kept_and_read_back_by_the_next_start(rig: Rig, log: MessageLog) -> None:
    await rig.alerts.set("OH2XYZ", Alert(on_air=True, within_km=5, direct=True))
    assert await log.prefs() == {"OH2XYZ": (None, False, Alert(on_air=True, within_km=5, direct=True))}
    again = await Rig(log, FixedClock()).start()
    assert again.alerts.alerts() == {"OH2XYZ": Alert(on_air=True, within_km=5, direct=True)}
    again.hear()
    assert again.kinds() == [("OH2XYZ", "on_air")]


def test_the_margin_beyond_the_distance_is_a_tenth_and_at_least_half_a_kilometre() -> None:
    check: Callable[[int], float] = outside_km
    assert (check(1), check(5), check(10), check(100)) == (1.5, 5.5, 11.0, 110.0)


async def test_the_daemon_tells_every_page_and_runs_the_alert_command_and_the_alert_outlives_a_restart(tmp_path: Path) -> None:
    out = tmp_path / "alert.txt"
    e = Env(tmp_path, web=True, settings={"messages/alert_command": writing_titled(out)})
    await e.start()
    await e.until_usable()
    page, other = await e.ws(), await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    await page.send({"cmd": "set_station_alert", "call": "oh2xyz", "on_air": True, "within_km": 10, "direct": False})
    wanted = {"path": None, "rf_only": False, "alert": {"on_air": True, "within_km": 10, "direct": False}}
    await other.until(lambda: other.topics["station_prefs"].get("OH2XYZ") == wanted)
    await page.send({"cmd": "set_station_alert", "call": "OH2GBA", "on_air": True, "within_km": None, "direct": False})
    assert (await page.expect("error"))["text"] == "set_station_alert: OH2GBA is our own: an alert is for another station"
    e.feed(on_air("OH2XYZ", b">on the air"))
    told = {"type": "station_alert", "call": "OH2XYZ", "kind": "on_air", "text": "OH2XYZ is on the air", "at": "2026-10-21T12:00:00Z", "km": None}
    assert await page.expect("station_alert") == told and await other.expect("station_alert") == told
    await until(out.is_file)
    assert out.read_text(encoding="utf-8").splitlines() == ["station", "APRS alert: OH2XYZ", "OH2XYZ", "OH2XYZ is on the air", "2026-10-21T12:00:00Z", "", "end"]
    await e.stop()
    second = Env(tmp_path, web=True)
    await second.start()
    again = await second.ws()
    await again.until(lambda: len(again.of("state")) == len(TOPIC_NAMES))
    assert again.topics["station_prefs"] == {"OH2XYZ": wanted} and second.ctl.stationalerts.alerts() == {"OH2XYZ": Alert(on_air=True, within_km=10)}
