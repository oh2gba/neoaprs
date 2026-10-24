"""How Update now puts a file of the release in place once its SHA-256 has been checked (neoaprs/services/selfupdate.py does the download and the check), for the kinds where the daemon can do it itself:

    windows-installer   the installer is run silently and detached from the daemon (`installer_argv`), from `update/` of the data folder, where the installer of an earlier update is deleted first. Like any update over a running NeoAPRS it ends the app and the daemon first; its `[Run]` entries for a silent update
                        start again what was running (the app when one held the data folder, else the daemon alone) on the same data folder (packaging/windows/neoaprs.iss)
    appimage            the new file is made executable and renamed over the file this runs from, the old one kept beside it as `<file>.old` (a hard link, else a copy) until the new version has started; then the
                        daemon ends and starts the file again with the arguments it had (neoaprs/selfreplace.py, after the daemon has let go of everything; the process stays the same, so a service manager sees no end)

Anything else gets no installer and the page shows the steps instead. `NEOAPRS_INSTALL_KIND` (a simulated kind, for development: neoaprs/cli/installkind.py) gets a rehearsal: every step but the last, the file
deleted instead of installed. `NEOAPRS_UPDATE_FROM` (the release folder of a fake server on the loopback) is used instead of GitHub only together with a simulated kind, or with `NEOAPRS_UPDATE_TEST=1`, the switch of the
end-to-end test of the release workflow, which updates a real install from it (scripts/update-e2e.py); an address that is not http(s) on 127.0.0.1 or localhost is never used."""
import logging
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import urlsplit

from neoaprs.instancelock import APP_LOCK_NAME, is_held
from neoaprs.selfreplace import keep_old
from neoaprs.updateasset import RELEASES, SELF_UPDATING, url_allowed
from neoaprs.versions import InstallInfo

log = logging.getLogger("neoaprs.update")

UPDATE_FOLDER = "update"                        # in the data folder: the installer that was downloaded, and its log
DETACHED = 0x00000008 | 0x00000200 | 0x08000000      # DETACHED_PROCESS, CREATE_NEW_PROCESS_GROUP, CREATE_NO_WINDOW
BREAKAWAY = 0x01000000                          # CREATE_BREAKAWAY_FROM_JOB: the installer outlives a job the daemon may be part of
ENV_KIND = "NEOAPRS_INSTALL_KIND"
ENV_FROM = "NEOAPRS_UPDATE_FROM"
ENV_TEST = "NEOAPRS_UPDATE_TEST"                 # "1": a real install may be updated from NEOAPRS_UPDATE_FROM (the end-to-end test only)
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})
Restart = Callable[[list[str]], None]           # the daemon ends and this command line is run in its place


class InstallError(Exception):
    """The file could not be put in place, or the update could not be started; the text says why."""


class Installer(Protocol):
    @property
    def folder(self) -> Path:
        """Where the file is downloaded to."""
        ...

    def blocked(self) -> str:
        """Why the update cannot be done here, in a sentence; empty when it can."""
        ...

    def install(self, file: Path, name: str, version: str) -> None:
        """Puts the checked file `file` (the release's `name`) in place and starts what restarts NeoAPRS; InstallError when it cannot. Runs on a thread of its own."""
        ...


