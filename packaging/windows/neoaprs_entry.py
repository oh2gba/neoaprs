"""The entry of the frozen app: one script for the three programs of the folder. `neoaprs.exe` has a console (the command line, `neoaprs doctor`, the logs on the screen); `neoaprsw.exe` has none and is the
daemon (`neoaprsw.exe run`, `open`, `stop`); `neoaprs-app.exe` has none and is the desktop app (the Start menu, the start at sign-in). They are the same program, told apart by their own names.
The app's role shows its splash (neoaprs/desktop/splash.py) before it imports the app, which is the heavy part of its start; each role imports only its own."""
import os
import sys


def role(executable: str) -> str:
    """"app", "daemon" or "cli", by the program's own name."""
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
