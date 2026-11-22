"""The default data folder, shared by the daemon and the command line tools.

It follows each system's convention: %LOCALAPPDATA% on Windows (not the roaming profile, which
would copy the database), Application Support on macOS, the XDG data folder elsewhere."""
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
