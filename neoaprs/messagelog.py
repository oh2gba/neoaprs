"""The messages table: every message sent and every message received.

Returns a failure value instead of raising when the database is not open."""

import logging
from dataclasses import replace
from datetime import datetime

from . import stationsql
from .chain import Attempt, HopSeen
from .clock import Clock, utcnow
from .db import Db
from .dberror import Row
from .dblog import DbLog
from .message import FAILURES, SEALS, MessageRecord
from .messagesql import (
    all_attempts,
    all_hops,
    all_keys,
    all_prefs,
    clear_chain,
    delete_conversation,
    delete_key,
    delete_message,
    delete_overheard,
    delete_pref,
    held_messages,
    insert_attempt,
    insert_hop,
    insert_message,
    recent_messages,
    save_key,
    save_pref,
    sending_messages,
    update_message,
)
from .packetcodec import parse_stamp, stamp
from .pref import Alert
from .radiotype import FM_ID, RadioId

log = logging.getLogger("neoaprs.messagelog")


def _alert(on_air: bool, within_km: int | None, direct: bool) -> Alert | None:
    alert = Alert(on_air, within_km, direct)
    return alert if alert.any else None


def message_row(record: MessageRecord) -> Row:
    return (
        stamp(record.at),
        record.direction,
        record.from_call,
        record.to_call,
        record.text,
        record.msg_id,
        record.state,
        record.attempts,
        None if record.last_attempt_at is None else stamp(record.last_attempt_at),
        None if record.acked_at is None else stamp(record.acked_at),
        record.attempts_max,
        record.route,
        record.seal,
        record.wire,
        record.radio_id,
        record.failure,
        record.snr,
        record.rssi,
    )


def message_of(row: Row) -> MessageRecord:
    """Return the message of a row. Raise ValueError or TypeError for an unknown shape."""
    (
        number,
        at,
        direction,
        from_call,
        to_call,
        text,
        msg_id,
        state,
        attempts,
        last_attempt_at,
        acked_at,
        attempts_max,
        route,
        seal,
        wire,
        radio,
        failure,
        snr,
        rssi,
    ) = row
    if seal not in SEALS:
        raise ValueError(f"seal {seal!r}")
    if failure is not None and failure not in FAILURES:
        raise ValueError(f"failure {failure!r}")
    return MessageRecord(
        int(number),
        parse_stamp(str(at)),
        direction,
        str(from_call),
        str(to_call),
        str(text),
        None if msg_id is None else str(msg_id),
        state,
        int(attempts),
        None if last_attempt_at is None else parse_stamp(str(last_attempt_at)),
        None if acked_at is None else parse_stamp(str(acked_at)),
        int(attempts_max),
        str(route),
        seal,
        wire=None if wire is None else str(wire),
        radio_id=None if radio is None else int(radio),
        failure=failure,
        snr=None if snr is None else float(snr),
        rssi=None if rssi is None else float(rssi),
    )


def attempt_of(row: Row) -> tuple[int, Attempt]:
    """Return (message id, attempt without hops) of a row. Raise ValueError or TypeError."""
    number, attempt, sent_at, path, radio = row
    return int(number), Attempt(
        int(attempt),
        parse_stamp(str(sent_at)),
        tuple(p for p in str(path).split(",") if p),
        radio_id=None if radio is None else int(radio),
    )


