"""Durable file replacement: sync the file, rename it, then sync the folder holding the name.

After a power cut the name is then never present without the data. Windows cannot sync a folder
and syncs only a file opened for writing."""
import os
import sys
from pathlib import Path


def fsync_file(path: Path) -> None:
    fd = os.open(path, os.O_RDWR | getattr(os, "O_BINARY", 0)) if sys.platform == "win32" else os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def fsync_dir(path: Path) -> None:
    if sys.platform != "win32":
        _sync_folder(path)


def _sync_folder(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)
