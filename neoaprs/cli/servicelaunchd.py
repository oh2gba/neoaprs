"""The service on macOS: a launchd agent of the user, ~/Library/LaunchAgents/eu.oh2gba.neoaprs.plist, started at login and kept running (`launchctl bootstrap` and `bootout` in the user's gui domain).
An agent that exits with a failure is started again after 30 seconds; a file at that place that is not this agent's is never touched."""
import os
import plistlib
import subprocess
from pathlib import Path

from .daemonstate import describe
from .servicecmd import Plan

LABEL = "eu.oh2gba.neoaprs"
RESTART_AFTER_SEC = 30
LOG_HINT = ""


def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def domain() -> str:
    return f"gui/{os.getuid()}"  # type: ignore[attr-defined, unused-ignore]


def render(plan: Plan) -> bytes:
    """The agent: this interpreter running `-m neoaprs --data DIR`; its own output (a traceback before the daemon logs anything) goes to launchd.log in the data folder."""
    return plistlib.dumps({
        "Label": LABEL,
        "ProgramArguments": [plan.python, "-m", "neoaprs", "--data", str(plan.data)],
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": RESTART_AFTER_SEC,
        "StandardOutPath": str(plan.data / "launchd.log"),
        "StandardErrorPath": str(plan.data / "launchd.log"),
        "WorkingDirectory": str(plan.clone or plan.data),
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
    })


def ours(path: Path) -> bool:
    try:
        content = plistlib.loads(path.read_bytes())
    except (OSError, plistlib.InvalidFileException, ValueError):
        return False
    return isinstance(content, dict) and content.get("Label") == LABEL


def installed(plan: Plan) -> tuple[bool, str]:
    path = plist_path()
    if ours(path):
        return True, f"the launchd agent {path}"
    return False, "no launchd agent" if not path.exists() else f"{path} exists but is not NeoAPRS's"


def launchctl(*args: str) -> int:
    try:
        return subprocess.run(["launchctl", *args], check=False).returncode
    except FileNotFoundError:
        print("launchctl was not found: this is not macOS")
        return -1


def loaded() -> bool:
    try:
        return subprocess.run(["launchctl", "print", f"{domain()}/{LABEL}"], capture_output=True, check=False).returncode == 0
    except FileNotFoundError:
        return False


def install(plan: Plan) -> int:
    path = plist_path()
    if path.exists() and not ours(path):
        print(f"{path} exists and is not NeoAPRS's; move it away and run this again")
        return 1
    plan.data.mkdir(parents=True, exist_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = render(plan)
    if not path.exists() or path.read_bytes() != content:
        scratch = path.with_name(path.name + ".new")
        scratch.write_bytes(content)
        scratch.replace(path)
        print(f"wrote {path} for {plan.python}")
    launchctl("bootout", f"{domain()}/{LABEL}")               # (an agent that is loaded already is replaced; there is nothing to stop the first time)
    if launchctl("bootstrap", domain(), str(path)) != 0:
        print("launchctl did not load the agent; try: launchctl bootstrap " + domain() + " " + path.as_posix())
        return 1
    print(f"neoaprs runs and starts at login (log: {plan.data / 'neoaprs.log'}); the page is on http://127.0.0.1:7303 (the setting web/port)")
    return 0


def remove(plan: Plan) -> int:
    path = plist_path()
    if path.exists() and not ours(path):
        print(f"{path} is not NeoAPRS's; nothing was changed")
        return 1
    launchctl("bootout", f"{domain()}/{LABEL}")
    if path.exists():
        path.unlink()
        print(f"removed {path}")
    print("neoaprs is no longer a service; the data folder is untouched")
    return 0


def status(plan: Plan) -> int:
    is_set, what = installed(plan)
    print(f"service: {'set up: ' + what if is_set else 'not set up (' + what + ')'}")
    is_loaded = is_set and loaded()
    if is_set:
        print("launchd: " + ("loaded" if is_loaded else "not loaded"))
    running, line = describe(plan.data)
    print(f"daemon: {line}")
    if not is_set:
        print("set it up with: neoaprs service install")
    return 0 if is_loaded and running else 1
