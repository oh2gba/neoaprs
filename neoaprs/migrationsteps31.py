"""Migration 31: the radios of a station become rows.

A released step is never edited, nor are the helper functions and constants it uses. It reads only
the database; the radio types, the tickbox words and the defaults are written out here."""
import json
import sqlite3

from .dberror import StoreError
from .migrationlog import log

# stored tickbox words
_TRUE, _FALSE = ("1", "true", "yes", "on"), ("0", "false", "no", "off")
# `tnc/profile` values; anything else is `kiss`
_FM_TYPES = ("kenwood-tnc2", "kenwood-d710", "kantronics", "kiss", "kiss-tcp", "dummy")
# `hf/profile` values; anything else is `mercury`
_HF_TYPES = ("mercury", "dummy-hf")
# (settings key, radio key it becomes on radio 1)
_FM_MOVES = (("serial/port", "port"), ("serial/baud", "baud"), ("tcp/host", "tcp_host"), ("tcp/port", "tcp_port"), ("beacon/path", "path"), ("digi/enabled", "digipeat"))
# the same for radio 2 (the path is kept there in case HF gets one)
_HF_MOVES = (("mercury/sound_card", "sound_card"), ("mercury/keying", "keying"), ("mercury/tx_gain_db", "tx_gain_db"), ("beacon/path", "path"))
# (daemon state row, radio row it becomes)
_STATE = (("serial/last_port", "radio/1/last_port"), ("beacon/last_sent_at", "radio/1/beacon_last_sent_at"), ("hf/beacon_last_sent_at", "radio/2/beacon_last_sent_at"))
# rows naming the HF radio; small tables first, as the station cache outlives its packets
_HF_ROWS = (("message_attempt", "radio = 'hf'"), ("message", "radio = 'hf'"), ("own_object", "radio IN ('hf', 'both')"), ("station", "heard_hf > 0"), ("packet", "radio = 'hf'"))
# tables whose rows migrations 32 and 33 give a radio; a row in any means an existing installation
_KEPT = ("own_object", "station_pref", "message", "message_attempt", "station", "packet")
# settings rows that belong to a radio from now on
_GONE = "key GLOB 'tnc/*' OR key GLOB 'hf/*' OR key GLOB 'mercury/*' OR key GLOB 'tcp/*' OR key IN ('serial/port', 'serial/baud', 'beacon/path', 'digi/enabled', 'fm/enabled')"
_CHOICES = "messages/radio_by_station"


def _tables31(db: sqlite3.Connection) -> None:
    """The tables of migration 31: `radio`, `radio_setting` (a radio's own settings, with a revision per row as `settings` has) and `_m31`, the one row that says which of today's two radios there is and
    which is on, for the migrations 32 and 33 (33 drops it)."""
    form = "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'"
    db.execute(f"""CREATE TABLE radio (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL CONSTRAINT radio_kind CHECK (kind IN ('fm', 'hf', 'lora')),
        type TEXT NOT NULL CONSTRAINT radio_type_present CHECK (type <> ''),
        name TEXT NOT NULL DEFAULT '' CONSTRAINT radio_name_length CHECK (length(name) <= 8),
        enabled INTEGER NOT NULL CONSTRAINT radio_enabled CHECK (enabled IN (0, 1)),
        position INTEGER NOT NULL,
        removed_at TEXT CONSTRAINT radio_removed_form CHECK (removed_at IS NULL OR removed_at GLOB {form})
    ) STRICT""")
    db.execute("CREATE UNIQUE INDEX radio_name ON radio (lower(name)) WHERE name <> '' AND removed_at IS NULL")
    db.execute("""CREATE TABLE radio_setting (
        radio_id INTEGER NOT NULL REFERENCES radio (id),
        key TEXT NOT NULL CONSTRAINT radio_setting_key_form CHECK (key <> '' AND key NOT GLOB '*/*'),
        value TEXT NOT NULL,
        rev INTEGER NOT NULL DEFAULT 1 CONSTRAINT radio_setting_rev_positive CHECK (rev >= 1),
        PRIMARY KEY (radio_id, key)
    ) STRICT""")
    db.execute("""CREATE TABLE _m31 (
        hf_exists INTEGER NOT NULL CHECK (hf_exists IN (0, 1)),
        fm_on INTEGER NOT NULL CHECK (fm_on IN (0, 1)),
        hf_on INTEGER NOT NULL CHECK (hf_on IN (0, 1))
    ) STRICT""")


def _on31(text: str | None, default: bool) -> bool:
    """A stored tickbox as the settings read it: its word, and the default for no row and for a word that is none."""
    word = (text or "").strip().lower()
    return True if word in _TRUE else False if word in _FALSE else default


def _type31(text: str | None, known: tuple[str, ...], default: str, key: str) -> str:
    """A stored type as the settings read it: the key of a type there is, and the default for no row and for a text that is no type (told, as the settings told it at every start)."""
    word = (text or "").strip()
    if word in known:
        return word
    if text is not None:
        log.info("%s was %r, which is no type of that radio: its type is %s, as it was in force", key, text, default)
    return default


def _choices31(text: str | None) -> dict[str, str]:
    """The stations' radios of `messages/radio_by_station` ({"OH2GAX-2": "hf"}) by call; a row that is not one says nothing."""
    try:
        kept = json.loads(text or "{}")
    except ValueError:
        return {}
    return {str(call): word for call, word in kept.items() if word in ("fm", "hf")} if isinstance(kept, dict) else {}


