"""No file that could be committed (tracked, or new and not ignored) holds the AISStream key of the
project's own station: every 40 hexadecimal characters in a row of such a text file, also inside a
longer run, are hashed and compared with the key's SHA-256, which is all this test knows of it."""

import hashlib
import re
import subprocess
from pathlib import Path

from tests.test_hygiene import ROOT, needs_git

KEY_SHA256 = "65427a5b7261c7e535bf7f2fefe46b3088b8110dc11435a397bb5db9bac7619b"
HEX_RUN = re.compile(rb"[0-9A-Fa-f]{40,}")
KEY_LENGTH = 40
MAX_BYTES = 8 * 1024 * 1024


def committable(root: Path = ROOT) -> list[str]:
    """The files git tracks, and the new ones it does not ignore: what a commit could take."""
    done = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    names = (name.decode("utf-8", "surrogateescape") for name in done.stdout.split(b"\0") if name)
    return [name for name in names if (root / name).is_file()]


def windows(run: bytes) -> set[bytes]:
    lower = run.lower()
    return {lower[i : i + KEY_LENGTH] for i in range(len(lower) - KEY_LENGTH + 1)}


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
        candidates = set().union(*(windows(run) for run in HEX_RUN.findall(data)))
        if any(hashlib.sha256(one).hexdigest() == digest for one in candidates):
            found.append(name)
    return found


def test_the_scan_finds_a_key_by_its_hash_in_either_case_and_inside_a_longer_run(tmp_path: Path) -> None:
    made_up = b"0123456789abcdef0123456789abcdef01234567"
    (tmp_path / "a.txt").write_bytes(b"key=" + made_up.upper() + b"\n")
    (tmp_path / "b.txt").write_bytes(b"key=cafe" + made_up + b"0\n")
    (tmp_path / "c.txt").write_bytes(b"key=" + made_up[:39] + b"\n")
    found = holders(["a.txt", "b.txt", "c.txt"], tmp_path, hashlib.sha256(made_up).hexdigest())
    assert found == ["a.txt", "b.txt"]


@needs_git
def test_a_new_file_not_yet_added_is_scanned_and_an_ignored_one_is_not(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("ignored.txt\n")
    (tmp_path / "new.txt").write_text("x\n")
    (tmp_path / "ignored.txt").write_text("x\n")
    assert sorted(committable(tmp_path)) == [".gitignore", "new.txt"]


@needs_git
def test_no_file_that_could_be_committed_holds_the_stations_aisstream_key() -> None:
    assert holders(committable(), ROOT) == []
