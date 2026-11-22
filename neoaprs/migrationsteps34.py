"""Migration 34: no main radio.

A released step is never edited, nor are the helper functions and constants it uses. It reads only
the database; the sending radio types, the e-mail radio kinds, the tickbox words and the keys are
written out here."""
import sqlite3

from .dberror import StoreError

# radio types that send
_SENDS34 = ("direwolf", "kiss", "kenwood-d710", "kenwood-tnc2", "kantronics", "kiss-tcp", "dummy", "dummy-hf", "mercury", "lora-tcp", "lora-serial", "dummy-lora")
_MAIL_KINDS34 = ("fm", "lora")                                      # radio kinds e-mail was sent on
_TRUE34, _FALSE34 = ("1", "true", "yes", "on"), ("0", "false", "no", "off")     # stored tickbox words
# unticked by default; the main radio's until a row exists
_CHOSEN_BY_ROW34 = ("status", "ask", "local_info")
_MAIN34, _MAIL34 = "station/main_radio", "email/radio"
_NEW_ONES34 = ("objects/send_on", "bulletins/send_on")              # defaults of a new object and bulletin


def _ticked34(value: object, default: bool) -> bool:
    """A stored tickbox as 0.20.0 read it: its word, the default for no row and for a word that is none."""
    word = str(value).strip().lower() if value is not None else ""
    return True if word in _TRUE34 else False if word in _FALSE34 else default


def _chosen34(db: sqlite3.Connection) -> int | None:
    """`station/main_radio` as 0.20.0 read it: a whole number from 1 to 2**31 - 1, else none."""
    row = db.execute("SELECT value FROM settings WHERE key = ?", (_MAIN34,)).fetchone()
    try:
        chosen = int(str(row[0]).strip()) if row is not None else None
    except ValueError:
        return None
    return chosen if chosen is not None and 1 <= chosen <= 2**31 - 1 else None


def _radios34(db: sqlite3.Connection) -> tuple[list[int], list[int], dict[int, str]]:
    """The radios not removed whose type sends, by position then id; those of them that are enabled; the kind of each."""
    marks = ", ".join("?" * len(_SENDS34))
    found = db.execute(f"SELECT id, enabled, kind FROM radio WHERE removed_at IS NULL AND type IN ({marks}) ORDER BY position, id", _SENDS34).fetchall()
    return [int(r[0]) for r in found], [int(r[0]) for r in found if int(r[1]) == 1], {int(r[0]): str(r[2]) for r in found}


def _row34(db: sqlite3.Connection, radio: int, key: str) -> tuple[bool, object]:
    """Whether the radio has a row of its own for the key, and its value."""
    row = db.execute("SELECT value FROM radio_setting WHERE radio_id = ? AND key = ?", (radio, key)).fetchone()
    return row is not None, None if row is None else row[0]


def _put34(db: sqlite3.Connection, radio: int, key: str, value: str) -> None:
    db.execute("INSERT INTO radio_setting (radio_id, key, value) VALUES (?, ?, ?) ON CONFLICT(radio_id, key) DO UPDATE SET value = excluded.value, rev = radio_setting.rev + 1", (radio, key, value))


def _order34(db: sqlite3.Connection, pivot: int, first: int) -> None:
    """The order of the boxes: while the pivot (the main radio; with none on, the radio chosen, else the first that sends) is not the first radio that sends in their order (the first that is on; with none
    on, the first that sends), or two live radios share a place, the live radios are numbered again from 1, the pivot first and the others in their order. The first that is on, once one is, is then the radio
    0.20.0 resolved the main radio to."""
    live = [int(r[0]) for r in db.execute("SELECT id FROM radio WHERE removed_at IS NULL ORDER BY position, id")]
    places = db.execute("SELECT COUNT(*), COUNT(DISTINCT position) FROM radio WHERE removed_at IS NULL").fetchone()
    if first == pivot and int(places[0]) == int(places[1]):
        return
    for position, id in enumerate([pivot, *(id for id in live if id != pivot)], 1):
        if db.execute("UPDATE radio SET position = ? WHERE id = ?", (position, id)).rowcount != 1:
            raise StoreError(f"radio {id} could not be given its place {position}; nothing was changed")


