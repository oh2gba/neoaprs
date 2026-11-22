"""Entry of the frozen app: one script for neoaprs.exe (console), neoaprsw.exe (daemon, no console)
and neoaprs-app.exe (desktop app, no console), told apart by the program's name.

The app role shows its splash before importing the heavy app modules."""

import os
import sys


def role(executable: str) -> str:
    """ "app", "daemon" or "cli", by the program's own name."""
    name = os.path.basename(executable).lower()
    if name.startswith("neoaprs-app"):
        return "app"
    return "daemon" if name.startswith("neoaprsw") else "cli"


def run(which: str, argv: list[str]) -> int:
    if which == "app":
        from neoaprs.desktop import splash

        splash.show(argv)
        from neoaprs.desktop.cmd import gui_main as app_main

        return app_main()
    from neoaprs.cli import gui_main, main

    return gui_main() if which == "daemon" else main()


if __name__ == "__main__":
    sys.exit(run(role(sys.executable), sys.argv[1:]))
