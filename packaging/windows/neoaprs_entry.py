"""The entry of the frozen app: one script for the three programs of the folder. `neoaprs.exe` has a console (the command line, `neoaprs doctor`, the logs on the screen); `neoaprsw.exe` has none and is the
daemon (`neoaprsw.exe run`, `open`, `stop`); `neoaprs-app.exe` has none and is the desktop app (the Start menu, the start at sign-in). They are the same program, told apart by their own names."""
import os
import sys

from neoaprs.cli import gui_main, main
from neoaprs.desktop.cmd import gui_main as app_main

if __name__ == "__main__":
    name = os.path.basename(sys.executable).lower()
    if name.startswith("neoaprs-app"):
        sys.exit(app_main())
    sys.exit(gui_main() if name.startswith("neoaprsw") else main())
