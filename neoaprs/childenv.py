"""The environment of a program NeoAPRS starts for the operator: the message alert's command.

NeoAPRS's own environment holds nothing a command of the operator's settings needs to see, so it gets what a program needs to find its way in a session and nothing else: where its programs and its home
are, the language, and the display, audio and message bus of the desktop session (an alert that shows a notification or plays a sound needs those). The unit sets DBUS_SESSION_BUS_ADDRESS
(neoaprs/cli/neoaprs.service), because a user service does not inherit the session's. If a command needs another variable it sets it itself: `env NAME=value command ...`.
"""
import os
from collections.abc import Mapping

_NAMES = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LANGUAGE", "TZ", "TERM", "TMPDIR",
    "DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "DESKTOP_SESSION",
    # Windows: without these PowerShell, Python and anything that uses Winsock fail to start
    "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "USERPROFILE", "USERNAME", "USERDOMAIN", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
    "PROGRAMFILES", "PROGRAMFILES(X86)", "COMMONPROGRAMFILES", "HOMEDRIVE", "HOMEPATH", "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS", "OS", "PSMODULEPATH",
})
# LC_* are the locale, XDG_* the session's directories (XDG_RUNTIME_DIR holds the sockets of the audio server and the bus), the others the sound system and the toolkits
_PREFIXES = ("LC_", "XDG_", "WAYLAND_", "PULSE_", "PIPEWIRE_", "ALSA_", "QT_", "GTK_", "GDK_")


def child_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """`source` (the environment of this process by default) reduced to the names above."""
    env = os.environ if source is None else source
    return {name: value for name, value in env.items() if name in _NAMES or name.startswith(_PREFIXES)}
