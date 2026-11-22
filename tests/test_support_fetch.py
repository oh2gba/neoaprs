"""`server/support-fetch.sh` with a secrets manager stand-in and a curl stand-in that serves a
made-up folder: a bundle is fetched as zip and json, a note sent alone as json only.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.support.ptyline import posix_only

pytestmark = posix_only

ROOT = Path(__file__).resolve().parent.parent
BUNDLE, NOTE = "NEO-20261116-1015-7F3A", "NEO-20261116-1020-0B1C"
BWS = """#!/usr/bin/env bash
echo '[{"key":"ftp_server","value":"host.invalid"},{"key":"ftp_login","value":"user-made-up"},{"key":"ftp_pw","value":"made-up-for-this-test"}]'
"""
CURL = """#!/usr/bin/env bash
# the last argument is the address; -o names the file to write: a folder is listed as sftp lists it, a file is copied from $REMOTE_DIR
out=""; url=""
while [ $# -gt 0 ]; do
  case "$1" in -o) out="$2"; shift ;; sftp://*) url="$1" ;; esac
  shift
done
echo "$url" >> "$CURL_ASKED"
name="${url##*/}"
if [ -z "$name" ]; then
  for f in "$REMOTE_DIR"/*; do echo "-rw------- 1 u g 10 Nov 16 10:15 $(basename "$f")"; done
elif [ -f "$REMOTE_DIR/$name" ]; then
  cp "$REMOTE_DIR/$name" "$out"
else
  echo "curl: (78) no such file" >&2; exit 78
fi
"""


@pytest.fixture
def served(tmp_path: Path) -> dict[str, Path]:
    """The script in a folder of its own, the server's folder with a bundle and a note alone, and
    the stand-ins."""
    script = tmp_path / "checkout" / "server" / "support-fetch.sh"
    script.parent.mkdir(parents=True)
    shutil.copy(ROOT / "server" / "support-fetch.sh", script)
    remote = tmp_path / "remote"
    remote.mkdir()
    (remote / f"{BUNDLE}.zip").write_bytes(b"PK" + b"x" * 4096)
    (remote / f"{BUNDLE}.json").write_text(
        json.dumps(
            {
                "ref": BUNDLE,
                "time": "2026-11-16T10:15:00Z",
                "call": "OH2GBA",
                "version": "0.20.1",
                "platform": "linux",
                "file": True,
                "size": 4098,
                "note": "It stopped.",
            }
        ),
        encoding="utf-8",
    )
    (remote / f"{NOTE}.json").write_text(
        json.dumps(
            {
                "ref": NOTE,
                "time": "2026-11-16T10:20:00Z",
                "call": "OH2GAX",
                "version": "0.20.1",
                "platform": "win32",
                "file": False,
                "size": 0,
                "note": "Thanks for the HF mode.",
            }
        ),
        encoding="utf-8",
    )
    (remote / "rate.json").write_text("{}", encoding="utf-8")
    tools = tmp_path / "tools"
    tools.mkdir()
    for name, text in (("bws", BWS), ("curl", CURL)):
        (tools / name).write_text(text, encoding="utf-8")
        (tools / name).chmod(0o755)
    (tmp_path / "token.txt").write_text("made-up-for-this-test\n", encoding="utf-8")
    return {
        "script": script,
        "remote": remote,
        "tools": tools,
        "asked": tmp_path / "asked.txt",
        "local": script.parent / "support",
    }


def run(served: dict[str, Path], *args: str) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    served["asked"].unlink(missing_ok=True)
    env = {
        "PATH": f"{served['tools']}:{os.environ['PATH']}",
        "HOME": str(served["tools"].parent),
        "SECRETS_FILE": str(served["tools"].parent / "token.txt"),
        "BWS": str(served["tools"] / "bws"),
        "REMOTE_DIR": str(served["remote"]),
        "CURL_ASKED": str(served["asked"]),
    }
    done = subprocess.run(["bash", str(served["script"]), *args], capture_output=True, text=True, env=env, timeout=60)
    return done, [
        line.rsplit("/", 1)[1] for line in served["asked"].read_text(encoding="utf-8").splitlines()
    ] if served["asked"].exists() else []


def test_a_bundle_comes_as_its_zip_and_json_and_a_note_alone_as_its_json_with_no_zip_asked_for(
    served: dict[str, Path],
) -> None:
    done, asked = run(served)
    assert done.returncode == 0, done.stderr
    assert sorted(p.name for p in served["local"].iterdir()) == [f"{BUNDLE}.json", f"{BUNDLE}.zip", f"{NOTE}.json"]
    assert f"{NOTE}.zip" not in asked and sorted(a for a in asked if a) == [
        f"{BUNDLE}.json",
        f"{BUNDLE}.zip",
        f"{NOTE}.json",
    ]
    lines = done.stdout.splitlines()
    assert (
        any(BUNDLE in line and "OH2GBA" in line and line.endswith("4 KB") for line in lines)
        and "      It stopped." in lines
    )
    assert (
        any(NOTE in line and "OH2GAX" in line and line.endswith("no file") for line in lines)
        and "      Thanks for the HF mode." in lines
    )
    assert lines[-1] == "2 new, 2 on the server in all"


def test_neither_is_fetched_twice(served: dict[str, Path]) -> None:
    assert run(served)[0].returncode == 0
    done, asked = run(served)
    assert done.returncode == 0 and asked == [""] and done.stdout.splitlines() == ["0 new, 2 on the server in all"], (
        "only the folder was listed"
    )


def test_the_list_shows_both_and_keeps_nothing(served: dict[str, Path]) -> None:
    done, asked = run(served, "--list")
    assert done.returncode == 0, done.stderr
    assert (
        done.stdout.count("new:") == 2
        and "no file" in done.stdout
        and "4 KB" in done.stdout
        and not any(a.endswith(".zip") for a in asked)
    )
    assert list(served["local"].iterdir()) == []
    assert run(served)[0].returncode == 0
    done, _ = run(served, "--list")
    assert done.stdout.count("here:") == 2 and "new:" not in done.stdout


def test_a_json_of_before_that_does_not_say_is_a_bundle(served: dict[str, Path]) -> None:
    path = served["remote"] / f"{BUNDLE}.json"
    meta = json.loads(path.read_text(encoding="utf-8"))
    del meta["file"]
    path.write_text(json.dumps(meta), encoding="utf-8")
    done, asked = run(served)
    assert done.returncode == 0 and f"{BUNDLE}.zip" in asked and (served["local"] / f"{BUNDLE}.zip").is_file()
