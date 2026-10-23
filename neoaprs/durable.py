"""What is on the disk before it has its name: a file is synced, then renamed, then the folder that holds the name is synced, so that after a power cut the name is never there
without the data (docs/ARCHITECTURE.md, "The database actor"). The copies of the database are written that way.

Windows cannot open a folder to sync it (NTFS journals its own metadata, so the rename is as durable as the system makes it), and it syncs only a file opened for writing."""
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
