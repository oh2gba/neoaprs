"""How Update now installs a checked release file (selfupdate.py downloads and verifies it).

The Windows installer runs silently and detached; an AppImage is renamed over the running file and
restarted. Other kinds get no installer. Two environment variables let a test rehearse an update.
"""
import contextlib
import logging
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol
from urllib.parse import urlsplit

from neoaprs import stopfile
from neoaprs.instancelock import APP_LOCK_NAME, is_held
from neoaprs.selfreplace import keep_old
from neoaprs.updateasset import RELEASES, SELF_UPDATING, public_key, url_allowed
from neoaprs.versions import InstallInfo

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

log = logging.getLogger("neoaprs.update")

UPDATE_FOLDER = "update"
# DETACHED_PROCESS, CREATE_NEW_PROCESS_GROUP, CREATE_NO_WINDOW
DETACHED = 0x00000008 | 0x00000200 | 0x08000000
# CREATE_BREAKAWAY_FROM_JOB: the installer outlives a job the daemon may belong to
BREAKAWAY = 0x01000000
ENV_KIND = "NEOAPRS_INSTALL_KIND"
ENV_FROM = "NEOAPRS_UPDATE_FROM"
ENV_KEY = "NEOAPRS_UPDATE_KEY"
ENV_TEST = "NEOAPRS_UPDATE_TEST"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})
Restart = Callable[[list[str]], None]


class InstallError(Exception):
    """The file could not be put in place or the update could not be started."""


class Installer(Protocol):
    @property
    def folder(self) -> Path:
        """Where the file is downloaded to."""
        ...

    def blocked(self) -> str:
        """Return why the update cannot be done here; empty when it can."""
        ...

    def install(self, file: Path, name: str, version: str) -> None:
        """Put the checked file in place and restart (in a thread); raise InstallError on failure."""
        ...


def installer_argv(installer: Path, data_dir: Path, restart: Literal["app", "daemon"], log_file: Path, encryption: bool = False) -> list[str]:
    """Return the installer's command line for an unattended update: silent, no Windows restart.

    The installer ends the daemon and app itself; the NEOAPRS* switches say what to start after."""
    return [str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOCLOSEAPPLICATIONS", "/CURRENTUSER", "/SP-", f"/LOG={log_file}", f"/NEOAPRSRESTART={restart}", f"/NEOAPRSDATA={data_dir}",
            *(["/NEOAPRSENCRYPTION=1"] if encryption else [])]


def launch_detached(argv: list[str]) -> None:
    """Start a program that outlives the daemon (Windows): no console, own group, no job."""
    devnull = subprocess.DEVNULL
    try:
        subprocess.Popen(argv, creationflags=DETACHED | BREAKAWAY, close_fds=True, stdin=devnull, stdout=devnull, stderr=devnull)
    except OSError:
        subprocess.Popen(argv, creationflags=DETACHED, close_fds=True, stdin=devnull, stdout=devnull, stderr=devnull)


class WindowsSetup:
    def __init__(self, data_dir: Path, launch: Callable[[list[str]], None] = launch_detached, app_running: Callable[[Path], bool] | None = None, encryption: bool = False,
                 leaving: Callable[[], None] | None = None) -> None:
        self.data_dir = data_dir
        self.encryption = encryption
        self._leaving = leaving or (lambda: None)
        self._folder = data_dir / UPDATE_FOLDER
        self._launch = launch
        self._app_running = app_running or (lambda data: is_held(data, APP_LOCK_NAME))

    @property
    def folder(self) -> Path:
        return self._folder

    def blocked(self) -> str:
        return ""

    def remove_earlier(self, name: str) -> None:
        """Delete earlier installers (about 50 MB each); this update's stays."""
        for earlier in self._folder.glob("NeoAPRS-Setup-*.exe"):
            if earlier.name != name:
                try:
                    earlier.unlink()
                except OSError as e:
                    log.warning("Update now: the installer of an earlier update, %s, could not be deleted: %s", earlier, e)

    def command(self, installer: Path) -> list[str]:
        restart: Literal["app", "daemon"] = "app" if self._app_running(self.data_dir) else "daemon"
        return installer_argv(installer, self.data_dir, restart, self._folder / "install.log", self.encryption)

    def install(self, file: Path, name: str, version: str) -> None:
        installer = self._folder / name
        self.remove_earlier(name)
        try:
            os.replace(file, installer)
            argv = self.command(installer)
            log.info("Update now: starting the installer of %s: %s", version, subprocess.list2cmdline(argv))
            self._leaving()
            try:
                self._launch(argv)
            except OSError:
                with contextlib.suppress(OSError):
                    # no installer, so no restart: the port note must not leak to the next start
                    stopfile.note_port(self.data_dir, 0)
                raise
        except OSError as e:
            raise InstallError(f"the installer could not be started: {e}") from None


