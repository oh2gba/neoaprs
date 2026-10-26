"""Which file of a release updates this copy, at which address, and whether a downloaded file is the one the release's SHA256SUMS names: the decisions of Update now that need no I/O.

The address is built here from the version alone: the release page of the project on github.com, the tag `v<version>`, the file's name. Nothing of the version page's answer but the version is used, and a version that is
not plainly one (digits and dots, an optional `-rc1`) builds no address. The download may be redirected only to GitHub's own hosts of release files, over https.
"""
import re
from urllib.parse import urlsplit

from neoaprs.versions import InstallKind

RELEASES = "https://github.com/oh2gba/neoaprs/releases/download"
ALLOWED_HOSTS = frozenset({"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"})       # the release page and where GitHub keeps the files it redirects to
CHECKSUMS = "SHA256SUMS"
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
    """The version as the wheel and the sdist are named, PEP 440 as the build makes it: `1.0.0-rc1` is `1.0.0rc1`, `1.0.0-dev2` is `1.0.0.dev2`; a plain version, and one that is no pre-release of those kinds, as it is."""
    found = _PRE_RELEASE.fullmatch(version)
    if found is None:
        return version
    base, tag, number = found.groups()
    return f"{base}.dev{number or 0}" if tag == "dev" else f"{base}{_PEP440_TAG[tag]}{number or 0}"


def asset_name(kind: InstallKind, version: str, arch: str = "") -> str | None:
    """The file of the release `version` that updates a copy installed as `kind` (`arch` is the .deb's architecture): None for a clone of the repository, a .deb of an architecture that has none, and a version that is not one."""
    if not release_version(version):
        return None
    match kind:
        case "windows-installer":
            return f"NeoAPRS-Setup-{version}.exe"
        case "appimage":
            return f"NeoAPRS-{version}-x86_64.AppImage"
        case "deb":
            return f"neoaprs_{version}_{arch}.deb" if arch in ("amd64", "arm64") else None
        case "uv-tool" | "pip":
            return f"neoaprs-{wheel_version(version)}-py3-none-any.whl"
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


def checksum_for(sums: bytes, name: str) -> str | None:
    """The SHA-256 (lower case hex) that the text of SHA256SUMS gives the file `name`, or None when it names it not at all, or twice with two sums."""
    found: set[str] = set()
    for line in sums.decode("utf-8", errors="replace").splitlines():
        match = _SUM_LINE.match(line.strip())
        if match and match.group(2).strip() == name:
            found.add(match.group(1).lower())
    return found.pop() if len(found) == 1 else None
