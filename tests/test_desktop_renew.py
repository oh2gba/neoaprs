"""Tests for the desktop app after an AppImage update (neoaprs/desktop/renew.py): the app that owns
its daemon restarts from the new file and keeps owning it; an attached app is left alone. The exec,
the toolkits and the daemons are stand-ins."""

import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from neoaprs import selfreplace, stopfile
from neoaprs.desktop import cmd, renew, splash
from neoaprs.desktop.menu import QUIT, KEEPS_RUNNING
from neoaprs.desktop.session import DaemonWatch, Session, open_session
from neoaprs.desktop.shell import Launch
from neoaprs.desktop.single import SingleApp
from tests.support import fakeshell
from tests.support.ptyline import SIGKILL
from tests.test_desktop_cmd import World
from tests.test_desktop_logic import PAGE, FakeDaemon, actions_for

DATA = Path("somewhere")


def new_file(path: Path, content: bytes) -> None:
    """A new file in the place of `path`, as Update now puts it there: written beside it and renamed
    over it."""
    part = path.with_name(path.name + ".part")
    part.write_bytes(content)
    os.replace(part, path)


# ---- the app's own file


def test_outside_an_appimage_there_is_no_file_to_watch(tmp_path: Path) -> None:
    assert renew.AppFile.of(None) is None and renew.AppFile.of("") is None
    assert renew.AppFile.of(str(tmp_path / "gone.AppImage")) is None


def test_the_file_is_replaced_once_another_one_is_in_its_place_and_the_same_at_two_looks_in_a_row(
    tmp_path: Path,
) -> None:
    image = tmp_path / "NeoAPRS-x86_64.AppImage"
    image.write_bytes(b"0.20.2")
    app_file = renew.AppFile.of(str(image))
    assert app_file is not None
    assert not app_file.replaced() and not app_file.replaced(), "the file the app started from"
    new_file(image, b"0.20.3")
    assert not app_file.replaced(), "seen once: it may still be being written"
    assert app_file.replaced()
    image.unlink()
    assert not app_file.replaced(), "no file is no new version"


def test_a_file_that_changes_between_looks_is_not_started(tmp_path: Path) -> None:
    image = tmp_path / "NeoAPRS-x86_64.AppImage"
    image.write_bytes(b"0.20.2")
    app_file = renew.AppFile.of(str(image))
    assert app_file is not None
    # (a copy by hand over the file: it grows at every look)
    for size in range(1, 5):
        with image.open("ab") as grows:
            grows.write(b"x" * size)
        os.utime(image, ns=(size, size))
        assert not app_file.replaced()
    assert app_file.replaced(), "once it has stopped changing"


def test_the_app_starts_again_from_the_same_file_on_the_same_folder_as_the_owner_of_its_daemon_with_its_flags() -> None:
    # (as this system writes a path: the app is an AppImage's, the test runs everywhere)
    data, folder = Path("/home/ham/.local/share/neoaprs"), str(Path("/d"))
    assert renew.argv("/home/ham/NeoAPRS.AppImage", data, False, False) == [
        "/home/ham/NeoAPRS.AppImage",
        "app",
        "--data",
        str(data),
        "--owns-daemon",
    ]
    assert renew.argv("/a/N.AppImage", Path("/d"), True, True) == [
        "/a/N.AppImage",
        "app",
        "--data",
        folder,
        "--owns-daemon",
        "--encryption",
        "--debug",
    ]
    args = cmd.parser().parse_args(renew.argv("/a/N.AppImage", Path("/d"), True, True)[2:])
    assert (args.data, args.owns_daemon, args.encryption, args.debug, args.tray) == (folder, True, True, True, False), (
        "the window comes back shown, as after the installer of Windows"
    )
    assert "--owns-daemon" not in cmd.parser().format_help(), "the flag is the app's own, not the operator's"
    assert splash.window_now(["--owns-daemon"]) is not None


