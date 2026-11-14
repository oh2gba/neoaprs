"""The messages in the database: every message we sent and every one that was sent to us.

Like the packet log (packetlog.py) this runs on the database thread (db.py) and says no instead of raising when the database is not open (dblog.py). `insert` is awaited (the message has its id, and is on the
disk, when it returns); `update_state` is an append that nobody waits for, in order with everything else the thread was asked. The statements are messagesql.py's, and stationsql.py's for the paths of
the stations by radio. The parts marked "before 33" are those of a database of version 30, in force until migrations 32 and 33 are listed (packetcodec.BY_RADIO)."""
import logging
from dataclasses import replace
from datetime import datetime

from . import packetcodec, stationsql
from .chain import Attempt, HopSeen
from .clock import Clock, utcnow
from .db import Db
from .dberror import Row
from .dblog import DbLog
from .message import FAILURES, SEALS, MessageRecord
from .messagesql import (all_attempts, all_hops, all_keys, all_prefs, clear_chain, delete_conversation, delete_key, delete_message, delete_overheard, delete_pref, held_messages, insert_attempt, insert_hop, insert_message, recent_messages, save_key, save_pref,
                         sending_messages, update_message)
from .packetcodec import parse_stamp, stamp, stored_radio_word
from .pref import Alert
from .radiotype import FM_ID, RadioId

log = logging.getLogger("neoaprs.messagelog")


def _alert(on_air: bool, within_km: int | None, direct: bool) -> Alert | None:
    """The alert of a row, None when it watches nothing."""
    alert = Alert(on_air, within_km, direct)
    return alert if alert.any else None


def message_row(record: MessageRecord) -> Row:
    """The columns of the message table without the id, in the order of the INSERT."""
    return (stamp(record.at), record.direction, record.from_call, record.to_call, record.text, record.msg_id, record.state, record.attempts,
            None if record.last_attempt_at is None else stamp(record.last_attempt_at), None if record.acked_at is None else stamp(record.acked_at), record.attempts_max, record.route, record.seal, record.wire,
            record.radio_id if packetcodec.BY_RADIO else record.radio, record.failure, record.snr, record.rssi)        # (before 33 the row holds the word)


def message_of(row: Row) -> MessageRecord:
    """The message from its row. Raises ValueError (or TypeError) for a row this program did not write."""
    (number, at, direction, from_call, to_call, text, msg_id, state, attempts, last_attempt_at, acked_at, attempts_max, route, seal, wire, radio, failure, snr, rssi) = row
    if seal not in SEALS:
        raise ValueError(f"seal {seal!r}")
    if failure is not None and failure not in FAILURES:
        raise ValueError(f"failure {failure!r}")
    return MessageRecord(int(number), parse_stamp(str(at)), direction, str(from_call), str(to_call), str(text), None if msg_id is None else str(msg_id), state, int(attempts),
                         None if last_attempt_at is None else parse_stamp(str(last_attempt_at)), None if acked_at is None else parse_stamp(str(acked_at)), int(attempts_max), str(route), seal, wire=None if wire is None else str(wire), radio=stored_radio_word(radio), failure=failure,
                         snr=None if snr is None else float(snr), rssi=None if rssi is None else float(rssi))


