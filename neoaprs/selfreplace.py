"""The file operations of Update now for an AppImage, which the daemon's process does at its end and at its start as well as the update itself (neoaprs/services/selfinstall.py): the old file kept beside the new one
as `<file>.old` until the new version has started, the old one put back when the new one cannot be started, and the exec of the new file in the place of this process."""
import logging
import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger("neoaprs.update")


def keep_old(path: Path) -> Path:
    """`<path>.old`, the same file as `path`: a hard link, or a copy on a file system that has none."""
    old = path.with_name(path.name + ".old")
    old.unlink(missing_ok=True)
    try:
        os.link(path, old)
    except OSError:
        shutil.copy2(path, old)
    return old


def restore(appimage: Path) -> bool:
    """Puts the kept `<file>.old` back in the place of the file; False when there is none."""
    old = appimage.with_name(appimage.name + ".old")
    if not old.is_file():
        return False
    os.replace(old, appimage)
    return True


def remove_old(appimage: str | None) -> None:
    """The new version is running: the old AppImage kept beside it goes."""
    if appimage:
        old = Path(appimage + ".old")
        try:
            old.unlink(missing_ok=True)
        except OSError as e:
            log.warning("the old AppImage %s could not be deleted: %s", old, e)


def close_inherited() -> None:
    """Closes every descriptor above stderr before an exec: an AppImage's runtime leaves one of its mount open in the program it starts, and the old mount goes with it."""
    if sys.platform != "win32":
        os.closerange(3, 65536)


def reexec(argv: list[str], execv: Callable[[str, list[str]], None] = os.execv, close: Callable[[], None] = close_inherited) -> None:
    """Runs `argv` (the AppImage file and the arguments this process had) in the place of this process, which has let go of everything already: the log, the database, the lock, the radio, the page's port.
    When the new file cannot be started, the kept old one is put back and started. Returns only when neither could be."""
    logging.shutdown()
    close()
    try:
        execv(argv[0], argv)
    except OSError as e:
        print(f"neoaprs: the new version could not be started ({e}); the old one is put back", file=sys.stderr)
    else:
        return                                  # (only a stand-in of execv returns)
    try:
        if restore(Path(argv[0])):
            execv(argv[0], argv)
    except OSError as e:
        print(f"neoaprs: the old version could not be started either ({e})", file=sys.stderr)
