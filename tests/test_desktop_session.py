"""The app's decision to attach or own, against real daemons: with none running one is started detached (as `neoaprs open` does) and is the app's own, which Quit stops cleanly; one that is running already
(the service of the machine, one started by `neoaprs open`) is attached to and left running. The daemons are given a TCP radio on the loopback and a free page port first (tests/test_open_stop.py has the fixtures)."""
from pathlib import Path

from neoaprs import PROGRAM
from neoaprs.cli.daemonstate import is_running, page_answers
from neoaprs.desktop.session import open_session, stop_owned
from tests.test_open_stop import command, data, radio  # noqa: F401  (fixtures)


def test_with_no_daemon_the_app_starts_one_owns_it_and_stops_it_at_quit(data: Path) -> None:  # noqa: F811
    session = open_session(data, timeout=60)
    assert session.owned and is_running(data) and page_answers(session.url)
    assert stop_owned(session) and not is_running(data)
    log = (data / "neoaprs.log").read_text(encoding="utf-8")
    assert log.count(" starting, data in ") == 1 and log.rstrip().endswith(f"{PROGRAM} ended") and " ERROR " not in log


def test_a_daemon_that_runs_is_attached_to_and_survives_the_app(data: Path) -> None:  # noqa: F811
    assert command("open", "--data", str(data), "--no-browser", "--timeout", "60").returncode == 0
    session = open_session(data, timeout=60)
    assert not session.owned and page_answers(session.url)
    assert stop_owned(session) and is_running(data), "Quit does not stop a daemon the app did not start"
    assert (data / "neoaprs.log").read_text(encoding="utf-8").count(" starting, data in ") == 1, "no second daemon was started"
    assert command("stop", "--data", str(data)).returncode == 0 and not is_running(data)
