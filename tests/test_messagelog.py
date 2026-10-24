"""The message log (neoaprs/messagelog.py, messagesql.py) on a real database thread: what goes in comes out equal, the order, the updates, the highest message id, the care, and the rows the table refuses."""
import sqlite3
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs.clock import utc
from neoaprs.message import MessageRecord
from neoaprs.messagelog import MessageLog, message_of, message_row
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.storedb import log_at, sql, store_at

T0 = utc(2026, 10, 21, 12, 0, 0)


def out(text: str = "hello", msg_id: str | None = "1", to: str = "OH2RDG", at: object = T0, **more: object) -> MessageRecord:
    return MessageRecord(0, at, "out", "OH2GBA", to, text, msg_id, "sending", **more)  # type: ignore[arg-type]


def came(text: str = "hi", frm: str = "OH2RDG", msg_id: str | None = "5", at: object = T0) -> MessageRecord:
    return MessageRecord(0, at, "in", frm, "OH2GBA", text, msg_id, "received")  # type: ignore[arg-type]


async def opened(tmp_path: Path, clock: FixedClock | None = None) -> tuple[MessageLog, FixedClock]:
    log, _, clock = await log_at(tmp_path, MessageLog, clock)
    return log, clock


async def settled(log: MessageLog) -> None:
    assert log.db is not None
    await log.db.barrier()


def test_a_record_gives_its_row_and_the_row_gives_the_record_back() -> None:
    full = out("åäö hello", "00042", attempts=3, last_attempt_at=T0 + timedelta(seconds=90), acked_at=T0 + timedelta(seconds=100))
    row = (7, *message_row(full))
    assert message_of(row) == replace(full, id=7)
    assert message_row(full)[0] == "2026-10-21T12:00:00.000000Z"
    assert message_of((8, *message_row(came(msg_id=None)))) == replace(came(msg_id=None), id=8)


async def test_a_message_that_is_kept_has_the_id_the_database_gave_it_and_comes_back_equal(tmp_path: Path) -> None:
    log, _ = await opened(tmp_path)
    first, second = await log.insert(out("one")), await log.insert(came("two"))
    assert first is not None and second is not None and (first.id, second.id) == (1, 2)
    assert await log.recent() == [second, first], "the newest first"
    assert first == replace(out("one"), id=1)


async def test_the_state_the_attempts_and_the_times_are_updated(tmp_path: Path) -> None:
    log, _ = await opened(tmp_path)
    kept = await log.insert(out())
    assert kept is not None
    changed = replace(kept, state="acked", attempts=2, last_attempt_at=T0 + timedelta(seconds=30), acked_at=T0 + timedelta(seconds=40))
    assert log.update_state(changed)
    await settled(log)
    assert await log.recent() == [changed]
    log.update_state(replace(changed, id=99))                                           # (a message that is not there: the update finds no row, and nothing is raised)
    await settled(log)
    assert await log.recent() == [changed]


async def test_recent_is_limited_and_the_newest_first(tmp_path: Path) -> None:
    log, _ = await opened(tmp_path)
    for n in range(5):
        await log.insert(out(f"to rdg {n}", str(n + 1), "OH2RDG", T0 + timedelta(minutes=n)))
    await log.insert(came("from rdg", "OH2RDG", "9", T0 + timedelta(minutes=6)))
    await log.insert(out("to other", "6", "OH2XYZ", T0 + timedelta(minutes=7)))
    await log.insert(came("from other", "OH2XYZ", None, T0 + timedelta(minutes=8)))
    assert [m.text for m in await log.recent(3)] == ["from other", "to other", "from rdg"]
    assert len(await log.recent()) == 8 and await log.recent(0) == []


async def test_only_the_messages_being_sent_are_listed_as_sending_oldest_first(tmp_path: Path) -> None:
    log, _ = await opened(tmp_path)
    a, b, c = await log.insert(out("a", "1")), await log.insert(out("b", "2")), await log.insert(came("c"))
    assert a is not None and b is not None and c is not None
    log.update_state(replace(a, state="failed", attempts=6))
    await settled(log)
    assert [m.text for m in await log.sending()] == ["b"]


async def test_a_log_without_a_database_says_no_instead_of_raising() -> None:
    log = MessageLog()
    assert not log.is_open() and await log.insert(out()) is None and not log.update_state(replace(out(), id=1)) and log.dropped == 1
    assert await log.recent() == [] and await log.sending() == [] and await log.held(10) == []