class MessageLog(DbLog):
    def __init__(self, db: Db | None = None, clock: Clock = utcnow) -> None:
        super().__init__(db, clock, log, "the messages could not be read")

    # ---- writes
    async def insert(self, record: MessageRecord) -> MessageRecord | None:
        """Store a message and return it with its new id; None if the database refuses."""
        row = message_row(record)
        number = await self._write(lambda conn: insert_message(conn, row), None, "a message could not be kept")
        return None if number is None else replace(record, id=number)

    def update_state(self, record: MessageRecord) -> bool:
        """Queue an update of the changing fields; False if not queued."""
        last = None if record.last_attempt_at is None else stamp(record.last_attempt_at)
        acked = None if record.acked_at is None else stamp(record.acked_at)
        return self._append(
            lambda conn: update_message(
                conn, record.id, record.state, record.attempts, last, acked, record.failure, (record.snr, record.rssi)
            )
        )

    async def delete(self, number: int) -> bool:
        """Remove a message; False if the database refuses."""
        return await self._done(lambda conn: delete_message(conn, number), "a message could not be removed")

    async def delete_conversation(self, call: str) -> int | None:
        """Remove the conversation with `call`; return the count, None on failure."""
        return await self._write(
            lambda conn: delete_conversation(conn, call), None, "a conversation could not be removed"
        )

    async def delete_overheard(self, from_call: str, to_call: str) -> int | None:
        """Remove overheard messages between the two; return the count or None."""
        return await self._write(
            lambda conn: delete_overheard(conn, from_call, to_call), None, "overheard messages could not be removed"
        )

    # ---- the delivery chain: each attempt of a message and the hops heard back
    def add_attempt(self, number: int, attempt: Attempt) -> bool:
        return self._append(
            lambda conn: insert_attempt(
                conn, number, attempt.number, stamp(attempt.sent_at), ",".join(attempt.path), attempt.radio_id
            )
        )

    def add_hop(self, number: int, attempt: int, seen: HopSeen) -> bool:
        """Queue a hop heard back (the first hearing is kept)."""
        return self._append(
            lambda conn: insert_hop(
                conn, number, attempt, seen.position, seen.call, stamp(seen.heard_at), seen.via_internet
            )
        )

    def clear_chain(self, number: int) -> bool:
        """Queue removal of a message's attempts and hops."""
        return self._append(lambda conn: clear_chain(conn, number))

    async def chains(self) -> dict[int, list[Attempt]]:
        """Return the attempts with their hops by message id."""
        attempts: list[Row] = await self._read(all_attempts, [])
        hops: list[Row] = await self._read(all_hops, [])
        found: dict[int, list[Attempt]] = {}
        for number, attempt in self._decoded(attempts, attempt_of, "message_attempt"):
            found.setdefault(number, []).append(attempt)
        for number, attempt, position, call, heard_at, via in hops:
            chain = found.get(int(number), [])
            for index, known in enumerate(chain):
                if known.number == int(attempt):
                    chain[index] = known.with_seen(
                        HopSeen(int(position), str(call), parse_stamp(str(heard_at)), bool(via))
                    )
        return found

    # ---- reads
    def _records(self, rows: list[Row]) -> list[MessageRecord]:
        return self._decoded(rows, message_of, "message")

    async def recent(self, count: int = 500, overheard: bool = False) -> list[MessageRecord]:
        """Return the latest `count` messages, newest first; with `overheard`, those of others."""
        rows: list[Row] = await self._read(lambda conn: recent_messages(conn, count, overheard), [])
        return self._records(rows)

    async def held(self, count: int) -> list[MessageRecord]:
        """Return the latest `count` messages of any kind, newest first."""
        rows: list[Row] = await self._read(lambda conn: held_messages(conn, count), [])
        return self._records(rows)

    async def sending(self) -> list[MessageRecord]:
        rows: list[Row] = await self._read(sending_messages, [])
        return self._records(rows)

    # ---- the public keys the stations announced (table station_key)
    async def keys(self) -> dict[str, tuple[str, datetime]]:
        """Return call to (key as 43 base64 characters, time heard)."""
        rows: list[Row] = await self._read(all_keys, [])
        return {str(call): (str(pubkey), parse_stamp(str(heard_at))) for call, pubkey, heard_at in rows}

    async def save_key(self, call: str, pubkey: str, heard_at: datetime) -> bool:
        """Store a station's key, replacing any earlier one."""
        stamped = stamp(heard_at)
        return await self._done(lambda conn: save_key(conn, call, pubkey, stamped), "a station's key could not be kept")

    async def forget_key(self, call: str) -> bool:
        return await self._done(lambda conn: delete_key(conn, call), "a station's key could not be removed")

    # ---- per-station settings (tables station_pref and station_path)
    async def prefs(self, *, radio: RadioId = FM_ID) -> dict[str, tuple[str | None, bool, Alert | None]]:
        """Return call to (path on `radio`, comma-joined or None, rf_only, alert)."""
        rows: list[Row] = await self._read(lambda conn: all_prefs(conn, radio_id=radio), [])
        return {
            str(call): (
                None if path is None else str(path),
                bool(rf_only),
                _alert(bool(on_air), None if within is None else int(within), bool(direct)),
            )
            for call, path, rf_only, on_air, within, direct in rows
        }

    async def save_pref(
        self, call: str, path: str | None, rf_only: bool = False, alert: Alert | None = None, *, radio: RadioId = FM_ID
    ) -> bool:
        """Store RF-only, the alert and the path on `radio`; a None path removes it there only."""
        stamped = stamp(self.clock())
        parts = (False, None, False) if alert is None else (alert.on_air, alert.within_km, alert.direct)
        return await self._done(
            lambda conn: save_pref(conn, call, path, rf_only, parts, stamped, radio_id=radio),
            "a station preference could not be kept",
        )

    async def forget_pref(self, call: str) -> bool:
        """Reset RF-only, the alert and the default radio's path; other radios' paths stay."""
        return await self._done(lambda conn: delete_pref(conn, call), "a station preference could not be removed")

    # ---- the paths of the stations, by radio (table station_path)
    async def paths(self) -> dict[str, dict[RadioId, str]]:
        """Return call to {radio: path}."""
        rows: list[Row] = await self._read(stationsql.station_paths, [])
        found: dict[str, dict[RadioId, str]] = {}
        for call, radio, path in rows:
            found.setdefault(str(call), {})[int(radio)] = str(path)
        return found

    async def save_path(self, call: str, radio: RadioId, path: str) -> bool:
        """Store a station's path on a radio, replacing any earlier one."""
        stamped = stamp(self.clock())
        return await self._done(
            lambda conn: stationsql.put_station_path(conn, call, radio, path, stamped),
            "a station's path could not be kept",
        )

    async def forget_path(self, call: str, radio: RadioId) -> bool:
        return await self._done(
            lambda conn: stationsql.clear_station_path(conn, call, radio), "a station's path could not be removed"
        )
