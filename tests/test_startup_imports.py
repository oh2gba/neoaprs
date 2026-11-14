"""What the program imports before it does its work (`python -X importtime`, which lists every module as it is loaded): the command line's short commands `--version` and `--help` import neither the web server nor
its libraries, and a plain start of the daemon, up to the line in the log that says it is running, does not import the certificates' library, the code of the secure connection or the modules that write the support bundle.
A daemon started with --encryption makes its message key at once, so there the library is loaded: the test says so, so that the lazy import is known to be only for a daemon that has no use for it."""
import subprocess
import sys
from pathlib import Path

import pytest

from neoaprs import PROGRAM
from tests.conftest import ROOT
from tests.support.proc import NEW_GROUP, stop
from tests.test_main import ended, environment, wait_for

# what only the daemon needs: the page's server and the libraries of its messages
WEB = ("tornado", "pydantic", "pydantic_core", "cryptography", "neoaprs.web", "neoaprs.controller", "neoaprs.app", "neoaprs.config")
# what a daemon without https and without a support bundle does not need before it listens
NOT_YET = ("cryptography", "neoaprs.web.tls", "neoaprs.cli.supportmake", "neoaprs.cli.supportgather", "neoaprs.cli.supportbundle", "neoaprs.cli.supportsummary", "neoaprs.cli.supportreadme", "neoaprs.cli.doctor")


def environment_of_a_start() -> dict[str, str]:
    return {**environment(), "NEOAPRS_NO_DEVICES": "1", "NEOAPRS_UPDATE_CHECK": "0"}


def modules_of(importtime: str) -> set[str]:
    """The names of the modules that `-X importtime` (on stderr) lists."""
    return {line.rsplit("|", 1)[1].strip() for line in importtime.splitlines() if line.startswith("import time:") and "|" in line}


def loaded(modules: set[str], names: tuple[str, ...]) -> list[str]:
    """Which of `names` are among the modules, as themselves or as a package of one."""
    return sorted(name for name in names if any(m == name or m.startswith(name + ".") for m in modules))


@pytest.mark.parametrize("flag", ["--version", "--help"])
def test_the_short_commands_do_not_import_the_web_server_or_its_libraries(flag: str) -> None:
    done = subprocess.run([sys.executable, "-X", "importtime", "-m", "neoaprs", flag], cwd=ROOT, env=environment_of_a_start(), capture_output=True, text=True, encoding="utf-8", check=True)
    assert PROGRAM in done.stdout if flag == "--version" else "commands (" in done.stdout
    assert loaded(modules_of(done.stderr), WEB) == []


def run_until_listening(data: Path, *extra: str) -> set[str]:
    """The modules a daemon has loaded when its log says it is running. The listing goes to a file, not to a pipe: it is tens of thousands of bytes written before the daemon does anything, a pipe nobody
    reads holds 4 KB on Windows, and a daemon that waits to write its listing never starts (the Windows test machine, 14 November 2026)."""
    data.parent.mkdir(parents=True, exist_ok=True)
    listing = data.parent / "importtime.txt"
    with listing.open("w", encoding="utf-8", errors="replace") as err:
        proc = subprocess.Popen([sys.executable, "-X", "importtime", "-m", "neoaprs", "--data", str(data), "--web-port", "0", *extra], cwd=ROOT, env=environment_of_a_start(), stdout=subprocess.DEVNULL, stderr=err,
                                text=True, encoding="utf-8", errors="replace", creationflags=NEW_GROUP)
        wait_for(data / "neoaprs.log", f"{PROGRAM} is running", proc)
        stop(proc)
        ended(proc, data)
    written = listing.read_text(encoding="utf-8", errors="replace")
    assert proc.returncode == 0, written[-2000:]
    return modules_of(written)


def test_a_plain_start_of_the_daemon_does_not_import_the_certificates_library_or_the_support_bundle(tmp_path: Path) -> None:
    modules = run_until_listening(tmp_path / "data")
    assert "neoaprs.web.server" in modules and "tornado" in modules, "the listing is of the daemon"
    assert loaded(modules, NOT_YET) == []


def test_a_daemon_started_with_encryption_loads_the_library_at_once_for_its_key(tmp_path: Path) -> None:
    modules = run_until_listening(tmp_path / "data", "--encryption")
    assert loaded(modules, ("cryptography",)) == ["cryptography"]
    assert loaded(modules, tuple(n for n in NOT_YET if n != "cryptography")) == []
