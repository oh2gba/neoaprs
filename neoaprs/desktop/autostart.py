"""Start at sign-in, behind the tray menu's checkbox.

It starts `neoaprs-app --tray`: on Windows the `NeoAPRS` Run key value (shared with
`neoaprs service install`), on Linux the XDG autostart file."""
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Protocol

from neoaprs.cli import servicecmd, servicewindows
from neoaprs.instancelock import is_file
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
                appimage: Callable[[], str | None] = servicecmd.appimage_file, encryption: bool = False) -> list[str]:
    """Return the command line that starts the app in the tray.

    An AppImage starts the file itself (its mount vanishes). `--data` only if not the default."""
    platform = sys.platform if platform is None else platform
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    here = (PureWindowsPath if platform == "win32" else PurePosixPath)(sys.executable if executable is None else executable)
    suffix = ".exe" if platform == "win32" else ""
    tail = (["--tray"] if data.resolve() == default_data_dir().resolve() else ["--tray", "--data", str(data)]) + (["--encryption"] if encryption else [])
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
    """Return the Exec line of a desktop entry, quoted as the Desktop Entry specification says.

    The file format's own escaping applies first, so each quoting backslash is doubled."""
    def one(arg: str) -> str:
        arg = arg.replace("\\", "\\" * 4).replace('"', '\\' * 2 + '"').replace("`", '\\' * 2 + "`").replace("$", '\\' * 2 + "$").replace("%", "%%")
        return f'"{arg}"' if any(c in arg for c in " \t\n\"'\\><~|&;*?#()`$") else arg
    return " ".join(one(a) for a in argv)


class RunKeyAutoStart:
    """Windows Run key; an entry that starts the daemon (the service) does not count as enabled."""

    def __init__(self, command: list[str]) -> None:
        self.command = subprocess.list2cmdline(command)

    def enabled(self) -> bool:
        try:
            current = servicewindows.current()
        except OSError:
            return False
        return current is not None and servicewindows.ours(current) and "--tray" in current

    def enable(self) -> None:
        try:
            current = servicewindows.current()
            if current is not None and not servicewindows.ours(current):
                raise AutoStartError(f"the Run entry {servicewindows.VALUE_NAME} exists and is not NeoAPRS's ({current}); remove it in Settings > Apps > Startup first")
            servicewindows.write(self.command)
        except OSError as e:
            raise AutoStartError(f"the Run entry could not be changed: {e}") from e

    def disable(self) -> None:
        try:
            current = servicewindows.current()
            if current is not None and servicewindows.ours(current):
                servicewindows.delete()
        except OSError as e:
            raise AutoStartError(f"the Run entry could not be changed: {e}") from e


class DesktopFileAutoStart:
    """Linux: `autostart/neoaprs.desktop` in the user's config folder."""

    def __init__(self, command: list[str]) -> None:
        self.command = command
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        self.path = Path(base) / "autostart" / DESKTOP_NAME

    def enabled(self) -> bool:
        return is_file(self.path)

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


def autostart_for(data: Path, platform: str | None = None, encryption: bool = False) -> AutoStart | None:
    """Return the sign-in start for this system, or None where there is none (macOS)."""
    platform = sys.platform if platform is None else platform
    if platform == "win32":
        return RunKeyAutoStart(app_command(data, platform, encryption=encryption))
    if platform.startswith("linux"):
        return DesktopFileAutoStart(app_command(data, platform, encryption=encryption))
    return None
