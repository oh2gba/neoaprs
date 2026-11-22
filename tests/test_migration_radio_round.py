"""Migrations 31, 32 and 33 together as the runner runs them, and the stores on the result: a
version 30 database with packets, messages, attempts, stations, paths and objects on both radios
reads back by radio id.
"""
import json
import sqlite3
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from neoaprs import ax25
from neoaprs.chain import Attempt
from neoaprs.message import MessageRecord
from neoaprs.messagelog import MessageLog
from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.ownlog import OwnLog
from neoaprs.ownobject import OwnObject
from neoaprs.packet import Packet, Status
from neoaprs.packetcodec import parse_stamp
from neoaprs.packetlog import PacketLog
from neoaprs.radiospec import RadioHeard
from neoaprs.station import Station
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, step_back
from tests.support.migrated32 import connect, old_database, tables
from tests.support.storedb import sql, store_at
from tests.test_migration_32 import PACKETS, messages, packets
from tests.test_migration_33 import HEARD, LATEST, STAMP, STATION, objects, prefs, stations

SETTINGS = {"station/call": "OH2GBA", "tnc/profile": "kenwood-d710", "fm/enabled": "true", "hf/enabled": "true", "hf/profile": "mercury", "serial/port": "/dev/ttyUSB0", "beacon/path": "WIDE1-1,WIDE2-1",
            "mercury/sound_card": "plughw:1,0", "beacon/last_sent_at": STAMP, "hf/beacon_last_sent_at": LATEST, "messages/radio_by_station": json.dumps({"OH2RDG": "fm", "Q3TKU": "hf"}, sort_keys=True)}
# A packet of the air with no word is radio 1's after 32 and comes back as `fm`: left out where the
# way back is compared
ON_AIR = [row for row in PACKETS if row[3] or row[2] == "is"]


def version_30(path: Path, settings: dict[str, str], *fill: Any) -> None:
    """A database file of version 30 with these settings rows (each at revision 1, the choices at 3)
    and the rows the functions of `fill` insert."""
    db = old_database(path, FixedClock())
    for key, value in settings.items():
        db.execute("INSERT INTO settings (key, value, rev) VALUES (?, ?, ?)", (key, value, 3 if key == "messages/radio_by_station" else 1))
    for rows in fill:
        rows(db)
    db.close()


def everything(path: Path) -> dict[str, list[tuple[Any, ...]]]:
    """Every row of every table but the history of the steps, each table's rows sorted."""
    db = connect(path)
    try:
        return {table: sorted((tuple(row) for row in db.execute(f"SELECT * FROM {table}")), key=repr) for table in sorted(tables(db) - {"schema_history"})}
    finally:
        db.close()


def run_the_runner(path: Path) -> None:
    found = opened(path, FixedClock())
    assert found.version() == SCHEMA_VERSION == 35 and [(n, name) for n, name, *_ in found.history()][-5:] == [(31, "_v31"), (32, "_v32"), (33, "_v33"), (34, "_v34"), (35, "_v35")]
    found.close()


def air(source: str, at: object, radio: int) -> Packet:
    frame = ax25.Frame(ax25.Address("APRS"), ax25.Address.parse(source), (), info=b">on radio 3")
    return Packet(at, "in", ax25.encode(frame), source, "APRS", (), b">on radio 3", Status("on radio 3"), radio_id=radio)   # type: ignore[arg-type]


