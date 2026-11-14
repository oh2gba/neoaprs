"""Versions and the update check's small decisions that need no I/O: which of two versions is newer, what the answer of the version page means, what this installation calls its platform, and how this copy was installed
(which is what tells the page the steps of an update)."""
import json
import re
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

UPDATE_URL = "https://neo.oh2gba.eu/version.php"              # the default of the setting update/url: the version page on the project's own name (since 0.16)
OLD_UPDATE_URL = "https://oh2gba.eu/neoaprs/version.php"      # where the copies before 0.16 ask: the same page, kept there for them (migration 26 moves a stored default over)
NOT_COUNTED = "update/not_counted"           # `true`: the update check sends the number 0 in place of this installation's own, so that the project does not count this run (services/updatecheck.py); set with `neoaprs db set`, never on the page; state of the daemon too, not a setting
FREQUENCIES_URL = "https://neo.oh2gba.eu/frequencies.json"      # the frequencies the project suggests, a file edited by hand and uploaded with the site (site/frequencies.json); the HF radio's box shows them (services/frequencies.py)
FREQUENCIES_ROW = "update/frequencies"                         # the last good list, kept by the daemon in the settings table (not a setting)
SUPPORT_URL = "https://neo.oh2gba.eu/support/send.php"      # where Send feedback / logs of the Help group posts the support file (neoaprs/web/supportsend.py); the server stores it and tells the project
MAX_MESSAGE = 200                    # the longest note of the answer that is kept
_DIAL = re.compile(r"^\d{1,2}\.\d{3,4} MHz (USB|LSB)$")      # an HF dial as the page names it and the HF box shows it: "7.0541 MHz USB"
_BAND = re.compile(r"^\d{1,3} m$")                              # the band of a suggested frequency: "40 m" (site/site.js checks the same two forms)
MAX_FREQUENCIES = 4                                            # the most the list keeps; the box keeps room for four lines (ui/src/components/HfFrequencies.vue)
_VERSION = re.compile(r"^\d+(\.\d+){0,3}([-+][0-9A-Za-z.]+)?$")
_PART = re.compile(r"\d+|[^\d.\-+]+")                             # a part of a version: a run of digits, or of what is not a digit or a separator ("rc10" is "rc" and 10)
_ARM_MACHINES = ("aarch64", "arm64", "armv7l", "armv6l", "armv8l")        # a Raspberry Pi
_DEB_ARCHITECTURES = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}          # `platform.machine()` to the name of the .deb that runs on it
_MAC_ARCHITECTURES = {"arm64": "arm64", "aarch64": "arm64"}                                             # `platform.machine()` to the name in the macOS app's .dmg, which is built for Apple silicon alone


@dataclass(frozen=True)
class Update:
    """What the version page said: the latest version, where to get it, an optional short note from the project, and the HF dial the group meets on."""
    version: str
    url: str                         # https, or empty
    message: str
    hf_dial: str = ""                # "7.0541 MHz USB"; empty when the page names none (a page older than 0.16.1) or names one that is not of that form


def _parts(version: str) -> list[str]:
    return _PART.findall(version.strip())


def compare_versions(a: str, b: str) -> int:
    """-1, 0 or 1 as `a` is older than, the same as or newer than `b`. "0.10.0" is newer than "0.9.0", a missing part counts as 0 ("1.0" is "1.0.0"), "1.0.0-rc1" is older than "1.0.0", and the number of a suffix counts as a number ("1.0.0-rc2" is older than "1.0.0-rc10")."""
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
    """The answer of the version page, `{"version", "url", "message", "hf_dial"}`, or None when it is not one: the version must look like one, an address that is not https is dropped, the note is cut to MAX_MESSAGE characters,
    and a dial that is not "N.NNNN MHz USB" (or LSB) is dropped."""
    try:
        data: Any = json.loads(body)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    version, url, message, dial = (text.strip() if isinstance(text := data.get(key), str) else "" for key in ("version", "url", "message", "hf_dial"))
    if not _VERSION.match(version):
        return None
    return Update(version, url if url.startswith("https://") else "", message[:MAX_MESSAGE], dial if _DIAL.match(dial) else "")


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


