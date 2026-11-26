"""Update now: download, verify and install the release file for this copy.

The SHA256SUMS file is trusted only if its signature holds; the file's SHA-256 must then match.
Any signature failure is the problem `unverified`; one that cannot be fetched is `download`."""

import asyncio
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from neoaprs.coded import CodedError
from neoaprs.signal import Signal
from neoaprs.tasks import TaskSet
from neoaprs.updateasset import CHECKSUMS, SIGNATURE, Unverified, asset_name, asset_url, public_key, signed_checksum
from neoaprs.updatedownload import Allowed, Cancelled, DownloadError, Progress, fetch_bytes, fetch_file, in_thread
from neoaprs.versions import InstallInfo

from .selfinstall import Installer, InstallError

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

log = logging.getLogger("neoaprs.update")

RESTART_GRACE_SEC = 300.0
# between `restarting` and the daemon's end: the page is told before its socket closes
TELL_SEC = 0.5
# SHA256SUMS.sig answer meaning no signature (`unverified`); other failures are `download`
NOT_THERE = 404
State = Literal["idle", "downloading", "verifying", "installing", "restarting", "error"]
Problem = Literal["", "download", "unverified", "checksum", "install", "no_restart"]
UNEXPECTED = "the update stopped on an unexpected error; the log says why"
FetchSums = Callable[[str, Allowed], bytes]
FetchFile = Callable[[str, Path, Allowed, Progress, threading.Event], str]


@dataclass(frozen=True)
class UpdateStatus:
    # this copy can update itself: the page offers Update now
    supported: bool
    state: State
    # the version being installed; empty while idle
    version: str
    # of the download; None when the server did not say the size
    percent: int | None
    downloaded: int
    total: int | None
    # what went wrong (state `error`); empty otherwise
    problem: Problem
    # the sentence for the log and the page's details; empty when all is well
    detail: str


IDLE = UpdateStatus(False, "idle", "", None, 0, None, "", "")


class UpdateNowError(CodedError):
    """`update_now` or `update_cancel` cannot be done now."""


class SelfUpdate:
    def _release_key(self) -> "Ed25519PublicKey":
        return self._key() if callable(self._key) else self._key if self._key is not None else public_key()

    def __init__(
        self,
        install: InstallInfo,
        installer: Installer | None,
        latest: Callable[[], str | None],
        source: tuple[str, Allowed],
        fetch_sums: FetchSums = fetch_bytes,
        fetch: FetchFile = fetch_file,
        restart_grace_sec: float = RESTART_GRACE_SEC,
        end: Callable[[], None] = lambda: None,
        key: "Ed25519PublicKey | Callable[[], Ed25519PublicKey] | None" = None,
    ) -> None:
        self.install = install
        self.installer = installer
        # the version the update check announced, None while there is none
        self._latest = latest
        self.base, self._allowed = source
        self._fetch_sums = fetch_sums
        self._fetch = fetch
        self.restart_grace_sec = restart_grace_sec
        # the project's key when None; a function defers loading the crypto library until needed
        self._key = key
        # ends the daemon when the installer asked for a restart into the new file (an AppImage)
        self._end = end
        self.changed: Signal[[]] = Signal("update_changed")
        self._tasks = TaskSet(log, "update")
        self._job = IDLE
        self._cancelled = threading.Event()
        # a job is running (a cancelled download ends its piece first)
        self._busy = False

    @property
    def supported(self) -> bool:
        return self.installer is not None and not self.installer.blocked()

    def status(self) -> UpdateStatus:
        return replace(self._job, supported=self.supported)

    def _set(self, **change: object) -> None:
        self._job = replace(self._job, **change)  # type: ignore[arg-type]
        self.changed.emit()

    def begin(self, version: str) -> None:
        """Start the update to `version`; raise UpdateNowError if it cannot be started."""
        if self.installer is None:
            raise UpdateNowError(
                "this copy of NeoAPRS cannot update itself; the page has the steps", "update.unsupported"
            )
        if why := self.installer.blocked():
            # the page words it without the folder; the log has the detail
            log.warning("Update now: %s", why)
            raise UpdateNowError(f"NeoAPRS cannot update itself here: {why}", "update.blocked")
        if version != self._latest():
            raise UpdateNowError(
                f"{version} is not the version the update check announced", "update.not_announced", version=version
            )
        name = asset_name(self.install.kind, version, self.install.arch)
        if name is None:
            raise UpdateNowError(
                f"the release {version} has no file for this copy of NeoAPRS", "update.no_file", version=version
            )
        if self._busy:
            raise UpdateNowError("an update is running already", "update.busy")
        self._busy = True
        self._cancelled = threading.Event()
        self._job = replace(IDLE, state="downloading", version=version)
        self.changed.emit()
        log.info("Update now: to %s, the file %s", version, name)
        self._tasks.spawn(self._run(version, name, self._cancelled), "update-now")

    def cancel(self) -> None:
        """End the download; raise UpdateNowError if none runs (an install cannot be stopped)."""
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
        except Exception:
            log.exception("Update now: the update to %s stopped on an unexpected error", version)
            self._fail("install" if self._job.state in ("installing", "restarting") else "download", UNEXPECTED)
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
            signature = await in_thread(
                lambda: self._fetch_sums(asset_url(version, SIGNATURE, self.base), self._allowed)
            )
        except DownloadError as e:
            if e.status != NOT_THERE:
                # a failed connection is `download`: a retry may work
                raise
            self._fail("unverified", f"the update to {version} could not be checked: {e}; nothing is installed")
            return
        try:
            expected = signed_checksum(sums, signature, version, name, self._release_key())
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

        got = await in_thread(
            lambda: self._fetch(asset_url(version, name, self.base), part, self._allowed, progress, cancelled)
        )
        if cancelled.is_set():
            return
        self._set(state="verifying")
        if got != expected:
            self._fail(
                "checksum",
                f"{name} is not the file of the release: its SHA-256 is {got}, the signed SHA256SUMS says {expected}; it was deleted and nothing is installed",
            )
            return
        log.info("Update now: %s has the SHA-256 that the signed SHA256SUMS gives it", name)
        self._set(state="installing")
        await in_thread(lambda: installer.install(part, name, version))
        self._set(state="restarting")
        await asyncio.sleep(TELL_SEC)
        self._end()
        await asyncio.sleep(self.restart_grace_sec)
        self._fail(
            "no_restart", f"NeoAPRS {version} was installed but NeoAPRS has not restarted; quit it and start it again"
        )

    def _progress(self, cancelled: threading.Event, done: int, total: int | None) -> None:
        if cancelled.is_set() or self._job.state != "downloading":
            return
        percent = min(100, done * 100 // total) if total else None
        if percent != self._job.percent or total is None or done == total:
            self._set(percent=percent, downloaded=done, total=total)

    def _fail(self, problem: Problem, detail: str) -> None:
        log.warning("Update now failed: %s", detail)
        if self._cancelled.is_set():
            # the operator cancelled: the state stays idle
            return
        self._set(state="error", problem=problem, detail=detail)
