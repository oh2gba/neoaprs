"""Where NeoAPRS keeps its data when nobody says: one rule for the daemon and the command line tools, so that they look in the same place. The place of the system's own convention: %LOCALAPPDATA%
on Windows (local, not the roaming profile: a database must not travel), Application Support on macOS, the XDG data folder on Linux and the others."""
import os
import sys
from pathlib import Path


def default_data_dir() -> Path:
    env = os.environ.get("NEOAPRS_DATA_DIR")
    if env:
        return Path(env)
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "NeoAPRS"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "NeoAPRS"
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        return Path(base) / "neoaprs"