async def test_a_row_this_program_did_not_write_is_left_out_of_a_read(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    store = await store_at(tmp_path / DB_NAME)
    assert store.db is not None
    log = MessageLog(store.db)
    await log.insert(out("good"))
    await store.db.write(lambda conn: conn.execute("PRAGMA ignore_check_constraints = ON"))
    await store.db.write(lambda conn: conn.execute("INSERT INTO message (at, direction, from_call, to_call, text, state, attempts) VALUES ('soon', 'out', 'A', 'B', 'bad', 'sending', 0)"))
    assert [m.text for m in await log.recent()] == ["good"]
    assert any("could not be read" in r.getMessage() for r in caplog.records)


@pytest.mark.expects_errors
async def test_the_table_refuses_a_message_that_reads_as_both_in_and_sent(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    assert store.db is not None
    log = MessageLog(store.db)
    assert await log.insert(replace(came(), state="sending")) is None, "an insert the table refuses is not kept, and the caller is told (None)"
    assert await sql(store, "SELECT COUNT(*) FROM message") == [(0,)]
    with pytest.raises(sqlite3.IntegrityError):
        await store.db.write(lambda conn: conn.execute("INSERT INTO message (at, direction, from_call, to_call, text, state) VALUES ('x', 'in', 'A', 'B', 't', 'received')"))


def overheard(text: str = "to others", frm: str = "OH2AAA", to: str = "OH2BBB", msg_id: str | None = "7", at: object = T0) -> MessageRecord:
    return MessageRecord(0, at, "in", frm, to, text, msg_id, "overheard")  # type: ignore[arg-type]


async def test_overheard_messages_are_kept_apart_from_the_conversations(tmp_path: Path) -> None:
    log, _ = await opened(tmp_path)
    await log.insert(out("ours"))
    await log.insert(overheard("not ours", "OH2RDG", "OH2XYZ"))
    await log.insert(came("to us", "OH2RDG"))
    assert [m.text for m in await log.recent()] == ["to us", "ours"]
    assert [m.text for m in await log.recent(overheard=True)] == ["not ours"]
    assert await log.sending() != []


async def test_a_conversation_is_removed_in_one_write_with_the_overheard_messages_and_the_other_stations_left(tmp_path: Path) -> None:
    log, _ = await opened(tmp_path)
    await log.insert(out("to him"))
    await log.insert(came("from him"))
    await log.insert(out("to another", to="OH2XYZ"))
    await log.insert(came("from another", "OH2XYZ"))
    await log.insert(came("from his ssid", "OH2RDG-7"))
    await log.insert(overheard("he sent it to others", "OH2RDG", "OH2XYZ"))
    await log.insert(overheard("sent to him by others", "OH2XYZ", "OH2RDG"))
    assert await log.delete_conversation("OH2RDG") == 2
    assert sorted(m.text for m in await log.recent()) == ["from another", "from his ssid", "to another"]
    assert sorted(m.text for m in await log.recent(overheard=True)) == ["he sent it to others", "sent to him by others"]
    assert await log.delete_conversation("OH2RDG") == 0
    log.db = None
    assert await log.delete_conversation("OH2XYZ") is None


async def test_held_gives_the_latest_of_any_kind_newest_first_and_nothing_is_pruned_by_age(tmp_path: Path) -> None:
    log, clock = await opened(tmp_path)
    await log.insert(out("ancient", "1", at=T0 - timedelta(days=400)))
    await log.insert(overheard("old chatter", at=T0 - timedelta(days=300)))
    await log.insert(came("fresh", at=T0 - timedelta(days=1)))
    clock.advance(86400 * 400)
    assert [m.text for m in await log.held(10)] == ["fresh", "old chatter", "ancient"]
    assert [m.text for m in await log.held(2)] == ["fresh", "old chatter"] and await log.held(0) == []
    assert not hasattr(log, "prune"), "the log has no way to remove a message by age"


async def test_what_is_said_of_a_station_is_kept_replaced_and_forgotten_and_an_empty_path_is_not_none(tmp_path: Path) -> None:
    log, clock = await opened(tmp_path)
    assert await log.prefs() == {}
    assert await log.save_pref("OH2RDG", "WIDE1-1,WIDE2-1") and await log.save_pref("OH2XYZ", "") and await log.save_pref("OH2ABC", "WIDE2-1", True)
    assert await log.save_pref("EMAIL-2", None, True)
    assert await log.prefs() == {"OH2RDG": ("WIDE1-1,WIDE2-1", False), "OH2XYZ": ("", False), "OH2ABC": ("WIDE2-1", True), "EMAIL-2": (None, True)}
    clock.advance(60)
    assert await log.save_pref("OH2RDG", "OH2RCH-2")
    assert (await log.prefs())["OH2RDG"] == ("OH2RCH-2", False)
    assert await log.forget_pref("OH2XYZ") and await log.forget_pref("NOBODY")
    assert set(await log.prefs()) == {"OH2RDG", "OH2ABC", "EMAIL-2"}
    assert log.db is not None
    assert await log.db.read(lambda conn: conn.execute("SELECT updated_at FROM station_pref WHERE call = 'OH2RDG'").fetchone()[0]) == "2026-10-21T12:01:00.000000Z"


@pytest.mark.expects_errors
async def test_a_preference_the_table_refuses_is_not_kept_and_the_caller_is_told(tmp_path: Path) -> None:
    log, _ = await opened(tmp_path)
    assert not await log.save_pref("OH2RDG", "wide1-1") and not await log.save_pref("OH2RDG", None)
    assert await log.prefs() == {}
    assert not await MessageLog().save_pref("OH2RDG", "") and not await MessageLog().forget_pref("OH2RDG") and await MessageLog().prefs() == {}
