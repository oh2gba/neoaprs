"""Alert commands for the tests, in the language the alert runs under: a POSIX shell line, or on Windows a PowerShell line (neoaprs/services/alerts.py). The same few commands on both, so that a test about
the alert does not care which system it is on."""
import sys
from pathlib import Path

WINDOWS = sys.platform == "win32"
MISSING_STATUS = 1 if WINDOWS else 127           # the status of a command that is not a program (PowerShell ends the script with 1)
TIMEOUT_SEC = 60.0 if WINDOWS else 5.0           # PowerShell takes a second or two to start on a runner, and more than 20 s when the runner is busy with a dozen test processes
SHORT_TIMEOUT_SEC = 3.0 if WINDOWS else 0.2      # the time a command is given when the test wants it to run out
SURVIVOR_AFTER_SEC = 5.0 if WINDOWS else 1.0     # when a program the command started would make its marker: later than the command is killed (PowerShell needs a second or two to get as far as starting it)
FIELDS = '$env:NEOAPRS_FROM,$env:NEOAPRS_TEXT,$env:NEOAPRS_AT,$env:NEOAPRS_MSG_ID'


def writing(path: Path, secret: bool = False) -> str:
    """A command that writes the four variables, one to a line, then a line `end` (or, with `secret`, what SECRET_OF_THE_DAEMON is, or `gone`), to the file."""
    if WINDOWS:
        last = "$(if($null -eq $env:SECRET_OF_THE_DAEMON){'gone'}else{$env:SECRET_OF_THE_DAEMON})" if secret else "'end'"
        return f"[IO.File]::WriteAllText('{path}.tmp',((@({FIELDS},{last}) -join \"`n\")+\"`n\"));Move-Item -Force '{path}.tmp' '{path}'"
    last = '"${SECRET_OF_THE_DAEMON-gone}"' if secret else '"end"'
    return f'printf "%s\\n" "$NEOAPRS_FROM" "$NEOAPRS_TEXT" "$NEOAPRS_AT" "$NEOAPRS_MSG_ID" {last} > {path}.tmp && mv {path}.tmp {path}'


def writing_titled(path: Path) -> str:
    """A command that writes the kind and the title of the alert, then the four variables `writing` writes and `end`, one to a line, to the file."""
    if WINDOWS:
        return f"[IO.File]::WriteAllText('{path}.tmp',((@($env:NEOAPRS_KIND,$env:NEOAPRS_TITLE,{FIELDS},'end') -join \"`n\")+\"`n\"));Move-Item -Force '{path}.tmp' '{path}'"
    return f'printf "%s\\n" "$NEOAPRS_KIND" "$NEOAPRS_TITLE" "$NEOAPRS_FROM" "$NEOAPRS_TEXT" "$NEOAPRS_AT" "$NEOAPRS_MSG_ID" "end" > {path}.tmp && mv {path}.tmp {path}'


def failing(status: int, *stderr: str) -> str:
    """A command that writes lines to stderr and ends with `status`."""
    if WINDOWS:
        return "".join(f"[Console]::Error.WriteLine('{line}');" for line in stderr) + f"exit {status}"
    return "".join(f"echo '{line}' >&2; " for line in stderr) + f"exit {status}"


def not_a_program() -> str:
    """A command that is no program. (On Windows a bare name makes PowerShell search every module it knows, which takes many seconds on a fresh machine: a path is refused at once.)"""
    return r"& 'C:\no-such-folder\program.exe' --please" if WINDOWS else "no-such-program-here --please"


def then_succeeds(command: str) -> str:
    """`command`, then a step that succeeds: a command that fails first must still fail."""
    return f"{command}; $true" if WINDOWS else f"{command}; true"


def missing_notifier() -> str:
    return not_a_program() if WINDOWS else "no-such-notifier-xyz"


def sleeping() -> str:
    return "Start-Sleep 30" if WINDOWS else "sleep 30"


def starting_a_survivor(marker: Path, after_sec: float) -> str:
    """A command that starts a program that would make `marker` after `after_sec` seconds, and then sleeps: ended with the command, the marker is never made."""
    if WINDOWS:
        code = f"import time,pathlib,sys;time.sleep({after_sec});pathlib.Path(sys.argv[1]).touch()"          # (no spaces: Start-Process joins the arguments with spaces and does not quote them)
        return f"Start-Process -WindowStyle Hidden -FilePath '{sys.executable}' -ArgumentList '-c','{code}','{marker}';Start-Sleep 30"
    return f"(sleep {after_sec}; touch {marker}) & sleep 30"
