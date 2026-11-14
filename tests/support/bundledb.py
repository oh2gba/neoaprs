"""A database made from a support bundle (neoaprs/cli/supportmake.py), for the proof that a real installation's settings come through the migrations of the radio round: a bundle carries no database file, but
its `settings.json` says every stored row of the settings table, and its `state.json` (when the running daemon made the bundle) whether each radio heard anything.

    left_out = bundle_database(path, bundle)        # `bundle`: the zip, or a folder with its files; `path`: the database file to make

The file is left as version 30 kept it (before the radios were rows), closed: `tests/support/migrated.opened(path)` then runs the migrations on it, as the daemon's start does. What the bundle does not
show cannot be stored: a secret (`web/key`, `igate/password`) and a changed alert command or update address are only said to be set, so those rows are left out (their defaults are in force) and
their keys are what the function gives back."""
import json
import re
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from neoaprs.cli.redaction import FREE_TEXT_SECRETS
from neoaprs.clock import Clock, utcnow
from neoaprs.configtypes import is_secret
from neoaprs.packetcodec import stamp
from tests.support.migrated31 import at_thirty

HIDDEN = re.compile(r"\(set, \d+ characters\)")          # how a bundle shows a value it does not show (neoaprs/cli/redaction.py)
PACKETS_MADE = 20                                       # at most this many packets are made for a radio that heard some
PACKET = ("INSERT INTO packet (heard_at, direction, raw, source, destination, path, kind, summary, decoded, via, radio) "
          "VALUES (?, 'in', x'00', ?, 'APRS', '', 'status', 'made from a support bundle', '{}', 'rf', ?)")


def bundle_files(bundle: Path) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """`settings.json` and `state.json` (None when the bundle has none) of a bundle's zip or of a folder that holds its files."""
    if bundle.is_dir():
        state = bundle / "state.json"
        return json.loads((bundle / "settings.json").read_text(encoding="utf-8")), json.loads(state.read_text(encoding="utf-8")) if state.exists() else None
    with zipfile.ZipFile(bundle) as z:
        return json.loads(z.read("settings.json")), json.loads(z.read("state.json")) if "state.json" in z.namelist() else None


def stored_rows(settings: Mapping[str, Any]) -> tuple[dict[str, str], list[str]]:
    """The rows of the settings table that a bundle's `settings.json` tells (key to the stored text), and the keys of the rows it only says are set. A setting is stored unless the bundle lists it among
    `defaults_are_used_for`; its text is the one of `stored_text_differs` when the stored text was not the value in force, else the value; the rows that are no setting are `other_rows`."""
    unstored = set(settings.get("defaults_are_used_for", []))
    differs: Mapping[str, str] = settings.get("stored_text_differs", {})
    told = {**{key: differs.get(key, value) for key, value in settings.get("values", {}).items() if key not in unstored}, **settings.get("other_rows", {})}
    if "radios" in settings and "messages/radio_by_station" in told:          # (a bundle of a database whose radios are rows: the choices are by id, which migration 31 reads by word)
        told["messages/radio_by_station"] = json.dumps({call: {1: "fm", 2: "hf"}.get(radio, radio) for call, radio in json.loads(told["messages/radio_by_station"]).items()}, sort_keys=True)
    hidden = sorted(key for key, text in told.items() if HIDDEN.fullmatch(str(text)))
    return {key: "" if text == "(empty)" and (is_secret(key) or key in FREE_TEXT_SECRETS) else str(text) for key, text in told.items() if key not in hidden}, hidden


def heard(state: Mapping[str, Any] | None) -> dict[str, int]:
    """How many packets each of today's two radios handed on, as a bundle's `state.json` tells (`tnc` the FM radio's line, `hf.tnc` the HF radio's); nothing without one."""
    if state is None:
        return {}
    lines = {"fm": state.get("tnc"), "hf": (state.get("hf") or {}).get("tnc")}
    return {radio: int(((line or {}).get("stats") or {}).get("packets") or 0) for radio, line in lines.items()}


def bundle_database(path: Path, bundle: Path, clock: Clock = utcnow) -> list[str]:
    """Makes the database file `path` as the installation of the bundle had it at version 30, as far as the bundle tells: its stored settings rows, and for each radio that heard packets some packets of
    that radio (made up: a bundle's state has their number, not the packets). The keys of the rows that were left out because the bundle hides their value."""
    settings, state = bundle_files(bundle)
    rows, hidden = stored_rows(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = at_thirty(path, clock)
    try:
        db.execute("BEGIN")
        db.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", sorted(rows.items()))
        for radio, count in heard(state).items():
            db.executemany(PACKET, [(stamp(clock()), f"BUNDLE-{n % 15 + 1}", radio) for n in range(min(count, PACKETS_MADE))])
        db.execute("COMMIT")
    finally:
        db.close()
    return hidden
