"""Update now: on a click of the page (the command `update_now`), and never by itself, the daemon fetches the file of the release that updates this copy (neoaprs/updateasset.py) from the release of exactly the version
the update check announced, and SHA256SUMS of the same release with its signature. SHA256SUMS is believed only when the signature holds with the project's key for exactly that version (neoaprs/updateasset.py,
`signed_checksum`), and the file's SHA-256 must be the one it gives the file, or the file is deleted and nothing is installed. Then the installer of this kind of install
(neoaprs/services/selfinstall.py) puts it in place, and NeoAPRS restarts as the new version. A kind that has no installer (and one whose folder cannot be written) is not `supported`: the page shows the steps.

The steps are the `state`: `downloading` (SHA256SUMS and its signature first, then the file, with its percent), `verifying`, `installing`, `restarting` (the daemon is about to end; still running RESTART_GRACE_SEC later, the update
failed and says so), or `error` with the `problem` and a sentence of `detail`. Every way the signature can fail is the one problem `unverified`: whatever the cause (no signature in the release, one
that does not hold, a list that is not one or does not name the file once), what the operator can do is the same, and the log has the cause. A signature that could not be fetched (the connection failed, the server answered other than 404) is `download`, as SHA256SUMS is. `cancel()` ends a download and leaves nothing of it. `status()` is what the page is told (the topic `update`); `changed` is
emitted with every change of it."""
import asyncio
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from neoaprs.coded import CodedError
from neoaprs.signal import Signal
from neoaprs.tasks import TaskSet
from neoaprs.updateasset import CHECKSUMS, SIGNATURE, Unverified, asset_name, asset_url, public_key, signed_checksum
from neoaprs.updatedownload import Allowed, Cancelled, DownloadError, Progress, fetch_bytes, fetch_file, in_thread
from neoaprs.versions import InstallInfo

from .selfinstall import Installer, InstallError

log = logging.getLogger("neoaprs.update")

RESTART_GRACE_SEC = 300.0
TELL_SEC = 0.5                  # between `restarting` and the daemon's end: the page is told before its socket closes
NOT_THERE = 404                 # the answer for SHA256SUMS.sig that means the release has no signature (`unverified`); any other failure to fetch it is `download`
State = Literal["idle", "downloading", "verifying", "installing", "restarting", "error"]
Problem = Literal["", "download", "unverified", "checksum", "install", "no_restart"]
FetchSums = Callable[[str, Allowed], bytes]
FetchFile = Callable[[str, Path, Allowed, Progress, threading.Event], str]


@dataclass(frozen=True)
class UpdateStatus:
    supported: bool                     # this copy can update itself: the page offers Update now
    state: State
    version: str                        # the version being installed; empty while idle
    percent: int | None                 # of the download; None when the server did not say the size
    downloaded: int                     # bytes of the file so far
    total: int | None                   # the size of the file, when the server said it
    problem: Problem                    # what went wrong (state `error`); empty otherwise
    detail: str                         # the sentence that says it, for the log and the page's details; empty when all is well


IDLE = UpdateStatus(False, "idle", "", None, 0, None, "", "")


class UpdateNowError(CodedError):
    """`update_now` or `update_cancel` cannot be done now."""


