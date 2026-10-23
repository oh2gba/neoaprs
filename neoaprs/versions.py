"""Versions and the update check's small decisions that need no I/O: which of two versions is newer, what the answer of the version page means, what this installation calls its platform, and how this copy was installed
(which is what tells the page the steps of an update)."""
import json
import re
from dataclasses import dataclass
from typing import Any, Literal, get_args

UPDATE_URL = "https://oh2gba.eu/neoaprs/version.php"          # the default of the setting update/url
MAX_MESSAGE = 200                    # the longest note of the answer that is kept
_VERSION = re.compile(r"^\d+(\.\d+){0,3}([-+][0-9A-Za-z.]+)?$")
_PART_SEPARATORS = re.compile(r"[.\-+]")
_ARM_MACHINES = ("aarch64", "arm64", "armv7l", "armv6l", "armv8l")        # a Raspberry Pi
_DEB_ARCHITECTURES = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}          # `platform.machine()` to the name of the .deb that runs on it


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


def deb_architecture(machine: str) -> str:
    """The architecture in the name of the .deb for this machine (`platform.machine()`): `amd64` or `arm64`, empty for a machine that has none."""
    return _DEB_ARCHITECTURES.get(machine.lower(), "")


InstallKind = Literal["windows-installer", "appimage", "deb", "uv-tool", "pip", "source"]
INSTALL_KINDS: tuple[str, ...] = get_args(InstallKind)


@dataclass(frozen=True)
class InstallInfo:
    """How this copy was installed. `appimage` is the file it runs from (kind `appimage` only, else empty); `arch` is the architecture of the package (kind `deb` only: `amd64` or `arm64`, else empty); `service` says whether a service (the systemd unit, the launchd agent, the Windows Run key) starts it."""
    kind: InstallKind
    appimage: str = ""
    service: bool = False
    arch: str = ""


def install_kind(frozen: bool, appimage: str | None, deb: bool, checkout: bool, uv_tool: bool) -> InstallKind:
    """The way this copy got here, from what the process can see: a frozen program is the Windows installer's, a run from an AppImage file is the AppImage, the Python of /opt/neoaprs is the .deb's, a package imported from a clone of
    the repository is a checkout, a package in the environment `uv tool` made is the install script's, anything else a plain pip (or `uv pip`) environment."""
    if frozen:
        return "windows-installer"
    if appimage:
        return "appimage"
    if deb:
        return "deb"
    if checkout:
        return "source"
    return "uv-tool" if uv_tool else "pip"


PLAIN_INSTALL = InstallInfo("pip")          # what a part that was not told how it was installed assumes (the tests)
