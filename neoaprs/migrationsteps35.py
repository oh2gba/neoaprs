"""Migration 35, frozen here beside migrations.py (which lists it in MIGRATIONS and runs it): the map's radius is at most 300 km. The same rules as for the earlier steps (migrationsteps31.py): a step is never
edited once it has been released, and what it uses beside itself is frozen with it. It reads the database and nothing of the program."""
import logging
import sqlite3

log = logging.getLogger(__name__)

_RADIUS35, _LIMIT35 = "map/radius_km", 300                          # the key, and the most the radius may be from this version on (it was 1000)


def _v35(db: sqlite3.Connection) -> None:
    """`map/radius_km` is 10 to 300 km, where it was 10 to 1000: a stored radius above 300 is brought to 300 (the map file the station has is not touched, and a radius from 10 to 300, a value that is not a whole
    number and no row at all stay as they are: the first is right, the others were the default already). One INFO line in the log says what was stored."""
    row = db.execute("SELECT value FROM settings WHERE key = ?", (_RADIUS35,)).fetchone()
    if row is None:
        return
    try:
        stored = int(str(row[0]).strip())
    except ValueError:
        return
    if stored > _LIMIT35:
        db.execute("UPDATE settings SET value = ?, rev = rev + 1 WHERE key = ?", (str(_LIMIT35), _RADIUS35))
        log.info("the map's radius was %d km, at most %d km is kept now: it is %d km", stored, _LIMIT35, _LIMIT35)
