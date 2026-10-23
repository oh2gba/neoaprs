"""The service on Windows: start at login for the current user, through the value `NeoAPRS` of the key HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run (winreg, in the standard
library; the same list that Settings > Apps > Startup shows). It runs `neoaprsw.exe run --data DIR`, the script that has no console window, or `pythonw.exe -m neoaprs run --data DIR` when NeoAPRS is not
installed as a script. It is not a Windows service: a service has no desktop and no profile of the user, and the COM port, the data folder and the page belong to the user who is logged in.
The registry is reached through the `winreg` module as `sys.modules` has it, so that the tests can put a stand-in in its place."""
import importlib
import subprocess
import sys
from typing import Any

from .daemonstate import describe, is_running
from .servicecmd import Plan

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "NeoAPRS"
LOG_HINT = ""
DETACHED = 0x00000008 | 0x00000200 | 0x08000000            # DETACHED_PROCESS, CREATE_NEW_PROCESS_GROUP, CREATE_NO_WINDOW


def launch_argv(plan: Plan) -> list[str]:
    """The program and arguments that start the daemon with no console window."""
    data = str(plan.data)
    if plan.gui_exe:
        return [plan.gui_exe, "run", "--data", data]
    return [plan.pythonw or plan.python, "-m", "neoaprs", "run", "--data", data]


def command_line(plan: Plan) -> str:
    return subprocess.list2cmdline(launch_argv(plan))


def _registry() -> Any:
    return importlib.import_module("winreg")


def current() -> str | None:
    """The command that is set, or None."""
    winreg = _registry()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return None
    return str(value)


def write(command: str) -> None:
    """Sets the Run entry to `command` (it is the entry of NeoAPRS's start at login, whichever program it starts)."""
    winreg = _registry()
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)


def delete() -> None:
    winreg = _registry()
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.DeleteValue(key, VALUE_NAME)


def ours(command: str) -> bool:
    return "neoaprs" in command.lower()


def installed(plan: Plan) -> tuple[bool, str]:
    command = current()
    if command is None:
        return False, "no Run entry"
    return True, f"the Run entry {VALUE_NAME}: {command}"


def spawn(argv: list[str]) -> None:
    """Starts the daemon now, detached from this console (the entry only starts it at the next login)."""
    flags = DETACHED if sys.platform == "win32" else 0
    subprocess.Popen(argv, creationflags=flags, close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def install(plan: Plan) -> int:
    before = current()
    if before is not None and not ours(before):
        print(f"the Run entry {VALUE_NAME} exists and is not NeoAPRS's ({before}); remove it in Settings > Apps > Startup or regedit and run this again")
        return 1
    command = command_line(plan)
    plan.data.mkdir(parents=True, exist_ok=True)
    write(command)
    print(f"NeoAPRS will start when you log in: {command}" if before in (None, command) else f"the start at login was changed to: {command}")
    if is_running(plan.data):
        print("a daemon is running on this data folder already; it is left alone")
    else:
        spawn(launch_argv(plan))
        print(f"started it now; its log is {plan.data / 'neoaprs.log'}, its page http://127.0.0.1:7303/ (the setting web/port)")
    return 0


def remove(plan: Plan) -> int:
    before = current()
    if before is not None and not ours(before):
        print(f"the Run entry {VALUE_NAME} is not NeoAPRS's ({before}); nothing was changed")
        return 1
    if before is None:
        print("NeoAPRS did not start at login; nothing was changed")
        return 0
    delete()
    print("NeoAPRS no longer starts at login; the data folder is untouched")
    if is_running(plan.data):
        print("the daemon that is running now goes on until you end it (`neoaprs stop`) or log out")
    return 0


def status(plan: Plan) -> int:
    is_set, what = installed(plan)
    print(f"start at login: {'set: ' + what if is_set else 'not set (' + what + ')'}")
    running, line = describe(plan.data)
    print(f"daemon: {line}")
    if not is_set:
        print("set it up with: neoaprs service install")
    return 0 if is_set and running else 1
