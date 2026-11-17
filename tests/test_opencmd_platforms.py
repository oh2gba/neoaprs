"""`neoaprs open` (neoaprs/cli/opencmd.py) where it branches on the system or on what the daemon has done so far, with the platform said and Popen, the Windows API and the daemon's state faked: the command that
starts the daemon on Windows and how it is detached, the message box of a program that has no console, and a wait for a page that is not up yet. Nothing is started and no window is made."""
import ctypes
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from neoaprs.cli import opencmd, servicecmd, servicewindows
from neoaprs.cli.logfile import LAUNCH_NAME, LOG_NAME


class Spawned:
    """`subprocess.Popen` as opencmd sees it: what it was asked to start."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        monkeypatch.setattr(opencmd.subprocess, "Popen", self.popen)

    def popen(self, argv: list[str], **kwargs: Any) -> object:
        self.calls.append((argv, kwargs))
        return object()


def test_on_windows_the_daemon_is_the_windowless_program_and_is_started_detached_with_no_log_on_the_console(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(servicecmd, "windowless_programs", lambda: ("C:/NeoAPRS/neoaprsw.exe", "C:/Python/pythonw.exe"))
    monkeypatch.setattr(servicecmd, "appimage_file", lambda: None)
    argv = opencmd.daemon_argv(tmp_path)
    assert argv == ["C:/NeoAPRS/neoaprsw.exe", "run", "--data", str(tmp_path)]
    assert opencmd.daemon_argv(tmp_path, encryption=True) == [*argv, "--encryption"], "the app started with --encryption passes it on (OH2GAX, 4 Nov 2026)"
    spawned = Spawned(monkeypatch)
    opencmd.spawn(argv, tmp_path / "data")
    [(started, options)] = spawned.calls
    assert started == argv and options["creationflags"] == servicewindows.DETACHED and options["stdout"] == subprocess.DEVNULL and options["stderr"] == subprocess.DEVNULL
    assert (tmp_path / "data").is_dir() and not (tmp_path / "data" / LOG_NAME).exists(), "(Windows has no console: the daemon logs to its file itself)"


def test_elsewhere_the_daemon_is_a_session_of_its_own_whose_output_goes_to_a_file_of_its_own_not_the_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    spawned = Spawned(monkeypatch)
    opencmd.spawn(["neoaprs", "run"], tmp_path / "data")
    [(_, options)] = spawned.calls
    assert options["start_new_session"] is True and "creationflags" not in options and (tmp_path / "data" / LAUNCH_NAME).is_file() and not (tmp_path / "data" / LOG_NAME).exists(), "(the daemon's warnings would be in the log twice)"


def test_the_daemon_of_an_appimage_that_runs_unpacked_runs_unpacked_too(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An AppImage started with --appimage-extract-and-run (a computer without FUSE): the runtime keeps the flag to itself, so the daemon the app starts, the same file again, tried to mount and never
    came up. The variable says the same and is inherited."""
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("APPIMAGE_EXTRACT_AND_RUN", raising=False)
    monkeypatch.delenv("NO_CLEANUP", raising=False)
    spawned = Spawned(monkeypatch)
    unpacked = tmp_path / "appimage_extracted_0123"
    unpacked.mkdir()
    for appdir, appimage, expected in ((str(unpacked), "/home/op/NeoAPRS.AppImage", "1"), ("/", "/home/op/NeoAPRS.AppImage", None), (str(unpacked), None, None), (None, None, None)):
        for name, value in (("APPDIR", appdir), ("APPIMAGE", appimage)):
            monkeypatch.setenv(name, value) if value is not None else monkeypatch.delenv(name, raising=False)
        opencmd.spawn(["/home/op/NeoAPRS.AppImage", "run"], tmp_path / "data")
        env = spawned.calls[-1][1]["env"]
        assert env.get("APPIMAGE_EXTRACT_AND_RUN") == expected, (appdir, appimage)
        added = ("APPIMAGE_EXTRACT_AND_RUN", "NO_CLEANUP")
        assert {k: v for k, v in env.items() if k not in added} == dict(os.environ) and not any(k in os.environ for k in added), "everything else as this process has it, which is left as it is"


