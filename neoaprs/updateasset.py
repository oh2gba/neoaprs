"""Decide, without I/O, which release file updates this copy and whether it is verified.

The address is built from the version alone; redirects go only to GitHub's hosts. SHA256SUMS is
trusted only with its Ed25519 signature (`signed_checksum`).
"""
import base64
import binascii
import re
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

# imported where a key is used, so a daemon that finds no new version never loads it
if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from neoaprs.versions import InstallKind

RELEASES = "https://github.com/oh2gba/neoaprs/releases/download"
ALLOWED_HOSTS = frozenset({"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"})
CHECKSUMS = "SHA256SUMS"
SIGNATURE = "SHA256SUMS.sig"
# the public half of the project's Ed25519 key, raw 32 bytes in base64
PUBLIC_KEY = "y+tv2daKD9MoQhAL7NBZrNMl1/RvvCRoMU0QN8NwZyc="
SIGNED_PREFIX = "NeoAPRS SHA256SUMS v"
SELF_UPDATING: frozenset[InstallKind] = frozenset({"windows-installer", "appimage"})
_RELEASE_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z]+(\.[0-9A-Za-z]+)*)?", re.ASCII)
_PRE_RELEASE = re.compile(r"([0-9]+\.[0-9]+\.[0-9]+)-(alpha|a|beta|b|rc|c|preview|pre|dev)\.?([0-9]*)", re.ASCII)
_PEP440_TAG = {"alpha": "a", "a": "a", "beta": "b", "b": "b", "rc": "rc", "c": "rc", "preview": "rc", "pre": "rc"}
_SUM_LINE = re.compile(r"^([0-9a-fA-F]{64}) [ *](.+)$")
_ASSET_NAME = re.compile(r"[0-9A-Za-z][0-9A-Za-z._-]*", re.ASCII)


def release_version(version: str) -> bool:
    return _RELEASE_VERSION.fullmatch(version) is not None


def wheel_version(version: str) -> str:
    """Return the version as PEP 440 names the sdist and wheel: `1.0.0-rc1` becomes `1.0.0rc1`."""
    found = _PRE_RELEASE.fullmatch(version)
    if found is None:
        return version
    base, tag, number = found.groups()
    return f"{base}.dev{number or 0}" if tag == "dev" else f"{base}{_PEP440_TAG[tag]}{number or 0}"


def asset_name(kind: InstallKind, version: str, arch: str = "") -> str | None:
    """Return the release file that updates a copy installed as `kind`, or None.

    None for a clone, wheel installs (a release carries no file for them) or an unknown `arch`.
    """
    if not release_version(version):
        return None
    match kind:
        case "windows-installer":
            return f"NeoAPRS-Setup-{version}.exe"
        case "appimage":
            return f"NeoAPRS-{version}-x86_64.AppImage"
        case "macos-app":
            return f"NeoAPRS-{version}-arm64.dmg" if arch == "arm64" else None
        case "deb":
            return f"neoaprs_{version}_{arch}.deb" if arch in ("amd64", "arm64") else None
        case _:
            return None


def asset_url(version: str, name: str, base: str = RELEASES) -> str:
    if not release_version(version) or not _ASSET_NAME.fullmatch(name):
        raise ValueError(f"no release address for {version!r} and {name!r}")
    return f"{base}/v{version}/{name}"


def url_allowed(url: str) -> bool:
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return parts.scheme == "https" and (parts.hostname or "").lower() in ALLOWED_HOSTS and port in (None, 443) and parts.username is None


class Unverified(Exception):
    """SHA256SUMS is untrusted or does not name the file exactly once; the text is for the log."""


def public_key(text: str = PUBLIC_KEY) -> "Ed25519PublicKey":
    """Return the Ed25519 public key from base64 of its 32 raw bytes; raise ValueError otherwise."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        raw = base64.b64decode(text.strip(), validate=True)
    except binascii.Error:
        raise ValueError("a public key is the base64 of 32 bytes") from None
    if len(raw) != 32:
        raise ValueError(f"a public key is 32 bytes, not {len(raw)}")
    return Ed25519PublicKey.from_public_bytes(raw)


def signed_message(sums: bytes, version: str) -> bytes:
    """Return the bytes signed: a line naming the release, then the list unchanged.

    The version is bound here, not in the list, so `sha256sum --check --strict` still reads it.
    """
    if not release_version(version):
        raise ValueError(f"{version!r} is not a version of a release")
    return f"{SIGNED_PREFIX}{version}\n".encode("ascii") + sums


def sign(sums: bytes, version: str, seed: bytes) -> str:
    if len(seed) != 32:
        raise ValueError(f"the signing key is a 32-byte seed, not {len(seed)} bytes")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    return base64.b64encode(Ed25519PrivateKey.from_private_bytes(seed).sign(signed_message(sums, version))).decode("ascii") + "\n"


def check_signature(sums: bytes, signature: bytes, version: str, key: "Ed25519PublicKey") -> None:
    """Raise Unverified unless `signature` is `key`'s signature of `sums` for `version`."""
    from cryptography.exceptions import InvalidSignature
    try:
        raw = base64.b64decode(signature.strip(), validate=True)
    except (binascii.Error, ValueError):
        raise Unverified(f"{SIGNATURE} is not base64") from None
    if len(raw) != 64:
        raise Unverified(f"{SIGNATURE} is {len(raw)} bytes, not the 64 of a signature")
    try:
        key.verify(raw, signed_message(sums, version))
    except InvalidSignature:
        raise Unverified(f"{SIGNATURE} is not the project's signature of this {CHECKSUMS} as the list of v{version}") from None


def checksums(sums: bytes) -> dict[str, str]:
    """Return file name to hex SHA-256 from a SHA256SUMS list; raise Unverified if malformed."""
    try:
        text = sums.decode("utf-8")
    except UnicodeDecodeError:
        raise Unverified(f"{CHECKSUMS} is not UTF-8") from None
    found: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        match = _SUM_LINE.match(line.strip())
        if match is None:
            raise Unverified(f"line {number} of {CHECKSUMS} is not a checksum and a file name")
        name = match.group(2).strip()
        if name in found:
            raise Unverified(f"{CHECKSUMS} names {name} twice")
        found[name] = match.group(1).lower()
    if not found:
        raise Unverified(f"{CHECKSUMS} is empty")
    return found


def signed_checksum(sums: bytes, signature: bytes, version: str, name: str, key: "Ed25519PublicKey") -> str:
    """Return the SHA-256 the signed SHA256SUMS of `version` gives file `name`; raise Unverified."""
    check_signature(sums, signature, version, key)
    sha = checksums(sums).get(name)
    if sha is None:
        raise Unverified(f"the signed {CHECKSUMS} of v{version} names no {name}")
    return sha
