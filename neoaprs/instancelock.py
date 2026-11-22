"""One daemon per data folder, enforced by a lock file held while the program runs.

The lock is `fcntl.flock` on POSIX and `msvcrt.locking` on Windows; the system releases it when the
process ends, so a crash leaves nothing to clean up."""

import os
import sys
from pathlib import Path

LOCK_NAME = "neoaprs.lock"
APP_LOCK_NAME = "neoaprs-app.lock"  # the desktop app's lock of the data folder


class AlreadyRunning(Exception):
    """Another NeoAPRS holds the lock of the data folder."""


class InstanceLock:
    def __init__(self, data_dir: Path, name: str = LOCK_NAME) -> None:
        self.path = data_dir / name
        self._fd: int | None = None

    def acquire(self) -> None:
        """Take the lock or raise AlreadyRunning. A second call on the same object does nothing."""
        if self._fd is not None:
            return
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o600)
        try:
            self._lock(fd)
        except OSError as e:
            os.close(fd)
            raise AlreadyRunning(
                f"another NeoAPRS is already running with the data folder {self.path.parent} (lock file {self.path.name}); stop it first, or give this one another folder with --data"
            ) from e
        self._fd = fd

    @staticmethod
    def _lock(fd: int) -> None:
        if sys.platform == "win32":
            import msvcrt

            # the first byte, even past the end of the file; fails at once if held
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def release(self) -> None:
        """Release the lock. The file stays, or two programs could lock different files."""
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        finally:
            os.close(fd)


def is_file(path: Path) -> bool:
    """Return whether `path` is a file; False if a parent folder cannot be read."""
    try:
        return path.is_file()
    except OSError:
        return False


def is_held(data_dir: Path, name: str = LOCK_NAME) -> bool:
    """Return whether a program holds lock `name`; found out by taking and releasing it."""
    if not is_file(data_dir / name):
        return False
    lock = InstanceLock(data_dir, name)
    try:
        lock.acquire()
    except AlreadyRunning:
        return True
    except OSError:
        return False
    lock.release()
    return False
