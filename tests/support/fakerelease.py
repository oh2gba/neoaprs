"""A release for the Update now tests, with no network: SHA256SUMS, its signature with a key of the
test's own, an AppImage, and an installer that only records what it was given.
"""
import hashlib
import re
import secrets
import threading
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from neoaprs.services.selfinstall import InstallError
from neoaprs.updateasset import CHECKSUMS, SIGNATURE, sign
from neoaprs.updatedownload import Allowed, Cancelled, DownloadError, Progress

NAME = "NeoAPRS-0.7.0-x86_64.AppImage"
BODY = b"the new AppImage" * 1000
SUMS = f"{hashlib.sha256(b'x').hexdigest()}  SHA256SUMS-of-another-file.deb\n{hashlib.sha256(BODY).hexdigest()}  {NAME}\n".encode()


OLD_SUM_LINE = re.compile(r"^([0-9a-fA-F]{64}) [ *](.+)$")
SEED = secrets.token_bytes(32)                       # the test's own signing key, made at each run


def public(seed: bytes = SEED) -> Ed25519PublicKey:
    return Ed25519PrivateKey.from_private_bytes(seed).public_key()


def old_checksum_for(sums: bytes, name: str) -> str | None:
    """`checksum_for` as the older programs read SHA256SUMS: the SHA-256 the list gives `name`, or
    None when it is missing or listed twice with two sums."""
    found: set[str] = set()
    for line in sums.decode("utf-8", errors="replace").splitlines():
        match = OLD_SUM_LINE.match(line.strip())
        if match and match.group(2).strip() == name:
            found.add(match.group(1).lower())
    return found.pop() if len(found) == 1 else None


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

    def __init__(self, sums: bytes = SUMS, body: bytes = BODY, gate: threading.Event | None = None, fail: str = "", signature: bytes | None = None, version: str = "0.7.0", signature_fails: str = "") -> None:
        self.sums = sums
        # The fetch of the signature fails with this, as a connection that drops does
        self.signature_fails = signature_fails
        # b"" serves no signature: a 404
        self.signature = sign(sums, version, SEED).encode() if signature is None else signature
        self.body = body
        self.gate = gate                    # the file waits for it after its first piece
        self.fail = fail
        self.asked: list[str] = []

    def fetch_sums(self, url: str, allowed: Allowed) -> bytes:
        assert allowed(url)
        self.asked.append(url)
        if url.endswith("/" + SIGNATURE):
            if self.signature_fails:
                raise DownloadError(self.signature_fails)
            if not self.signature:
                raise DownloadError(f"{SIGNATURE}: the server answered 404 Not Found", 404)
            return self.signature
        assert url.endswith("/" + CHECKSUMS)
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
