"""Migration 37: a station that gated to APRS-IS keeps gating, by its own tick.

A released step is never edited, nor are the constants it uses. It reads only the database."""
import logging
import sqlite3

log = logging.getLogger(__name__)

_SHOW37, _PASSWORD37, _GATE37 = "igate/enabled", "igate/password", "igate/gate"   # the keys
_TRUE37 = ("1", "true", "yes", "on")                                                # what a stored true is


def _v37(db: sqlite3.Connection) -> None:
    """`igate/gate` (Send what I hear) is its own switch, off by default, where gating was `igate/enabled` with a passcode in `igate/password`: a station with both gets `igate/gate` true, so that it
    goes on gating; any other station gets no row, as it gated nothing. A row already there is left as it is. One INFO line in the log says it."""
    rows = dict(db.execute("SELECT key, value FROM settings WHERE key IN (?, ?, ?)", (_SHOW37, _PASSWORD37, _GATE37)).fetchall())
    if _GATE37 in rows or str(rows.get(_SHOW37, "")).strip().lower() not in _TRUE37 or not str(rows.get(_PASSWORD37, "")).strip():
        return
    db.execute("INSERT INTO settings (key, value, rev) VALUES (?, 'true', 1)", (_GATE37,))
    log.info("the iGate gated with a passcode set by hand: Send what I hear is on")