class SelfUpdate:
    def __init__(self, install: InstallInfo, installer: Installer | None, latest: Callable[[], str | None], source: tuple[str, Allowed], fetch_sums: FetchSums = fetch_bytes,
                 fetch: FetchFile = fetch_file, restart_grace_sec: float = RESTART_GRACE_SEC, end: Callable[[], None] = lambda: None, key: Ed25519PublicKey | None = None) -> None:
        self.install = install
        self.installer = installer
        self._latest = latest                   # the version the update check announced, None while there is none
        self.base, self._allowed = source
        self._fetch_sums = fetch_sums
        self._fetch = fetch
        self.restart_grace_sec = restart_grace_sec
        self._key = key if key is not None else public_key()          # the project's key (a test's own with NEOAPRS_UPDATE_KEY: neoaprs/services/selfinstall.py, release_key)
        self._end = end                         # ends the daemon when the installer asked for a restart into the new file (an AppImage); nothing otherwise
        self.changed: Signal[[]] = Signal("update_changed")
        self._tasks = TaskSet(log, "update")
        self._job = IDLE
        self._cancelled = threading.Event()
        self._busy = False                      # a job is running (a cancelled download ends its piece first)

    @property
    def supported(self) -> bool:
        return self.installer is not None and not self.installer.blocked()

    def status(self) -> UpdateStatus:
        return replace(self._job, supported=self.supported)

    def _set(self, **change: object) -> None:
        self._job = replace(self._job, **change)          # type: ignore[arg-type]
        self.changed.emit()

    def begin(self, version: str) -> None:
        """Starts the update to `version`; UpdateNowError when this copy cannot update itself, the version is not the one announced, or an update is running."""
        if self.installer is None:
            raise UpdateNowError("this copy of NeoAPRS cannot update itself; the page has the steps", "update.unsupported")
        if why := self.installer.blocked():
            raise UpdateNowError(f"NeoAPRS cannot update itself here: {why}", "update.blocked", reason=why)
        if version != self._latest():
            raise UpdateNowError(f"{version} is not the version the update check announced", "update.not_announced", version=version)
        name = asset_name(self.install.kind, version, self.install.arch)
        if name is None:
            raise UpdateNowError(f"the release {version} has no file for this copy of NeoAPRS", "update.no_file", version=version)
        if self._busy:
            raise UpdateNowError("an update is running already", "update.busy")
        self._busy = True
        self._cancelled = threading.Event()
        self._job = replace(IDLE, state="downloading", version=version)
        self.changed.emit()
        log.info("Update now: to %s, the file %s", version, name)
        self._tasks.spawn(self._run(version, name, self._cancelled), "update-now")

    def cancel(self) -> None:
        """Ends the download; UpdateNowError when none is running (the install of a file cannot be stopped half way)."""
        if self._job.state not in ("downloading", "verifying"):
            raise UpdateNowError("no download of an update is running", "update.not_running")
        self._cancelled.set()
        log.info("Update now: cancelled")
        self._set(state="idle", version="", percent=None, downloaded=0, total=None)

    async def stop(self) -> None:
        self._cancelled.set()
        await self._tasks.cancel_all()

    async def _run(self, version: str, name: str, cancelled: threading.Event) -> None:
        assert self.installer is not None
        part = self.installer.folder / f"{name}.part"
        try:
            await self._download_and_install(version, name, part, cancelled)
        except Cancelled:
            pass
        except DownloadError as e:
            self._fail("download", str(e))
        except InstallError as e:
            self._fail("install", str(e))
        except OSError as e:
            self._fail("download", f"{part.name} could not be written: {e}")
        finally:
            try:
                part.unlink(missing_ok=True)
            except OSError as e:
                log.warning("%s could not be deleted: %s", part.name, e)
            finally:
                self._busy = False

    async def _download_and_install(self, version: str, name: str, part: Path, cancelled: threading.Event) -> None:
        assert self.installer is not None
        installer = self.installer
        sums = await in_thread(lambda: self._fetch_sums(asset_url(version, CHECKSUMS, self.base), self._allowed))
        try:
            signature = await in_thread(lambda: self._fetch_sums(asset_url(version, SIGNATURE, self.base), self._allowed))
        except DownloadError as e:
            if e.status != NOT_THERE:
                raise                                      # (a connection that failed is the problem `download`: tried again, it may well work)
            self._fail("unverified", f"the update to {version} could not be checked: {e}; nothing is installed")
            return
        try:
            expected = signed_checksum(sums, signature, version, name, self._key)
        except Unverified as e:
            self._fail("unverified", f"the update to {version} could not be checked: {e}; nothing is installed")
            return
        log.info("Update now: the SHA256SUMS of %s is signed with the project's key", version)
        if cancelled.is_set():
            return
        installer.folder.mkdir(parents=True, exist_ok=True)
        loop = asyncio.get_running_loop()

        def progress(done: int, total: int | None) -> None:
            loop.call_soon_threadsafe(self._progress, cancelled, done, total)
        got = await in_thread(lambda: self._fetch(asset_url(version, name, self.base), part, self._allowed, progress, cancelled))
        if cancelled.is_set():
            return
        self._set(state="verifying")
        if got != expected:
            self._fail("checksum", f"{name} is not the file of the release: its SHA-256 is {got}, the signed SHA256SUMS says {expected}; it was deleted and nothing is installed")
            return
        log.info("Update now: %s has the SHA-256 that the signed SHA256SUMS gives it", name)
        self._set(state="installing")
        await in_thread(lambda: installer.install(part, name, version))
        self._set(state="restarting")
        await asyncio.sleep(TELL_SEC)
        self._end()
        await asyncio.sleep(self.restart_grace_sec)
        self._fail("no_restart", f"NeoAPRS {version} was installed but NeoAPRS has not restarted; quit it and start it again")

    def _progress(self, cancelled: threading.Event, done: int, total: int | None) -> None:
        if cancelled.is_set() or self._job.state != "downloading":
            return
        percent = min(100, done * 100 // total) if total else None
        if percent != self._job.percent or total is None or done == total:
            self._set(percent=percent, downloaded=done, total=total)

    def _fail(self, problem: Problem, detail: str) -> None:
        log.warning("Update now failed: %s", detail)
        self._set(state="error", problem=problem, detail=detail)