async def test_the_runner_takes_a_database_of_version_30_to_33_and_the_stores_read_every_value_with_its_radio_and_take_a_third(tmp_path: Path) -> None:
    path = tmp_path / DB_NAME
    version_30(path, SETTINGS, lambda db: packets(db, ON_AIR), messages, stations, prefs, objects)
    run_the_runner(path)
    clock = FixedClock()
    store = await store_at(path, clock)
    assert store.db is not None
    assert await sql(store, "SELECT id, kind, type, enabled FROM radio ORDER BY id") == [(1, "fm", "kenwood-d710", 1), (2, "hf", "mercury", 1)]
    assert await sql(store, "PRAGMA foreign_key_check") == [], "every row names a radio the table has"
    packetlog, messagelog, ownlog = PacketLog(store.db, clock), MessageLog(store.db, clock), OwnLog(store.db, clock)
    assert sorted((p.source, p.direction, p.radio_id or 0) for p in await packetlog.recent()) == sorted((row[1], row[0], {"fm": 1, "hf": 2}.get(row[3], 0)) for row in ON_AIR), "(0 for none)"
    assert [(m.from_call, m.radio_id) for m in reversed(await messagelog.held(10))] == [("OH2GBA", None), ("OH2RDG", 1), ("Q3TKU", 2), ("OH2AAA", 1), ("OH2NET", None), ("OH2GBA", None)]
    assert [(a.number, a.radio_id) for a in (await messagelog.chains())[1]] == [(1, 1), (2, 2), (3, None)]
    found = {s.call: s for s in await packetlog.stations()}
    assert {call: {radio: (heard.count, None if heard.last_at is None else heard.last_at, ",".join(heard.last_path)) for radio, heard in s.heard_by.items()} for call, s in found.items() if s.heard_by} == \
        {call: {radio: (count, None if at is None else parse_stamp(at), last) for radio, (count, at, last) in heard.items()} for call, heard in HEARD.items()}
    assert await messagelog.paths() == {"OH2ALL": {1: "WIDE2-1"}, "OH2BOTH": {1: "OH2RCH-2"}, "OH2DIRECT": {1: ""}, "OH2PATH": {1: "WIDE1-1,WIDE2-1"}}
    assert sorted((o.name, o.radios) for o in await ownlog.objects()) == [("ONBOTH", (1, 2)), ("ONFM", (1,)), ("ONHF", (2,))]

    third = await store.add_radio("fm", "kiss", "", True, 3)
    assert third == 3, "the next radio takes an id no radio had"
    at = parse_stamp(LATEST) + timedelta(hours=1)                  # (the newest of every table)
    assert packetlog.append(air("OH2THR", at, third))
    came = await messagelog.insert(MessageRecord(0, at, "in", "OH2THR", "OH2GBA", "on three", "5", "received", radio_id=third))
    assert came is not None and messagelog.add_attempt(1, Attempt(4, at, ("WIDE1-1",), radio_id=third))
    assert packetlog.save_station(Station("OH2THR", first_heard=at, last_heard=at, packets=1, heard_rf=1, last_rf_at=at, heard_by={third: RadioHeard(1, at, ("WIDE1-1*",))}))
    assert await messagelog.save_path("OH2PATH", third, "OH2RCH-2") and ownlog.save_object(OwnObject("ONTHREE", "object", 60.2, 25.0, "/", "-", at, at, radios=(1, third)))
    assert (await packetlog.recent(1))[0].radio_id == 3 and [m.radio_id for m in await messagelog.recent(1)] == [3] and (await messagelog.chains())[1][-1].radio_id == 3
    assert {s.call: s for s in await packetlog.stations()}["OH2THR"].heard_by == {3: RadioHeard(1, at, ("WIDE1-1*",))}
    assert (await messagelog.paths())["OH2PATH"] == {1: "WIDE1-1,WIDE2-1", 3: "OH2RCH-2"} and {o.name: o.radios for o in await ownlog.objects()}["ONTHREE"] == (1, 3)
    assert await sql(store, "SELECT (SELECT radio FROM packet WHERE source = 'OH2THR'), (SELECT radio FROM message WHERE from_call = 'OH2THR'), (SELECT radio FROM message_attempt WHERE attempt = 4), "
                            "(SELECT radio_id FROM station_radio WHERE call = 'OH2THR'), (SELECT radios FROM own_object WHERE name = 'ONTHREE')") == [(3, 3, 3, 3, "1,3")], "each as the id"
    assert await sql(store, "PRAGMA foreign_key_check") == []


@pytest.mark.parametrize("settings", [{}, {"station/call": "OH2GBA"}], ids=["no settings row", "settings"])
async def test_a_database_whose_only_trace_of_hf_is_a_station_heard_on_it_comes_through_with_radio_two(tmp_path: Path, settings: dict[str, str]) -> None:
    """The packets that counted it were pruned long ago; the station cache keeps the count, and that
    is enough for migration 31 to make radio 2 (off) and for 33 to give the count to it."""
    path = tmp_path / DB_NAME
    version_30(path, settings, lambda db: db.execute(STATION, ("OH2HF", STAMP, LATEST, STAMP, 5, "", 5, 0, LATEST, None, 0, 5, None, LATEST, LATEST)))
    run_the_runner(path)
    clock = FixedClock()
    store = await store_at(path, clock)
    assert store.db is not None
    assert await sql(store, "SELECT id, kind, enabled FROM radio ORDER BY id") == [(1, "fm", 1), (2, "hf", 0)] and await sql(store, "PRAGMA foreign_key_check") == []
    assert [(s.call, s.heard_by) for s in await PacketLog(store.db, clock).stations()] == [("OH2HF", {2: RadioHeard(5, parse_stamp(LATEST), ())})]


def test_the_way_back_to_30_gives_the_rows_of_30_and_the_runner_then_gives_the_same_rows_again(tmp_path: Path) -> None:
    path = tmp_path / DB_NAME
    version_30(path, SETTINGS, lambda db: packets(db, ON_AIR), messages, stations, prefs, objects)
    before = everything(path)
    run_the_runner(path)
    first = everything(path)
    assert {"radio", "radio_setting", "station_radio", "station_path"} <= set(first) and first["radio_setting"] and first["station_radio"]
    db = sqlite3.connect(path, isolation_level=None)
    db.execute("DELETE FROM schema_history WHERE version > 30")
    step_back(db, 30)
    db.execute("PRAGMA user_version = 30")
    db.close()
    assert everything(path) == before, "the way back gives every row of version 30, the settings of the radios with their revisions among them"
    run_the_runner(path)
    assert everything(path) == first, "and the runner run again gives the same rows"
