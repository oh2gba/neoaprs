"""Made-up satellites for the demo daemon's map (scripts/demo-daemon --satellites), a module of that script.

The project's list of satellites merged with the elements of the test fixture, as the server merges
them, every epoch moved by the same amount to an hour ago, so that the daemon draws them on any day."""

import csv
import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ELEMENTS = ROOT / "tests" / "fixtures" / "satellites" / "amateur.csv"
LISTED = ROOT / "server" / "neo" / "private" / "satellites-list.json"
FILE_NAME = "satellites.json"  # the name the daemon reads in its data folder (neoaprs/satellitelist.py)


def _epoch(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def satellites_file(now: datetime) -> bytes:
    """The satellites file the project's server would serve, with its newest epoch an hour before `now`."""
    rows = {int(row["NORAD_CAT_ID"]): row for row in csv.DictReader(io.StringIO(ELEMENTS.read_text(encoding="utf-8")))}
    shift = now - timedelta(hours=1) - max(_epoch(row["EPOCH"]) for row in rows.values())
    for row in rows.values():
        row["EPOCH"] = (_epoch(row["EPOCH"]) + shift).replace(tzinfo=None).isoformat(timespec="microseconds")
    listed = json.loads(LISTED.read_text(encoding="utf-8"))["satellites"]
    satellites = [
        {**{k: v for k, v in one.items() if k != "source"}, "elements": rows[one["id"]]}
        for one in listed
        if one["id"] in rows
    ]
    stamp = now.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    return json.dumps({"v": 1, "made": stamp, "elements_at": stamp, "satellites": satellites}).encode()


def put(data: Path, now: datetime) -> Path:
    """Write the made-up file into the data folder `data`; return its path."""
    path = data / FILE_NAME
    path.write_bytes(satellites_file(now))
    return path