def test_the_daemon_of_an_appimage_that_runs_unpacked_leaves_the_folder_it_shares_with_the_app_to_the_apps_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The runtime unpacks one file into one folder for every run of it and removes the folder when its program ends: the daemon, which the app stops at Quit before it ends itself, removed the app's
    files under it, and the app's runtime then failed with "Failed to clean up cache directory" (work/par/r3/appe2e, risk 2). The app's runtime removes the folder at the app's end."""
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("NO_CLEANUP", raising=False)
    spawned = Spawned(monkeypatch)
    unpacked = tmp_path / "appimage_extracted_0123"
    unpacked.mkdir()
    for appdir, appimage, program, expected in ((str(unpacked), "/home/op/NeoAPRS.AppImage", "/home/op/NeoAPRS.AppImage", "neoaprs"), ("/", "/home/op/NeoAPRS.AppImage", "/home/op/NeoAPRS.AppImage", None),
                                                (str(unpacked), "/home/op/NeoAPRS.AppImage", "/home/op/Other.AppImage", None), (None, None, "/usr/bin/python3", None)):
        for name, value in (("APPDIR", appdir), ("APPIMAGE", appimage)):
            monkeypatch.setenv(name, value) if value is not None else monkeypatch.delenv(name, raising=False)
        opencmd.spawn([program, "run"], tmp_path / "data")
        assert spawned.calls[-1][1]["env"].get("NO_CLEANUP") == expected, (appdir, program)
    monkeypatch.setenv("APPDIR", str(unpacked))
    monkeypatch.setenv("NO_CLEANUP", "1")
    opencmd.spawn(["/home/op/NeoAPRS.AppImage", "run"], tmp_path / "data")
    assert spawned.calls[-1][1]["env"]["NO_CLEANUP"] == "1", "the operator's own is left as it is"


class Windows:
    """The two calls of the Windows API of the message box: the console window the program has (0: none) and the box."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, console: int) -> None:
        self.boxes: list[tuple[object, str, str, int]] = []
        kernel32 = SimpleNamespace(GetConsoleWindow=lambda: console)
        user32 = SimpleNamespace(MessageBoxW=lambda owner, text, title, flags: self.boxes.append((owner, text, title, flags)))
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(ctypes, "windll", SimpleNamespace(kernel32=kernel32, user32=user32), raising=False)


def test_a_program_with_no_console_says_why_nothing_happened_in_a_message_box(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    windows = Windows(monkeypatch, console=0)
    opencmd.tell_the_user("open: NeoAPRS did not come up: no page within 60 s")
    assert windows.boxes == [(None, "open: NeoAPRS did not come up: no page within 60 s", "NeoAPRS", 0x10)]
    assert "did not come up" in capsys.readouterr().err


def test_a_program_in_a_console_says_it_there_and_makes_no_box(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    windows = Windows(monkeypatch, console=4242)
    opencmd.tell_the_user("open: NeoAPRS did not come up")
    assert windows.boxes == [] and "did not come up" in capsys.readouterr().err


def test_a_page_that_is_not_up_yet_is_waited_for_and_the_address_comes_when_it_answers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(opencmd, "POLL_SEC", 0.01)
    states = iter([("http://127.0.0.1:7303/", False), (None, False), ("http://127.0.0.1:7303/", True)])
    current: list[Any] = []

    def next_state() -> None:
        current[:] = next(states)

    monkeypatch.setattr(opencmd, "is_running", lambda data: True)
    monkeypatch.setattr(opencmd, "page_url", lambda data: (next_state(), current[0])[1])
    monkeypatch.setattr(opencmd, "page_answers", lambda url: current[1])
    assert opencmd.wait_for_page(tmp_path, None, 5.0) == "http://127.0.0.1:7303/"
