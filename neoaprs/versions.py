"""Versions and the update check's two small decisions that need no I/O: which of two versions is newer, what the answer of the version page means, and what this installation calls its platform."""
import json
import re
from dataclasses import dataclass
from typing import Any

UPDATE_URL = "https://oh2gba.eu/neoaprs/version.php"          # the default of the setting update/url
MAX_MESSAGE = 200                    # the longest note of the answer that is kept
_VERSION = re.compile(r"^\d+(\.\d+){0,3}([-+][0-9A-Za-z.]+)?$")
_PART_SEPARATORS = re.compile(r"[.\-+]")
_ARM_MACHINES = ("aarch64", "arm64", "armv7l", "armv6l", "armv8l")        # a Raspberry Pi


@dataclass(frozen=True)
class Update:
    """What the version page said: the latest version, where to get it and an optional short note from the project."""
    version: str
    url: str                         # https, or empty
    message: str


def _parts(version: str) -> list[str]:
    return [part for part in _PART_SEPARATORS.split(version.strip()) if part]


def compare_versions(a: str, b: str) -> int:
    """-1, 0 or 1 as `a` is older than, the same as or newer than `b`. "0.10.0" is newer than "0.9.0", a missing part counts as 0 ("1.0" is "1.0.0"), and "1.0.0-rc1" is older than "1.0.0"."""
    left, right = _parts(a), _parts(b)
    for i in range(max(len(left), len(right))):
        x, y = left[i] if i < len(left) else "0", right[i] if i < len(right) else "0"
        if x.isdigit() and y.isdigit():
            if int(x) != int(y):
                return -1 if int(x) < int(y) else 1
        elif x.isdigit() != y.isdigit():
            return 1 if x.isdigit() else -1             # a number comes after a suffix: "1.0.0-rc1" sorts before "1.0.0"
        elif x.lower() != y.lower():
            return -1 if x.lower() < y.lower() else 1
    return 0


def parse_update(body: bytes | str) -> Update | None:
    """The answer of the version page, `{"version", "url", "message"}`, or None when it is not one: the version must look like one, an address that is not https is dropped, the note is cut to MAX_MESSAGE characters."""
    try:
        data: Any = json.loads(body)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    version, url, message = (text.strip() if isinstance(text := data.get(key), str) else "" for key in ("version", "url", "message"))
    if not _VERSION.match(version):
        return None
    return Update(version, url if url.startswith("https://") else "", message[:MAX_MESSAGE])


def platform_name(system: str, machine: str, appimage: bool) -> str:
    """What the version page is told about this installation: `windows`, `macos`, `linux-appimage`, `linux-arm` (a Raspberry Pi) or `linux`. `system` is `sys.platform`, `machine` is `platform.machine()`."""
    if system.startswith("win"):
        return "windows"
    if system == "darwin":
        return "macos"
    if appimage:
        return "linux-appimage"
    return "linux-arm" if machine.lower() in _ARM_MACHINES else "linux"