def _send_on34(db: sqlite3.Connection, senders: list[int], on: list[int], main: int | None, pivot: int) -> None:
    """The status, Ask around and Local info, where the station has several radios that send (one alone carries them whatever is stored, and a radio added beside it later ticks it then): the pivot
    ticked where no radio that sends has a row for the key (a radio without one is unticked, the field's default); where some has, the rows as they are, and while several are on and none of them is
    ticked, the main radio ticked (what 0.20.1 sent it on)."""
    if len(senders) < 2:
        return
    for key in _CHOSEN_BY_ROW34:
        rows = {radio: _row34(db, radio, key) for radio in senders}
        if not any(has for has, _ in rows.values()):
            _put34(db, pivot, key, "true")
        elif len(on) > 1 and main is not None and not any(_ticked34(rows[radio][1], False) for radio in on):
            _put34(db, main, key, "true")


def _beacon34(db: sqlite3.Connection, on: list[int], main: int | None) -> None:
    """The beacon: while several radios are on and none of them is ticked (a radio without a row is), the main radio ticked, where 0.20.0 sent it."""
    if len(on) > 1 and main is not None and not any(_ticked34(_row34(db, radio, "beacon")[1], True) for radio in on):
        _put34(db, main, "beacon", "true")


def _objects34(db: sqlite3.Connection, on: list[int], main: int | None) -> None:
    """Our objects: while several radios are on, an object none of whose radios is on gets the main radio, where 0.20.0 sent it."""
    if len(on) < 2 or main is None:
        return
    for name, radios in db.execute("SELECT name, radios FROM own_object").fetchall():
        ids = [int(part) for part in str(radios).split(",")]
        if not set(ids) & set(on):
            if db.execute("UPDATE own_object SET radios = ? WHERE name = ?", (",".join(str(id) for id in sorted({*ids, main})), name)).rowcount != 1:
                raise StoreError(f"the object {name!r} could not be given its radio; nothing was changed")


def _mail34(db: sqlite3.Connection, on: list[int], later: list[int], kinds: dict[int, str], several: bool) -> None:
    """E-mail: `email/radio` is the radio 0.20.0 sent a mail on (the main radio while it is of a kind internet gateways hear, else the first that is on of such a kind), wherever several radios send, so
    that a later change of the radios does not decide it again (a station with one radio that sends needs none: that one carries it, and a radio added beside it keeps it there, neoaprs/sendonrule.py);
    with none of such a kind on, the radio 0.20.0 would send it on once one is (the radio chosen while it is of such a kind, else the first of such a kind that sends, though it is off); a choice already
    stored is left; no row where no radio of such a kind sends. `on` begins with the main radio, `later` with the radio chosen while it sends."""
    heard = [radio for radio in on if kinds[radio] in _MAIL_KINDS34] or [radio for radio in later if kinds[radio] in _MAIL_KINDS34]
    if heard and several:
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO NOTHING", (_MAIL34, str(heard[0])))


def _state34(db: sqlite3.Connection, pivot: int, several: bool) -> None:
    """The state: where several radios send, a new object and a new bulletin start on the pivot (`objects/send_on`, `bulletins/send_on`; a row already there is left; with one, that one is what they start
    with, and a radio added beside it comes after it). The station's last status (`status/last_sent_at`) stays the
    station's: a radio with no send of its own counts from it when it first carries the status, so that none goes out early on a radio that carries it later (a copy into every radio's own row would make
    that radio's status due at once)."""
    for key in _NEW_ONES34 if several else ():
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO NOTHING", (key, str(pivot)))