def test_the_start_again_puts_nothing_back_when_the_new_file_cannot_be_started(tmp_path: Path) -> None:
    image = tmp_path / "NeoAPRS.AppImage"
    image.write_bytes(b"new version")
    (tmp_path / "NeoAPRS.AppImage.old").write_bytes(b"old version")
    tried: list[list[str]] = []

    def refused(path: str, argv: list[str]) -> None:
        tried.append(argv)
        raise OSError("exec format error")

    renew.start_again(
        [str(image), "app"],
        lambda argv, put_back: selfreplace.reexec(argv, refused, close=lambda: None, environ={}, put_back=put_back),
    )
    assert tried == [[str(image), "app"]], "tried once, the new file only"
    assert (
        image.read_bytes() == b"new version" and (tmp_path / "NeoAPRS.AppImage.old").read_bytes() == b"old version"
    ), "the daemon runs the new file: nothing is put back"


# ---- the owner of the daemon it finds


def test_an_app_started_again_owns_the_daemon_it_attaches_to() -> None:
    daemon = FakeDaemon(up=True)
    assert open_session(DATA, daemon, owns=True) == Session(DATA, PAGE, owned=True)
    assert daemon.started == []
    assert open_session(DATA, FakeDaemon(up=True)) == Session(DATA, PAGE, owned=False), "without the flag, as always"


def test_an_app_started_again_waits_for_a_daemon_that_is_starting_again_instead_of_starting_a_second_one() -> None:
    daemon = FakeDaemon(up=False)
    daemon.restarting = lambda data: True
    assert open_session(DATA, daemon, owns=True) == Session(DATA, PAGE, owned=True)
    assert daemon.started == []


def test_an_app_started_again_that_finds_no_daemon_starts_one_and_does_not_own_one_that_won_the_folder_from_it() -> (
    None
):
    daemon = FakeDaemon(up=False)
    assert open_session(DATA, daemon, owns=True).owned and daemon.started == [DATA]
    assert open_session(DATA, FakeDaemon(up=False, child_alive=False), owns=True).owned is False


def test_the_menu_of_the_app_started_again_is_stop_and_quit() -> None:
    actions, frame, daemon, _ = actions_for(owned=open_session(DATA, FakeDaemon(up=True), owns=True).owned)
    assert actions.items()[-1].label == "Stop and quit" and KEEPS_RUNNING not in actions.items()[-1].label
    actions.quit_now()
    assert daemon.stopped == [Path("data")] and frame.quits == 1


# ---- the watch


class Replaced(renew.AppFile):
    """An app's file that says it was replaced from the `after`th look on."""

    def __init__(self, after: int = 1) -> None:
        super().__init__("/home/ham/NeoAPRS.AppImage", (0, 0, 0, 0))
        self.looks, self.after = 0, after

    def replaced(self) -> bool:
        self.looks += 1
        return self.looks >= self.after


def watch(
    owned: bool, daemon: FakeDaemon, app_file: Replaced | None
) -> tuple[DaemonWatch, threading.Event, threading.Event]:
    """The watch as the app makes it (it follows the page too: an attached app's watch runs for
    that)."""
    renewed, gone = threading.Event(), threading.Event()
    daemon.address = lambda data: None
    w = DaemonWatch(
        Session(DATA, PAGE, owned),
        gone.set,
        daemon,
        every=0.02,
        moved=lambda url: None,
        app_file=app_file,
        renewed=renewed.set,
    )
    w.start()
    return w, renewed, gone


def test_the_watch_says_renewed_once_the_file_is_new_and_the_daemon_it_owns_runs_it() -> None:
    w, renewed, gone = watch(True, FakeDaemon(up=True), Replaced(after=3))
    assert renewed.wait(60) and not gone.is_set()
    w.thread.join(60)
    assert not w.thread.is_alive(), "once: the watch is over"


def test_the_watch_waits_while_the_daemon_is_starting_again_or_has_a_restart_pending() -> None:
    daemon = FakeDaemon(up=False)
    pending = [True]
    daemon.restarting = lambda data: pending[0]
    w, renewed, gone = watch(True, daemon, Replaced())
    assert not renewed.wait(0.3), "the daemon ended to start again: not yet"
    daemon.up = True
    assert not renewed.wait(0.3), (
        "it runs, and its note of the restart is still there: the old daemon is about to end, or the new one is not up yet"
    )
    pending[0] = False
    assert renewed.wait(60) and not gone.is_set()


