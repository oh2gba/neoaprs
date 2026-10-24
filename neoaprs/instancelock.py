"""One daemon to a data folder: two of them would both write the database and both answer the same messages on the air. The lock is a file in the data folder that the program holds for as long
as it runs (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows); the system lets go of it when the process ends, however it ends, so a crash leaves nothing to clean up."""
import os
import sys
from pathlib import Path

LOCK_NAME = "neoaprs.lock"
APP_LOCK_NAME = "neoaprs-app.lock"           # the desktop app's own lock of the data folder (neoaprs/desktop/single.py)


class AlreadyRunning(Exception):
    """Another NeoAPRS holds the lock of the data folder."""


class InstanceLock:
    def __init__(self, data_dir: Path, name: str = LOCK_NAME) -> None:
        self.path = data_dir / name
        self._fd: int | None = None

    def acquire(self) -> None:
        """Takes the lock or raises AlreadyRunning. Taken twice by one object it is taken once."""
        if self._fd is not None:
            return
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o600)      # (not inherited by a program the daemon starts: Python's descriptors are not)
        try:
            self._lock(fd)
        except OSError as e:
            os.close(fd)
            raise AlreadyRunning(f"another NeoAPRS is already running with the data folder {self.path.parent} (lock file {self.path.name}); stop it first, or give this one another folder with --data") from e
        self._fd = fd

    @staticmethod
    def _lock(fd: int) -> None:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)           # the first byte of the file, which may be beyond its end; fails at once when it is held
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def release(self) -> None:
        """Lets go (the lock file stays: removing it would let a second program lock a file that a third one is about to)."""
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


def is_held(data_dir: Path, name: str = LOCK_NAME) -> bool:
    """Whether a program holds the lock `name` of the data folder (the lock is taken for a moment, and let go, to find out; a folder with no lock file has no such program)."""
    if not (data_dir / name).is_file():
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
