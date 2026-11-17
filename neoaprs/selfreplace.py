"""The file operations of Update now for an AppImage, which the daemon's process does at its end and at its start as well as the update itself (neoaprs/services/selfinstall.py): the old file kept beside the new one
as `<file>.old` until the new version has started, the old one put back when the new one cannot be started, and the exec of the new file in the place of this process.

An AppImage started with `--appimage-extract-and-run` (a system without FUSE) runs from a folder its runtime unpacked it into, not from a mount; the runtime takes the flag away before the program sees it. The
file is executed again with `APPIMAGE_EXTRACT_AND_RUN=1` in the environment, which the runtime takes for the flag: without it the new runtime tries to mount the file, cannot, and NeoAPRS is gone. One that
was mounted is executed again without it, and is mounted again: unpacked, it is some 430 MB in the temporary folder, which is memory on many systems.

The mount lives as long as a descriptor does: the runtime (AppImage/type2-runtime, src/runtime/runtime.c; the one scripts/build-appimage puts in front of the image) hands the program it starts the read end
of a pipe, and the process that serves the mount writes into that pipe until the write fails, then ends itself, unmounts and removes the folder. So the question "was this mounted?" is asked while this
process still holds its descriptors, and they are let go of by the exec itself (close-on-exec), not before it: asked after the close, as it was up to 0.20.1, the answer for a mounted image was "no",
and the update of a mounted AppImage from 0.20.0 to 0.20.1 came back unpacked (16 Nov 2026)."""
import contextlib
import logging
import os
import shutil
import sys
from collections.abc import Callable, MutableMapping
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


FD_FOLDER = "/proc/self/fd"


def close_inherited(folder: str = FD_FOLDER) -> None:
    """Has the exec close every descriptor above stderr: an AppImage's runtime leaves those of its mount open in the program it starts, and the old mount goes with them. They are marked close-on-exec,
    not closed: the mount, which this program runs from, is there until the new file has taken the place of the process, and still there when it could not be started. Where the descriptors
    cannot be listed (no /proc) they are closed, as they were up to 0.20.1."""
    if sys.platform != "win32":
        try:
            open_now = [int(name) for name in os.listdir(folder)]
        except (OSError, ValueError):
            os.closerange(3, 65536)
            return
        for fd in open_now:
            if fd > 2:
                with contextlib.suppress(OSError):      # (the one the listing itself used is closed again)
                    os.set_inheritable(fd, False)


EXTRACT_AND_RUN = "APPIMAGE_EXTRACT_AND_RUN"


def keep_extract_and_run(environ: MutableMapping[str, str], is_mount: Callable[[str], bool] = os.path.ismount) -> None:
    """Sets `APPIMAGE_EXTRACT_AND_RUN=1` when the AppImage this runs from was unpacked rather than mounted (its `$APPDIR` is no mount point), so that the file executed next runs the same way. Asked while
    the descriptors of the mount are open: without them there is no mount to find."""
    appdir = environ.get("APPDIR")
    if appdir and environ.get("APPIMAGE") and not is_mount(appdir):
        environ[EXTRACT_AND_RUN] = "1"


def reexec(argv: list[str], execv: Callable[[str, list[str]], None] = os.execv, close: Callable[[], None] = close_inherited, environ: MutableMapping[str, str] = os.environ,
           is_mount: Callable[[str], bool] = os.path.ismount, put_back: bool = True) -> None:
    """Runs `argv` (the AppImage file and the arguments this process had) in the place of this process, which has let go of everything already: the log, the database, the lock, the radio, the page's port.
    When the new file cannot be started, the kept old one is put back and started (`put_back`; the desktop app, started again after its daemon, puts nothing back: the daemon runs the new file). Returns only
    when neither could be."""
    logging.shutdown()
    keep_extract_and_run(environ, is_mount)         # (before the descriptors go: the mount goes with them)
    close()
    try:
        execv(argv[0], argv)
    except OSError as e:
        print(f"neoaprs: the new version could not be started ({e}){'; the old one is put back' if put_back else ''}", file=sys.stderr)
    else:
        return                                  # (only a stand-in of execv returns)
    if not put_back:
        return
    try:
        if restore(Path(argv[0])):
            execv(argv[0], argv)
    except OSError as e:
        print(f"neoaprs: the old version could not be started either ({e})", file=sys.stderr)
