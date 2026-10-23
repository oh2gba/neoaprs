"""A pmtiles program for the tests: a Python script made executable that answers `pmtiles extract SOURCE TARGET --maxzoom=Z [--bbox=W,S,E,N] [--dry-run]` the way go-pmtiles does (the lines it logs, the progress
bar redrawn with a carriage return) and writes a file that has a PMTiles header. Nothing is fetched from anywhere.

    fake = install_fake(tmp_path / "bin")          # the program, `fake.path`
    fake.mode("fail")                              # ok (default), fail (a part of the file, then an error), slow (a bar at 10% and then waits to be killed), linger (a bar at 75% for a second, then done), nosize (a dry run that says nothing of the size)
    fake.calls()                                   # one list of the arguments for each run, in order
    fake.pid()                                     # the process id of the latest run"""
import json
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

SCRIPT = r'''#!{python}
import json, os, struct, sys, time
here = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
with open(os.path.join(here, "calls.jsonl"), "a") as f:
    f.write(json.dumps(args) + "\n")
with open(os.path.join(here, "pid"), "w") as f:
    f.write(str(os.getpid()))
try:
    mode = open(os.path.join(here, "mode")).read().strip()
except OSError:
    mode = "ok"
source, target = args[1], args[2]
options = dict(a.lstrip("-").split("=", 1) if "=" in a else (a.lstrip("-"), "") for a in args[3:])
stamp = "2026/10/22 12:00:00 extract.go:"

def say(text):
    sys.stdout.write(text)
    sys.stdout.flush()

def header():
    west, south, east, north = (float(v) for v in options["bbox"].split(",")) if "bbox" in options else (-180.0, -85.0, 180.0, 85.0)
    return b"PMTiles" + bytes([3]) + bytes(92) + struct.pack("<BB4i", 0, int(options["maxzoom"]), *(round(v * 1e7) for v in (west, south, east, north))) + bytes(9)

say(stamp + "401: fetching 3 dirs, 3 chunks, 1 requests\n")
say(stamp + "441: Region tiles 83211, result tile entries 41233\n")
say(stamp + "450: fetching 41233 tiles, 5000 chunks, 120 requests\n")
if mode == "nosize" and "dry-run" in options:
    sys.exit(0)
if "dry-run" in options:
    say(stamp + "606: Completed in 1.2s with 4 download threads (35 tiles/s).\n")
    say(stamp + "611: Extract required 124 total requests.\n")
    say(stamp + "612: Extract transferred 512 MB (overfetch 0.05) for an archive size of 493 MB\n")
    sys.exit(0)
data = header()
with open(target, "wb") as out:
    out.write(data[:60])
    bar = "fetching chunks {:3d}% |{:<10}| ({}/512 MB, 20 MB/s) [1s:1s]"
    if mode == "slow":
        say("\r" + bar.format(10, "#", 51))
        time.sleep(60)
        sys.exit(1)
    for percent in (0, 25, 50, 75):
        say("\r" + bar.format(percent, "#" * (percent // 10), percent * 5))
    if mode == "linger":
        time.sleep(1.2)
    if mode == "fail":
        say("\n" + "2026/10/22 12:00:01 main.go:229: Failed to extract, Get \"" + source + "\": connection refused\n")
        sys.exit(1)
    out.write(data[60:] + b"tiles" * 100)
say("\r" + bar.format(100, "#" * 10, 512) + "\n")
say(stamp + "606: Completed in 3.1s with 4 download threads (35 tiles/s).\n")
say(stamp + "612: Extract transferred 512 MB (overfetch 0.05) for an archive size of 493 MB\n")
'''


@dataclass(frozen=True)
class FakePmtiles:
    path: Path

    def mode(self, mode: str) -> None:
        (self.path.parent / "mode").write_text(mode)

    def calls(self) -> list[list[str]]:
        log = self.path.parent / "calls.jsonl"
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []

    def pid(self) -> int:
        return int((self.path.parent / "pid").read_text(encoding="utf-8"))


def install_fake(bin_dir: Path, name: str = "pmtiles") -> FakePmtiles:
    if os.name == "nt":
        pytest.skip("the pmtiles stand-in is a script with a shebang: POSIX only")
    bin_dir.mkdir(parents=True, exist_ok=True)
    program = bin_dir / name
    program.write_text(SCRIPT.replace("#!{python}", "#!" + sys.executable, 1))
    program.chmod(program.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return FakePmtiles(program)


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
