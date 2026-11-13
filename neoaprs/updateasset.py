"""Which file of a release updates this copy, at which address, and whether the release's SHA256SUMS is signed by the project and names a downloaded file: the decisions of Update now that need no I/O.

The address is built here from the version alone: the release page of the project on github.com, the tag `v<version>`, the file's name. Nothing of the version page's answer but the version is used, and a version that is
not plainly one (digits and dots, an optional `-rc1`) builds no address. The download may be redirected only to GitHub's own hosts of release files, over https.

SHA256SUMS is believed only with its signature (`signed_checksum`): SHA256SUMS.sig is the base64 of the 64-byte Ed25519 signature, made by `scripts/release` with the project's key, which is on the maintainer's machine
and not on GitHub; PUBLIC_KEY is its public half, and the only place the program has it. What is signed is `signed_message`: the line `NeoAPRS SHA256SUMS v<version>` and the list as it is. The version is bound there
and not in the list, so that the list stays what `sha256sum --check --strict` and the programs from before the signature read, and the version the check holds it to is the one Update now asked for: it is never read
out of the bytes that came with the download, so a signed list of an older release offered as a newer one does not hold.
"""
import base64
import binascii
import re
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from neoaprs.versions import InstallKind

RELEASES = "https://github.com/oh2gba/neoaprs/releases/download"
ALLOWED_HOSTS = frozenset({"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"})       # the release page and where GitHub keeps the files it redirects to
CHECKSUMS = "SHA256SUMS"
SIGNATURE = "SHA256SUMS.sig"
PUBLIC_KEY = "y+tv2daKD9MoQhAL7NBZrNMl1/RvvCRoMU0QN8NwZyc="                     # the public half of the project's Ed25519 key, raw 32 bytes in base64
SIGNED_PREFIX = "NeoAPRS SHA256SUMS v"
SELF_UPDATING: frozenset[InstallKind] = frozenset({"windows-installer", "appimage"})        # the kinds whose update the daemon can do itself (neoaprs/services/selfinstall.py)
_RELEASE_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z]+(\.[0-9A-Za-z]+)*)?", re.ASCII)
_PRE_RELEASE = re.compile(r"([0-9]+\.[0-9]+\.[0-9]+)-(alpha|a|beta|b|rc|c|preview|pre|dev)\.?([0-9]*)", re.ASCII)
_PEP440_TAG = {"alpha": "a", "a": "a", "beta": "b", "b": "b", "rc": "rc", "c": "rc", "preview": "rc", "pre": "rc"}
_SUM_LINE = re.compile(r"^([0-9a-fA-F]{64}) [ *](.+)$")
_ASSET_NAME = re.compile(r"[0-9A-Za-z][0-9A-Za-z._-]*", re.ASCII)


def release_version(version: str) -> bool:
    """Is this a version a release can have, safe to put in an address: `0.6.8`, `1.0.0-rc1`?"""
    return _RELEASE_VERSION.fullmatch(version) is not None


def wheel_version(version: str) -> str:
    """The version as the sdist (and the wheel the build makes with it) is named, PEP 440 as the build makes it: `1.0.0-rc1` is `1.0.0rc1`, `1.0.0-dev2` is `1.0.0.dev2`; a plain version, and one that is no pre-release of those kinds, as it is."""
    found = _PRE_RELEASE.fullmatch(version)
    if found is None:
        return version
    base, tag, number = found.groups()
    return f"{base}.dev{number or 0}" if tag == "dev" else f"{base}{_PEP440_TAG[tag]}{number or 0}"


def asset_name(kind: InstallKind, version: str, arch: str = "") -> str | None:
    """The file of the release `version` that updates a copy installed as `kind` (`arch` is the .deb's or the Mac's architecture): None for a clone of the repository, a .deb or a Mac of an architecture that has none, a
    version that is not one, and an install made from the wheel (`uv-tool`, `pip`), which a release no longer carries: such a copy is updated by installing one of the release's files (the page says so). The macOS app's
    file is named here so that the page can offer it; the daemon does not install it itself (neoaprs/services/selfinstall.py says why)."""
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
    """The address of the file `name` of the release `version`; ValueError for a version or a name that has no place in one."""
    if not release_version(version) or not _ASSET_NAME.fullmatch(name):
        raise ValueError(f"no release address for {version!r} and {name!r}")
    return f"{base}/v{version}/{name}"


def url_allowed(url: str) -> bool:
    """May the download go to this address: https, to the release page or to GitHub's hosts of release files, on the usual port?"""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return parts.scheme == "https" and (parts.hostname or "").lower() in ALLOWED_HOSTS and port in (None, 443) and parts.username is None


class Unverified(Exception):
    """SHA256SUMS cannot be believed, or does not name the file once: the text says why, for the log."""


def public_key(text: str = PUBLIC_KEY) -> Ed25519PublicKey:
    """The Ed25519 public key of the base64 of its 32 raw bytes; ValueError for text that is not one."""
    try:
        raw = base64.b64decode(text.strip(), validate=True)
    except binascii.Error:
        raise ValueError("a public key is the base64 of 32 bytes") from None
    if len(raw) != 32:
        raise ValueError(f"a public key is 32 bytes, not {len(raw)}")
    return Ed25519PublicKey.from_public_bytes(raw)


def signed_message(sums: bytes, version: str) -> bytes:
    """What the signature of SHA256SUMS of the release `version` is made over: the line that names the release, then the list unchanged."""
    if not release_version(version):
        raise ValueError(f"{version!r} is not a version of a release")
    return f"{SIGNED_PREFIX}{version}\n".encode("ascii") + sums


def sign(sums: bytes, version: str, seed: bytes) -> str:
    """The text of SHA256SUMS.sig for the list `sums` of the release `version`: the base64 of the Ed25519 signature with the key whose 32-byte seed is `seed` (scripts/release, at the moment it signs)."""
    if len(seed) != 32:
        raise ValueError(f"the signing key is a 32-byte seed, not {len(seed)} bytes")
    return base64.b64encode(Ed25519PrivateKey.from_private_bytes(seed).sign(signed_message(sums, version))).decode("ascii") + "\n"


def check_signature(sums: bytes, signature: bytes, version: str, key: Ed25519PublicKey) -> None:
    """Unverified unless `signature` (the text of SHA256SUMS.sig) is the signature of `sums` as the list of the release `version`, made with the key whose public half is `key`."""
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
    """Every line of a signed SHA256SUMS, the file's name to its SHA-256 (lower case hex); Unverified for an empty list, a line that is not a checksum line and a name that is there twice."""
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


def signed_checksum(sums: bytes, signature: bytes, version: str, name: str, key: Ed25519PublicKey) -> str:
    """The SHA-256 (lower case hex) that the signed SHA256SUMS of the release `version` gives the file `name`; Unverified when the signature does not hold for that version with `key`, the list is not one, or it
    does not name the file."""
    check_signature(sums, signature, version, key)
    sha = checksums(sums).get(name)
    if sha is None:
        raise Unverified(f"the signed {CHECKSUMS} of v{version} names no {name}")
    return sha
