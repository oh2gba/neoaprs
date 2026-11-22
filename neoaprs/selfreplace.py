"""File operations for replacing a running AppImage: keep the old file, restore it, exec the new."""
import contextlib
import logging
import os
import shutil
import sys
from collections.abc import Callable, MutableMapping
from pathlib import Path

log = logging.getLogger("neoaprs.update")


def keep_old(path: Path) -> Path:
    """Keep `path` as `<path>.old` (a hard link, else a copy); return it."""
    old = path.with_name(path.name + ".old")
    old.unlink(missing_ok=True)
    try:
        os.link(path, old)
    except OSError:
        shutil.copy2(path, old)
    return old


def restore(appimage: Path) -> bool:
    """Put `<file>.old` back; return False if there is none."""
    old = appimage.with_name(appimage.name + ".old")
    if not old.is_file():
        return False
    os.replace(old, appimage)
    return True


def remove_old(appimage: str | None) -> None:
    """Delete the old AppImage kept beside the running new one."""
    if appimage:
        old = Path(appimage + ".old")
        try:
            old.unlink(missing_ok=True)
        except OSError as e:
            log.warning("the old AppImage %s could not be deleted: %s", old, e)


FD_FOLDER = "/proc/self/fd"


def close_inherited(folder: str = FD_FOLDER) -> None:
    """Mark every descriptor above stderr close-on-exec, which ends the old mount at the exec."""
    if sys.platform != "win32":
        try:
            open_now = [int(name) for name in os.listdir(folder)]
        except (OSError, ValueError):
            os.closerange(3, 65536)
            return
        for fd in open_now:
            if fd > 2:
                with contextlib.suppress(OSError):
                    os.set_inheritable(fd, False)


EXTRACT_AND_RUN = "APPIMAGE_EXTRACT_AND_RUN"


def keep_extract_and_run(environ: MutableMapping[str, str], is_mount: Callable[[str], bool] = os.path.ismount) -> None:
    """Set `APPIMAGE_EXTRACT_AND_RUN=1` if `$APPDIR` is no mount; call with descriptors open."""
    appdir = environ.get("APPDIR")
    if appdir and environ.get("APPIMAGE") and not is_mount(appdir):
        environ[EXTRACT_AND_RUN] = "1"


NO_CLEANUP = "NO_CLEANUP"
LEFT_TO_THE_STARTER = "neoaprs"


def leave_the_folder(environ: MutableMapping[str, str], argv0: str, is_mount: Callable[[str], bool] = os.path.ismount) -> None:
    """Set `NO_CLEANUP` for the daemon (`argv0`) started from this unpacked AppImage."""
    appdir, appimage = environ.get("APPDIR"), environ.get("APPIMAGE")
    if appdir and appimage and os.path.abspath(appimage) == os.path.abspath(argv0) and not is_mount(appdir):
        environ.setdefault(NO_CLEANUP, LEFT_TO_THE_STARTER)


def reexec(argv: list[str], execv: Callable[[str, list[str]], None] | None = None, close: Callable[[], None] = close_inherited, environ: MutableMapping[str, str] = os.environ,
           is_mount: Callable[[str], bool] = os.path.ismount, put_back: bool = True) -> None:
    """Run `argv` in place of this process; if it cannot start, restore and start the old file.

    The desktop app passes `put_back` False. Return only if neither starts.
    """
    execv = execv or os.execv
    logging.shutdown()
    keep_extract_and_run(environ, is_mount)
    left = environ.get(NO_CLEANUP) == LEFT_TO_THE_STARTER
    if left:
        del environ[NO_CLEANUP]
    close()
    try:
        execv(argv[0], argv)
    except OSError as e:
        print(f"neoaprs: the new version could not be started ({e}){'; the old one is put back' if put_back else ''}", file=sys.stderr)
    else:
        return
    if not put_back:
        return
    if left:
        environ[NO_CLEANUP] = LEFT_TO_THE_STARTER
    try:
        if restore(Path(argv[0])):
            execv(argv[0], argv)
    except OSError as e:
        print(f"neoaprs: the old version could not be started either ({e})", file=sys.stderr)
