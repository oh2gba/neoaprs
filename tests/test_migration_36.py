"""Migration 36 (neoaprs/migrationsteps36.py): a bulletin of ours keeps how long it is sent. A file of
version 35 with posts in it gives each bulletin and group bulletin 4 hours and each announcement 72,
and comes out as a fresh file is; the schedules go on by them.
"""

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.migrationsteps36 import _v36
from neoaprs.ownlog import OwnLog
from neoaprs.packetcodec import stamp
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, step_back
from tests.support.storedb import store_at
from tests.test_migrations import GOLDEN, raw, shape
from tests.test_ownbulletins import Rig

T0 = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
COLUMNS35 = "slot, group_name, text, created_at, sent, first_sent_at, last_sent_at, radios"


def at(seconds: float) -> str:
    return stamp(T0 + timedelta(seconds=seconds))


# slot, group, sent, first, last: as version 35 kept them
POSTS = [
    ("BLN1", "", 4, at(0), at(1560)),  # a bulletin in the middle of its schedule
    ("BLN0A", "A", 0, None, None),  # a group bulletin whose group starts with a letter
    ("BLN3HAMS", "HAMS", 2, at(0), at(120)),
    ("BLNQ", "", 74, at(-4 * 86400), at(-4 * 86400 + 360 + 71 * 3600)),  # an announcement that has ended
    ("BLNB", "", 0, None, None),
]


def version_35(path: Path, posts: list[tuple[str, str, int, str | None, str | None]]) -> None:
    """A database at version 35 with these posts of ours."""
    opened(path, FixedClock(T0)).close()
    db = raw(path)
    db.execute("DELETE FROM schema_history WHERE version >= 36")
    step_back(db, 35)
    db.execute("PRAGMA user_version = 35")
    db.executemany(
        f"INSERT INTO own_bulletin ({COLUMNS35}) VALUES (?, ?, 'text', ?, ?, ?, ?, '1')",
        [(slot, group, at(-60), sent, first, last) for slot, group, sent, first, last in posts],
    )
    db.close()


def lasts(path: Path) -> dict[str, int]:
    db = sqlite3.connect(path)
    try:
        return {str(slot): int(h) for slot, h in db.execute("SELECT slot, lasts_h FROM own_bulletin")}
    finally:
        db.close()


def test_bulletins_and_group_bulletins_get_4_hours_and_announcements_72_and_the_file_is_as_a_fresh_one(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / DB_NAME
    version_35(path, POSTS)
    with caplog.at_level("INFO"):
        migrated = opened(path, FixedClock(T0))
    fresh = opened(tmp_path / "fresh.sqlite", FixedClock(T0))
    assert migrated.version() == SCHEMA_VERSION and [(r[0], r[1], r[2]) for r in migrated.history()][-1] == (
        36,
        "_v36",
        GOLDEN[36],
    )
    assert shape(migrated.db) == shape(fresh.db)
    assert migrated.db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    migrated.close()
    fresh.close()
    assert lasts(path) == {"BLN1": 4, "BLN0A": 4, "BLN3HAMS": 4, "BLNQ": 72, "BLNB": 72}
    assert "3 bulletins of ours are sent for 4 hours and 2 announcements for 72 hours" in caplog.text


def test_an_empty_table_migrates_and_the_column_takes_1_to_168_hours_only(tmp_path: Path) -> None:
    path = tmp_path / DB_NAME
    version_35(path, [])
    opened(path, FixedClock(T0)).close()
    assert lasts(path) == {}
    db = raw(path)
    insert = f"INSERT INTO own_bulletin ({COLUMNS35}, lasts_h) VALUES (?, '', 'x', ?, 0, NULL, NULL, '1', ?)"
    for hours in (0, 169, -1):
        with pytest.raises(sqlite3.IntegrityError, match="own_bulletin_lasts"):
            db.execute(insert, ("BLN5", at(0), hours))
    db.execute(insert, ("BLN5", at(0), 168))
    db.close()


async def test_a_post_in_the_middle_of_its_schedule_goes_on_to_4_hours_after_its_first_packet(tmp_path: Path) -> None:
    path = tmp_path / DB_NAME
    version_35(path, POSTS[:1] + POSTS[3:4])
    clock = FixedClock(T0 + timedelta(seconds=1600))
    store = await store_at(path, clock)
    assert store.db is not None
    rig = await Rig(OwnLog(store.db, clock), clock, store).start()
    assert [(b.slot, b.hours, b.sent) for b in rig.posts.records()] == [("BLN1", 4, 4), ("BLNQ", 72, 74)]
    rig.run(5 * 3600, step=60)
    sent = [rig.begin + timedelta(seconds=t) for t, _ in rig.sent]
    assert len(sent) == 10 and sent[0] >= T0 + timedelta(seconds=2760) and sent[-1] <= T0 + timedelta(hours=4)
    assert all(info.startswith(b":BLN1") for _, info in rig.sent), "the announcement stays ended"


def test_the_step_says_nothing_in_the_log_for_no_posts(caplog: pytest.LogCaptureFixture) -> None:
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE own_bulletin (slot TEXT PRIMARY KEY)")
    with caplog.at_level("INFO"):
        _v36(db)
    assert caplog.text == "" and db.execute("SELECT lasts_h FROM own_bulletin").fetchall() == []
