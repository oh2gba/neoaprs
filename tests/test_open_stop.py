"""`neoaprs open` and `neoaprs stop` and the stop file they stand on (neoaprs/stopfile.py): a daemon that is not running is started detached and its page answers, one that is running is left alone, the browser is
asked for the page's address, a daemon that cannot start is reported, and `stop` ends the daemon through the file in its data folder, cleanly. The detached daemons are given a TCP radio on the loopback and a free
page port in their database first (a daemon with neither would listen to the operator's serial ports and take port 7303)."""
import asyncio
import http.client
import http.server
import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from neoaprs import PROGRAM, stopfile
from neoaprs.cli import opencmd, stopcmd
from neoaprs.cli.daemonstate import SCAN_BYTES, is_running, page_address, page_answers, page_url
from neoaprs.cli.logfile import LAUNCH_NAME, LOG_NAME, PAGE_FILE, read_page, remove_page, write_page
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


# ---- where the page is

PAGE = "http://127.0.0.1:7303/"


def wait_until(condition: Callable[..., object], *args: object, seconds: float = 30.0) -> None:
    deadline = time.monotonic() + seconds
    while not condition(*args):
        assert time.monotonic() < deadline, "the condition did not come true"
        time.sleep(0.02)


def log_with_a_page(data: Path, lines_after: int) -> None:
    data.mkdir(parents=True, exist_ok=True)
    filler = "2026-10-22 12:00:30Z  INFO  beacon sent: OH2GBA-9>APOTC1,WIDE1-1:!6010.00N/02456.00E>\n" * lines_after
    (data / LOG_NAME).write_text(f"2026-10-22 12:00:00Z  INFO  NeoAPRS 0.14.0 starting, data in {data}\n2026-10-22 12:00:01Z  INFO  web page at {PAGE}\n{filler}", encoding="utf-8")


def test_the_address_the_daemon_wrote_is_found_however_long_the_log_has_grown_since(tmp_path: Path) -> None:
    log_with_a_page(tmp_path, 10)
    assert page_url(tmp_path) == PAGE, "(a short log has the line)"
    log_with_a_page(tmp_path, SCAN_BYTES // 80 + 100)
    assert page_url(tmp_path) is None, "(the line has scrolled out of what is read of the log)"
    write_page(tmp_path, "http://127.0.0.1:7305/")
    assert page_url(tmp_path) == "http://127.0.0.1:7305/" and read_page(tmp_path) == "http://127.0.0.1:7305/"
    remove_page(tmp_path)
    remove_page(tmp_path)                                                  # (nothing to take away is no error)
    assert read_page(tmp_path) is None and page_url(tmp_path) is None


@pytest.mark.parametrize("text", ["", "not an address", "http://", "https://127.0.0.1:7304/", "http://127.0.0.1:7303/ and more"])
def test_a_file_that_holds_no_address_is_no_address_and_the_log_is_looked_at(tmp_path: Path, text: str) -> None:
    log_with_a_page(tmp_path, 3)
    (tmp_path / PAGE_FILE).write_text(text + "\n", encoding="ascii")
    assert read_page(tmp_path) is None and page_url(tmp_path) == PAGE


def test_the_page_a_service_is_told_to_be_on_is_the_port_of_the_settings(data: Path) -> None:
    assert page_address(data.parent / "nothing") == "http://127.0.0.1:7303/", "(no database yet: the default)"
    assert page_address(data) == "(a free port: the log says which)", "(the fixture's web/port is 0)"
    assert command("db", "--data", str(data), "set", "web/port", "7411").returncode == 0
    assert page_address(data) == "http://127.0.0.1:7411/"


class Answer(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format: str, *args: object) -> None:
        return None


def test_the_page_of_the_daemon_is_asked_for_directly_whatever_proxy_the_environment_names(monkeypatch: pytest.MonkeyPatch) -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Answer)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        for name in ("http_proxy", "HTTP_PROXY", "all_proxy", "ALL_PROXY"):
            monkeypatch.setenv(name, "http://127.0.0.1:9")                  # (nothing listens there: a request that goes by the proxy fails)
        for name in ("no_proxy", "NO_PROXY"):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setattr("urllib.request._opener", None)
        assert page_answers(f"http://127.0.0.1:{server.server_address[1]}/")
    finally:
        server.shutdown()
        server.server_close()


def test_the_daemon_writes_its_page_into_the_data_folder_and_takes_it_away_at_a_clean_stop_and_says_each_warning_once(data: Path) -> None:
    opened = command("open", "--data", str(data), "--no-browser", "--timeout", "60")
    assert opened.returncode == 0, opened
    url = opened.stdout.strip()
    assert read_page(data) == url
    log_with_filler = data / LOG_NAME
    with log_with_filler.open("a", encoding="utf-8") as f:
        f.write("2026-10-22 12:00:30Z  INFO  beacon sent\n" * (SCAN_BYTES // 40))
    assert page_url(data) == url, "(the log has grown past what is read of it)"
    port = int(url.rsplit(":", 1)[1].rstrip("/"))

    def said(name: str) -> bool:
        return name in log_with_filler.read_text(encoding="utf-8")

    for name in ("first-evil.example", "second-evil.example"):
        link = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        link.request("GET", "/", headers={"Host": name})
        assert link.getresponse().status == 403
        link.close()
        wait_until(said, name)
    log = log_with_filler.read_text(encoding="utf-8")
    assert log.count("'first-evil.example' was refused") == 1 and log.count("'second-evil.example' was refused") == 1, "(a daemon that was started by a command did not write its stderr into the log)"
    launch = data / LAUNCH_NAME
    if sys.platform == "win32":
        assert not launch.exists(), "(a daemon without a console writes nothing before it has its log)"
    else:
        assert not [line for line in launch.read_text(encoding="utf-8").splitlines() if "was refused" in line]
    assert command("stop", "--data", str(data)).returncode == 0
    assert not (data / PAGE_FILE).exists()


def test_a_data_folder_that_cannot_be_used_is_one_sentence_and_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    afile = tmp_path / "afile"
    afile.write_text("not a folder")
    shown: list[str] = []
    monkeypatch.setattr(opencmd, "tell_the_user", lambda text: shown.append(text))
    assert opencmd.main(["--data", str(afile / "inside"), "--no-browser", "--timeout", "1"]) == 1
    assert len(shown) == 1 and "could not be started" in shown[0] and "Traceback" not in shown[0] and str(afile / "inside") in shown[0]
