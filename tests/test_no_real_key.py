"""No tracked file holds the AISStream key of the project's own station: every run of 40 hexadecimal
characters in a tracked text file is hashed and compared with the key's SHA-256, which is all this
test knows of it."""

import hashlib
import re
from pathlib import Path

from tests.test_hygiene import ROOT, needs_git, tracked

KEY_SHA256 = "65427a5b7261c7e535bf7f2fefe46b3088b8110dc11435a397bb5db9bac7619b"
HEX_RUN = re.compile(rb"(?<![0-9A-Fa-f])[0-9A-Fa-f]{40}(?![0-9A-Fa-f])")
MAX_BYTES = 8 * 1024 * 1024


def holders(paths: list[str], root: Path, digest: str = KEY_SHA256) -> list[str]:
    """Return the files among `paths` that hold a 40-character hex run with that SHA-256."""
    found = []
    for name in paths:
        path = root / name
        if path.stat().st_size > MAX_BYTES:
            continue
        data = path.read_bytes()
        if b"\0" in data[:8192]:
            continue  # not a text file
        runs = {run.lower() for run in HEX_RUN.findall(data)}
        if any(hashlib.sha256(run).hexdigest() == digest for run in runs):
            found.append(name)
    return found


def test_the_scan_finds_a_key_by_its_hash_in_either_case(tmp_path: Path) -> None:
    made_up = b"0123456789abcdef0123456789abcdef01234567"
    (tmp_path / "a.txt").write_bytes(b"key=" + made_up.upper() + b"\n")
    (tmp_path / "b.txt").write_bytes(b"key=" + made_up + b"0\n")  # 41 characters: another thing
    assert holders(["a.txt", "b.txt"], tmp_path, hashlib.sha256(made_up).hexdigest()) == ["a.txt"]


@needs_git
def test_no_tracked_file_holds_the_stations_aisstream_key() -> None:
    assert holders(tracked(), ROOT) == []
