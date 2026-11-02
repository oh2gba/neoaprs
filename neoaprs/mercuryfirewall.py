"""Whether the network is kept away from Mercury on Windows: the daemon asks the Windows Firewall and starts Mercury only when the answer is yes.

Rhizomatica's Mercury listens on its control port, its ARQ port and its KISS port on every network interface and has no password and no option to listen on this computer only. Anyone on the LAN could send it a
tune command, or a KISS frame, and key the transmitter past every interlock of NeoAPRS. On Linux NeoAPRS builds Mercury from source and patches that away; on Windows the program is Rhizomatica's signed release, which
cannot be changed, so the installer (packaging/windows/neoaprs.iss) adds a rule to the Windows Firewall that blocks inbound connections to `mercury.exe`. A block rule and not an allow one: a block beats every allow rule
(also one that Windows or another program adds), and the Firewall does not filter the loopback, so the daemon's own connections to Mercury on this computer go through untouched. The installer makes the rule (it takes
administrator rights, which the daemon has not); this module only confirms that it is there and in force, and the answer is the sentence for the status line when it is not.

PowerShell is asked and not netsh: netsh's words are in the language of the Windows, PowerShell's enum names are English in every one, so one script prints one line per fact and `judge` reads the lines with no
translation table. `judge` is pure; `loopback_only` runs the program and is for a thread (the caller does `asyncio.to_thread`): it waits for PowerShell, which takes a second or two to start."""
import os
import subprocess
import sys
from pathlib import Path

RULE_NAME = "NeoAPRS Mercury"        # the rule's name in the installer
TIMEOUT_SEC = 20.0                   # PowerShell's start is slow on a busy computer; a stuck one is given this long
FIX = "run the NeoAPRS installer again and allow it"

SCRIPT = (
    f"$r = Get-NetFirewallRule -DisplayName '{RULE_NAME}' -ErrorAction SilentlyContinue | Select-Object -First 1; "
    "if ($null -eq $r) { 'rule none' } else { $p = ($r | Get-NetFirewallApplicationFilter).Program; \"rule $($r.Enabled) $($r.Direction) $($r.Action) $p\" }; "
    "Get-NetFirewallProfile | ForEach-Object { \"profile $($_.Name) $($_.Enabled) $($_.DefaultInboundAction)\" }"
)


def _same_path(a: str, b: Path) -> bool:
    return os.path.normcase(os.path.normpath(a.strip())) == os.path.normcase(os.path.normpath(str(b)))


def _lines(output: str) -> tuple[list[str] | None, list[list[str]]]:
    """The first `rule` line of the output (its fields after the word, the program last and whole) and every `profile` line."""
    rule: list[str] | None = None
    profiles: list[list[str]] = []
    for line in output.splitlines():
        parts = line.split(None, 4)
        if parts and parts[0] == "rule" and rule is None:
            rule = parts[1:]
        elif parts and parts[0] == "profile":
            profiles.append(parts[1:])
    return rule, profiles


def _rule_problem(rule: list[str] | None, program: Path) -> str:
    if rule is None or rule[0] == "none":
        return f"the Windows Firewall rule '{RULE_NAME}' of the installer is missing: {FIX}"
    if len(rule) < 4:
        return f"the Windows Firewall rule '{RULE_NAME}' has no program: {FIX}"
    enabled, direction, action, path = rule[:4]
    if enabled != "True":
        return f"the Windows Firewall rule '{RULE_NAME}' is switched off: turn it on, or {FIX}"
    if direction != "Inbound":
        return f"the Windows Firewall rule '{RULE_NAME}' is not for inbound connections: {FIX}"
    if action != "Block":
        return f"the Windows Firewall rule '{RULE_NAME}' does not block: {FIX}"
    if not _same_path(path, program):
        return f"the Windows Firewall rule '{RULE_NAME}' is for another program ({path.strip()}), not {program}: {FIX}"
    return ""


def _profile_problem(profiles: list[list[str]]) -> str:
    if not profiles:
        return "the Windows Firewall could not be asked: it named no profile"
    for profile in profiles:
        if len(profile) >= 2 and profile[1] != "True":
            return f"Windows Firewall is off for the {profile[0]} profile: Mercury would be reachable from the network, and is not started"
    return ""


def judge(output: str, program: Path) -> str:
    """The sentence that says why `program` is not shielded from the network, from the lines the script printed; "" when a rule blocks inbound connections to it and the Firewall is on in every profile."""
    rule, profiles = _lines(output)
    return _rule_problem(rule, program) or _profile_problem(profiles)


def _on_windows() -> bool:
    return sys.platform == "win32"


def loopback_only(program: Path) -> str:
    """"" when the network cannot reach `program` (Mercury) through the Windows Firewall, else the sentence why not. Runs PowerShell and waits: call it from a thread. Elsewhere than Windows it answers "" and runs
    nothing (Linux has Mercury listen on the loopback itself)."""
    if not _on_windows():
        return ""
    command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", SCRIPT]
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=TIMEOUT_SEC, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return f"the Windows Firewall could not be asked: PowerShell did not answer in {TIMEOUT_SEC:.0f} s"
    except OSError as error:
        return f"the Windows Firewall could not be asked: PowerShell could not be run ({error})"
    if done.returncode != 0:
        return f"the Windows Firewall could not be asked: PowerShell ended with {done.returncode}"
    return judge(done.stdout, program)
