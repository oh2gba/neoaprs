"""Migration 36: a bulletin of ours keeps how long it is sent.

A released step is never edited, nor are the constants it uses. It reads only the database."""
import logging
import sqlite3

log = logging.getLogger(__name__)

_BULLETIN36, _ANNOUNCEMENT36 = 4, 72                                   # hours a bulletin and an announcement were sent for


def _v36(db: sqlite3.Connection) -> None:
    """`own_bulletin.lasts_h`: how many hours after its first packet a post of ours is sent, 1 to 168. A bulletin and a group bulletin get 4, an announcement (`BLNA` to `BLNZ`, four characters: a group
    bulletin is longer even when its group starts with a letter) 72, the times they were sent for before. One INFO line in the log gives the counts."""
    db.execute(f"ALTER TABLE own_bulletin ADD COLUMN lasts_h INTEGER NOT NULL DEFAULT {_BULLETIN36} CONSTRAINT own_bulletin_lasts CHECK (lasts_h BETWEEN 1 AND 168)")
    announcements = db.execute("UPDATE own_bulletin SET lasts_h = ? WHERE length(slot) = 4 AND substr(slot, 4, 1) GLOB '[A-Z]'", (_ANNOUNCEMENT36,)).rowcount
    total = int(db.execute("SELECT COUNT(*) FROM own_bulletin").fetchone()[0])
    if total:
        log.info("%d bulletins of ours are sent for %d hours and %d announcements for %d hours", total - announcements, _BULLETIN36, announcements, _ANNOUNCEMENT36)
