"""Where the programs NeoAPRS ships with live, in every kind of installation, as one rule.

NeoAPRS carries the programs it needs (the Mercury HF modem) inside its own release files, pinned to one version and built or taken by the release workflow, so that what the suite ran against is what the operator
has, and nothing is installed, fetched or looked for on the operator's system. Each install kind puts them in its own tree: the Windows app in `bin/` beside its executables (the installer packs the whole app
folder), the AppImage in `usr/tools/` of its image and the .deb in `/opt/neoaprs/tools/`, which are both `<sys.prefix>/tools` of the Python they bring, as is `.venv/tools` of a checkout where the developer
built them (scripts/build-mercury --install). A program `X` is the folder `tools_dir()/X` with the program file and everything it needs beside it (its libraries, its licence)."""
import sys
from pathlib import Path


def tools_dir() -> Path:
    """The folder of the shipped programs: `bin/` beside the executable of a frozen program (the Windows app), else `tools/` of the Python's prefix (the AppImage, the .deb, a venv)."""
    return Path(sys.executable).resolve().parent / "bin" if getattr(sys, "frozen", False) else Path(sys.prefix) / "tools"
