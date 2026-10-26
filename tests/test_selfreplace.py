"""The file operations of Update now for an AppImage (neoaprs/selfreplace.py) where tests/test_selfinstall.py does not look: an old file that cannot be deleted, the descriptors closed before the exec (never for real here,
and not on Windows), and a new version that cannot be started followed by an old one that cannot either."""
import os
from pathlib import Path

import pytest

from neoaprs import selfreplace


def test_an_old_appimage_that_cannot_be_deleted_is_said_and_not_an_error(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    image = tmp_path / "NeoAPRS.AppImage"
    (tmp_path / "NeoAPRS.AppImage.old").mkdir()                        # (a name that unlink cannot take: a folder)
    caplog.set_level("WARNING", logger="neoaprs.update")
    selfreplace.remove_old(str(image))
    assert "the old AppImage" in caplog.text and "could not be deleted" in caplog.text


def test_every_descriptor_above_stderr_is_closed_before_the_exec_except_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "closerange", lambda low, high: closed.append((low, high)))
    monkeypatch.setattr(selfreplace.sys, "platform", "linux")
    selfreplace.close_inherited()
    assert closed == [(3, 65536)]
    monkeypatch.setattr(selfreplace.sys, "platform", "win32")
    selfreplace.close_inherited()
    assert closed == [(3, 65536)]


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