class AppImageSwap:
    def __init__(self, appimage: Path, argv: list[str], restart: Restart) -> None:
        self.appimage = appimage
        self.argv = argv
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
            os.chmod(file, 0o755)  # noqa: S103  (a program: anyone may run it, only the owner may write)
            keep_old(self.appimage)
            os.replace(file, self.appimage)
        except OSError as e:
            raise InstallError(f"the new AppImage could not be put in the place of {self.appimage.name}: {e}") from None
        log.info("Update now: %s is now %s; NeoAPRS starts it again", self.appimage, version)
        self._restart([str(self.appimage), *self.argv])


class Rehearsal:
    """For a simulated kind: the checked file is deleted, nothing installed."""

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


def installer_for(install: InstallInfo, data_dir: Path, restart: Restart, environ: Mapping[str, str] = os.environ, argv: list[str] | None = None, platform: str = sys.platform,
                  encryption: bool = False, leaving: Callable[[], None] | None = None) -> Installer | None:
    """Return the installer of this copy, None where the page shows the steps instead.

    `leaving` is called before the Windows installer starts."""
    if environ.get(ENV_KIND):
        return Rehearsal(data_dir) if install.kind in SELF_UPDATING else None
    if install.kind == "windows-installer" and platform == "win32":
        return WindowsSetup(data_dir, encryption=encryption, leaving=leaving)
    if install.kind == "appimage" and install.appimage and platform.startswith("linux"):
        return AppImageSwap(Path(install.appimage), sys.argv[1:] if argv is None else argv, restart)
    return None


def loopback_folder(text: str) -> str:
    """Return `text` without a trailing slash if it is an http(s) folder on this host, else empty."""
    base = text.strip().rstrip("/")
    try:
        parts = urlsplit(base)
        # a non-numeric port raises here
        _ = parts.port
    except ValueError:
        return ""
    if parts.scheme not in ("http", "https") or (parts.hostname or "") not in LOOPBACK_HOSTS or "@" in parts.netloc or parts.query or parts.fragment or any(c.isspace() for c in base):
        return ""
    return base


def release_source(environ: Mapping[str, str] = os.environ) -> tuple[str, Callable[[str], bool]]:
    """Return the release folder (holding `v<version>` folders) and a check for allowed addresses.

    The fake folder replaces GitHub only for a simulated kind or `NEOAPRS_UPDATE_TEST=1`."""
    base = _fake_release(environ)
    if base:
        log.warning("Update now downloads from %s, not from GitHub (%s)", base, ENV_TEST if environ.get(ENV_TEST) == "1" else ENV_KIND)
        return base, lambda url: url.startswith(base + "/")
    return RELEASES, url_allowed


def _fake_release(environ: Mapping[str, str]) -> str:
    """Return the `NEOAPRS_UPDATE_FROM` folder when in effect, else empty."""
    wanted = bool(environ.get(ENV_KIND)) or environ.get(ENV_TEST) == "1"
    return loopback_folder(environ.get(ENV_FROM, "")) if wanted else ""


def release_key(environ: Mapping[str, str] = os.environ) -> "Ed25519PublicKey":
    """Return the key the SHA256SUMS signature must hold with: the project's.

    `NEOAPRS_UPDATE_KEY` counts only with the fake server."""
    text = environ.get(ENV_KEY, "")
    if text and _fake_release(environ):
        try:
            key = public_key(text)
        except ValueError as e:
            log.warning("%s is not taken: %s", ENV_KEY, e)
        else:
            log.warning("Update now believes the signature of the key of %s, not the project's", ENV_KEY)
            return key
    return public_key()
