"""Where the programs shipped with NeoAPRS (the Mercury HF modem, Direwolf) are installed.

Windows: `bin/` beside the executable. Elsewhere `<sys.prefix>/tools`: `usr/tools/` in the AppImage,
`Contents/Resources/tools/` in the macOS app, `/opt/neoaprs/tools/` in the .deb and `.venv/tools`
in a checkout. A program `X` lives in `tools_dir()/X`."""

import sys
from pathlib import Path


def tools_dir() -> Path:
    """Return the folder of the shipped programs."""
    return (
        Path(sys.executable).resolve().parent / "bin" if getattr(sys, "frozen", False) else Path(sys.prefix) / "tools"
    )
