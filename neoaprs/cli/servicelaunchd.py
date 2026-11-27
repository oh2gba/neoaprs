"""The service on macOS: a per-user launchd agent, ~/Library/LaunchAgents/eu.oh2gba.neoaprs.plist.

It starts at login and restarts after a crash; after a refusal to start it stays stopped, with the
reason kept for `status`. A plist at that path that is not this agent's is never touched."""

import os
import plistlib
import subprocess
from pathlib import Path

from .daemonstate import describe, page_address
from .logfile import LOG_NAME
from .servicecmd import Plan

LABEL = "eu.oh2gba.neoaprs"
RESTART_AFTER_SEC = 30
LOG_HINT = ""
# In the agent's environment: the daemon runs under launchd.
UNDER_LAUNCHD = "NEOAPRS_LAUNCHD"
# In the data folder: why the daemon last refused to start under launchd.
REFUSAL_NAME = "launchd.refused"


def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def domain() -> str:
    return f"gui/{os.getuid()}"  # type: ignore[attr-defined, unused-ignore]


def render(plan: Plan) -> bytes:
    """Return the plist running `-m neoaprs --data DIR` with this interpreter.

    Output from before the daemon logs (a traceback) goes to launchd.log in the data folder."""
    return plistlib.dumps(
        {
            "Label": LABEL,
            "ProgramArguments": [plan.python, "-m", "neoaprs", "--data", str(plan.data)],
            "RunAtLoad": True,
            "KeepAlive": {"SuccessfulExit": False},
            "ThrottleInterval": RESTART_AFTER_SEC,
            "StandardOutPath": str(plan.data / "launchd.log"),
            "StandardErrorPath": str(plan.data / "launchd.log"),
            "WorkingDirectory": str(plan.clone or plan.data),
            "EnvironmentVariables": {"PYTHONUNBUFFERED": "1", UNDER_LAUNCHD: "1"},
        }
    )


def refused(data_dir: Path, code: int, reason: str) -> int:
    """Return the exit code of a refusal to start: under launchd a success with the reason kept,
    since launchd cannot tell exit codes apart and would restart it every 30 s."""
    if os.environ.get(UNDER_LAUNCHD) != "1":
        return code
    try:
        (data_dir / REFUSAL_NAME).write_text(reason + "\n", encoding="utf-8")
    except OSError:
        pass  # a data folder that cannot be written: the reason is on stderr, which is launchd.log
    return 0


def started(data_dir: Path) -> None:
    """The daemon runs: a refusal from before no longer says why the service is stopped."""
    try:
        (data_dir / REFUSAL_NAME).unlink(missing_ok=True)
    except OSError:
        pass


def refusal(data_dir: Path) -> str | None:
    """Return why the service is stopped after a refusal, or None."""
    if not os.access(data_dir, os.W_OK):
        return "the data folder cannot be made or used"
    try:
        return (data_dir / REFUSAL_NAME).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


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
        return subprocess.run(["launchctl", *args], check=False).returncode  # noqa: S607  (the system's launchctl, found on PATH)
    except FileNotFoundError:
        print("launchctl was not found: this is not macOS")
        return -1


def loaded() -> bool:
    try:
        return (
            subprocess.run(["launchctl", "print", f"{domain()}/{LABEL}"], capture_output=True, check=False).returncode  # noqa: S607
            == 0
        )
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
    launchctl("bootout", f"{domain()}/{LABEL}")  # replaces an agent that is already loaded
    if launchctl("bootstrap", domain(), str(path)) != 0:
        print("launchctl did not load the agent; try: launchctl bootstrap " + domain() + " " + path.as_posix())
        return 1
    print(
        f"neoaprs runs and starts at login (log: {plan.data / LOG_NAME}); the page is on {page_address(plan.data)} (the setting web/port)"
    )
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
    why = refusal(plan.data) if is_set else None
    if why is not None:
        print(f"the service is stopped because {why}; start it again with: neoaprs service install")
    if not is_set:
        print("set it up with: neoaprs service install")
    return 0 if is_loaded and running and why is None else 1
