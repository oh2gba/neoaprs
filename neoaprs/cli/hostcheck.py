"""What on this computer keeps a serial port from working, as `neoaprs doctor` and `neoaprs service install` say it: the user is not in the group that owns the serial devices, and the programs
(brltty, ModemManager) that take a USB serial adapter for a braille display or a modem as soon as it is plugged in. Linux only; elsewhere there is nothing to say."""
import glob
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

GROUPS = ("dialout", "uucp")               # who owns the serial devices: dialout on Debian, Ubuntu, Fedora and openSUSE, uucp on Arch
DEVICE_GLOBS = ("/dev/ttyUSB*", "/dev/ttyACM*")
BRLTTY_FILES = ("/usr/bin/brltty", "/usr/sbin/brltty", "/usr/lib/udev/rules.d/85-brltty.rules", "/lib/udev/rules.d/85-brltty.rules")
MODEMMANAGER_FILES = ("/usr/sbin/ModemManager", "/usr/bin/ModemManager", "/usr/lib/systemd/system/ModemManager.service", "/lib/systemd/system/ModemManager.service")


@dataclass(frozen=True)
class GroupCheck:
    status: str                 # "ok", "missing" (not in the group), "relogin" (in it, but this session started before) or "unknown"
    group: str
    fix: str                    # the command or the step that cures it; empty when ok


def decide(wanted: list[str], session: set[str], member: set[str], user: str) -> GroupCheck:
    """Whether the user has one of the groups `wanted` in this session (`session`) or only in the group database (`member`)."""
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
    """The check for this user: the groups of the serial devices that are plugged in, else the one of the groups above that this system has."""
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
