#!/usr/bin/env python3
"""Refreshes neoaprs/devicedata.py, the snapshot of the APRS device identification list that the station card names a station's device from (neoaprs/device.py).

The list is tocalls.yaml of https://github.com/aprsorg/aprs-deviceid (CC BY-SA 2.0, maintained by Hessu, OH7LZB). This script is the only thing that fetches it: the daemon never does. It reads the file
(from the list's own address, or `--from FILE`), keeps for each device the name the card shows ("Kenwood TH-D74" for a hand-held or a rig, the model alone for software and trackers) and writes the module,
with the credit and the licence in its head. Run it with the venv's python from the repository root:  .venv/bin/python scripts/gen-devices.py
`--check FILE` writes nothing and exits 1 when the module is not what FILE would make (the module's date aside).
"""
import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "neoaprs" / "devicedata.py"
URL = "https://raw.githubusercontent.com/aprsorg/aprs-deviceid/main/tocalls.yaml"
VENDOR_SHOWN = {"ht", "rig"}            # the classes whose maker is part of the name; software, trackers and the like are known by their model
NOT_A_NAME = {"unknown", "experimental"}            # what the list writes for a call that no one has a device for (`APRS`) or that anyone may use (`APZ*`)
PER_LINE = 3
SECTIONS = ("mice", "micelegacy", "tocalls")


def parse(text: str) -> dict[str, list[dict[str, object]]]:
    """The few shapes tocalls.yaml has: top-level lists of items, each a `- key: value` line and the `key: value` lines under it (`features:` has a list of words)."""
    sections: dict[str, list[dict[str, object]]] = {}
    items: list[dict[str, object]] | None = None
    item: dict[str, object] | None = None
    feature_key: str | None = None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#") or line == "---":
            continue
        if not line.startswith(" "):
            name = line.rstrip(":")
            if not line.endswith(":") or name in sections:
                raise ValueError(f"line {number}: unexpected {line!r}")
            items, item, feature_key = sections.setdefault(name, []), None, None
            continue
        body = line.strip()
        if items is None:
            raise ValueError(f"line {number}: an item before a section")
        if body.startswith("- ") and ":" in body:
            item, feature_key = {}, None
            items.append(item)
            body = body[2:]
        elif body.startswith("- "):
            if item is None or feature_key is None:
                raise ValueError(f"line {number}: a list item with no list")
            assert isinstance(item[feature_key], list)
            item[feature_key].append(body[2:].strip())          # type: ignore[union-attr]
            continue
        if item is None:
            raise ValueError(f"line {number}: a value before an item")
        key, _, value = body.partition(":")
        value = value.strip()
        if value == "":
            item[key], feature_key = [], key
        else:
            item[key], feature_key = (json.loads(value) if value.startswith('"') else value), None
    return sections


def device_name(entry: dict[str, object]) -> str:
    """"Kenwood TH-D74" for a radio, "APRSdroid" for software: the vendor only where the class is a hand-held or a rig; the vendor alone when the list has no model. The list's "Unknown" and "Experimental" are no name: empty (the entry
    stays, so that it keeps a wider one from naming the call)."""
    vendor, model = str(entry.get("vendor", "")).strip(), str(entry.get("model", "")).strip()
    if vendor and "," not in vendor and entry.get("class") in VENDOR_SHOWN and model and not model.lower().startswith(vendor.lower()):
        name = f"{vendor} {model}"
    else:
        name = model or vendor
    return "" if name.lower() in NOT_A_NAME else name


def rows(sections: dict[str, list[dict[str, object]]]) -> dict[str, list[tuple[str, ...]]]:
    """The three tables of the module: (tocall, name), (suffix, name) and (prefix, suffix, name); the first entry of a key wins."""
    made: dict[str, list[tuple[str, ...]]] = {}
    for section, keys in (("tocalls", ("tocall",)), ("mice", ("suffix",)), ("micelegacy", ("prefix", "suffix"))):
        seen: set[tuple[str, ...]] = set()
        made[section] = []
        for entry in sections.get(section, []):
            name = device_name(entry)
            key = tuple(str(entry.get(k, "")) for k in keys)
            if not all(key[:1]) or key in seen:
                continue
            seen.add(key)
            made[section].append((*key, name))
    return made


def literal(row: tuple[str, ...]) -> str:
    return "(" + ", ".join(json.dumps(cell, ensure_ascii=False) for cell in row) + ")"


def table_text(name: str, annotation: str, table: list[tuple[str, ...]]) -> str:
    lines = [", ".join(literal(row) for row in table[i:i + PER_LINE]) + "," for i in range(0, len(table), PER_LINE)]
    return f"{name}: tuple[{annotation}, ...] = (\n" + "".join(f"    {line}\n" for line in lines) + ")\n"


def module_text(made: dict[str, list[tuple[str, ...]]], digest: str, date: str) -> str:
    head = (
        '"""The APRS device identification list, a snapshot: what a destination call (`tocall`) or the type code of a Mic-E packet says the sender runs. Written by scripts/gen-devices.py, never edited by hand.\n\n'
        "Source: tocalls.yaml of https://github.com/aprsorg/aprs-deviceid, maintained by Hessu, OH7LZB (the list of aprs.fi), licensed CC BY-SA 2.0 (http://creativecommons.org/licenses/by-sa/2.0/). This module is\n"
        "that list reduced to the name a station card shows, and carries the same licence. The wildcards of a tocall: `?` is any one character, `n` a digit, `*` the rest of the call.\n"
        f"Snapshot of {date}, sha256 of the source file {digest}.\n"
        '"""\n')
    return (head + table_text("TOCALLS", "tuple[str, str]", made["tocalls"]) + "\n" + table_text("MICE", "tuple[str, str]", made["mice"]) + "\n"
            + table_text("MICE_LEGACY", "tuple[str, str, str]", made["micelegacy"]))


def source_of(args: argparse.Namespace) -> str:
    if args.source is not None:
        return Path(args.source).read_text(encoding="utf-8")
    with urllib.request.urlopen(URL, timeout=60) as response:
        return str(response.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Refreshes neoaprs/devicedata.py from the APRS device identification list (tocalls.yaml of aprsorg/aprs-deviceid).")
    ap.add_argument("--from", dest="source", metavar="FILE", help="read this tocalls.yaml instead of fetching the list")
    ap.add_argument("--check", metavar="FILE", help="write nothing; exit 1 when the module is not what this tocalls.yaml makes")
    args = ap.parse_args()
    text = Path(args.check).read_text(encoding="utf-8") if args.check else source_of(args)
    made = rows(parse(text))
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if args.check:
        current = TARGET.read_text(encoding="utf-8")
        date = next((line.split()[2] for line in current.splitlines() if line.startswith("Snapshot of ")), "")
        if module_text(made, digest, date.rstrip(",")) != current:
            print("neoaprs/devicedata.py is not made from that file: run scripts/gen-devices.py", file=sys.stderr)
            return 1
        return 0
    TARGET.write_text(module_text(made, digest, datetime.now(UTC).strftime("%Y-%m-%d")), encoding="utf-8")
    print(f"{TARGET.relative_to(ROOT)}: {len(made['tocalls'])} tocalls, {len(made['mice'])} Mic-E suffixes, {len(made['micelegacy'])} legacy Mic-E types")
    return 0


if __name__ == "__main__":
    sys.exit(main())
