"""`neoaprs open` and `neoaprs stop` and the stop file they stand on (neoaprs/stopfile.py): a daemon that is not running is started detached and its page answers, one that is running is left alone, the browser is
asked for the page's address, a daemon that cannot start is reported, and `stop` ends the daemon through the file in its data folder, cleanly. The detached daemons are given a TCP radio on the loopback and a free
page port in their database first (a daemon with neither would listen to the operator's serial ports and take port 7303)."""
import asyncio
import os
import socket
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from neoaprs import PROGRAM, stopfile
from neoaprs.cli import opencmd, stopcmd
from neoaprs.cli.daemonstate import is_running, page_answers, page_url
from tests.conftest import ROOT
from tests.support.env import idle_for
from tests.support.proc import NEW_GROUP


def environment() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in ("NEOAPRS_DATA_DIR", "NEOAPRS_DEBUG")}


def command(*args: str, timeout: float = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "neoaprs", *args], cwd=ROOT, env=environment(), capture_output=True, text=True, timeout=timeout, creationflags=NEW_GROUP)


@pytest.fixture
def radio() -> Iterator[str]:
    """A TCP server on the loopback that accepts and says nothing: a radio for a daemon that nobody started in the test itself."""
    server = socket.create_server(("127.0.0.1", 0))
    held: list[socket.socket] = []

    def accept() -> None:
        while True:
            try:
                held.append(server.accept()[0])
            except OSError:
                return

    threading.Thread(target=accept, daemon=True).start()
    yield f"socket://127.0.0.1:{server.getsockname()[1]}"
    server.close()
    for client in held:
        client.close()


@pytest.fixture
def data(tmp_path: Path, radio: str) -> Iterator[Path]:
    """A data folder whose settings give the daemon the fake radio and a free page port; the daemon, if the test left one running, is stopped."""
    folder = tmp_path / "data"
    assert command("db", "--data", str(folder), "set", "serial/port", radio).returncode == 0
    assert command("db", "--data", str(folder), "set", "web/port", "0").returncode == 0
    yield folder
    if is_running(folder):
        command("stop", "--data", str(folder), "--timeout", "30")


def test_the_stop_file_is_asked_for_seen_and_taken_away(tmp_path: Path) -> None:
    assert not stopfile.requested(tmp_path)
    stopfile.request(tmp_path)
    assert stopfile.requested(tmp_path) and (tmp_path / "neoaprs.stop").is_file()
    stopfile.clear(tmp_path)
    stopfile.clear(tmp_path)                                               # (nothing to take away is no error)
    assert not stopfile.requested(tmp_path)


async def test_the_watch_ends_the_run_when_the_file_appears_and_deletes_it(tmp_path: Path) -> None:
    stop = asyncio.Event()
    watching = asyncio.create_task(stopfile.watch(tmp_path, stop, poll_sec=0.01))
    await idle_for(0.05)
    assert not stop.is_set()
    stopfile.request(tmp_path)
    await asyncio.wait_for(stop.wait(), 5)
    await asyncio.wait_for(watching, 5)
    assert not stopfile.requested(tmp_path)


def test_stop_with_no_daemon_says_so_and_clears_a_request_that_was_left(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    stopfile.request(tmp_path)
    assert stopcmd.main(["--data", str(tmp_path)]) == 0
    assert "not running" in capsys.readouterr().err and not stopfile.requested(tmp_path)
    assert stopcmd.main(["--data", str(tmp_path / "never-made")]) == 0


def test_open_starts_a_detached_daemon_once_and_stop_ends_it_cleanly(data: Path) -> None:
    first = command("open", "--data", str(data), "--no-browser", "--timeout", "60")
    assert first.returncode == 0, first
    url = first.stdout.strip()
    assert url.startswith("http://127.0.0.1:") and page_answers(url) and is_running(data) and page_url(data) == url
    again = command("open", "--data", str(data), "--no-browser", "--timeout", "60")
    assert again.returncode == 0 and again.stdout.strip() == url
    log = (data / "neoaprs.log").read_text(encoding="utf-8")
    assert log.count(" starting, data in ") == 1, "the second open found the daemon and started no other"
    done = command("stop", "--data", str(data))
    assert done.returncode == 0 and "has ended" in done.stderr, done
    assert not is_running(data) and not stopfile.requested(data)
    log = (data / "neoaprs.log").read_text(encoding="utf-8")
    assert log.rstrip().endswith(f"{PROGRAM} ended") and " ERROR " not in log
    assert "not running" in command("stop", "--data", str(data)).stderr


def test_a_stop_request_left_in_the_folder_does_not_end_the_next_daemon(data: Path) -> None:
    data.mkdir(parents=True, exist_ok=True)
    stopfile.request(data)
    opened = command("open", "--data", str(data), "--no-browser", "--timeout", "60")
    assert opened.returncode == 0, opened
    assert is_running(data) and not stopfile.requested(data)


def test_open_asks_the_browser_for_the_address_the_daemon_logged(data: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    assert command("open", "--data", str(data), "--no-browser").returncode == 0
    url = page_url(data)
    assert url is not None
    asked: list[str] = []
    monkeypatch.setattr(opencmd.webbrowser, "open", lambda address: asked.append(address) or True)
    assert opencmd.main(["--data", str(data)]) == 0
    assert asked == [url] and capsys.readouterr().out.strip() == url
    monkeypatch.setattr(opencmd.webbrowser, "open", lambda address: False)
    assert opencmd.main(["--data", str(data)]) == 0
    assert f"open {url} yourself" in capsys.readouterr().err


def test_open_reports_a_daemon_that_ends_before_its_page_is_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(opencmd, "daemon_argv", lambda data: [sys.executable, "-c", "raise SystemExit(3)"])
    shown: list[str] = []
    monkeypatch.setattr(opencmd, "tell_the_user", lambda text: shown.append(text))
    assert opencmd.main(["--data", str(tmp_path / "data"), "--no-browser", "--timeout", "30"]) == 1
    assert len(shown) == 1 and "exit code 3" in shown[0] and str(tmp_path / "data" / "neoaprs.log") in shown[0]


def test_open_gives_up_when_no_page_comes_in_time(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(opencmd, "daemon_argv", lambda data: [sys.executable, "-c", "import time; time.sleep(30)"])
    shown: list[str] = []
    monkeypatch.setattr(opencmd, "tell_the_user", lambda text: shown.append(text))
    spawned: list["subprocess.Popen[bytes]"] = []
    real = opencmd.spawn
    monkeypatch.setattr(opencmd, "spawn", lambda argv, data: spawned.append(real(argv, data)) or spawned[-1])
    try:
        assert opencmd.main(["--data", str(tmp_path / "data"), "--no-browser", "--timeout", "1"]) == 1
    finally:
        for child in spawned:
            child.kill()
            child.wait()
    assert len(shown) == 1 and "no page within 1 s" in shown[0]


def test_the_commands_are_known_to_the_neoaprs_command() -> None:
    from neoaprs import cli
    assert "open" in cli.COMMANDS and "stop" in cli.COMMANDS and cli.HANDLERS["open"] is cli._open and cli.HANDLERS["stop"] is cli._stop
