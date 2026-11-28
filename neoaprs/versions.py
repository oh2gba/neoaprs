"""Version comparison and the update check's small decisions that need no I/O.

Version order, the version page's answer, the platform name and the install kind.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

UPDATE_URL = "https://neo.oh2gba.eu/version.php"
OLD_UPDATE_URL = "https://oh2gba.eu/neoaprs/version.php"
# `true`: the update check sends 0 instead of the installation number; set with `neoaprs db set`
NOT_COUNTED = "update/not_counted"
FREQUENCIES_URL = "https://neo.oh2gba.eu/frequencies.json"
# the last good list, kept in the settings table (not a setting)
FREQUENCIES_ROW = "update/frequencies"
SUPPORT_URL = "https://neo.oh2gba.eu/support/send.php"
MAX_MESSAGE = 200
# an HF dial as the page names it: "7.0541 MHz USB"
DIAL_PATTERN = r"^\d{1,2}\.\d{3,4} MHz (USB|LSB)$"
_DIAL = re.compile(DIAL_PATTERN, re.ASCII)
_BAND = re.compile(r"^\d{1,3} m$", re.ASCII)
MAX_FREQUENCIES = 5
_VERSION = re.compile(r"^\d+(\.\d+){0,3}([-+][0-9A-Za-z.]+)?$", re.ASCII)
# a run of digits or of anything else but separators ("rc10" is "rc" and 10)
_PART = re.compile(r"\d+|[^\d.\-+]+", re.ASCII)
_ARM_MACHINES = ("aarch64", "arm64", "armv7l", "armv6l", "armv8l")
_DEB_ARCHITECTURES = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}
_MAC_ARCHITECTURES = {"arm64": "arm64", "aarch64": "arm64"}


@dataclass(frozen=True)
class Update:
    """The version page's answer: latest version, where to get it, a note, the HF dial."""

    version: str
    url: str  # https, or empty
    message: str
    hf_dial: str = ""


def _parts(version: str) -> list[str]:
    return _PART.findall(version.strip())


def _number(part: str) -> tuple[int, str] | None:
    """Return a run of ASCII digits as a key that orders it as a number, of any length; else None."""
    digits = part.lstrip("0")
    return (len(digits), digits) if part.isascii() and part.isdigit() else None


def compare_versions(a: str, b: str) -> int:
    """Return -1, 0 or 1 as `a` is older than, equal to or newer than `b`.

    A missing part counts as 0, "1.0.0-rc1" is older than "1.0.0", suffix numbers are numeric.
    """
    left, right = _parts(a), _parts(b)
    for i in range(max(len(left), len(right))):
        x, y = left[i] if i < len(left) else "0", right[i] if i < len(right) else "0"
        nx, ny = _number(x), _number(y)
        if nx is not None and ny is not None:
            if nx != ny:
                return -1 if nx < ny else 1
        elif (nx is None) != (ny is None):
            # a number comes after a suffix: "1.0.0-rc1" sorts before "1.0.0"
            return 1 if nx is not None else -1
        elif x.lower() != y.lower():
            return -1 if x.lower() < y.lower() else 1
    return 0


def parse_update(body: bytes | str) -> Update | None:
    """Parse the version page's JSON answer, or return None; a non-https address is dropped."""
    try:
        data: Any = json.loads(body)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    version, url, message, dial = (
        text.strip() if isinstance(text := data.get(key), str) else ""
        for key in ("version", "url", "message", "hf_dial")
    )
    if not _VERSION.match(version):
        return None
    return Update(
        version, url if url.startswith("https://") else "", message[:MAX_MESSAGE], dial if is_dial(dial) else ""
    )


def platform_name(system: str, machine: str, appimage: bool) -> str:
    if system.startswith("win"):
        return "windows"
    if system == "darwin":
        return "macos"
    if appimage:
        return "linux-appimage"
    return "linux-arm" if machine.lower() in _ARM_MACHINES else "linux"


def deb_architecture(machine: str) -> str:
    return _DEB_ARCHITECTURES.get(machine.lower(), "")


def mac_architecture(machine: str) -> str:
    return _MAC_ARCHITECTURES.get(machine.lower(), "")


InstallKind = Literal["windows-installer", "appimage", "macos-app", "deb", "uv-tool", "pip", "source"]


@dataclass(frozen=True)
class InstallInfo:
    """How this copy was installed: `appimage` its file, `arch` the file's, `service` a starter."""

    kind: InstallKind
    appimage: str = ""
    service: bool = False
    arch: str = ""


def install_kind(
    frozen: bool, appimage: str | None, deb: bool, checkout: bool, uv_tool: bool, app_bundle: bool = False
) -> InstallKind:
    if frozen:
        return "windows-installer"
    if appimage:
        return "appimage"
    if app_bundle:
        return "macos-app"
    if deb:
        return "deb"
    if checkout:
        return "source"
    return "uv-tool" if uv_tool else "pip"


PLAIN_INSTALL = InstallInfo("pip")


@dataclass(frozen=True)
class Frequency:
    band: str
    dial: str


def is_dial(text: str) -> bool:
    return _DIAL.fullmatch(text) is not None


def parse_frequencies(body: bytes | str) -> list[Frequency] | None:
    """Parse the frequencies file, sorted by band, the longest first; bad entries are dropped, None if
    no good entry remains."""
    try:
        data: Any = json.loads(body)
    except ValueError:
        return None
    entries = data.get("frequencies") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return None
    found: list[Frequency] = []
    for entry in entries:
        band, dial = (
            text.strip() if isinstance(entry, dict) and isinstance(text := entry.get(key), str) else ""
            for key in ("band", "dial")
        )
        if _BAND.match(band) and is_dial(dial) and all(f.band != band for f in found) and len(found) < MAX_FREQUENCIES:
            found.append(Frequency(band, dial))
    # the file adds a band at its end, where an older copy's limit leaves it out
    return sorted(found, key=lambda f: -int(f.band.split()[0])) or None


def frequencies_text(frequencies: list[Frequency]) -> str:
    return json.dumps({"frequencies": [{"band": f.band, "dial": f.dial} for f in frequencies]})


def suggested(listed: list[Frequency], hf_dial: str, built_in: list[Frequency], dial_band: str) -> list[Frequency]:
    """Return what the HF box shows: the project's list, else the page's dial, else built-in."""
    if listed:
        return listed
    return [Frequency(dial_band, hf_dial)] if hf_dial else built_in


def on_this_computer(text: str) -> bool:
    try:
        parts = urlsplit(text)
        _ = parts.port
    except ValueError:
        return False
    return (
        parts.scheme in ("http", "https")
        and parts.hostname in ("127.0.0.1", "localhost")
        and "@" not in parts.netloc
        and not any(c.isspace() for c in text)
    )
