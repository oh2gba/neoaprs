"""Start at sign-in, the app's checkbox in the tray menu: it starts `neoaprs-app --tray` (the app in the tray, the window hidden) and not the daemon, which the app starts itself. On Windows it is the value
`NeoAPRS` of the Run key of the user, the one entry that `neoaprs service install` and the installer's task write too (so there is one start at sign-in, whichever wrote it); on Linux an XDG autostart file,
`~/.config/autostart/neoaprs.desktop`, which KDE, GNOME and the others read. Elsewhere there is none and the menu does not offer it. Both are told what to run by `app_command`."""
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Protocol

from neoaprs.cli import servicecmd, servicewindows
from neoaprs.paths import default_data_dir

APP_NAME = "neoaprs-app"
DESKTOP_NAME = "neoaprs.desktop"


class AutoStartError(Exception):
    """The start at sign-in cannot be changed; the text says why."""


class AutoStart(Protocol):
    def enabled(self) -> bool: ...
    def enable(self) -> None: ...
    def disable(self) -> None: ...


def app_command(data: Path, platform: str | None = None, frozen: bool | None = None, executable: str | None = None, which: Callable[[str], str | None] = shutil.which,
                appimage: Callable[[], str | None] = servicecmd.appimage_file) -> list[str]:
    """The program and arguments that start the app in the tray: in an AppImage the AppImage file with `app` (the interpreter is in a folder that is gone when it ends), else the installed program `neoaprs-app`
    (next to this Python; in a frozen app its own windowless program, beside whichever one of the folder is running), else this Python with `-m neoaprs app` (`pythonw` on Windows: no console window).
    `--data` is given only when the folder is not the default one."""
    platform = sys.platform if platform is None else platform
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    here = (PureWindowsPath if platform == "win32" else PurePosixPath)(sys.executable if executable is None else executable)
    suffix = ".exe" if platform == "win32" else ""
    tail = ["--tray"] if data.resolve() == default_data_dir().resolve() else ["--tray", "--data", str(data)]
    image = appimage() if platform.startswith("linux") else None
    if image:
        return [image, "app", *tail]
    if frozen:
        return [str(here.with_name(APP_NAME + suffix)), *tail]
    script = here.with_name(APP_NAME + suffix)
    program = str(script) if Path(script).is_file() else which(APP_NAME)
    if program:
        return [program, *tail]
    python = here.with_name("pythonw.exe") if platform == "win32" and Path(here.with_name("pythonw.exe")).is_file() else here
    return [str(python), "-m", "neoaprs", "app", *tail]


def desktop_exec(argv: list[str]) -> str:
    """The Exec line of a desktop entry: an argument with a space or a quote is in double quotes, and the characters the specification says (`"`, `` ` ``, `$`, `\\`) have a backslash, `%` is doubled."""
    def one(arg: str) -> str:
        arg = arg.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$").replace("%", "%%")
        return f'"{arg}"' if any(c in arg for c in " \t\n\"'\\><~|&;*?#()`$") else arg
    return " ".join(one(a) for a in argv)


class RunKeyAutoStart:
    """Windows: the Run key. `enabled` is true when the entry is NeoAPRS's and starts the app (`--tray`); an entry that starts the daemon (the service) is not the app's, and enabling replaces it."""

    def __init__(self, command: list[str]) -> None:
        self.command = subprocess.list2cmdline(command)

    def enabled(self) -> bool:
        current = servicewindows.current()
        return current is not None and servicewindows.ours(current) and "--tray" in current

    def enable(self) -> None:
        current = servicewindows.current()
        if current is not None and not servicewindows.ours(current):
            raise AutoStartError(f"the Run entry {servicewindows.VALUE_NAME} exists and is not NeoAPRS's ({current}); remove it in Settings > Apps > Startup first")
        servicewindows.write(self.command)

    def disable(self) -> None:
        current = servicewindows.current()
        if current is not None and servicewindows.ours(current):
            servicewindows.delete()


class DesktopFileAutoStart:
    """Linux: `autostart/neoaprs.desktop` in the user's config folder (`$XDG_CONFIG_HOME`, else `~/.config`)."""

    def __init__(self, command: list[str]) -> None:
        self.command = command
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        self.path = Path(base) / "autostart" / DESKTOP_NAME

    def enabled(self) -> bool:
        return self.path.is_file()

    def enable(self) -> None:
        text = ("[Desktop Entry]\nType=Application\nName=NeoAPRS\nComment=APRS client, in the tray\n"
                f"Exec={desktop_exec(self.command)}\nTerminal=false\nX-GNOME-Autostart-enabled=true\n")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(text, encoding="utf-8")
        except OSError as e:
            raise AutoStartError(f"{self.path} could not be written: {e}") from e

    def disable(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError as e:
            raise AutoStartError(f"{self.path} could not be removed: {e}") from e


def autostart_for(data: Path, platform: str | None = None) -> AutoStart | None:
    """The start at sign-in of this system, or None where the app has none to offer (macOS)."""
    platform = sys.platform if platform is None else platform
    if platform == "win32":
        return RunKeyAutoStart(app_command(data, platform))
    if platform.startswith("linux"):
        return DesktopFileAutoStart(app_command(data, platform))
    return None