def test_the_watch_does_not_look_at_the_daemons_lock_while_the_daemon_starts_again() -> None:
    """A look at the lock takes it for a moment: the new daemon that takes it in that moment finds
    it held and ends, and no daemon is left (work/par/r3/appe2e, risk 3)."""
    daemon = FakeDaemon(up=False)
    pending = [True]
    looks: list[bool] = []
    daemon.restarting = lambda data: pending[0]
    daemon.running = lambda data: looks.append(pending[0]) or daemon.up
    w, renewed, gone = watch(True, daemon, Replaced())
    try:
        assert not renewed.wait(0.3) and not gone.is_set()
        assert looks == [], "while the note of the restart is fresh the lock is not looked at"
        daemon.up = True
        pending[0] = False
        assert renewed.wait(60) and looks and True not in looks, "once the new daemon runs, it is"
    finally:
        w.cancel()


def test_an_app_attached_to_a_daemon_or_outside_an_appimage_is_never_started_again() -> None:
    w, renewed, _ = watch(False, FakeDaemon(up=True), Replaced())
    assert w.thread.is_alive() and not renewed.wait(0.3), "a service's daemon: the app only attached to it"
    w.cancel()
    other, renewed, _ = watch(True, FakeDaemon(up=True), None)
    assert not renewed.wait(0.3)
    other.cancel()
    unasked = DaemonWatch(Session(DATA, PAGE, True), lambda: None, FakeDaemon(up=True), app_file=Replaced())
    assert unasked.app_file is None, "a file with nobody to tell is not watched"


def test_with_the_daemons_own_files_and_notes_the_app_waits_for_the_restart_and_an_old_file_put_back_is_no_new_version(
    tmp_path: Path,
) -> None:
    """The steps of Update now as the daemon takes them (selfinstall.py and app.py: the old file
    kept as a hard link, the new one renamed over it, the note of the restart at once), on real
    files."""
    data, image = tmp_path / "data", tmp_path / "NeoAPRS-x86_64.AppImage"
    data.mkdir()
    image.write_bytes(b"0.20.2")
    app_file = renew.AppFile.of(str(image))
    assert app_file is not None
    daemon = FakeDaemon(up=True)
    daemon.restarting = stopfile.restarting
    renewed = threading.Event()
    w = DaemonWatch(Session(data, PAGE, True), lambda: None, daemon, every=0.02, app_file=app_file, renewed=renewed.set)
    w.start()
    try:
        selfreplace.keep_old(image)
        new_file(image, b"0.20.3")
        stopfile.mark_restart(data)
        assert not renewed.wait(0.3), "the daemon has its restart ahead of it: the old version still runs"
        assert selfreplace.restore(image)
        stopfile.clear_restart(data)
        assert image.read_bytes() == b"0.20.2"
        if os.stat(image).st_ino == app_file.started[1]:
            assert not renewed.wait(0.3), (
                "the new file could not be started and the old one is back: the app is the version that runs"
            )
        new_file(image, b"0.20.3")
        stopfile.mark_restart(data)
        assert not renewed.wait(0.3)
        stopfile.clear_restart(data)
        assert renewed.wait(60), "the new daemon runs the new file"
    finally:
        w.cancel()


# ---- what the app does then


def test_renew_ends_the_app_as_quit_would_and_leaves_the_daemon_running() -> None:
    actions, frame, daemon, _ = actions_for(owned=True)
    actions.renew()
    assert frame.quits == 1 and daemon.stopped == [] and actions.renewing
    actions.renew()
    actions.run(QUIT)
    if actions.thread is not None:
        actions.thread.join(60)
    assert frame.quits == 1 and daemon.stopped == [], "once, whoever asks"
    late, frame, _, _ = actions_for(owned=True)
    late.quit_now()
    late.renew()
    assert not late.renewing and frame.quits == 1, "an app that is quitting is not started again"


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    return World(tmp_path, monkeypatch)


class Started(Exception):
    """The exec: nothing after it runs in this process."""


