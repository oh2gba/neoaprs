"""The page's port across a restart of the daemon (daemon.py `kept_port`, the `neoaprs.restart-port`
note of stopfile.py, web/listen.py): a daemon that ends to be restarted says where its page is, and
the one that starts in its place serves it there. A start that is no restart listens as usual.
"""

import argparse
import asyncio
import logging
import os
import socket
from collections.abc import Awaitable, Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from neoaprs import VERSION, app, stopfile
from neoaprs import daemon as entry
from neoaprs.cli import dbcmd
from neoaprs.cli.logfile import LOG_NAME, page_of_the_run_before, read_page
from neoaprs.controller import Controller
from tests.support.daemonrun import PATIENCE_SEC, log_text, signals_restored as signals_restored
from tests.support.env import until
from tests.test_main import taken_ports
from tests.test_scripts import load_script
from tests.test_scripts_on_the_daemon import closed

Serve = Callable[[Controller, asyncio.Event, logging.Logger], Awaitable[int]]


def port_of(url: str | None) -> int:
    assert url is not None
    return int(url.rstrip("/").rsplit(":", 1)[1])


class Daemons:
    """The daemons of one data folder, one after the other: `start(*flags)` runs one until its page
    is served and gives the port; `restart()` ends it as Update now of an AppImage does (the note,
    then the stop) and gives the command line it handed back; `stop()` ends it as `neoaprs stop`
    does. A daemon that has ended leaves the log as its process would: the handlers it added are
    taken away, so that the next one writes each line once."""

    def __init__(self, data: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.data = data
        self.handlers = list(logging.getLogger().handlers)
        self.controllers: list[Controller] = []
        self.task: asyncio.Task[int] | None = None
        self.after: list[list[str]] = []
        serve: Serve = entry._serve

        async def kept(controller: Controller, stop: asyncio.Event, log: logging.Logger) -> int:
            self.controllers.append(controller)
            return await serve(controller, stop, log)

        monkeypatch.setattr(entry, "_serve", kept)

    def arguments(self, *flags: str) -> argparse.Namespace:
        return entry.build_parser().parse_args(["--data", str(self.data), *flags])

    async def start(self, *flags: str) -> int:
        self.after = []
        task = self.task = asyncio.ensure_future(entry.run(self.arguments(*flags), self.after))
        runs = log_text(self.data).count("is running")
        await until(
            lambda: (
                task.done() or (log_text(self.data).count("is running") > runs and read_page(self.data) is not None)
            ),
            PATIENCE_SEC,
        )
        assert not task.done(), log_text(self.data)[-2000:]
        return port_of(read_page(self.data))

    async def restart(self, argv: list[str]) -> list[list[str]]:
        self.controllers[-1].restart_into(argv)
        self.controllers[-1]._end_for_restart()
        await self.ended()
        return self.after

    async def stop(self) -> None:
        stopfile.request(self.data)
        await self.ended()

    async def ended(self) -> None:
        assert self.task is not None
        assert await asyncio.wait_for(self.task, PATIENCE_SEC) == 0
        for handler in logging.getLogger().handlers[:]:
            if handler not in self.handlers:
                logging.getLogger().removeHandler(handler)
                handler.close()


@pytest.fixture
def daemons(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, signals_restored: None) -> Daemons:
    return Daemons(tmp_path / "data", monkeypatch)


# ---- the daemon
@pytest.mark.slow("starts the daemon, a script or pytest as a process of its own")
async def test_a_daemon_on_a_fallback_port_starts_again_on_that_port_though_the_port_it_asked_for_is_free_by_then(
    daemons: Daemons,
) -> None:
    with taken_ports(1) as taken:
        port = await daemons.start("--web-port", str(taken))
        assert taken < port <= taken + 10, "the port it asked for was taken: the page is on one of the ten after it"
        image = ["/home/ham/NeoAPRS.AppImage", "run", "--data", str(daemons.data), "--web-port", str(taken)]
        assert await daemons.restart(image) == [image], "the same arguments: nothing of the port is in them"
        assert (
            (daemons.data / stopfile.PORT_NAME).read_text(encoding="ascii") == f"{port}\n"
            and stopfile.restarting(daemons.data)
            and read_page(daemons.data) is None
        )
    assert await daemons.start("--web-port", str(taken)) == port, (
        "the port it asked for is free now, and the pages that are open wait on the other"
    )
    assert f"the page stays on port {port}, where it was before the restart" in log_text(daemons.data)
    assert not (daemons.data / stopfile.PORT_NAME).exists() and not (daemons.data / stopfile.RESTART_NAME).exists(), (
        "read once: the notes go when the daemon runs"
    )
    await daemons.stop()
    assert await daemons.start("--web-port", str(taken)) == taken, (
        "a start that is no restart listens where it is told, as it always did"
    )
    await daemons.stop()


@pytest.mark.slow("starts the daemon, a script or pytest as a process of its own")
async def test_a_daemon_on_the_port_of_its_settings_or_of_its_flag_starts_again_there(daemons: Daemons) -> None:
    # Two neighbouring ports that are free once the block ends: one for the settings, one for the
    # flag
    with taken_ports(2) as free:
        pass
    assert await asyncio.to_thread(dbcmd.main, ["--data", str(daemons.data), "set", "web/port", str(free)]) == 0
    assert await daemons.start() == free, "the settings' port"
    await daemons.restart(["/home/ham/NeoAPRS.AppImage", "run", "--data", str(daemons.data)])
    assert await daemons.start() == free
    assert "where it was before the restart" not in log_text(daemons.data), (
        "it is the port of the settings: nothing to say"
    )
    await daemons.stop()
    assert await daemons.start("--web-port", str(free + 1)) == free + 1, "--web-port"
    await daemons.restart(
        ["/home/ham/NeoAPRS.AppImage", "run", "--data", str(daemons.data), "--web-port", str(free + 1)]
    )
    assert await daemons.start("--web-port", str(free + 1)) == free + 1
    await daemons.stop()
    assert (
        await asyncio.to_thread(dbcmd.main, ["--data", str(daemons.data), "get", "web/port"]) == 0
        and read_page(daemons.data) is None
    )


@pytest.mark.slow("starts the daemon, a script or pytest as a process of its own")
async def test_a_daemon_on_a_free_port_starts_again_on_the_port_it_was_given(daemons: Daemons) -> None:
    port = await daemons.start("--web-port", "0")
    await daemons.restart(["/home/ham/NeoAPRS.AppImage", "run", "--data", str(daemons.data), "--web-port", "0"])
    assert await daemons.start("--web-port", "0") == port, (
        "--web-port 0 is a free port at the first start, and the port of the open pages at a restart"
    )
    await daemons.stop()


@pytest.mark.slow("starts the daemon, a script or pytest as a process of its own")
async def test_a_port_of_before_the_restart_that_is_taken_by_then_does_not_keep_the_daemon_from_its_page(
    daemons: Daemons,
) -> None:
    with taken_ports(1) as taken:
        port = await daemons.start("--web-port", str(taken))
        await daemons.restart(
            ["/home/ham/NeoAPRS.AppImage", "run", "--data", str(daemons.data), "--web-port", str(taken)]
        )
    # Another program has the port the page was on by the time the daemon starts again
    with socket.socket() as holder:
        try:
            holder.bind(("127.0.0.1", port))
            holder.listen()
        except OSError:
            pytest.skip("the port of the first run was taken by another program meanwhile")
        assert await daemons.start("--web-port", str(taken)) == taken, "as at any start: the port it was told"
    assert f"port {port}, where the page was before the restart, cannot be had" in log_text(daemons.data)
    await daemons.stop()


@pytest.mark.slow("starts the daemon, a script or pytest as a process of its own")
async def test_the_daemon_that_starts_in_the_place_of_one_of_0_20_1_finds_its_port_in_the_log(daemons: Daemons) -> None:
    """An older daemon leaves the restart note and no port, and removes the page's file as it ends:
    only the log has its port."""
    with taken_ports(1) as taken:
        port = await daemons.start("--web-port", str(taken))
        daemons.controllers[-1].reexec = ["/home/ham/NeoAPRS.AppImage", "run"]
        # As the older daemon wrote it.
        stopfile.mark_restart(daemons.data)
        daemons.controllers[-1]._end_for_restart()
        await daemons.ended()
    assert stopfile.restarting(daemons.data) and not (daemons.data / stopfile.PORT_NAME).exists()
    assert await daemons.start("--web-port", str(taken)) == port
    await daemons.stop()


# ---- the note and the log, read
def log_of(data: Path, *lines: str) -> None:
    data.mkdir(exist_ok=True)
    (data / LOG_NAME).write_text("".join(f"2026-11-16 08:00:00Z  INFO  {line}\n" for line in lines), encoding="utf-8")


def test_the_page_of_the_run_before_is_the_last_page_line_before_the_last_start_and_of_no_earlier_run(
    tmp_path: Path,
) -> None:
    assert page_of_the_run_before(tmp_path) is None, "no log"
    start, page, end = "NeoAPRS 0.20.1 starting, data in /d", "web page at http://127.0.0.1:%d/", "NeoAPRS ended"
    log_of(tmp_path, start)
    assert page_of_the_run_before(tmp_path) is None, "the first run of the folder"
    log_of(tmp_path, start, page % 7304, "NeoAPRS is running", end, start)
    assert page_of_the_run_before(tmp_path) == "http://127.0.0.1:7304/"
    log_of(tmp_path, start, page % 7304, end, start, page % 7303)
    assert page_of_the_run_before(tmp_path) == "http://127.0.0.1:7304/", "asked after this run's page line too"
    log_of(tmp_path, start, page % 7304, end, start, "the web server cannot listen on 127.0.0.1:7303", end, start)
    assert page_of_the_run_before(tmp_path) is None, "the run before had no page: the one before that is not asked"
    log_of(tmp_path, page % 7304, "NeoAPRS is running")
    assert page_of_the_run_before(tmp_path) is None, "a log without this run's start line"


def test_the_port_that_is_kept_is_the_notes_or_for_an_older_note_the_logs_and_none_without_a_fresh_note(
    tmp_path: Path,
) -> None:
    log_of(
        tmp_path,
        "NeoAPRS 0.20.1 starting, data in /d",
        "web page at http://127.0.0.1:7304/",
        "NeoAPRS ended",
        "NeoAPRS 0.20.2 starting, data in /d",
    )
    assert entry.kept_port(tmp_path) == 0, "no note: this start is no restart, whatever the log says"
    stopfile.note_port(tmp_path, 7310)
    assert entry.kept_port(tmp_path) == 7310, (
        "the note's, with no note of a restart beside it too (the Windows installer starts the daemon)"
    )
    stopfile.mark_restart(tmp_path)
    assert entry.kept_port(tmp_path) == 7310
    stopfile.note_port(tmp_path, 0)
    assert entry.kept_port(tmp_path) == 7304, "the restart of 0.20.1, which noted no port: the log's"
    log_of(tmp_path, "NeoAPRS 0.20.1 starting, data in /d", "NeoAPRS ended", "NeoAPRS 0.20.2 starting, data in /d")
    assert entry.kept_port(tmp_path) == 0, "that daemon had no page"
    note = tmp_path / stopfile.RESTART_NAME
    log_of(
        tmp_path,
        "NeoAPRS 0.20.1 starting, data in /d",
        "web page at http://127.0.0.1:7304/",
        "NeoAPRS ended",
        "NeoAPRS 0.20.2 starting, data in /d",
    )
    assert entry.kept_port(tmp_path) == 7304
    old = note.stat().st_mtime - stopfile.RESTART_FRESH_SEC - 5
    os.utime(note, (old, old))
    assert entry.kept_port(tmp_path) == 0, (
        "a note that is not fresh is of a restart that did not come up: the log is not asked"
    )


def test_only_a_whole_line_the_daemon_said_itself_names_the_page_of_the_run_before(tmp_path: Path) -> None:
    """The log also holds what others sent (a packet's text in a warning): the words of a page line
    or of a start line inside another line name no port and start no run, and neither does an
    address that is not the page's own on this computer."""
    start, page, end = "NeoAPRS 0.20.1 starting, data in /d", "web page at http://127.0.0.1:7304/", "NeoAPRS ended"

    def lines(*more: str) -> None:
        tmp_path.joinpath(LOG_NAME).write_text(
            "".join(
                f"2026-11-16 08:00:00Z  {line}\n"
                for line in (f"INFO  {start}", f"INFO  {page}", *more, f"INFO  {end}", f"INFO  {start}")
            ),
            encoding="utf-8",
        )

    stopfile.mark_restart(tmp_path)
    for more in (
        "WARNING  OH2XYZ>APRS: a packet that says web page at http://127.0.0.1:4444/ and more",
        "INFO  heard: web page at http://127.0.0.1:4444/",
        "WARNING  web page at http://127.0.0.1:4444/",
        "INFO  web page at http://example.org:81/",
        "INFO  web page at http://127.0.0.1:80@example.org/",
        "INFO  web page at http://127.0.0.1:4444/x/",
        "INFO  a text with  starting, data in  inside",
        "INFO   web page at http://127.0.0.1:4444/",
    ):
        lines(more)
        assert page_of_the_run_before(tmp_path) == "http://127.0.0.1:7304/" and entry.kept_port(tmp_path) == 7304, more
    lines("INFO  web page at http://127.0.0.1:99999/")
    assert entry.kept_port(tmp_path) == 0, "a number that is no port"
    tmp_path.joinpath(LOG_NAME).write_bytes(
        f"2026-11-16 08:00:00Z  INFO  {start}\r\n2026-11-16 08:00:01Z  INFO  {page}\r\n2026-11-16 08:09:00Z  INFO  {start}\r\n".encode()
    )
    assert page_of_the_run_before(tmp_path) == "http://127.0.0.1:7304/", "the line ends of Windows"


@pytest.mark.slow("starts the daemon, a script or pytest as a process of its own")
async def test_a_note_of_a_restart_that_never_came_pins_no_port(daemons: Daemons) -> None:
    """The note is believed for a quarter of an hour and read by one start: an old one (the
    installer never ended the daemon, the computer was switched off in the middle) is passed over
    and taken away by the daemon that runs, and a fresh one is used by the first start and by no
    later one. A daemon that is stopped, by `neoaprs stop` or a service manager, leaves none."""
    with taken_ports(2) as free:
        pass
    daemons.data.mkdir()
    note = daemons.data / stopfile.PORT_NAME
    stopfile.note_port(daemons.data, free + 1)
    old = note.stat().st_mtime - stopfile.PORT_FRESH_SEC - 5
    os.utime(note, (old, old))
    assert await daemons.start("--web-port", str(free)) == free, "an old note: the port it is told"
    assert not note.exists(), "and the note is gone once the daemon runs"
    await daemons.stop()
    assert not note.exists() and not (daemons.data / stopfile.RESTART_NAME).exists(), (
        "a stop is no restart: nothing is left for the next start"
    )
    assert await daemons.start("--web-port", str(free)) == free
    # Written while the daemon runs, as before an installer that then never ends it
    stopfile.note_port(daemons.data, free + 1)
    await daemons.stop()
    assert await daemons.start("--web-port", str(free)) == free + 1, (
        "the start within the quarter of an hour is on the port the pages wait on"
    )
    await daemons.stop()
    assert await daemons.start("--web-port", str(free)) == free, "and no start after it"
    await daemons.stop()


async def test_a_note_that_names_a_port_the_daemon_may_not_have_is_passed_over(daemons: Daemons) -> None:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", 1))
        except OSError:
            pass
        else:
            pytest.skip("this user may have port 1 (the superuser, a system that keeps no ports for it)")
    with taken_ports(1) as free:
        pass
    daemons.data.mkdir()
    stopfile.note_port(daemons.data, 1)
    assert await daemons.start("--web-port", str(free)) == free
    assert "port 1, where the page was before the restart, cannot be had" in log_text(daemons.data)
    await daemons.stop()


# ---- the end-to-end test's own reading of it
@pytest.mark.slow("starts the daemon, a script or pytest as a process of its own")
async def test_the_update_test_finds_the_page_beside_the_port_it_holds_and_the_same_page_after_the_restart(
    daemons: Daemons,
) -> None:
    """scripts/update-e2e.py holds the port of the settings while the old version starts, finds its
    page on a later port, lets go of the port and finds the new version's page: here with the daemon
    of this tree in the place of both versions (the real files are the release workflow's to run).
    """
    e2e = load_script("update-e2e.py")
    holder, held = e2e.held_port()
    try:
        port = await daemons.start("--web-port", str(held))
        page, found = await e2e.Page.among(range(held + 1, held + e2e.PORT_TRIES + 1), VERSION, 30)
        assert found == port == held + 1 and page.hello["version"] == VERSION
        await closed(page.connection)
        await daemons.restart(
            ["/home/ham/NeoAPRS.AppImage", "run", "--data", str(daemons.data), "--web-port", str(held)]
        )
    finally:
        holder.close()
    assert await daemons.start("--web-port", str(held)) == port
    page, found = await e2e.Page.among(range(held, held + e2e.PORT_TRIES + 1), VERSION, 30)
    await closed(page.connection)
    install = e2e.AppImageInstall(
        daemons.data.parent / "work",
        Path(f"NeoAPRS-{VERSION}-x86_64.AppImage"),
        Path("NeoAPRS-9.9.9-x86_64.AppImage"),
        False,
    )
    e2e.check_port(install, held, port, found, VERSION)
    await daemons.stop()
    # Hold the three ports (bound, not listening) so that no other test's daemon can answer on them.
    shut = [socket.socket() for _ in range(3)]
    try:
        try:
            for offset, sock in enumerate(shut):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", held + offset))
        except OSError:
            pytest.skip("another program took one of the ports: the refusals cannot be shown on them")
        with pytest.raises(e2e.Failure, match=f"no daemon of {VERSION} on the ports {held} to {held + 2} within"):
            await e2e.Page.among(range(held, held + 3), VERSION, 0.5)
        with pytest.raises(e2e.Failure, match="the program ended"):
            await e2e.Page.among(range(held, held + 3), VERSION, 30, alive=lambda: False)
    finally:
        for sock in shut:
            sock.close()


# ---- the note, written
async def test_the_daemon_notes_its_page_for_the_restart_of_an_appimage_and_for_the_windows_installer_alike(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    handed: dict[str, object] = {}

    def installer(install: object, data_dir: Path, restart: object, **more: object) -> None:
        handed.update(more, restart=restart)

    monkeypatch.setattr(app, "installer_for", installer)
    services = app.Services(tmp_path)
    assert handed["restart"] == services.restart_into and handed["leaving"] == services.note_page_port, (
        "the AppImage's way restarts through the one, the Windows installer's way calls the other before it starts"
    )
    note = tmp_path / stopfile.PORT_NAME
    services.note_page_port()
    assert not note.exists(), "a daemon without a page has no port to keep"
    services.web = SimpleNamespace(bound_port=lambda: 7304)  # type: ignore[assignment]
    services.note_page_port()
    assert note.read_text(encoding="ascii") == "7304\n" and services.reexec is None, (
        "the installer ends the daemon: nothing is run in its place"
    )
    assert not stopfile.restarting(tmp_path), (
        "and the app there is ended by the installer: it is given no restart to wait for"
    )
    services.web = SimpleNamespace(bound_port=lambda: 7305)  # type: ignore[assignment]
    services.restart_into(["/home/ham/NeoAPRS.AppImage", "run"])
    assert (
        note.read_text(encoding="ascii") == "7305\n"
        and stopfile.restarting(tmp_path)
        and services.reexec == ["/home/ham/NeoAPRS.AppImage", "run"]
    )
    services.web = None
    services.note_page_port()
    assert not note.exists(), "the note of an earlier restart is not this one's"

    def refused(data_dir: Path, port: int) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(stopfile, "note_port", refused)
    caplog.set_level(logging.WARNING, logger="neoaprs.controller")
    services.note_page_port()
    assert "the port of the page could not be noted for the restart" in caplog.text, (
        "the installer is started all the same"
    )