def _nowhere34(db: sqlite3.Connection, on: list[int]) -> list[str]:
    """What of the things of a station with several radios on is in force on none of them: the status, Ask around, Local info, the beacon, an object, a bulletin."""
    problems = [f"{key} is on none of the radios that are on" for key in _CHOSEN_BY_ROW34 if not any(_ticked34(_row34(db, radio, key)[1], False) for radio in on)]
    if not any(_ticked34(_row34(db, radio, "beacon")[1], True) for radio in on):
        problems.append("the beacon is on none of the radios that are on")
    sets = db.execute("SELECT radios FROM own_object UNION ALL SELECT radios FROM own_bulletin").fetchall()
    if any(not {int(part) for part in str(row[0]).split(",")} & set(on) for row in sets):
        problems.append("an object or a bulletin is on none of the radios that are on")
    return problems


def _checked34(db: sqlite3.Connection, on: list[int]) -> None:
    """Before the commit: while several radios are on, every thing in force on one of them (the status, Ask around, Local info, the beacon, each object and bulletin); the setting gone; the live
    places distinct. StoreError otherwise: the rollback leaves the file as it was."""
    problems = _nowhere34(db, on) if len(on) > 1 else []
    if db.execute("SELECT 1 FROM settings WHERE key = ?", (_MAIN34,)).fetchone() is not None:
        problems.append(f"{_MAIN34} is still there")
    places = db.execute("SELECT COUNT(*), COUNT(DISTINCT position) FROM radio WHERE removed_at IS NULL").fetchone()
    if int(places[0]) != int(places[1]):
        problems.append("two live radios share a place")
    if problems:
        raise StoreError(f"{'; '.join(problems)}; nothing was changed")


def _v34(db: sqlite3.Connection) -> None:
    """No main radio: every thing has its own Send on. A bulletin of ours names the radios it goes out on, `own_bulletin.radios` (their ids, ascending, separated by commas, as an object's), on every
    database first. Then the ticks the main radio stood for are written: the main radio as 0.20.0 resolved it (`station/main_radio` while it is on and sends, else the first that is on and sends) and the
    pivot (the main radio; with none on, the chosen one while it sends, else the first that sends); the pivot's box first where it was not the first that sends; where several radios send, the status, Ask around and
    Local info ticked for the pivot (a radio without a row is unticked, the field's default; a key some radio has a row for is left as it is, and the main radio ticked where several are on and none of
    them is), `email/radio` the radio 0.20.0 sent a mail on (or would, once a radio internet gateways hear is on) and what a new object and a new bulletin start with, the pivot (one radio that sends carries all of it, and a radio added beside it keeps it
    there: neoaprs/sendonrule.py); the beacon and the objects on the main radio where several are on and none of their radios is; every bulletin on the pivot. `station/main_radio` is deleted. Checked before the commit; any doubt raises, and the rollback leaves the file as it was."""
    db.execute("ALTER TABLE own_bulletin ADD COLUMN radios TEXT NOT NULL DEFAULT '1' CONSTRAINT own_bulletin_radios CHECK "
               "(radios GLOB '[1-9]*' AND radios NOT GLOB '*[^0-9,]*' AND radios NOT GLOB '*,' AND radios NOT GLOB '*,,*' AND radios NOT GLOB '*,0*')")
    senders, on, kinds = _radios34(db)
    chosen = _chosen34(db)
    main = chosen if chosen is not None and chosen in on else on[0] if on else None
    pivot = main if main is not None else chosen if chosen is not None and chosen in senders else senders[0] if senders else None
    db.execute("DELETE FROM settings WHERE key = ?", (_MAIN34,))
    if pivot is None:
        _checked34(db, on)
        return
    _order34(db, pivot, on[0] if on else senders[0])
    _send_on34(db, senders, on, main, pivot)
    _beacon34(db, on, main)
    _objects34(db, on, main)
    bulletins = int(db.execute("SELECT COUNT(*) FROM own_bulletin").fetchone()[0])
    if db.execute("UPDATE own_bulletin SET radios = ?", (str(pivot),)).rowcount != bulletins:
        raise StoreError(f"of {bulletins} bulletins not every one was given its radio; nothing was changed")
    _mail34(db, [main, *(radio for radio in on if radio != main)] if main is not None else [], [*([chosen] if chosen is not None and chosen in senders else []), *senders], kinds, len(senders) > 1)
    _state34(db, pivot, len(senders) > 1)
    _checked34(db, on)
