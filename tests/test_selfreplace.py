"""The file operations of Update now for an AppImage (neoaprs/selfreplace.py) beyond
tests/test_selfinstall.py: an undeletable old file, the descriptors the exec closes, the
was-it-mounted question, and a new version that must start unpacked.
"""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from neoaprs import selfreplace


def test_an_old_appimage_that_cannot_be_deleted_is_said_and_not_an_error(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    image = tmp_path / "NeoAPRS.AppImage"
    (tmp_path / "NeoAPRS.AppImage.old").mkdir()                        # (a name that unlink cannot take: a folder)
    caplog.set_level("WARNING", logger="neoaprs.update")
    selfreplace.remove_old(str(image))
    assert "the old AppImage" in caplog.text and "could not be deleted" in caplog.text


def listing(tmp_path: Path, *descriptors: int) -> str:
    """A folder that lists these descriptors, as /proc/self/fd lists those of the process."""
    folder = tmp_path / "fd"
    folder.mkdir()
    for fd in descriptors:
        (folder / str(fd)).touch()
    return str(folder)


@pytest.mark.skipif(sys.platform == "win32", reason="a descriptor that a program started later inherits is POSIX's")
def test_every_descriptor_above_stderr_is_left_open_and_marked_for_the_exec_to_close(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    read, write = os.pipe()
    terminal = [os.get_inheritable(fd) for fd in (0, 1, 2)]
    try:
        # As the runtime of an AppImage hands the pipe of its mount to the program it starts
        os.set_inheritable(read, True)
        os.set_inheritable(write, True)
        monkeypatch.setattr(selfreplace.sys, "platform", "linux")
        monkeypatch.setattr(os, "closerange", lambda low, high: pytest.fail("closed before the exec"))
        # One that is gone by now, as the listing's own is: passed over
        selfreplace.close_inherited(listing(tmp_path, 0, 1, 2, read, 987654))
        assert not os.get_inheritable(read) and os.fstat(read), "open, and closed by the exec"
        assert os.get_inheritable(write), "only what the listing names"
        assert [os.get_inheritable(fd) for fd in (0, 1, 2)] == terminal, "the three of the terminal stay as they were"
    finally:
        os.close(read)
        os.close(write)


def test_where_the_descriptors_cannot_be_listed_they_are_closed_and_on_windows_nothing_is_done(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "closerange", lambda low, high: closed.append((low, high)))
    monkeypatch.setattr(selfreplace.sys, "platform", "linux")
    selfreplace.close_inherited(str(tmp_path / "no such folder"))
    assert closed == [(3, 65536)]
    monkeypatch.setattr(selfreplace.sys, "platform", "win32")
    selfreplace.close_inherited(str(tmp_path / "no such folder"))
    assert closed == [(3, 65536)]


def test_a_mounted_appimage_whose_mount_goes_with_its_descriptors_is_executed_again_mounted() -> None:
    """The mount of an AppImage lives as long as the descriptors its runtime handed the program:
    asked after they are let go, "is it mounted?" is answered no, and the new file is started
    unpacked. `close` ends the stand-in mount."""
    gone: list[bool] = []
    environ = {"APPIMAGE": "/home/ham/NeoAPRS.AppImage", "APPDIR": "/tmp/.mount_NeoAPRxyz"}
    seen: list[tuple[str | None, bool]] = []
    selfreplace.reexec(["/home/ham/NeoAPRS.AppImage", "run"], lambda path, argv: seen.append((environ.get("APPIMAGE_EXTRACT_AND_RUN"), bool(gone))), close=lambda: gone.append(True), environ=environ,
                       is_mount=lambda path: not gone)
    assert seen == [(None, True)], "started as it ran, mounted, with the descriptors let go before the exec"
    unpacked = {"APPIMAGE": "/home/ham/NeoAPRS.AppImage", "APPDIR": "/tmp/appimage_extracted_0123"}
    selfreplace.reexec(["/home/ham/NeoAPRS.AppImage", "run"], lambda path, argv: seen.append((unpacked.get("APPIMAGE_EXTRACT_AND_RUN"), True)), close=lambda: None, environ=unpacked, is_mount=lambda path: False)
    assert seen[1] == ("1", True), "and one that ran unpacked is started unpacked"


def test_a_daemon_that_left_its_folder_to_the_app_has_its_new_version_remove_the_folder_of_its_own() -> None:
    """The daemon the app started unpacked leaves the folder it shares with the app to the app's
    runtime (selfreplace.leave_the_folder). The new file of Update now is unpacked into another
    folder, which no other run removes: started in the daemon's place, its runtime is to remove it.
    A NO_CLEANUP the operator set is kept."""
    seen: list[str | None] = []
    ours = {"APPIMAGE": "/home/ham/NeoAPRS.AppImage", "APPDIR": "/tmp/appimage_extracted_0123", "NO_CLEANUP": selfreplace.LEFT_TO_THE_STARTER}
    selfreplace.reexec(["/home/ham/NeoAPRS.AppImage", "run"], lambda path, argv: seen.append(ours.get("NO_CLEANUP")), close=lambda: None, environ=ours, is_mount=lambda path: False)
    operators = {**ours, "NO_CLEANUP": "1"}
    selfreplace.reexec(["/home/ham/NeoAPRS.AppImage", "run"], lambda path, argv: seen.append(operators.get("NO_CLEANUP")), close=lambda: None, environ=operators, is_mount=lambda path: False)
    assert seen == [None, "1"]


def test_the_old_version_put_back_in_the_place_of_a_daemon_that_left_its_folder_to_the_app_leaves_it_again(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The new file of Update now cannot be started: the old one is put back, and it has the old
    contents, so its runtime unpacks into the folder the app runs from. It is started with
    NO_CLEANUP again, or at Quit its runtime would remove the folder under the app."""
    image = tmp_path / "NeoAPRS.AppImage"
    image.write_bytes(b"new")
    (tmp_path / "NeoAPRS.AppImage.old").write_bytes(b"old")
    environ = {"APPIMAGE": str(image), "APPDIR": "/tmp/appimage_extracted_0123", "NO_CLEANUP": selfreplace.LEFT_TO_THE_STARTER}
    tried: list[tuple[bytes, str | None]] = []

    def execv(path: str, argv: list[str]) -> None:
        tried.append((Path(path).read_bytes(), environ.get("NO_CLEANUP")))
        raise OSError(8, "Exec format error")

    selfreplace.reexec([str(image), "run"], execv, close=lambda: None, environ=environ, is_mount=lambda path: False)
    assert tried == [(b"new", None), (b"old", selfreplace.LEFT_TO_THE_STARTER)]
    capsys.readouterr()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the AppImage is Linux's, and so is /proc/self/fd")
def test_the_program_started_in_the_place_of_the_process_does_not_hold_the_descriptor_of_the_old_mount(tmp_path: Path) -> None:
    """For real, in a child process: it holds the read end of a pipe it was handed, as the program
    of a mounted AppImage does, and starts another program in its place. The pipe is open until the
    exec (the mount is there while the old program runs) and closed in the new program (the mount
    goes), whose writer then finds no reader."""
    read, write = os.pipe()
    program = textwrap.dedent("""
        import os, sys
        from neoaprs import selfreplace
        held = int(sys.argv[1])
        selfreplace.close_inherited()
        os.fstat(held)
        print("open until the exec", flush=True)
        after = "import os, sys\\ntry:\\n    os.fstat(int(sys.argv[1]))\\n    print('still open')\\nexcept OSError:\\n    print('closed by the exec')"
        selfreplace.reexec([sys.executable, "-c", after, str(held)], environ={})
    """)
    try:
        done = subprocess.run([sys.executable, "-c", program, str(read)], pass_fds=(read,), capture_output=True, text=True, timeout=60, cwd=Path(__file__).resolve().parent.parent)
    finally:
        os.close(read)
    assert done.stdout.split("\n")[:2] == ["open until the exec", "closed by the exec"], done.stderr
    with pytest.raises(BrokenPipeError):
        os.write(write, b"x")
    os.close(write)


def test_a_new_version_that_cannot_be_started_and_an_old_one_that_cannot_either_say_so_and_return(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    image = tmp_path / "NeoAPRS.AppImage"
    image.write_bytes(b"new")
    (tmp_path / "NeoAPRS.AppImage.old").write_bytes(b"old")
    tried: list[bytes] = []

    def execv(path: str, argv: list[str]) -> None:
        tried.append(Path(path).read_bytes())
        raise OSError(8, "Exec format error")

    selfreplace.reexec([str(image), "run"], execv, close=lambda: None, environ={})
    assert tried == [b"new", b"old"], "(the new file first, then the one that was put back)"
    err = capsys.readouterr().err
    assert "the new version could not be started" in err and "the old version could not be started either" in err


def test_a_new_version_that_cannot_be_started_when_no_old_one_was_kept_ends_with_the_one_message(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    image = tmp_path / "NeoAPRS.AppImage"
    image.write_bytes(b"new")
    tried: list[str] = []

    def execv(path: str, argv: list[str]) -> None:
        tried.append(path)
        raise OSError(13, "Permission denied")

    selfreplace.reexec([str(image)], execv, close=lambda: None, environ={})
    err = capsys.readouterr().err
    assert tried == [str(image)] and "the new version could not be started" in err and "either" not in err


def test_an_old_version_that_cannot_be_put_back_is_said_too(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    image = tmp_path / "NeoAPRS.AppImage"
    image.write_bytes(b"new")
    (tmp_path / "NeoAPRS.AppImage.old").write_bytes(b"old")

    def no_replace(source: object, target: object) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(selfreplace.os, "replace", no_replace)
    selfreplace.reexec([str(image)], lambda path, argv: (_ for _ in ()).throw(OSError(8, "Exec format error")), close=lambda: None, environ={})
    assert "the old version could not be started either (" in capsys.readouterr().err
