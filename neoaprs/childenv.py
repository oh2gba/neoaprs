"""The environment of programs started for the operator, and the path of Windows system programs.

A child gets only what a program needs in a desktop session: search path, home, language,
and the display, audio and message bus.
"""

import os
from collections.abc import Mapping
from pathlib import PureWindowsPath

_NAMES = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "LANG",
        "LANGUAGE",
        "TZ",
        "TERM",
        "TMPDIR",
        "DISPLAY",
        "XAUTHORITY",
        "WAYLAND_DISPLAY",
        "DBUS_SESSION_BUS_ADDRESS",
        "DESKTOP_SESSION",
        # Windows: PowerShell, Python and Winsock programs fail to start without these.
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "USERNAME",
        "USERDOMAIN",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "COMMONPROGRAMFILES",
        "HOMEDRIVE",
        "HOMEPATH",
        "PROCESSOR_ARCHITECTURE",
        "NUMBER_OF_PROCESSORS",
        "OS",
        "PSMODULEPATH",
    }
)
# Locale, session directories (XDG_RUNTIME_DIR holds the audio and bus sockets), sound system,
# toolkits.
_PREFIXES = ("LC_", "XDG_", "WAYLAND_", "PULSE_", "PIPEWIRE_", "ALSA_", "QT_", "GTK_", "GDK_")


def child_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return `source` (default: this process's environment) reduced to the names above."""
    env = os.environ if source is None else source
    return {name: value for name, value in env.items() if name in _NAMES or name.startswith(_PREFIXES)}


def windows_program(*parts: str, system32: bool = True, source: Mapping[str, str] | None = None) -> str:
    """Return the full path of a Windows system program below %SystemRoot%\\System32.

    A bare name is searched in the working folder first, where a planted file could shadow it.
    """
    env = {name.upper(): value for name, value in (os.environ if source is None else source).items()}
    root = PureWindowsPath(env.get("SYSTEMROOT") or env.get("WINDIR") or "C:\\Windows")
    return str(root / "System32" / PureWindowsPath(*parts) if system32 else root / PureWindowsPath(*parts))
