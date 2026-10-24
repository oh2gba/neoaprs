"""A release for Update now's tests, with no network: the files a download finds (SHA256SUMS and the AppImage of 0.7.0) and what was asked for, and an installer that only writes down what it was given."""
import hashlib
import threading
from pathlib import Path

from neoaprs.services.selfinstall import InstallError
from neoaprs.updatedownload import Allowed, Cancelled, DownloadError, Progress

NAME = "NeoAPRS-0.7.0-x86_64.AppImage"
BODY = b"the new AppImage" * 1000
SUMS = f"{hashlib.sha256(b'x').hexdigest()}  install.sh\n{hashlib.sha256(BODY).hexdigest()}  {NAME}\n".encode()


class FakeInstaller:
    def __init__(self, folder: Path, blocked: str = "", fail: str = "") -> None:
        self.folder = folder
        self._blocked = blocked
        self.fail = fail
        self.installed: list[tuple[bytes, str, str]] = []

    def blocked(self) -> str:
        return self._blocked

    def install(self, file: Path, name: str, version: str) -> None:
        if self.fail:
            raise InstallError(self.fail)
        self.installed.append((file.read_bytes(), name, version))
        file.unlink()                          # (a real one moves it)


class FakeRelease:
    """The files of a release as the downloads see them, and what was asked for."""

    def __init__(self, sums: bytes = SUMS, body: bytes = BODY, gate: threading.Event | None = None, fail: str = "") -> None:
        self.sums = sums
        self.body = body
        self.gate = gate                    # the file waits for it after its first piece
        self.fail = fail
        self.asked: list[str] = []

    def fetch_sums(self, url: str, allowed: Allowed) -> bytes:
        assert allowed(url)
        self.asked.append(url)
        return self.sums

    def fetch(self, url: str, target: Path, allowed: Allowed, progress: Progress, cancelled: threading.Event) -> str:
        assert allowed(url)
        self.asked.append(url)
        if self.fail:
            raise DownloadError(self.fail)
        half = len(self.body) // 2
        target.write_bytes(self.body[:half])
        progress(half, len(self.body))
        if self.gate is not None:
            self.gate.wait(5)
        if cancelled.is_set():
            raise Cancelled()
        target.write_bytes(self.body)
        progress(len(self.body), len(self.body))
        return hashlib.sha256(self.body).hexdigest()