def mac_architecture(machine: str) -> str:
    """The architecture in the name of the macOS app's .dmg for this Mac (`platform.machine()`): `arm64` for Apple silicon, empty for a Mac the release has no app for."""
    return _MAC_ARCHITECTURES.get(machine.lower(), "")


InstallKind = Literal["windows-installer", "appimage", "macos-app", "deb", "uv-tool", "pip", "source"]


@dataclass(frozen=True)
class InstallInfo:
    """How this copy was installed. `appimage` is the file it runs from (kind `appimage` only, else empty); `arch` is the architecture of the file it was installed from (kind `deb`: `amd64` or `arm64`; kind `macos-app`: `arm64`; else empty, and empty for a machine the release has no file for); `service` says whether a service (the systemd unit, the launchd agent, the Windows Run key) starts it."""
    kind: InstallKind
    appimage: str = ""
    service: bool = False
    arch: str = ""


def install_kind(frozen: bool, appimage: str | None, deb: bool, checkout: bool, uv_tool: bool, app_bundle: bool = False) -> InstallKind:
    """The way this copy got here, from what the process can see: a frozen program is the Windows installer's, a run from an AppImage file is the AppImage, a Python inside `NeoAPRS.app` is the macOS app's, the Python of
    /opt/neoaprs is the .deb's, a package imported from a clone of the repository is a checkout, a package in the environment `uv tool` made is an install of the wheel (which releases before 0.16 offered), anything else
    a plain pip (or `uv pip`) environment."""
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


PLAIN_INSTALL = InstallInfo("pip")          # what a part that was not told how it was installed assumes (the tests)


@dataclass(frozen=True)
class Frequency:
    """A frequency the project suggests: the band, `40 m`, and the dial with its mode, `7.0541 MHz USB`."""
    band: str
    dial: str


def is_dial(text: str) -> bool:
    """Whether the text is an HF dial as the page names it, `7.0541 MHz USB` (or LSB): the form of the suggested frequencies and of a sked."""
    return _DIAL.fullmatch(text) is not None


def parse_frequencies(body: bytes | str) -> list[Frequency] | None:
    """The list in the project's file, `{"frequencies": [{"band": "40 m", "dial": "7.0541 MHz USB"}, ...]}`: every entry that is not of the two forms is dropped, a band that is there already is dropped, and the first MAX_FREQUENCIES are kept.
    None for a file that is no list or has not one good entry (the last good list stands then)."""
    try:
        data: Any = json.loads(body)
    except ValueError:
        return None
    entries = data.get("frequencies") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return None
    found: list[Frequency] = []
    for entry in entries:
        band, dial = (text.strip() if isinstance(entry, dict) and isinstance(text := entry.get(key), str) else "" for key in ("band", "dial"))
        if _BAND.match(band) and _DIAL.match(dial) and all(f.band != band for f in found) and len(found) < MAX_FREQUENCIES:
            found.append(Frequency(band, dial))
    return found or None


def frequencies_text(frequencies: list[Frequency]) -> str:
    """The list as the settings table keeps it: the file's own form."""
    return json.dumps({"frequencies": [{"band": f.band, "dial": f.dial} for f in frequencies]})


def suggested(listed: list[Frequency], hf_dial: str, built_in: list[Frequency], dial_band: str) -> list[Frequency]:
    """What the HF box shows: the project's list when there is one; else the dial the version page names (for `dial_band`, the 40 m the earlier copies were told of); else the built-in list."""
    if listed:
        return listed
    return [Frequency(dial_band, hf_dial)] if hf_dial else built_in


def on_this_computer(text: str) -> bool:
    """Whether `text` is the address of a server on this computer: http or https, the host 127.0.0.1 or localhost, no user, no space (what a test or a bench may point the frequencies at)."""
    try:
        parts = urlsplit(text)
        _ = parts.port
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and parts.hostname in ("127.0.0.1", "localhost") and "@" not in parts.netloc and not any(c.isspace() for c in text)
