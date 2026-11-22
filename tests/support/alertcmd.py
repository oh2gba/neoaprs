"""Alert commands for the tests, as a POSIX shell line or a PowerShell line on Windows."""
import sys
from pathlib import Path

WINDOWS = sys.platform == "win32"
# Status of a command that is not a program (PowerShell ends the script with 1).
MISSING_STATUS = 1 if WINDOWS else 127
# PowerShell takes a second or two to start, and over 20 s on a busy runner.
TIMEOUT_SEC = 60.0 if WINDOWS else 5.0
SHORT_TIMEOUT_SEC = 3.0 if WINDOWS else 0.2
# When a started program would make its marker: later than the command is killed.
SURVIVOR_AFTER_SEC = 5.0 if WINDOWS else 1.0
FIELDS = '$env:NEOAPRS_FROM,$env:NEOAPRS_TEXT,$env:NEOAPRS_AT,$env:NEOAPRS_MSG_ID'


def writing(path: Path, secret: bool = False) -> str:
    """A command that writes the four variables, one per line, then `end` (or the secret, or
    `gone`)."""
    if WINDOWS:
        last = "$(if($null -eq $env:SECRET_OF_THE_DAEMON){'gone'}else{$env:SECRET_OF_THE_DAEMON})" if secret else "'end'"
        return f"[IO.File]::WriteAllText('{path}.tmp',((@({FIELDS},{last}) -join \"`n\")+\"`n\"));Move-Item -Force '{path}.tmp' '{path}'"
    last = '"${SECRET_OF_THE_DAEMON-gone}"' if secret else '"end"'
    return f'printf "%s\\n" "$NEOAPRS_FROM" "$NEOAPRS_TEXT" "$NEOAPRS_AT" "$NEOAPRS_MSG_ID" {last} > {path}.tmp && mv {path}.tmp {path}'


def writing_titled(path: Path) -> str:
    """A command that writes the kind and title of the alert, the four variables and `end`."""
    if WINDOWS:
        return f"[IO.File]::WriteAllText('{path}.tmp',((@($env:NEOAPRS_KIND,$env:NEOAPRS_TITLE,{FIELDS},'end') -join \"`n\")+\"`n\"));Move-Item -Force '{path}.tmp' '{path}'"
    return f'printf "%s\\n" "$NEOAPRS_KIND" "$NEOAPRS_TITLE" "$NEOAPRS_FROM" "$NEOAPRS_TEXT" "$NEOAPRS_AT" "$NEOAPRS_MSG_ID" "end" > {path}.tmp && mv {path}.tmp {path}'


def failing(status: int, *stderr: str) -> str:
    """A command that writes lines to stderr and ends with `status`."""
    if WINDOWS:
        return "".join(f"[Console]::Error.WriteLine('{line}');" for line in stderr) + f"exit {status}"
    return "".join(f"echo '{line}' >&2; " for line in stderr) + f"exit {status}"


def not_a_program() -> str:
    """A command that is no program. A bare name makes PowerShell search every module; a path is
    refused at once."""
    return r"& 'C:\no-such-folder\program.exe' --please" if WINDOWS else "no-such-program-here --please"


def then_succeeds(command: str) -> str:
    """`command`, then a step that succeeds: a command that fails first must still fail."""
    return f"{command}; $true" if WINDOWS else f"{command}; true"


def missing_notifier() -> str:
    return not_a_program() if WINDOWS else "no-such-notifier-xyz"


def sleeping() -> str:
    return "Start-Sleep 30" if WINDOWS else "sleep 30"


def starting_a_survivor(marker: Path, after_sec: float) -> str:
    """A command that starts a program that would make `marker` after `after_sec` and then sleeps.
    """
    if WINDOWS:
        # No spaces: Start-Process joins the arguments with spaces and does not quote them.
        code = f"import time,pathlib,sys;time.sleep({after_sec});pathlib.Path(sys.argv[1]).touch()"
        return f"Start-Process -WindowStyle Hidden -FilePath '{sys.executable}' -ArgumentList '-c','{code}','{marker}';Start-Sleep 30"
    return f"(sleep {after_sec}; touch {marker}) & sleep 30"
