"""The Windows Firewall rule "NeoAPRS Mercury" made by the daemon, for the HF radio's Allow button: the line the installer runs (packaging/windows/neoaprs.iss, AddMercuryFirewallRule) as an administrator through
the verb `runas` (winelevate.py), so that a copy updated silently from a version before Mercury, which never saw the installer's prompt, gets the rule too.

A rule that blocks inbound connections to the shipped `mercury.exe` beats every allow rule, so one such rule is all that is made. A rule of the name that is wrong (another program, switched off, not a block, not inbound)
is deleted first in the same elevated run, so that one prompt does both: `cmd /s /c` runs the two `netsh` lines (`/s` makes cmd take the quotes of the line as they are, between the first and the last). The result
of the run is the exit code of `netsh`; whether the rule is in force is for mercuryfirewall.check to say afterwards."""
import logging
import ntpath
import os
from pathlib import Path
from typing import Literal

from .mercuryfirewall import RULE_NAME
from .winelevate import Declined, elevated, on_windows

log = logging.getLogger("neoaprs.mercury")

DESCRIPTION = "NeoAPRS: the Mercury HF modem is reached by NeoAPRS on this computer only"
DELETE_ARGUMENTS = f'advfirewall firewall delete rule name="{RULE_NAME}"'
TIMEOUT_SEC = 60.0               # for netsh to end once the prompt has been answered
Outcome = Literal["ran", "not_run"]       # `ran`: the program ended (its exit code is in the log); `not_run`: the prompt was declined, or the program could not be started, or did not end


def add_arguments(program: Path) -> str:
    """The arguments of the installer's netsh line: a rule that blocks inbound connections to `program`."""
    return f'advfirewall firewall add rule name="{RULE_NAME}" dir=in action=block program="{program}" description="{DESCRIPTION}"'


def command(program: Path, replace: bool) -> tuple[str, str]:
    """The program and the arguments of the one elevated run: the netsh line that adds the rule, or, with `replace` (a rule of the name exists), cmd with the netsh line that deletes it and the one that adds the new.
    ValueError for a path that cmd would read differently (`%` and `"` in it)."""
    system = ntpath.join(os.environ.get("SystemRoot") or r"C:\Windows", "System32")
    netsh = ntpath.join(system, "netsh.exe")
    if not replace:
        return netsh, add_arguments(program)
    if "%" in str(program) or '"' in str(program):
        raise ValueError(f"the path {program} has a character that cmd would read as its own")
    return ntpath.join(system, "cmd.exe"), f'/s /c ""{netsh}" {DELETE_ARGUMENTS} & "{netsh}" {add_arguments(program)}"'


async def make_rule(program: Path, replace: bool) -> Outcome:
    """Makes the rule for `program` as an administrator (a rule of the name that exists is replaced when `replace`). Every step is logged; nothing is raised: a declined prompt and a failure are `not_run`."""
    if not on_windows():
        log.info("Mercury firewall rule: not made, this is not Windows")
        return "not_run"
    try:
        file, parameters = command(program, replace)
    except ValueError as e:
        log.warning("Mercury firewall rule: not made: %s", e)
        return "not_run"
    log.info("Mercury firewall rule: running as administrator: %s %s", file, parameters)
    try:
        code = await elevated(file, parameters, TIMEOUT_SEC)
    except Declined:
        log.info("Mercury firewall rule: the prompt for administrator rights was declined, nothing was changed")
        return "not_run"
    except (OSError, TimeoutError) as e:
        log.warning("Mercury firewall rule: the run as administrator did not happen: %s", e)
        return "not_run"
    log.info("Mercury firewall rule: the run ended with exit code %d", code)
    return "ran"
