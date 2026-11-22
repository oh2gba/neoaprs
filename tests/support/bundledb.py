"""A database made from a support bundle (neoaprs/cli/supportmake.py), as version 30 kept it.

A bundle has no database file: its `settings.json` lists the stored settings rows and its
`state.json` whether each radio heard anything. Secrets and changed commands are only said to be
set, so their rows are left out and their keys are returned.
"""

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
from tests.support.migrated31 import OWN_31, STATE_31, at_thirty

# A radio's state row now, and the row of version 30 it was (radio/1/last_port: serial/last_port).
STATE_BACK = {new: old for old, new in STATE_31.items()}
# How a bundle shows a value it hides (neoaprs/cli/redaction.py).
HIDDEN = re.compile(r"\(set, \d+ characters\)")
# At most this many packets are made for a radio that heard some.
PACKETS_MADE = 20
PACKET = (
    "INSERT INTO packet (heard_at, direction, raw, source, destination, path, kind, summary, decoded, via, radio) "
    "VALUES (?, 'in', x'00', ?, 'APRS', '', 'status', 'made from a support bundle', '{}', 'rf', ?)"
)


def bundle_files(bundle: Path) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """`settings.json` and `state.json` (None when absent) of a bundle zip or folder."""
    if bundle.is_dir():
        state = bundle / "state.json"
        return json.loads((bundle / "settings.json").read_text(encoding="utf-8")), json.loads(
            state.read_text(encoding="utf-8")
        ) if state.exists() else None
    with zipfile.ZipFile(bundle) as z:
        return json.loads(z.read("settings.json")), json.loads(
            z.read("state.json")
        ) if "state.json" in z.namelist() else None


def stored_rows(settings: Mapping[str, Any]) -> tuple[dict[str, str], list[str]]:
    """The settings rows a bundle tells (key to stored text) and the keys it only says are set."""
    unstored = set(settings.get("defaults_are_used_for", []))
    differs: Mapping[str, str] = settings.get("stored_text_differs", {})
    told = {
        **{key: differs.get(key, value) for key, value in settings.get("values", {}).items() if key not in unstored},
        **settings.get("other_rows", {}),
    }
    # The choices are by id, which migration 31 reads by word.
    if "radios" in settings and "messages/radio_by_station" in told:
        told["messages/radio_by_station"] = json.dumps(
            {
                call: {1: "fm", 2: "hf"}.get(radio, radio)
                for call, radio in json.loads(told["messages/radio_by_station"]).items()
            },
            sort_keys=True,
        )
    # Radios 1 and 2 are rows of their own: made again as the version 30 rows migration 31 reads.
    if "radios" in settings:
        told = {**told, **rows_of_radios(settings["radios"])}
    for new, old in STATE_BACK.items():
        if new in told:
            told[old] = told.pop(new)
    hidden = sorted(key for key, text in told.items() if HIDDEN.fullmatch(str(text)))
    return {
        key: "" if text == "(empty)" and (is_secret(key) or key in FREE_TEXT_SECRETS) else str(text)
        for key, text in told.items()
        if key not in hidden
    }, hidden


def rows_of_radios(radios: list[Mapping[str, Any]]) -> dict[str, str]:
    """The version 30 settings rows of radios 1 and 2 of a bundle that has radios as rows."""
    rows: dict[str, str] = {}
    for radio in radios:
        id = radio.get("id")
        if radio.get("removed_at") is not None or id not in (1, 2):
            continue
        profile, tickbox = ("tnc/profile", "fm/enabled") if id == 1 else ("hf/profile", "hf/enabled")
        rows[profile], rows[tickbox] = str(radio["type"]), "true" if radio["enabled"] else "false"
        stored: Mapping[str, str] = radio.get("stored", {})
        rows.update({flat: str(stored[own]) for flat, (of, own) in OWN_31.items() if of == id and own in stored})
    return rows


def heard(state: Mapping[str, Any] | None) -> dict[str, int]:
    """How many packets radios 1 and 2 handed on, as the bundle's `state.json` tells."""
    if state is None:
        return {}
    radios = {entry.get("id"): entry.get("tnc") for entry in state.get("radios") or [] if isinstance(entry, dict)}
    lines = (
        {"fm": radios.get(1), "hf": radios.get(2)}
        if radios
        else {"fm": state.get("tnc"), "hf": (state.get("hf") or {}).get("tnc")}
    )
    return {radio: int(((line or {}).get("stats") or {}).get("packets") or 0) for radio, line in lines.items()}


def bundle_database(path: Path, bundle: Path, clock: Clock = utcnow) -> list[str]:
    """Make the database file `path` as the bundle's installation had it at version 30; return the
    left-out keys."""
    settings, state = bundle_files(bundle)
    rows, hidden = stored_rows(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = at_thirty(path, clock)
    try:
        db.execute("BEGIN")
        db.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", sorted(rows.items()))
        for radio, count in heard(state).items():
            db.executemany(
                PACKET, [(stamp(clock()), f"BUNDLE-{n % 15 + 1}", radio) for n in range(min(count, PACKETS_MADE))]
            )
        db.execute("COMMIT")
    finally:
        db.close()
    return hidden