@pytest.fixture
def renewing(
    world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[World, Path, list[Launch], list[tuple[list[str], bool]]]:
    """`neoaprs app` in an AppImage, with the scripted shell; what was started in its place and
    whether the app held the data folder then."""
    image = tmp_path / "NeoAPRS-x86_64.AppImage"
    image.write_bytes(b"0.20.2")
    monkeypatch.setattr(cmd, "appimage_file", lambda: str(image))
    launches: list[Launch] = []

    class Kept(Launch):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            launches.append(self)

    monkeypatch.setattr(cmd, "Launch", Kept)
    started: list[tuple[list[str], bool]] = []

    def start(argv: list[str]) -> None:
        started.append((argv, SingleApp(world.data).running()))
        raise Started

    monkeypatch.setattr(renew, "start_again", start)
    monkeypatch.setattr(
        renew,
        "end_helpers",
        lambda: started.append((["the web engine's processes ended"], SingleApp(world.data).running())),
    )
    return world, image, launches, started


def test_the_app_lets_go_of_the_data_folder_and_is_started_again_from_the_new_file(
    renewing: tuple[World, Path, list[Launch], list[tuple[list[str], bool]]],
) -> None:
    world, image, launches, started = renewing
    fakeshell.STEPS.append(lambda frame: launches[0].ctx.actions.renew())  # type: ignore[union-attr]
    with pytest.raises(Started):
        world.run("--encryption")
    assert started == [
        (["the web engine's processes ended"], False),
        ([str(image), "app", "--data", str(world.data), "--owns-daemon", "--encryption"], False),
    ], "the one-app lock and its port are let go of, and the web engine's processes ended, before the exec"
    assert not (world.data / "neoaprs-app.port").exists()
    assert world.owns == [False], "the first app was not started again"
    assert (
        launches[0].ctx is not None and launches[0].ctx.watch is not None and launches[0].ctx.watch.app_file is not None
    )
    assert launches[0].ctx.watch.app_file.path == str(image)


def test_an_app_that_quits_is_not_started_again(
    renewing: tuple[World, Path, list[Launch], list[tuple[list[str], bool]]],
) -> None:
    world, _, _, started = renewing
    fakeshell.STEPS.append(lambda frame: SingleApp(world.data).tell_the_other("quit"))
    assert world.run() == 0 and started == []


def test_the_app_started_again_asks_to_own_its_daemon(
    renewing: tuple[World, Path, list[Launch], list[tuple[list[str], bool]]],
) -> None:
    world, _, _, _ = renewing
    fakeshell.STEPS.append(lambda frame: SingleApp(world.data).tell_the_other("quit"))
    assert world.run("--owns-daemon") == 0 and world.owns == [True]


def test_when_the_new_file_cannot_be_started_the_daemon_no_app_owns_now_is_stopped(
    renewing: tuple[World, Path, list[Launch], list[tuple[list[str], bool]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    world, _, launches, started = renewing
    monkeypatch.setattr(renew, "start_again", lambda argv: started.append((argv, False)))
    stopped: list[Session] = []
    monkeypatch.setattr(cmd, "stop_owned", lambda session, daemon=None: stopped.append(session) or True)
    fakeshell.STEPS.append(lambda frame: launches[0].ctx.actions.renew())  # type: ignore[union-attr]
    assert world.run() == 1
    assert len(started) == 2 and stopped == [Session(world.data, PAGE, True)]
    assert any("could not be started" in line for line in world.said)


# ---- the web engine's processes


def proc_entry(proc: Path, pid: int, line: str) -> None:
    (proc / str(pid)).mkdir()
    (proc / str(pid) / "stat").write_text(line, encoding="utf-8")


def test_the_web_engines_processes_are_the_children_of_the_app_by_the_engines_program_names(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    proc.mkdir()
    proc_entry(proc, 501, "501 (QtWebEngineProc) S 500 500 500 0 -1")
    proc_entry(proc, 502, "502 (WebKitNetworkPr) Z 500 500 500 0 -1")
    proc_entry(proc, 503, "503 (python3) S 500 503 503 0 -1")  # (the daemon the app started)
    # (a renderer, the child of the engine's own process)
    proc_entry(proc, 504, "504 (QtWebEngineProc) S 501 500 500 0 -1")
    proc_entry(proc, 505, "505 (QtWebEngineProc) S 900 900 900 0 -1")  # (another app's)
    proc_entry(proc, 506, "506 (a) (QtWebEngineProc) S 500 500 500 0 -1")  # (a name of brackets of its own)
    # (WebKitGTK's web process in its sandbox)
    proc_entry(proc, 508, "508 (bwrap) S 500 500 500 0 -1")
    # (the web process itself, inside the sandbox)
    proc_entry(proc, 509, "509 (WebKitWebProces) S 510 500 500 0 -1")
    proc_entry(proc, 511, "511 (xdg-dbus-proxy) Z 500 500 500 0 -1")
    (proc / "self").mkdir()
    (proc / "self" / "stat").write_text("500 (python3) S 1 500 500 0 -1", encoding="utf-8")
    # (one that ended while the folder was listed)
    (proc / "507").mkdir()
    assert renew.helpers(str(proc), parent=500) == [501, 502, 508, 511]
    assert renew.helpers(str(tmp_path / "no proc"), parent=500) == []


class Helpers:
    """The kill and the wait of the web engine's processes, in virtual time: `stubborn` ones end
    only when killed."""

    def __init__(self, stubborn: set[int]) -> None:
        self.stubborn, self.now = stubborn, 0.0
        self.signals: list[tuple[int, int]] = []
        self.ended: set[int] = set()

    def kill(self, pid: int, sig: int) -> None:
        self.signals.append((pid, sig))
        if sig == SIGKILL or pid not in self.stubborn:
            self.ended.add(pid)

    def waited_for(self, pid: int, block: bool = False) -> bool:
        return pid in self.ended

    def sleep(self, seconds: float) -> None:
        self.now += seconds


@pytest.mark.skipif(sys.platform == "win32", reason="the installer ends the app on Windows")
def test_the_web_engines_processes_are_asked_to_end_and_those_that_do_not_are_killed() -> None:
    h = Helpers(stubborn={602})
    renew.end_helpers([601, 602], kill=h.kill, waited_for=h.waited_for, seconds=5, clock=lambda: h.now, sleep=h.sleep)
    assert h.signals == [(601, signal.SIGTERM), (602, signal.SIGTERM), (602, SIGKILL)] and h.ended == {601, 602}
    assert 5 <= h.now < 5.5, "the stubborn one was given its seconds"
    quick = Helpers(stubborn=set())
    renew.end_helpers([601], kill=quick.kill, waited_for=quick.waited_for, clock=lambda: quick.now, sleep=quick.sleep)
    assert quick.signals == [(601, signal.SIGTERM)] and quick.now == 0
    renew.end_helpers([], kill=quick.kill)
    assert quick.signals == [(601, signal.SIGTERM)], "none: nothing is done"


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the AppImage is Linux's, and so is /proc")
def test_a_real_child_named_as_the_web_engine_is_ended_and_waited_for_and_the_daemon_beside_it_is_left() -> None:
    """For real: two children of this process, one named as Qt's web engine names its process, the
    other as a daemon is named. The engine's ends and is waited for (no process is left that nobody
    waits for); the daemon runs on."""
    program = (
        "import sys\nopen('/proc/self/comm', 'w').write(sys.argv[1])\nprint('ready', flush=True)\nsys.stdin.read()"
    )
    started = [
        subprocess.Popen(
            [sys.executable, "-c", program, name], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
        )
        for name in ("QtWebEngineProcess", "neoaprs-daemon")
    ]
    engine, daemon = started
    try:
        for child in started:
            assert child.stdout is not None and child.stdout.readline() == "ready\n"
        found = renew.helpers()
        assert engine.pid in found and daemon.pid not in found
        renew.end_helpers([engine.pid])
        with pytest.raises(ChildProcessError):
            os.waitpid(engine.pid, 0)  # (waits, were it not waited for already)
        assert daemon.poll() is None, "the daemon is not the engine's"
    finally:
        for child in started:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=30)