def installer_argv(installer: Path, data_dir: Path, restart: Literal["app", "daemon"], log_file: Path) -> list[str]:
    """The installer's command line for an update with nobody at the keyboard: no window, no question, no restart of Windows. The daemon and the app are ended by the installer's own code, before it replaces a
    file (so Windows' Restart Manager is not asked to close them), and `NEOAPRSRESTART` and `NEOAPRSDATA` say what it starts again after (packaging/windows/neoaprs.iss)."""
    return [str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOCLOSEAPPLICATIONS", "/CURRENTUSER", "/SP-", f"/LOG={log_file}", f"/NEOAPRSRESTART={restart}", f"/NEOAPRSDATA={data_dir}"]


def launch_detached(argv: list[str]) -> None:
    """Starts a program that outlives the daemon (Windows): no console, a process group of its own, out of the daemon's job where the job allows it."""
    devnull = subprocess.DEVNULL
    try:
        subprocess.Popen(argv, creationflags=DETACHED | BREAKAWAY, close_fds=True, stdin=devnull, stdout=devnull, stderr=devnull)
    except OSError:
        subprocess.Popen(argv, creationflags=DETACHED, close_fds=True, stdin=devnull, stdout=devnull, stderr=devnull)       # (a job that allows no breakaway)


class WindowsSetup:
    def __init__(self, data_dir: Path, launch: Callable[[list[str]], None] = launch_detached, app_running: Callable[[Path], bool] | None = None) -> None:
        self.data_dir = data_dir
        self._folder = data_dir / UPDATE_FOLDER
        self._launch = launch
        self._app_running = app_running or (lambda data: is_held(data, APP_LOCK_NAME))

    @property
    def folder(self) -> Path:
        return self._folder

    def blocked(self) -> str:
        return ""

    def remove_earlier(self, name: str) -> None:
        """The installers of earlier updates go (each is some 50 MB); the one of this update stays beside its log until the next."""
        for earlier in self._folder.glob("NeoAPRS-Setup-*.exe"):
            if earlier.name != name:
                try:
                    earlier.unlink()
                except OSError as e:
                    log.warning("Update now: the installer of an earlier update, %s, could not be deleted: %s", earlier, e)

    def command(self, installer: Path) -> list[str]:
        restart: Literal["app", "daemon"] = "app" if self._app_running(self.data_dir) else "daemon"
        return installer_argv(installer, self.data_dir, restart, self._folder / "install.log")

    def install(self, file: Path, name: str, version: str) -> None:
        installer = self._folder / name
        self.remove_earlier(name)
        try:
            os.replace(file, installer)
            argv = self.command(installer)
            log.info("Update now: starting the installer of %s: %s", version, subprocess.list2cmdline(argv))
            self._launch(argv)
        except OSError as e:
            raise InstallError(f"the installer could not be started: {e}") from None


class AppImageSwap:
    def __init__(self, appimage: Path, argv: list[str], restart: Restart) -> None:
        self.appimage = appimage
        self.argv = argv                        # the arguments the AppImage was started with
        self._restart = restart

    @property
    def folder(self) -> Path:
        return self.appimage.parent

    def blocked(self) -> str:
        if not os.access(self.folder, os.W_OK) or not os.access(self.appimage, os.W_OK):
            return f"the folder of the AppImage, {self.folder}, cannot be written by this user"
        return ""

    def install(self, file: Path, name: str, version: str) -> None:
        try:
            os.chmod(file, 0o755)
            keep_old(self.appimage)
            os.replace(file, self.appimage)
        except OSError as e:
            raise InstallError(f"the new AppImage could not be put in the place of {self.appimage.name}: {e}") from None
        log.info("Update now: %s is now %s; NeoAPRS starts it again", self.appimage, version)
        self._restart([str(self.appimage), *self.argv])


class Rehearsal:
    """For a simulated install kind: the file was downloaded and checked, and is deleted; nothing is installed and nothing restarts."""

    def __init__(self, data_dir: Path) -> None:
        self._folder = data_dir / UPDATE_FOLDER

    @property
    def folder(self) -> Path:
        return self._folder

    def blocked(self) -> str:
        return ""

    def install(self, file: Path, name: str, version: str) -> None:
        log.warning("Update now: the install kind is simulated (%s): %s was checked and is deleted; nothing is installed", ENV_KIND, name)
        file.unlink(missing_ok=True)


def installer_for(install: InstallInfo, data_dir: Path, restart: Restart, environ: Mapping[str, str] = os.environ, argv: list[str] | None = None, platform: str = sys.platform) -> Installer | None:
    """The installer of this copy, None where the page shows the steps instead."""
    if environ.get(ENV_KIND):
        return Rehearsal(data_dir) if install.kind in SELF_UPDATING else None
    if install.kind == "windows-installer" and platform == "win32":
        return WindowsSetup(data_dir)
    if install.kind == "appimage" and install.appimage and platform.startswith("linux"):
        return AppImageSwap(Path(install.appimage), sys.argv[1:] if argv is None else argv, restart)
    return None


def loopback_folder(text: str) -> str:
    """`text` without its trailing slash when it is the address of a folder of a server on this computer: http or https, the host 127.0.0.1 or localhost, no user, query or fragment; else empty."""
    base = text.strip().rstrip("/")
    try:
        parts = urlsplit(base)
        _ = parts.port                                  # (a port that is not a number raises)
    except ValueError:
        return ""
    if parts.scheme not in ("http", "https") or (parts.hostname or "") not in LOOPBACK_HOSTS or "@" in parts.netloc or parts.query or parts.fragment or any(c.isspace() for c in base):
        return ""
    return base


def release_source(environ: Mapping[str, str] = os.environ) -> tuple[str, Callable[[str], bool]]:
    """Where the release's files are (the folder that holds a folder `v<version>` for each release) and the addresses a download may go to: GitHub; or the folder of `NEOAPRS_UPDATE_FROM` alone, for a simulated kind
    or with `NEOAPRS_UPDATE_TEST=1`, and only when it is on this computer."""
    wanted = bool(environ.get(ENV_KIND)) or environ.get(ENV_TEST) == "1"
    base = loopback_folder(environ.get(ENV_FROM, "")) if wanted else ""
    if base:
        log.warning("Update now downloads from %s, not from GitHub (%s)", base, ENV_TEST if environ.get(ENV_TEST) == "1" else ENV_KIND)
        return base, lambda url: url.startswith(base + "/")
    return RELEASES, url_allowed
