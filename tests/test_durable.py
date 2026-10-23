"""A folder that cannot be synced is no reason to lose a copy (neoaprs/durable.py): the sync of the folder that holds a name is a best effort, and the descriptor is closed whatever happened. What is synced on each
system is in tests/test_portable.py."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from neoaprs import durable

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="a folder is not synced on Windows")


@posix_only
def test_a_folder_that_cannot_be_opened_is_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(path: object, flags: int) -> int:
        raise PermissionError("no")
    monkeypatch.setattr(durable, "os", SimpleNamespace(O_RDONLY=os.O_RDONLY, open=refuse))
    durable.fsync_dir(tmp_path)                                      # (does not raise)


@posix_only
def test_a_folder_that_cannot_be_synced_is_still_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[int] = []

    def no_sync(fd: int) -> None:
        raise OSError("the file system does not sync folders")
    monkeypatch.setattr(durable, "os", SimpleNamespace(O_RDONLY=os.O_RDONLY, open=lambda path, flags: 77, fsync=no_sync, close=closed.append))
    durable.fsync_dir(tmp_path)
    assert closed == [77]
