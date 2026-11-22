#!/usr/bin/env python3
"""Refresh neoaprs/airportdata.py from OurAirports' airports.csv (public domain).

  scripts/gen-airports.py [--from FILE]    write the module from the list's address or FILE
  scripts/gen-airports.py --check FILE     write nothing; exit 1 if the module differs"""
import argparse
import csv
import hashlib
import io
import re
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "neoaprs" / "airportdata.py"
URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
KINDS = {"large_airport", "medium_airport"}
BRACKETED = re.compile(r"\([^()]*\)")            # bracketed additions to a place
PER_LINE = 3
CODE_LENGTH = 4


def code_of(row: dict[str, str]) -> str:
    """Return the upper-case ICAO code (`icao_code`, `gps_code` or `ident`), or ""."""
    code = next((value.strip() for value in (row.get("icao_code", ""), row.get("gps_code", ""), row.get("ident", "")) if value.strip()), "")
    return code.upper() if len(code) == CODE_LENGTH and code.isascii() and code.isalnum() else ""


def place_of(row: dict[str, str]) -> str:
    """Return the place a card shows: the municipality or the name, without bracketed additions."""
    whole = " ".join((row.get("municipality", "").strip() or row.get("name", "")).split())
    return " ".join(BRACKETED.sub(" ", whole).split()) or whole


def rows(text: str) -> list[tuple[str, str]]:
    """Return (code, place) of every large or medium airport with a code, sorted; the first row
    wins."""
    seen: dict[str, str] = {}
    for row in csv.DictReader(io.StringIO(text)):
        code = code_of(row)
        place = place_of(row)
        if row.get("type") in KINDS and code and place and code not in seen:
            seen[code] = place
    return sorted(seen.items())


def literal(row: tuple[str, str]) -> str:
    return "(" + ", ".join(json.dumps(cell, ensure_ascii=False) for cell in row) + ")"


def module_text(table: list[tuple[str, str]], digest: str, date: str) -> str:
    head = (
        '"""The airports, a snapshot: the place of each large or medium airport by its ICAO code, which a card names the departure and the destination of an aircraft from. Written by scripts/gen-airports.py, never edited by hand.\n\n'
        "Source: airports.csv of OurAirports, https://ourairports.com/data/, public domain. This module is that list reduced to the code and the place (the municipality, or the airport's name where there is none).\n"
        f"Snapshot of {date}, sha256 of the source file {digest}.\n"
        '"""\n')
    lines = [", ".join(literal(row) for row in table[i:i + PER_LINE * 5]) + "," for i in range(0, len(table), PER_LINE * 5)]
    return head + "AIRPORTS: tuple[tuple[str, str], ...] = (\n" + "".join(f"    {line}\n" for line in lines) + ")\n"


def source_of(args: argparse.Namespace) -> str:
    if args.source is not None:
        return Path(args.source).read_text(encoding="utf-8")
    with urllib.request.urlopen(URL, timeout=60) as response:
        return str(response.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Refreshes neoaprs/airportdata.py from OurAirports' airports.csv.")
    ap.add_argument("--from", dest="source", metavar="FILE", help="read this airports.csv instead of fetching the list")
    ap.add_argument("--check", metavar="FILE", help="write nothing; exit 1 when the module is not what this airports.csv makes")
    args = ap.parse_args()
    text = Path(args.check).read_text(encoding="utf-8") if args.check else source_of(args)
    table = rows(text)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if args.check:
        current = TARGET.read_text(encoding="utf-8")
        date = next((line.split()[2] for line in current.splitlines() if line.startswith("Snapshot of ")), "")
        if module_text(table, digest, date.rstrip(",")) != current:
            print("neoaprs/airportdata.py is not made from that file: run scripts/gen-airports.py", file=sys.stderr)
            return 1
        return 0
    TARGET.write_text(module_text(table, digest, datetime.now(UTC).strftime("%Y-%m-%d")), encoding="utf-8")
    print(f"{TARGET.relative_to(ROOT) if TARGET.is_relative_to(ROOT) else TARGET}: {len(table)} airports")
    return 0


if __name__ == "__main__":
    sys.exit(main())