def attempt_of(row: Row) -> tuple[int, Attempt]:
    """(the id of the message, the attempt without the hops heard) from a row of `message_attempt`. Raises ValueError (or TypeError) for a row this program did not write."""
    number, attempt, sent_at, path, radio = row
    return int(number), Attempt(int(attempt), parse_stamp(str(sent_at)), tuple(p for p in str(path).split(",") if p), radio=stored_radio_word(radio))


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
        """Keeps the state, the attempts, the times, the failure and the reading of the answer of a message as they are now; False when it could not be queued."""
        last = None if record.last_attempt_at is None else stamp(record.last_attempt_at)
        acked = None if record.acked_at is None else stamp(record.acked_at)
        return self._append(lambda conn: update_message(conn, record.id, record.state, record.attempts, last, acked, record.failure, (record.snr, record.rssi)))

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
        radio = attempt.radio_id if packetcodec.BY_RADIO else attempt.radio             # (before 33 the row holds the word)
        return self._append(lambda conn: insert_attempt(conn, number, attempt.number, stamp(attempt.sent_at), ",".join(attempt.path), radio))

    def add_hop(self, number: int, attempt: int, seen: HopSeen) -> bool:
        """Keeps a hop that was heard back (the first time it was heard stays); False when it could not be queued."""
        return self._append(lambda conn: insert_hop(conn, number, attempt, seen.position, seen.call, stamp(seen.heard_at), seen.via_internet))

    def clear_chain(self, number: int) -> bool:
        """Forgets the attempts and hops of a message (it is sent again from the first attempt)."""
        return self._append(lambda conn: clear_chain(conn, number))

    async def chains(self) -> dict[int, list[Attempt]]:
        """The attempts of every message, with the hops heard, by message id; an attempt whose row is not ours is left out and told."""
        attempts: list[Row] = await self._read(all_attempts, [])
        hops: list[Row] = await self._read(all_hops, [])
        found: dict[int, list[Attempt]] = {}
        for number, attempt in self._decoded(attempts, attempt_of, "message_attempt"):
            found.setdefault(number, []).append(attempt)
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

    # ---- the public keys the stations announced (the table station_key; services/keyring.py)
    async def keys(self) -> dict[str, tuple[str, datetime]]:
        """Every station whose key is kept: call to (the key, 43 characters of base64, and when it was heard)."""
        rows: list[Row] = await self._read(all_keys, [])
        return {str(call): (str(pubkey), parse_stamp(str(heard_at))) for call, pubkey, heard_at in rows}

    async def save_key(self, call: str, pubkey: str, heard_at: datetime) -> bool:
        """Keeps the key a station announced, replacing the one it had; False when the database would not take it."""
        stamped = stamp(heard_at)
        return await self._done(lambda conn: save_key(conn, call, pubkey, stamped), "a station's key could not be kept")

    async def forget_key(self, call: str) -> bool:
        """Removes the key of a station; False when the database would not take it."""
        return await self._done(lambda conn: delete_key(conn, call), "a station's key could not be removed")

    # ---- what the operator said about each station (the tables station_pref, by station, and station_path, by station and radio)
    async def prefs(self, *, radio: RadioId = FM_ID) -> dict[str, tuple[str | None, bool, Alert | None]]:
        """Every station that has a preference: call to (path, rf_only, alert). The path is the station's on `radio` (the FM radio of today when not given), digipeater calls separated by commas (empty is
        direct), None when none is set there; the alert is None when it watches nothing."""
        rows: list[Row] = await self._read(lambda conn: all_prefs(conn, radio_id=radio), [])
        return {str(call): (None if path is None else str(path), bool(rf_only), _alert(bool(on_air), None if within is None else int(within), bool(direct)))
                for call, path, rf_only, on_air, within, direct in rows}

    async def save_pref(self, call: str, path: str | None, rf_only: bool = False, alert: Alert | None = None, *, radio: RadioId = FM_ID) -> bool:
        """Keeps what is said of a station (replacing what was kept): RF only and the alert, and its path on `radio` (the FM radio of today when not given; None takes the path away there, its paths on
        other radios stay); False when the database would not take it."""
        stamped = stamp(self.clock())
        parts = (False, None, False) if alert is None else (alert.on_air, alert.within_km, alert.direct)
        return await self._done(lambda conn: save_pref(conn, call, path, rf_only, parts, stamped, radio_id=radio), "a station preference could not be kept")

    async def forget_pref(self, call: str) -> bool:
        """Removes what is said of a station as `save_pref` keeps it without a radio named (RF only, the alert, its path on the FM radio of today), so that it has the defaults again; its paths on other
        radios stay (`forget_path`). False when the database would not take it."""
        return await self._done(lambda conn: delete_pref(conn, call), "a station preference could not be removed")

    # ---- the paths of the stations, by radio (the table station_path; there is none before migration 33)
    async def paths(self) -> dict[str, dict[RadioId, str]]:
        """Every path the operator gave a station on a radio: call to (radio to the path, digipeater calls separated by commas, empty for direct)."""
        rows: list[Row] = await self._read(stationsql.station_paths, [])
        found: dict[str, dict[RadioId, str]] = {}
        for call, radio, path in rows:
            found.setdefault(str(call), {})[int(radio)] = str(path)
        return found

    async def save_path(self, call: str, radio: RadioId, path: str) -> bool:
        """Keeps the path of a station on a radio, replacing the one it had there; False when the database would not take it."""
        stamped = stamp(self.clock())
        return await self._done(lambda conn: stationsql.put_station_path(conn, call, radio, path, stamped), "a station's path could not be kept")

    async def forget_path(self, call: str, radio: RadioId) -> bool:
        """Removes the path of a station on a radio; False when the database would not take it."""
        return await self._done(lambda conn: stationsql.clear_station_path(conn, call, radio), "a station's path could not be removed")
