"""Find what on this computer keeps a serial port from working (Linux only).

Used by `neoaprs doctor` and `neoaprs service install`: serial group membership, brltty and
ModemManager (which grab USB serial adapters), and Firefox as a Flatpak on KDE."""
import glob
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# The group owning serial devices: dialout on most distributions, uucp on Arch.
GROUPS = ("dialout", "uucp")
DEVICE_GLOBS = ("/dev/ttyUSB*", "/dev/ttyACM*")
BRLTTY_FILES = ("/usr/bin/brltty", "/usr/sbin/brltty", "/usr/lib/udev/rules.d/85-brltty.rules", "/lib/udev/rules.d/85-brltty.rules")
MODEMMANAGER_FILES = ("/usr/sbin/ModemManager", "/usr/bin/ModemManager", "/usr/lib/systemd/system/ModemManager.service", "/lib/systemd/system/ModemManager.service")


@dataclass(frozen=True)
class GroupCheck:
    # "ok", "missing", "relogin" (in the group, but not this session) or "unknown".
    status: str
    group: str
    fix: str  # empty when ok


def decide(wanted: list[str], session: set[str], member: set[str], user: str) -> GroupCheck:
    if not wanted:
        return GroupCheck("unknown", "", "")
    for group in wanted:
        if group in session:
            return GroupCheck("ok", group, "")
    for group in wanted:
        if group in member:
            return GroupCheck("relogin", group, f"{user} is in the group {group}, but this session began before: log out and in again (or reboot)")
    return GroupCheck("missing", wanted[0], f"sudo usermod -aG {wanted[0]} {user}   (then log out and in again)")


def serial_group_check(devices: list[str] | None = None, user: str | None = None) -> GroupCheck:
    """Check this user against the groups of the serial devices present, else of GROUPS."""
    if not _linux():
        return GroupCheck("unknown", "", "")
    import grp
    import getpass
    name = user or os.environ.get("USER") or getpass.getuser()
    found = devices if devices is not None else [p for pattern in DEVICE_GLOBS for p in glob.glob(pattern)]
    wanted: list[str] = []
    for device in sorted(found):
        try:
            owner = grp.getgrgid(os.stat(device).st_gid).gr_name  # type: ignore[attr-defined, unused-ignore]
        except (OSError, KeyError):
            continue
        if owner not in wanted and owner != "root":
            wanted.append(owner)
    if not wanted:
        wanted = [g for g in GROUPS if _group_exists(g)]
    session = {_group_name(gid) for gid in os.getgroups()} | {_group_name(os.getgid())}  # type: ignore[attr-defined, unused-ignore]
    member = {g.gr_name for g in grp.getgrall() if name in g.gr_mem}  # type: ignore[attr-defined, unused-ignore]
    return decide(wanted, session - {""}, member, name)


def _linux() -> bool:
    return sys.platform == "linux"


def _group_exists(name: str) -> bool:
    import grp
    try:
        grp.getgrnam(name)  # type: ignore[attr-defined, unused-ignore]
    except KeyError:
        return False
    return True


def _group_name(gid: int) -> str:
    import grp
    try:
        return grp.getgrgid(gid).gr_name  # type: ignore[attr-defined, no-any-return, unused-ignore]
    except KeyError:
        return ""


def _installed(program: str, files: tuple[str, ...]) -> bool:
    return shutil.which(program) is not None or any(Path(f).exists() for f in files)


def brltty_installed() -> bool:
    return sys.platform == "linux" and _installed("brltty", BRLTTY_FILES)


def modemmanager_installed() -> bool:
    return sys.platform == "linux" and _installed("ModemManager", MODEMMANAGER_FILES)


FIREFOX_FLATPAK = "org.mozilla.firefox"
NOTIFICATIONS_BUS_NAME = "org.freedesktop.Notifications"
IGNORE_PORTAL = "NOTIFY_IGNORE_PORTAL=1"
FLATPAK_WAIT_SEC = 10

# Runs `flatpak ARGS`; returns (exit status, stdout).
FlatpakRun = Callable[[list[str]], tuple[int, str]]


@dataclass(frozen=True)
class FlatpakFirefox:
    # "ok" or "missing" (notifications go to a portal).
    status: str
    fix: str  # one command per line; empty when ok


def run_flatpak(args: list[str]) -> tuple[int, str]:
    try:
        done = subprocess.run(["flatpak", *args], capture_output=True, text=True, timeout=FLATPAK_WAIT_SEC, check=False)  # noqa: S607
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return done.returncode, done.stdout


def firefox_flatpak(run: FlatpakRun = run_flatpak, desktop: str | None = None, flatpak_installed: bool | None = None) -> FlatpakFirefox | None:
    """Check whether Firefox as a Flatpak on KDE loses web notifications (the portal drops them).

    Return None where this does not apply (not Linux, not KDE, no flatpak, Firefox not a Flatpak).
    """
    if not _linux():
        return None
    where = os.environ.get("XDG_CURRENT_DESKTOP", "") if desktop is None else desktop
    if "KDE" not in where.upper().split(":"):
        return None
    if not (shutil.which("flatpak") is not None if flatpak_installed is None else flatpak_installed):
        return None
    if run(["info", FIREFOX_FLATPAK])[0] != 0:
        return None
    settings = "\n".join(
        run(args)[1]
        for args in (["override", "--user", "--show", FIREFOX_FLATPAK], ["override", "--system", "--show", FIREFOX_FLATPAK], ["info", "--show-permissions", FIREFOX_FLATPAK])
    )
    lines = {line.strip() for line in settings.splitlines()}
    fix = []
    if not lines & {f"{NOTIFICATIONS_BUS_NAME}=talk", f"{NOTIFICATIONS_BUS_NAME}=own"}:
        fix.append(f"flatpak override --user --talk-name={NOTIFICATIONS_BUS_NAME} {FIREFOX_FLATPAK}")
    if IGNORE_PORTAL not in lines:
        fix.append(f"flatpak override --user --env={IGNORE_PORTAL} {FIREFOX_FLATPAK}")
    if not fix:
        return FlatpakFirefox("ok", "")
    return FlatpakFirefox("missing", "\n      ".join([*fix, "then restart Firefox"]))