def _hf_named31(db: sqlite3.Connection, settings: dict[str, str]) -> bool:
    """Whether anything stored names the HF radio: a settings row of its own (`hf/*`, `mercury/*`: the program writes only what was changed, so a row means it was set), the type `mercury` of the build
    before two radios, a station's choice, or a packet, a message, an attempt or an object on it, or a station it heard (the cache keeps the count after the daily prune took the packets)."""
    if any(key.startswith(("hf/", "mercury/")) for key in settings) or settings.get("tnc/profile", "").strip() == "mercury" or "hf" in _choices31(settings.get(_CHOICES)).values():
        return True
    return any(db.execute(f"SELECT EXISTS (SELECT 1 FROM {table} WHERE {where})").fetchone()[0] for table, where in _HF_ROWS)


def _move31(db: sqlite3.Connection, hf_exists: bool) -> None:
    """The settings rows of the radios become the radios' own, each with its value and its revision as they are; the rows of the daemon's state take their radio's name; the stations' choices name the radio
    by its id; then the old rows are deleted. Any doubt raises, and the rollback leaves everything where it was."""
    expected = moved = 0
    for radio, moves in ((1, _FM_MOVES), (2, _HF_MOVES if hf_exists else ())):
        for old, new in moves:
            expected += int(db.execute("SELECT COUNT(*) FROM settings WHERE key = ?", (old,)).fetchone()[0])
            moved += db.execute("INSERT INTO radio_setting (radio_id, key, value, rev) SELECT ?, ?, value, rev FROM settings WHERE key = ?", (radio, new, old)).rowcount
    kept = int(db.execute("SELECT COUNT(*) FROM radio_setting").fetchone()[0])
    if not expected == moved == kept:
        raise StoreError(f"{expected} settings of the radios were to become the radios' own, {moved} were written and {kept} are there; nothing was changed")
    for old, new in _STATE:
        db.execute("UPDATE OR REPLACE settings SET key = ? WHERE key = ?", (new, old))
    row = db.execute("SELECT value FROM settings WHERE key = ?", (_CHOICES,)).fetchone()
    if row is not None:
        by_id = json.dumps({call: 1 if word == "fm" else 2 for call, word in _choices31(str(row[0])).items()}, sort_keys=True)
        db.execute("UPDATE settings SET value = ?, rev = rev + 1 WHERE key = ?", (by_id, _CHOICES))
    db.execute(f"DELETE FROM settings WHERE {_GONE}")


def _v31(db: sqlite3.Connection) -> None:
    """Any number of radios (neoaprs/radiospec.py): a radio is a row of `radio` (its id, which is never used again, its kind, its type, the name the operator gave it, whether it is enabled, its place in
    the list, and when it was removed: a removed radio keeps its row, so that what came by it still says so) and its own settings are rows of `radio_setting`.

    A database with no settings row and no row of an installation (`_KEPT`: a packet, a message, an object, a station, a station's preference) is a new installation and gets no radio. Any other gets
    radio 1, today's FM radio, and radio 2, today's HF radio, when anything stored names it
    (`_hf_named31`). Each radio's type and tickbox are written plainly, with the defaults and the two old rules that the settings applied at every start: `tnc/enter_kiss` true with no `tnc/profile` is
    the Kenwood TNC-2 type, and `tnc/profile = mercury` with neither tickbox stored (the build before two radios) is the HF radio on and the FM radio off. The settings rows of the radios
    (`tnc/*`, `fm/enabled`, `hf/*`, `mercury/*`, `serial/port`, `serial/baud`, `tcp/*`, `beacon/path`, `digi/enabled`) become the radios' own and are deleted; `serial/pattern` and `serial/skip` stay,
    they are the computer's. The rows of the daemon's state take their radio's name (`radio/1/last_port`, `radio/<id>/beacon_last_sent_at`) and the stations' choices of `messages/radio_by_station`
    say 1 and 2 for `fm` and `hf`. What was decided is left in `_m31` for the migrations 32 and 33."""
    _tables31(db)
    settings = {str(key): str(value) for key, value in db.execute("SELECT key, value FROM settings")}
    if not settings and not any(db.execute(f"SELECT EXISTS (SELECT 1 FROM {table})").fetchone()[0] for table in _KEPT):
        db.execute("INSERT INTO _m31 (hf_exists, fm_on, hf_on) VALUES (0, 0, 0)")
        return
    alone = settings.get("tnc/profile", "").strip() == "mercury" and "hf/enabled" not in settings and "fm/enabled" not in settings      # (the Mercury modem as the type of the one radio)
    profile = None if alone else settings.get("tnc/profile")
    fm_type = "kenwood-tnc2" if profile is None and _on31(settings.get("tnc/enter_kiss"), False) else _type31(profile, _FM_TYPES, "kiss", "tnc/profile")
    fm_on, hf_on = (False, True) if alone else (_on31(settings.get("fm/enabled"), True), _on31(settings.get("hf/enabled"), False))
    hf_exists = _hf_named31(db, settings)
    db.execute("INSERT INTO radio (id, kind, type, name, enabled, position) VALUES (1, 'fm', ?, '', ?, 1)", (fm_type, int(fm_on)))
    if hf_exists:
        db.execute("INSERT INTO radio (id, kind, type, name, enabled, position) VALUES (2, 'hf', ?, '', ?, 2)", (_type31(settings.get("hf/profile"), _HF_TYPES, "mercury", "hf/profile"), int(hf_on)))
    db.execute("INSERT INTO _m31 (hf_exists, fm_on, hf_on) VALUES (?, ?, ?)", (int(hf_exists), int(fm_on), int(hf_on and hf_exists)))
    _move31(db, hf_exists)
    log.info("the radios are rows of their own now: radio 1 is the FM radio (%s, %s)%s", fm_type, "on" if fm_on else "off",
             f", radio 2 the HF radio ({'on' if hf_on else 'off'})" if hf_exists else "; no HF radio was ever set up, so there is none")
