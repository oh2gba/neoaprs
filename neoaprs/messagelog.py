"""The messages in the database: every message we sent and every one that was sent to us.

Like the packet log (packetlog.py) this runs on the database thread (db.py) and says no instead of raising when the database is not open (dblog.py). `insert` is awaited (the message has its id, and is on the
disk, when it returns); `update_state` is an append that nobody waits for, in order with everything else the thread was asked. The statements are messagesql.py's."""
import logging
from dataclasses import replace

from .chain import Attempt, HopSeen
from .clock import Clock, utcnow
from .db import Db
from .dblog import DbLog
from .message import MessageRecord
from .messagesql import (Row, all_attempts, all_hops, all_prefs, clear_chain, delete_conversation, delete_message, delete_overheard, delete_pref, held_messages, insert_attempt, insert_hop, insert_message, recent_messages, save_pref, sending_messages,
                         update_message)
from .packetcodec import parse_stamp, stamp

log = logging.getLogger("neoaprs.messagelog")


def message_row(record: MessageRecord) -> Row:
    """The columns of the message table without the id, in the order of the INSERT."""
    return (stamp(record.at), record.direction, record.from_call, record.to_call, record.text, record.msg_id, record.state, record.attempts,
            None if record.last_attempt_at is None else stamp(record.last_attempt_at), None if record.acked_at is None else stamp(record.acked_at), record.attempts_max, record.route)


def message_of(row: Row) -> MessageRecord:
    """The message from its row. Raises ValueError (or TypeError) for a row this program did not write."""
    (number, at, direction, from_call, to_call, text, msg_id, state, attempts, last_attempt_at, acked_at, attempts_max, route) = row
    return MessageRecord(int(number), parse_stamp(str(at)), direction, str(from_call), str(to_call), str(text), None if msg_id is None else str(msg_id), state, int(attempts),
                         None if last_attempt_at is None else parse_stamp(str(last_attempt_at)), None if acked_at is None else parse_stamp(str(acked_at)), int(attempts_max), str(route))


class MessageLog(DbLog):
    def __init__(self, db: Db | None = None, clock: Clock = utcnow) -> None:
        super().__init__(db, clock, log, "the messages could not be read")

    # ---- writes
    async def insert(self, record: MessageRecord) -> MessageRecord | None:
        """Keeps a message and gives it back with the id the database gave it (the `id` of the argument is not used); None when the database would not take it."""
        row = message_row(record)
        number = await self._write(lambda conn: insert_message(conn, row), None, "a message could not be kept")
        return None if number is None else replace(record, id=number)

    def update_state(self, record: MessageRecord) -> bool:
        """Keeps the state, the attempts and the times of a message as they are now; False when it could not be queued."""
        last = None if record.last_attempt_at is None else stamp(record.last_attempt_at)
        acked = None if record.acked_at is None else stamp(record.acked_at)
        return self._append(lambda conn: update_message(conn, record.id, record.state, record.attempts, last, acked))

    async def delete(self, number: int) -> bool:
        """Removes a message; False when the database would not take it (a message that is not there is removed already, so that is True)."""
        return await self._done(lambda conn: delete_message(conn, number), "a message could not be removed")

    async def delete_conversation(self, call: str) -> int | None:
        """Removes every message of the conversation with the call in one write; how many the database had, None when it would not take the removal."""
        return await self._write(lambda conn: delete_conversation(conn, call), None, "a conversation could not be removed")

    async def delete_overheard(self, from_call: str, to_call: str) -> int | None:
        """Removes every message we only overheard `from_call` sending to `to_call` in one write; how many the database had, None when it would not take the removal."""
        return await self._write(lambda conn: delete_overheard(conn, from_call, to_call), None, "overheard messages could not be removed")

    # ---- the delivery chain (neoaprs/chain.py): each attempt of a message and the hops heard back
    def add_attempt(self, number: int, attempt: Attempt) -> bool:
        """Keeps an attempt as it was sent; False when it could not be queued."""
        return self._append(lambda conn: insert_attempt(conn, number, attempt.number, stamp(attempt.sent_at), ",".join(attempt.path)))

    def add_hop(self, number: int, attempt: int, seen: HopSeen) -> bool:
        """Keeps a hop that was heard back (the first time it was heard stays); False when it could not be queued."""
        return self._append(lambda conn: insert_hop(conn, number, attempt, seen.position, seen.call, stamp(seen.heard_at), seen.via_internet))

    def clear_chain(self, number: int) -> bool:
        """Forgets the attempts and hops of a message (it is sent again from the first attempt)."""
        return self._append(lambda conn: clear_chain(conn, number))

    async def chains(self) -> dict[int, list[Attempt]]:
        """The attempts of every message, with the hops heard, by message id."""
        attempts: list[Row] = await self._read(all_attempts, [])
        hops: list[Row] = await self._read(all_hops, [])
        found: dict[int, list[Attempt]] = {}
        for number, attempt, sent_at, path in attempts:
            found.setdefault(int(number), []).append(Attempt(int(attempt), parse_stamp(str(sent_at)), tuple(p for p in str(path).split(",") if p)))
        for number, attempt, position, call, heard_at, via in hops:
            chain = found.get(int(number), [])
            for index, known in enumerate(chain):
                if known.number == int(attempt):
                    chain[index] = known.with_seen(HopSeen(int(position), str(call), parse_stamp(str(heard_at)), bool(via)))
        return found

    # ---- reads
    def _records(self, rows: list[Row]) -> list[MessageRecord]:
        return self._decoded(rows, message_of, "message")

    async def recent(self, count: int = 500, overheard: bool = False) -> list[MessageRecord]:
        """The latest `count` messages, the newest first: those we sent or were sent, or with `overheard` those we only heard sent to somebody else."""
        rows: list[Row] = await self._read(lambda conn: recent_messages(conn, count, overheard), [])
        return self._records(rows)

    async def held(self, count: int) -> list[MessageRecord]:
        """The latest `count` messages of any kind, overheard ones included, the newest first: what the daemon holds after a start."""
        rows: list[Row] = await self._read(lambda conn: held_messages(conn, count), [])
        return self._records(rows)

    async def sending(self) -> list[MessageRecord]:
        """The messages that are still being sent, the oldest first."""
        rows: list[Row] = await self._read(sending_messages, [])
        return self._records(rows)

    # ---- what the operator said about each station (the table station_pref)
    async def prefs(self) -> dict[str, tuple[str | None, int | None, bool]]:
        """Every station that has a preference: call to (path, hide_after_min, rf_only). The path is digipeater calls separated by commas (empty is direct), None when none is set; the timeout is None when none is set."""
        rows: list[Row] = await self._read(all_prefs, [])
        return {str(call): (None if path is None else str(path), None if hide is None else int(hide), bool(rf_only)) for call, path, hide, rf_only in rows}

    async def save_pref(self, call: str, path: str | None, hide_after_min: int | None, rf_only: bool = False) -> bool:
        """Keeps what is said of a station (replacing the row it had); False when the database would not take it."""
        stamped = stamp(self.clock())
        return await self._done(lambda conn: save_pref(conn, call, path, hide_after_min, rf_only, stamped), "a station preference could not be kept")

    async def forget_pref(self, call: str) -> bool:
        """Removes the row of a station, so that it has the defaults again; False when the database would not take it."""
        return await self._done(lambda conn: delete_pref(conn, call), "a station preference could not be removed")
