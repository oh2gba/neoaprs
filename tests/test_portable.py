"""What the process layer does differently on Windows, as far as a Linux run can show it: the one-daemon lock (a fake `msvcrt` stands in for the real one), the files that are synced, the page's path rules
for a path with backslashes."""
import os
import sys
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from types import SimpleNamespace

import pytest

from neoaprs import durable, instancelock
from neoaprs.instancelock import LOCK_NAME, AlreadyRunning, InstanceLock
from neoaprs.web.pagefiles import is_hashed_asset
from neoaprs.web.pagesnapshot import is_hidden


# ---- the lock of the data folder

def test_a_second_lock_on_the_same_folder_is_refused_until_the_first_lets_go(tmp_path: Path) -> None:
    first, second = InstanceLock(tmp_path), InstanceLock(tmp_path)
    first.acquire()
    first.acquire()                                                  # (taken twice, held once)
    with pytest.raises(AlreadyRunning) as refused:
        second.acquire()
    assert str(tmp_path) in str(refused.value) and "--data" in str(refused.value)
    first.release()
    second.acquire()
    second.release()
    second.release()
    assert (tmp_path / LOCK_NAME).is_file(), "the file stays"


def test_a_lock_on_another_folder_is_not_in_the_way(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    one, other = InstanceLock(tmp_path / "a"), InstanceLock(tmp_path / "b")
    one.acquire()
    other.acquire()
    one.release()
    other.release()


def test_the_lock_file_is_private_and_not_inherited_by_a_child(tmp_path: Path) -> None:
    lock = InstanceLock(tmp_path)
    lock.acquire()
    if sys.platform != "win32":
        assert (tmp_path / LOCK_NAME).stat().st_mode & 0o077 == 0
    assert lock._fd is not None and not os.get_inheritable(lock._fd), "a program the daemon starts must not keep the lock after the daemon is gone"
    lock.release()


class FakeMsvcrt:
    """msvcrt.locking as Windows has it: a byte that is locked once, and the error of a lock that is held."""
    LK_NBLCK, LK_UNLCK = 2, 0

    def __init__(self) -> None:
        self.held: set[int] = set()
        self.calls: list[tuple[int, int, int]] = []

    def locking(self, fd: int, mode: int, size: int) -> None:
        self.calls.append((fd, mode, size))
        if mode == self.LK_NBLCK:
            if self.held:
                raise PermissionError(13, "Permission denied")
            self.held.add(fd)
        else:
            self.held.discard(fd)


def test_on_windows_the_lock_is_one_byte_of_the_file_taken_without_waiting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeMsvcrt()
    monkeypatch.setattr(instancelock, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setitem(sys.modules, "msvcrt", fake)
    first, second = InstanceLock(tmp_path), InstanceLock(tmp_path)
    first.acquire()
    assert [(mode, size) for _, mode, size in fake.calls] == [(fake.LK_NBLCK, 1)]
    with pytest.raises(AlreadyRunning):
        second.acquire()
    first.release()
    assert fake.calls[-1][1:] == (fake.LK_UNLCK, 1) and not fake.held
    second.acquire()
    second.release()


# ---- what is synced

@pytest.mark.skipif(sys.platform == "win32", reason="Windows opens the file for writing: the next test")
def test_on_linux_a_file_is_synced_read_only_and_a_folder_is_synced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[tuple[str, int]] = []
    real = os.open
    monkeypatch.setattr(os, "open", lambda path, flags, *a, **k: (opened.append((Path(path).name, flags)), real(path, flags, *a, **k))[1])
    (tmp_path / "f").write_bytes(b"x")
    durable.fsync_file(tmp_path / "f")
    durable.fsync_dir(tmp_path)
    assert opened == [("f", os.O_RDONLY), (tmp_path.name, os.O_RDONLY)]


def test_on_windows_a_file_is_synced_opened_for_writing_and_a_folder_is_not_opened(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[tuple[str, int]] = []
    real = os.open
    monkeypatch.setattr(durable, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(os, "open", lambda path, flags, *a, **k: (opened.append((Path(path).name, flags)), real(path, flags & ~getattr(os, "O_BINARY", 0), *a, **k))[1])
    (tmp_path / "f").write_bytes(b"x")
    durable.fsync_file(tmp_path / "f")
    durable.fsync_dir(tmp_path)
    assert len(opened) == 1 and opened[0][0] == "f" and opened[0][1] & os.O_RDWR, "a read-only descriptor cannot be flushed there, and a folder cannot be opened"


# ---- the page's path rules do not depend on the separator

@pytest.mark.parametrize("flavour", [PurePosixPath, PureWindowsPath])
@pytest.mark.parametrize("name, hidden", [
    ("index.html", False), ("assets/index-abc.js", False), (".env", True), (".git/config", True), ("assets/.hidden/x.js", True), ("a/.b", True),
    ("assets/index-abc.js.map", True), ("x.map", True), ("a.mapx", False), ("folder.map/x.js", False)])
def test_a_dot_name_anywhere_in_the_path_and_a_source_map_are_hidden(flavour: type[PurePath], name: str, hidden: bool) -> None:
    assert is_hidden(flavour(name)) is hidden


@pytest.mark.parametrize("name", [r"a\.hidden\x.js", r".git\config", r"assets\.env"])
def test_a_windows_path_with_backslashes_is_split_into_its_parts(name: str) -> None:
    assert is_hidden(PureWindowsPath(name))


@pytest.mark.parametrize("flavour", [PurePosixPath, PureWindowsPath])
def test_only_a_file_under_assets_is_a_hashed_asset(flavour: type[PurePath]) -> None:
    assert is_hashed_asset(flavour("assets/index-abc.js")) and is_hashed_asset(flavour("assets/sub/x.js"))
    assert not is_hashed_asset(flavour("index.html")) and not is_hashed_asset(flavour("assets")) and not is_hashed_asset(flavour("assetsx/a.js")) and not is_hashed_asset(flavour("x/assets/a.js"))


def test_windows_separators_are_the_assets_rule_too() -> None:
    assert is_hashed_asset(PureWindowsPath(r"assets\index-abc.js")) and not is_hashed_asset(PureWindowsPath(r"sub\assets\index-abc.js"))
