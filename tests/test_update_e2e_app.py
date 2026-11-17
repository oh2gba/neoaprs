"""The desktop app's part of the end-to-end test of Update now (`scripts/update-e2e.py appimage OLD NEW --app`): its copies of the program's names and log lines, its readers of /proc (the app and
the daemon of a data folder by their command lines, the sockets, the locks, the mounts, what the test left running) on a made-up /proc and, where the kernel's own format is what counts, on this one,
the question that tells an old app with no restart as the new version from one that has it, and what the test holds of the app after the update, on stand-ins of the processes. The run with real
AppImages is the release workflow's or the maintainer's (docs/development.md, "Update now end to end")."""
import importlib.util
import logging
import os
import socket
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
LINUX = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the AppImage and /proc are Linux's")


def update_e2e() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("update_e2e", ROOT / "scripts" / "update-e2e.py")
    assert spec and spec.loader
    e2e = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(e2e)
    return e2e


def test_the_test_names_the_apps_files_flags_and_log_lines_as_the_program_has_them(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    from neoaprs import instancelock, selfreplace
    from neoaprs.cli import logfile
    from neoaprs.desktop import cmd, renew, single
    from neoaprs.desktop.session import Opening, Session
    from neoaprs.desktop.shell import Launch
    e2e = update_e2e()
    assert (e2e.APP_PID, e2e.APP_PORT, e2e.APP_LOCK, e2e.DAEMON_LOCK) == (single.PID_NAME, single.PORT_NAME, single.LOCK_NAME, instancelock.LOCK_NAME)
    assert (e2e.PAGE_FILE, e2e.OWNS_DAEMON, e2e.EXTRACT_AND_RUN, e2e.LOG) == (logfile.PAGE_FILE, renew.OWNS_DAEMON, selfreplace.EXTRACT_AND_RUN, logfile.LOG_NAME)
    assert e2e.QUIT_SEC > cmd.QUIT_WAIT_SEC, "the test waits longer for `app --quit` than it waits for the app"
    assert cmd.parser().parse_args([e2e.OWNS_DAEMON, "--quit"]).owns_daemon, "this tree's app takes the flag: it is after LAST_WITHOUT_RENEW"
    assert 'log.info("' + e2e.SHELL_RUNS + '%s)"' in (ROOT / "neoaprs" / "desktop" / "qtshell.py").read_text(encoding="utf-8")
    assert "QT_QPA_PLATFORM=offscreen QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu" in (ROOT / "scripts" / "smoke-appimage").read_text(encoding="utf-8")
    assert e2e.APP_ENV == {"QT_QPA_PLATFORM": "offscreen", "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu"}
    caplog.set_level(logging.INFO, logger="neoaprs.desktop")
    for owned in (True, False):
        session = Session(tmp_path, "http://127.0.0.1:7303/", owned)
        Launch(tmp_path, Opening.opened(session), False, False, None, single.SingleApp(tmp_path)).context(session)
    sessions = [r.getMessage() for r in caplog.records if e2e.APP_SESSION in r.getMessage()]
    assert len(sessions) == 2 and e2e.OWN_DAEMON in sessions[0] and e2e.OWN_DAEMON not in sessions[1]
    renew.start_again(["/home/ham/NeoAPRS.AppImage", "app"], reexec=lambda command, put_back: None)
    assert any(r.getMessage().startswith(e2e.RENEWS) for r in caplog.records)


def test_the_old_app_is_asked_whether_it_starts_again_as_the_new_version(tmp_path: Path) -> None:
    """The question is the program's own answer to `app --owns-daemon --quit` on a folder with no app: this tree's takes the flag and ends at once without making the folder; an app of 0.20.2 refuses it."""
    e2e = update_e2e()
    probe = tmp_path / "probe"
    env = {k: v for k, v in os.environ.items() if k != "NEOAPRS_DATA_DIR"} | {"HOME": str(tmp_path / "home"), "XDG_CONFIG_HOME": str(tmp_path / "config"), "XDG_DATA_HOME": str(tmp_path / "share")}
    done = subprocess.run([sys.executable, "-m", "neoaprs", "app", e2e.OWNS_DAEMON, "--quit", "--data", str(probe)], capture_output=True, text=True, timeout=120, env=env, stdin=subprocess.DEVNULL)
    assert e2e.knows_renew(done) and not probe.exists(), done.stdout + done.stderr
    refused = subprocess.CompletedProcess([], 2, "", f"usage: neoaprs app [-h] ...\nneoaprs app: error: unrecognized arguments: {e2e.OWNS_DAEMON}\n")
    assert not e2e.knows_renew(refused)
    for odd in (subprocess.CompletedProcess([], 2, "", "neoaprs: error: invalid choice: 'app'"), subprocess.CompletedProcess([], 1, "app: no", "")):
        with pytest.raises(e2e.Failure, match="neither: exit code"):
            e2e.knows_renew(odd)


def test_put_old_decides_known_old_of_the_app_by_its_answer_and_its_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A build of 0.20.2's tree has the restart and the release 0.20.2 has not, under the same name: the answer decides, and the version only bounds --known-old."""
    e2e = update_e2e()
    monkeypatch.setattr(e2e.AppImageInstall, "put_old", lambda self: None)

    def made(old: str, known_old: bool, takes: bool) -> Any:
        install = e2e.AppImageAppInstall(tmp_path / "work", Path(f"NeoAPRS-{old}-x86_64.AppImage"), Path("NeoAPRS-9.9.9-x86_64.AppImage"), False, known_old)
        stderr = "" if takes else f"error: unrecognized arguments: {e2e.OWNS_DAEMON}"
        install.run = lambda *args, **kw: subprocess.CompletedProcess(args, 0 if takes else 2, "", stderr)
        install.put_old()
        return install

    assert not made("0.20.2", False, True).app_stays_old and not made("0.20.2", True, True).app_stays_old, "an app that starts again is held to it, --known-old or not"
    assert made("0.20.2", True, False).app_stays_old and made("0.20.0", True, False).app_stays_old
    with pytest.raises(e2e.Failure, match="refuses --owns-daemon: it does not start again .* \\(--known-old is for"):
        made("0.20.2", False, False)
    with pytest.raises(e2e.Failure, match="though 0.20.3-e2e is after 0.20.2"):
        made("0.20.3-e2e", True, False)


def fake_process(proc: Path, pid: int, parent: int, cmdline: list[str], state: str = "S", exe: str = "", **environ: str) -> None:
    folder = proc / str(pid)
    folder.mkdir(parents=True)
    (folder / "stat").write_text(f"{pid} (x y) {state} {parent} {pid} {pid} 0 -1 4194304", encoding="ascii")
    (folder / "cmdline").write_bytes(b"\0".join(a.encode() for a in cmdline) + b"\0")
    (folder / "environ").write_bytes(b"\0".join(f"{k}={v}".encode() for k, v in environ.items()))
    if exe:
        (folder / "exe").symlink_to(exe)


def test_the_app_and_the_daemon_of_a_data_folder_are_found_by_their_command_lines(tmp_path: Path) -> None:
    e2e = update_e2e()
    proc, data, other = tmp_path / "proc", tmp_path / "data folder", tmp_path / "other"
    data.mkdir()
    other.mkdir()
    image, mount = str(tmp_path / "NeoAPRS-0.20.2-x86_64.AppImage"), str(tmp_path / ".mount_NeoAPRabc")
    python = [f"{mount}/usr/bin/python3", "-I", "-m", "neoaprs"]
    fake_process(proc, 1, 0, ["/sbin/init"])
    fake_process(proc, 500, 1, [*python, "app", "--data", str(data)], exe=f"{mount}/usr/bin/python3.13", APPIMAGE=image, APPDIR=mount)
    fake_process(proc, 501, 500, [*python, "run", "--data", str(data)], exe=f"{mount}/usr/bin/python3.13", APPIMAGE=image, APPDIR=mount)
    fake_process(proc, 502, 1, [image, "run", "--data", str(data)], exe=image)                                   # the process that serves the daemon's mount: no Python of NeoAPRS
    fake_process(proc, 503, 1, [*python, "app", "--quit", "--data", str(data)])                                  # the question to end, not an app
    fake_process(proc, 504, 1, [*python, "db", "--data", str(data), "get", "web/port"])
    fake_process(proc, 505, 1, [*python, "run", "--data", str(other)])
    fake_process(proc, 506, 500, [*python, "run", "--data", str(data)], state="Z")
    fake_process(proc, 507, 1, [*python, "app", "--data"])
    (proc / "self").mkdir()
    found = e2e.neoaprs_processes(data, proc)
    assert [(p.pid, p.parent, p.role, p.folder, p.appimage) for p in found] == [(500, 1, "app", mount, image), (501, 500, "run", mount, image)]
    assert found[0].args == ("app", "--data", str(data)) and e2e.runs_from(found[0])
    assert not e2e.runs_from(e2e.Running(1, 0, "app", (), mount, image, f"{tmp_path}/.mount_NeoAPRold/usr/bin/python3")) and not e2e.runs_from(e2e.Running(1, 0, "app", (), "", image, "/x"))
    assert e2e.state_of(506, proc) == ("Z", 500) and e2e.state_of(999, proc) == ("", 0) and e2e.exe_of(999, proc) == ""
    assert "the app 500 (no version from" in found[0].describe() and found[1].describe().startswith("the daemon 501")


def test_the_version_a_program_runs_is_read_from_its_folder(tmp_path: Path) -> None:
    e2e = update_e2e()
    init = tmp_path / "usr" / "lib" / "python3.13" / "site-packages" / "neoaprs" / "__init__.py"
    init.parent.mkdir(parents=True)
    init.write_text('"""NeoAPRS."""\n\nVERSION = "0.20.3-e2e"\n', encoding="utf-8")
    assert e2e.version_in(str(tmp_path)) == "0.20.3-e2e" and e2e.version_in(str(tmp_path / "gone")) == "" and e2e.version_in("") == ""
    assert (ROOT / "scripts" / "build-appimage").read_text(encoding="utf-8").count("usr/lib/python3.*/site-packages/neoaprs/__init__.py") == 1, "where --retag changes the VERSION"


def test_the_sockets_locks_and_mounts_are_read_from_proc(tmp_path: Path) -> None:
    e2e = update_e2e()
    proc = tmp_path / "proc"
    (proc / "net").mkdir(parents=True)
    head = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
    (proc / "net" / "tcp").write_text(head + "   0: 0100007F:9C41 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 4242 1 0 100 0 0 10 0\n"
                                      "   1: 0100007F:9C41 0100007F:D000 01 00000000:00000000 00:00000000 00000000  1000        0 4343 1 0 20 4 30 10 -1\n", encoding="ascii")
    (proc / "net" / "tcp6").write_text(head, encoding="ascii")
    assert e2e.listening(0x9C41, proc) == {4242} and e2e.listening(7303, proc) == set()
    fake_process(proc, 700, 1, ["python3"])
    (proc / "700" / "fd").mkdir()
    for fd, target in (("3", "socket:[4242]"), ("4", "/dev/null"), ("5", "socket:[77]"), ("6", "anon_inode:[eventfd]")):
        (proc / "700" / "fd" / fd).symlink_to(target)
    assert e2e.sockets_of(700, proc) == {4242, 77} and e2e.sockets_of(999, proc) == set()
    lock = tmp_path / "neoaprs-app.lock"
    lock.write_bytes(b"")
    inode = lock.stat().st_ino
    (proc / "locks").write_text(f"1: FLOCK  ADVISORY  WRITE 700 fd:01:{inode} 0 EOF\n1: -> FLOCK  ADVISORY  WRITE 701 fd:01:{inode} 0 EOF\n2: POSIX  ADVISORY  WRITE 702 fd:01:9 0 EOF\n"
                                f"3: OFDLCK ADVISORY  READ  -1 fd:01:{inode} 0 EOF\n", encoding="ascii")
    assert e2e.lock_holders(lock, proc) == {700} and e2e.lock_holders(tmp_path / "none", proc) == set()
    work = tmp_path / "work with a blank"
    (proc / "self").mkdir(exist_ok=True)
    (proc / "self" / "mountinfo").write_text(f"22 1 0:21 / /proc rw,nosuid - proc proc rw\n"
                                             f"90 22 0:50 / {str(work).replace(' ', chr(92) + '040')}/tmp/.mount_NeoAPRx1 ro,nosuid,nodev - fuse.NeoAPRS-0.20.2-x86_64.AppImage NeoAPRS ro\n"
                                             f"91 22 0:51 / {tmp_path}/elsewhere/.mount_y ro - fuse.Other Other ro\n", encoding="utf-8")
    assert e2e.mounts_under(work, proc) == [f"{work}/tmp/.mount_NeoAPRx1"] and e2e.mounts_under(work / "tmp", proc) == [f"{work}/tmp/.mount_NeoAPRx1"]
    assert e2e.mounts_under(tmp_path / "none", proc) == []
    data = tmp_path / "data"
    data.mkdir()
    assert e2e.page_port(data) is None
    (data / e2e.PAGE_FILE).write_text("http://127.0.0.1:7304/\n", encoding="ascii")
    assert e2e.page_port(data) == 7304
    (data / e2e.PAGE_FILE).write_text("http://192.0.2.1:7304/\n", encoding="ascii")
    assert e2e.page_port(data) is None


@LINUX
def test_the_readers_read_this_kernels_own_proc(tmp_path: Path) -> None:
    """The format is the kernel's: a socket this test listens on, a lock it holds and a folder with no mount, read from the real /proc."""
    from neoaprs.instancelock import InstanceLock
    e2e = update_e2e()
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        assert e2e.listening(server.getsockname()[1]) & e2e.sockets_of(os.getpid())
    lock = InstanceLock(tmp_path, "neoaprs-app.lock")
    lock.acquire()
    try:
        assert e2e.lock_holders(tmp_path / "neoaprs-app.lock") == {os.getpid()}
    finally:
        lock.release()
    assert e2e.lock_holders(tmp_path / "neoaprs-app.lock") == set()
    assert e2e.mounts_under(tmp_path) == []
    assert e2e.processes_from(tmp_path, tmp_path / "NeoAPRS-0.20.2-x86_64.AppImage") == [], "this test runs nothing from its folder"


def test_what_the_test_left_running_is_every_process_from_its_folder_or_of_its_file(tmp_path: Path) -> None:
    e2e = update_e2e()
    proc, work = tmp_path / "proc", tmp_path / "work"
    image = work / "Applications" / "NeoAPRS-0.20.2-x86_64.AppImage"
    fake_process(proc, 1, 0, ["/sbin/init"], exe="/usr/lib/systemd/systemd")
    fake_process(proc, 600, 1, [str(image), "run", "--data", "d"], exe=f"{image} (deleted)")                                        # a runtime, or the process that serves a mount
    fake_process(proc, 601, 1, [f"{work}/tmp/.mount_x/usr/bin/python3", "-I", "-m", "neoaprs", "run"], exe=f"{work}/tmp/.mount_x/usr/bin/python3.13")
    fake_process(proc, 602, 1, ["/usr/lib/qt6/QtWebEngineProcess"], exe="/usr/lib/qt6/QtWebEngineProcess", APPIMAGE=str(image))
    fake_process(proc, 603, 1, ["bash"], exe="/usr/bin/bash", APPIMAGE="/home/ham/Other.AppImage")
    fake_process(proc, 604, 1, [str(image)], state="Z")
    fake_process(proc, os.getpid(), 1, [f"{work}/python"], exe=f"{work}/python")
    assert e2e.processes_from(work, image, proc) == [f"600 {image} run --data d", f"601 {work}/tmp/.mount_x/usr/bin/python3 -I -m neoaprs run", "602 /usr/lib/qt6/QtWebEngineProcess"]


def app_install(tmp_path: Path, e2e: types.ModuleType, extract_and_run: bool, old: str = "0.20.2") -> Any:
    install = e2e.AppImageAppInstall(tmp_path / "work", Path(f"NeoAPRS-{old}-x86_64.AppImage"), Path("NeoAPRS-0.20.3-e2e-x86_64.AppImage"), extract_and_run)
    install.data = tmp_path / "data"
    install.data.mkdir(exist_ok=True)
    return install


@LINUX
def test_the_app_started_again_is_held_to_the_new_version_in_the_old_ones_place(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Mounted the same process goes on as the new app, unpacked the new app is the child of the old app's process (its runtime); in its folder of the new version, with --owns-daemon, owning the daemon.
    The root of this system and /proc stand in for the mounts, folders of the test's for the unpacked ones."""
    e2e = update_e2e()
    monkeypatch.setattr(e2e, "RENEW_SEC", 0.6)
    monkeypatch.setattr(e2e, "PAGE_SEC", 0.6)
    versions = {"/": "0.20.2", "/proc": "0.20.3-e2e", "/sys": "0.20.3-e2e", str(tmp_path / "old"): "0.20.2", str(tmp_path / "new"): "0.20.3-e2e", str(tmp_path / "newd"): "0.20.3-e2e"}
    monkeypatch.setattr(e2e, "version_in", lambda folder: versions.get(folder, ""))
    for name in ("old", "new", "newd"):
        (tmp_path / name).mkdir()

    def running(pid: int, parent: int, role: str, folder: str, *more: str) -> Any:
        return e2e.Running(pid, parent, role, (role, "--data", "d", *more), folder, str(tmp_path / "work" / "Applications" / "NeoAPRS-0.20.2-x86_64.AppImage"), os.path.realpath(folder).rstrip("/") + "/usr/bin/python3")

    def renewed(install: Any, now: list[Any], log: str) -> str:
        monkeypatch.setattr(e2e, "neoaprs_processes", lambda data: now)
        (install.data / e2e.APP_LOG).write_text(log, encoding="utf-8")
        capsys.readouterr()
        app, own = install.check_app_renewed(lambda app, own: own.folder in ("/sys", str(tmp_path / "newd")), "0.20.3-e2e")
        return str(capsys.readouterr().out)

    good_log = f"x  INFO  NeoAPRS app on d, page u, its own daemon; window\nx  INFO  {e2e.RENEWS} (f)\nx  INFO  a daemon runs on d: attaching as its owner\nx  INFO  NeoAPRS app on d, page u, its own daemon; w\nx  INFO  the Qt shell runs (window and tray)\n"
    mounted = app_install(tmp_path, e2e, False)
    mounted.old_app, mounted.old_folder = running(500, 1, "app", "/"), "/x"
    out = renewed(mounted, [running(500, 1, "app", "/proc", e2e.OWNS_DAEMON), running(501, 500, "run", "/sys")], good_log)
    assert "the app of 0.20.3-e2e runs in the same process, with --owns-daemon, owning the daemon 501" in out and "the new app runs mounted, as the old one did, from /proc" in out
    with pytest.raises(e2e.Failure, match="the new app is the process 777, not 500"):
        renewed(mounted, [running(777, 1, "app", "/proc", e2e.OWNS_DAEMON), running(501, 500, "run", "/sys")], good_log)
    with pytest.raises(e2e.Failure, match="the app of 0.20.3-e2e with --owns-daemon .* not within .*running on the data folder: the app 500 \\(0.20.2 from /\\), the daemon 501"):
        renewed(mounted, [running(500, 1, "app", "/"), running(501, 500, "run", "/sys")], good_log)
    with pytest.raises(e2e.Failure, match="does not say 'NeoAPRS was updated"):
        renewed(mounted, [running(500, 1, "app", "/proc", e2e.OWNS_DAEMON), running(501, 500, "run", "/sys")], good_log.replace(e2e.RENEWS, "something else"))
    with pytest.raises(e2e.Failure, match="does not own its daemon"):
        renewed(mounted, [running(500, 1, "app", "/proc", e2e.OWNS_DAEMON), running(501, 500, "run", "/sys")], good_log.replace("its own daemon; w", "a running daemon; w"))

    unpacked = app_install(tmp_path, e2e, True)
    unpacked.old_app, unpacked.old_folder = running(500, 400, "app", str(tmp_path / "old")), "/x"
    out = renewed(unpacked, [running(510, 500, "app", str(tmp_path / "new"), e2e.OWNS_DAEMON), running(511, 1, "run", str(tmp_path / "newd"))], good_log)
    assert "as the child 510 of the old app's process 500, which runs the new file's runtime" in out and "the new app runs unpacked, as the old one did" in out
    with pytest.raises(e2e.Failure, match="the new app 510 is a child of 1, not of 500"):
        renewed(unpacked, [running(510, 1, "app", str(tmp_path / "new"), e2e.OWNS_DAEMON), running(511, 1, "run", str(tmp_path / "newd"))], good_log)
    with pytest.raises(e2e.Failure, match="the new app runs mounted, from /proc, though the old one ran unpacked"):
        renewed(unpacked, [running(510, 500, "app", "/proc", e2e.OWNS_DAEMON), running(511, 1, "run", str(tmp_path / "newd"))], good_log)


def test_an_old_app_that_does_not_start_again_is_watched_staying_as_it_was(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    e2e = update_e2e()
    monkeypatch.setattr(e2e, "STAYS_SEC", 0.3)
    monkeypatch.setattr(e2e.time, "sleep", lambda s: None)
    install = app_install(tmp_path, e2e, False)
    old = e2e.Running(500, 1, "app", ("app", "--data", "d"), "/", "f", "/usr/bin/python3")
    install.old_app = old
    new_daemon = e2e.Running(501, 500, "run", ("run", "--data", "d"), "/proc", "f", "/proc/usr/bin/python3")
    monkeypatch.setattr(e2e, "neoaprs_processes", lambda data: [old, new_daemon])
    assert install.check_app_stays(lambda app, own: True) == (old, new_daemon)
    assert "known of 0.20.2 (--known-old): the app 500 stays the old program, from /" in capsys.readouterr().out
    monkeypatch.setattr(e2e, "neoaprs_processes", lambda data: [e2e.Running(500, 1, "app", (), "/sys", "f", "/sys/python3"), new_daemon])
    with pytest.raises(e2e.Failure, match="was to stay as it was, and is the app 500"):
        install.check_app_stays(lambda app, own: True)


def test_the_exit_code_is_0_or_the_unpacked_runtimes_own_1_and_the_mounts_are_those_of_the_programs_that_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    e2e = update_e2e()
    mounted, unpacked = app_install(tmp_path, e2e, False), app_install(tmp_path, e2e, True)
    for install in (mounted, unpacked):
        install.exit_code("app --quit", 0, "app: NeoAPRS app has ended")
    unpacked.exit_code("the app", 1, f"{e2e.RUNTIME_CLEANUP}\n")
    assert "the app ended with exit code 1 from the unpacked file's runtime alone" in capsys.readouterr().out
    for install, code, said in ((mounted, 1, e2e.RUNTIME_CLEANUP), (unpacked, 1, "Traceback"), (unpacked, 2, e2e.RUNTIME_CLEANUP)):
        with pytest.raises(e2e.Failure, match=f"ended with exit code {code}, not 0"):
            install.exit_code("app --quit", code, said)

    monkeypatch.setattr(e2e, "MOUNTS_SEC", 0.3)
    app, own = e2e.Running(1, 0, "app", (), "/m/new-app", "f", ""), e2e.Running(2, 1, "run", (), "/m/new-daemon", "f", "")
    mounted.old_app_folder, mounted.old_folder = "/m/old-app", "/m/old-daemon"
    monkeypatch.setattr(e2e, "mounts_under", lambda folder: ["/m/new-app", "/m/new-daemon"])
    mounted.check_mounts(app, own)
    assert "the mounts in the temporary folder are ['/m/new-app', '/m/new-daemon']" in capsys.readouterr().out
    monkeypatch.setattr(e2e, "mounts_under", lambda folder: ["/m/new-app", "/m/new-daemon", "/m/old-app"])
    for install in (mounted, unpacked):                                        # an old mount that stays is said here and held gone at the end (leftovers)
        capsys.readouterr()
        install.check_mounts(app, own)
        said = capsys.readouterr().out
        assert "still has the mounts" in said and "/m/old-app" in said and "held: none is left once the test has ended" in said


def test_the_app_is_started_offscreen_and_unpacked_by_the_variable_that_reaches_its_daemon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    e2e = update_e2e()
    started: list[tuple[list[str], dict[str, str]]] = []

    class Child:
        pid = 4242

    monkeypatch.setattr(e2e.subprocess, "Popen", lambda argv, **kw: started.append((argv, kw["env"])) or Child())
    for extract_and_run in (False, True):
        install = app_install(tmp_path, e2e, extract_and_run)
        install.work.mkdir(exist_ok=True)
        install.start(tmp_path / "data folder", {"APPIMAGE_EXTRACT_AND_RUN": "1", "APPDIR": "/tmp/.mount_parent", "NEOAPRS_UPDATE_TEST": "1"})
        argv, env = started[-1]
        assert argv == [str(install.file), "app", "--data", str(tmp_path / "data folder")] and install.pid == 4242
        assert env["QT_QPA_PLATFORM"] == "offscreen" and env["NEOAPRS_UPDATE_TEST"] == "1" and "APPDIR" not in env and env["HOME"] == str(install.home)
        assert env.get("APPIMAGE_EXTRACT_AND_RUN") == ("1" if extract_and_run else None)
    with pytest.raises(e2e.Failure, match="the old app runs mounted from /, though the test started it with APPIMAGE_EXTRACT_AND_RUN=1"):
        app_install(tmp_path, e2e, True).held_start("app", "/")


def test_the_home_folder_is_held_for_neoaprs_own_files_alone_and_the_page_is_looked_for_where_a_known_old_one_may_serve_it(tmp_path: Path) -> None:
    """Qt and the web engine write into the home folder as they run and end (caches, the certificate database): what an update must not touch is NeoAPRS's data, its start at sign-in and its menu entries."""
    e2e = update_e2e()
    install = app_install(tmp_path, e2e, False)
    install.folder.mkdir(parents=True)
    for name in (".cache/fontconfig/x.cache", ".pki/nssdb/cert9.db", ".config/QtProject.conf"):
        (install.home / name).parent.mkdir(parents=True, exist_ok=True)
        (install.home / name).write_text("x", encoding="utf-8")
    quiet = install.outside()
    assert quiet["the home folder"] == [] and len(install.home_files()) > 3
    for name in (".config/autostart/neoaprs.desktop", ".local/share/applications/NeoAPRS.desktop", ".local/share/neoaprs/neoaprs.sqlite"):
        (install.home / name).parent.mkdir(parents=True, exist_ok=True)
        (install.home / name).write_text("x", encoding="utf-8")
    assert install.outside()["the home folder"] != quiet["the home folder"] and len(install.outside()["the home folder"]) == 5          # (the three files and the two folders that are named so)
    install.data.joinpath(e2e.PAGE_FILE).write_text("http://127.0.0.1:7304/\n", encoding="ascii")
    ports = range(7303, 7314)
    assert install.page_ports(install.data, ports, lambda: True) == range(7304, 7305)
    old = e2e.AppImageAppInstall(tmp_path / "work", Path("NeoAPRS-0.20.1-x86_64.AppImage"), Path("NeoAPRS-0.20.3-e2e-x86_64.AppImage"), False, True)
    old.data = install.data
    assert old.known_old and old.page_ports(old.data, ports, lambda: True) == ports
