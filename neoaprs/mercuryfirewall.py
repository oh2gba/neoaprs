"""Whether the network is kept away from Mercury on Windows: the daemon asks the Windows Firewall and starts Mercury only when the answer is yes.

Rhizomatica's Mercury listens on its control port, its ARQ port and its KISS port on every network interface and has no password and no option to listen on this computer only. Anyone on the LAN could send it a
tune command, or a KISS frame, and key the transmitter past every interlock of NeoAPRS. On Linux NeoAPRS builds Mercury from source and patches that away; on Windows the program is Rhizomatica's signed release, which
cannot be changed, so the Windows Firewall is what keeps the network from it, and this module confirms that it does. The Firewall does not filter the loopback, so the daemon's own connections to Mercury on this
computer go through untouched. Mercury is shielded when EITHER (a) the rule "NeoAPRS Mercury", which the installer adds and the HF radio's box can add (mercuryrule.py; both take administrator rights, which the daemon
has not), is in force: an enabled inbound block rule for the shipped `mercury.exe`. A block rule and not an allow one: a block beats every allow rule, also one that Windows or another program adds. Or (b) with no such rule:
the Firewall is on in every profile, every profile blocks inbound connections by default (`NotConfigured` is Windows' default, which blocks), and no enabled inbound allow rule lets Mercury in: one for `mercury.exe`
(Windows makes it itself when someone answers "Allow access" in its pop-up) or one for any program whose local ports include one of the ports Mercury is given. A Firewall that is off for a profile (another security
program may manage the firewall) shields nothing there, and the rule does not count either.

PowerShell is asked and not netsh: netsh's words are in the language of the Windows, PowerShell's enum names are English in every one, so one script prints one line per fact and `judge` reads the lines with no
translation table. `judge` is pure; `check` runs the program and is for a thread (the caller does `asyncio.to_thread`): it waits for PowerShell, which takes a second or two to start. Both give a `Verdict`: the sentence
for the log, the code the page puts in its own words, whether a rule of the name exists (to be replaced, not added) and the names of the rules that let Mercury in. The decision is logged with the facts it was taken on."""
import logging
import ntpath
import os
import re
import subprocess
from collections.abc import Collection
from pathlib import Path
from typing import NamedTuple

from .winelevate import on_windows

log = logging.getLogger("neoaprs.mercury")

RULE_NAME = "NeoAPRS Mercury"        # the rule's name in the installer
TIMEOUT_SEC = 30.0                   # PowerShell's start is slow on a busy computer, and the list of the allow rules is long; a stuck one is given this long
SHOWN_NAMES = 3                      # how many rules that let Mercury in are named

# The facts through the Firewall's COM interface (HNetCfg.FwPolicy2), which every user may read: the NetSecurity cmdlets (Get-NetFirewallApplicationFilter) answer "Access is denied" to a user who is not an administrator
# on some Windows 10 (OH2GAX's, 0.16.1). Numbers, not words, come back (direction 1 in, action 0 block / 1 allow, protocol 6 TCP / 17 UDP / 256 any, profiles 1 domain / 2 private / 4 public), so the lines are the same
# in every language of Windows; they are printed in the form `_facts` reads.
SCRIPT = (
    "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
    "$p = New-Object -ComObject HNetCfg.FwPolicy2; $found = $false; "
    "foreach ($x in $p.Rules) { "
    f"if ($x.Name -eq '{RULE_NAME}') {{ $found = $true; $d = if ($x.Direction -eq 1) {{ 'Inbound' }} else {{ 'Outbound' }}; $a = if ($x.Action -eq 0) {{ 'Block' }} else {{ 'Allow' }}; \"rule $($x.Enabled) $d $a $($x.ApplicationName)\" }}; "
    "if ($x.Enabled -and $x.Direction -eq 1 -and $x.Action -eq 1) { "
    "$prog = if ($x.ApplicationName) { $x.ApplicationName } else { 'Any' }; "
    "$proto = switch ($x.Protocol) { 6 { 'TCP' } 17 { 'UDP' } 256 { 'Any' } default { \"$($x.Protocol)\" } }; "
    "$lp = if (-not $x.LocalPorts -or $x.LocalPorts -eq '*') { 'Any' } else { $x.LocalPorts }; "
    "\"allow`t$($x.Name)`t$prog`t$proto`t$lp\" } }; "
    "if (-not $found) { 'rule none' }; "
    "foreach ($k in @(@(1, 'Domain'), @(2, 'Private'), @(4, 'Public'))) { $e = $p.FirewallEnabled($k[0]); $i = if ($p.DefaultInboundAction($k[0]) -eq 0) { 'Block' } else { 'Allow' }; \"profile $($k[1]) $e $i\" }"
)


class Verdict(NamedTuple):
    problem: str = ""        # why the network is not kept from Mercury, in English for the log; "" when it is
    reason: str = ""         # for the page: "firewall" (a block rule would fix it), "firewall_off" (the Firewall is off for a profile), "not_started" (it could not be asked); "" when shielded
    rule: bool = False       # a rule named RULE_NAME exists, right or wrong
    lets_in: str = ""        # the names of the rules that let Mercury in, up to SHOWN_NAMES, for the page; empty when none does
    decision: str = ""       # the verdict and the facts it was taken on, one line for the log


class Allow(NamedTuple):
    name: str
    program: str
    protocol: str
    ports: str


class Facts(NamedTuple):
    rules: list[list[str]]       # the rules of the name: enabled, direction, action, program (the program whole, spaces and all)
    profiles: list[list[str]]    # name, enabled, default inbound action
    allows: list[Allow]          # the enabled inbound allow rules


def _expand(path: str) -> str:
    """The variables of a path: `%LOCALAPPDATA%` as Windows writes them (the Firewall may keep a rule's program unexpanded; the name is looked up without regard to case) and `$VAR`."""
    env = {name.upper(): value for name, value in os.environ.items()}
    return os.path.expandvars(re.sub(r"%([^%\s]+)%", lambda m: env.get(m.group(1).upper(), m.group(0)), path))


def _win_long_path(path: str) -> str:
    """The long name of a path that has 8.3 short names in it (`PROGRA~1`), by Windows (GetLongPathNameW); the path as given when it cannot be (the file is not there)."""
    import ctypes
    size = 32768
    buffer = ctypes.create_unicode_buffer(size)
    got = ctypes.windll.kernel32.GetLongPathNameW(path, buffer, size)      # type: ignore[attr-defined, unused-ignore]
    return buffer.value if 0 < got < size else path


def _long_path(path: str) -> str:
    return _win_long_path(path) if on_windows() else path


def _key(path: str) -> str:
    """A path as it is compared: variables expanded, 8.3 names spelled out, either kind of slash, no `\\\\?\\`, no trailing backslash, the case dropped."""
    path = _long_path(_expand(path.strip().strip('"').strip()))
    if path.startswith("\\\\?\\"):
        path = path[4:]
    return ntpath.normcase(ntpath.normpath(path))


def _same_path(a: str, b: Path) -> bool:
    return _key(a) == _key(str(b))


def _facts(output: str) -> Facts:
    """The lines the script printed, sorted by their first word."""
    rules: list[list[str]] = []
    profiles: list[list[str]] = []
    allows: list[Allow] = []
    for line in output.splitlines():
        parts = line.split(None, 4)
        if line.startswith("allow\t"):
            fields = (line.split("\t") + ["", "", "", ""])[1:5]
            allows.append(Allow(*fields))
        elif parts and parts[0] == "rule":
            rules.append(parts[1:])
        elif parts and parts[0] == "profile":
            profiles.append(parts[1:])
    return Facts(rules, profiles, allows)


def _rule_fault(rule: list[str], program: Path) -> str:
    """What is wrong with one rule of the name; "" when it is the block rule that shields `program`."""
    if len(rule) < 4:
        return f"the Windows Firewall rule '{RULE_NAME}' has no program"
    enabled, direction, action, path = rule[:4]
    if enabled != "True":
        return f"the Windows Firewall rule '{RULE_NAME}' is switched off"
    if direction != "Inbound":
        return f"the Windows Firewall rule '{RULE_NAME}' is not for inbound connections"
    if action != "Block":
        return f"the Windows Firewall rule '{RULE_NAME}' does not block"
    if not _same_path(path, program):
        return f"the Windows Firewall rule '{RULE_NAME}' is for another program ({path.strip()}), not {program}"
    return ""


def _rule_fault_of(rules: list[list[str]], program: Path) -> str:
    """"" when any rule of the name shields `program`, else the fault of the nearest (the first that is for the program, else the first), or that there is none."""
    if not rules or rules[0][:1] == ["none"]:
        return f"the Windows Firewall rule '{RULE_NAME}' that blocks it is missing"
    faults = [_rule_fault(rule, program) for rule in rules]
    if "" in faults:
        return ""
    near = [fault for rule, fault in zip(rules, faults) if len(rule) >= 4 and _same_path(rule[3], program)]
    return (near or faults)[0]


def _port_numbers(ports: str) -> list[range] | None:
    """The ranges of a rule's local ports, `8100,8300-8400`; None for Any (an empty list is taken as Any too). A word such as RPC is no port of ours and is left out."""
    ranges: list[range] = []
    for token in (t.strip() for t in ports.split(",")):
        if token.lower() in ("", "any"):
            return None
        low, _, high = token.partition("-")
        if low.isdigit() and (high.isdigit() or not high):
            ranges.append(range(int(low), int(high or low) + 1))
    return ranges


def _lets_in(allows: list[Allow], program: Path, ports: Collection[int]) -> list[str]:
    """The names of the enabled inbound allow rules that apply to Mercury: one for its program (any ports), or one for any program whose local TCP ports are Any or include one of `ports`. A rule for another program does not
    apply to it, whatever its ports are."""
    names: list[str] = []
    for allow in allows:
        if allow.protocol.upper() not in ("TCP", "ANY", "6", ""):
            continue
        own = allow.program.strip().lower() not in ("any", "") and _same_path(allow.program, program)
        anyone = allow.program.strip().lower() in ("any", "")
        ranges = _port_numbers(allow.ports)
        if own or (anyone and (ranges is None or any(p in r for r in ranges for p in ports))):
            names.append(allow.name)
    return names


def _profile_words(names: list[str]) -> str:
    return f"the {names[0]} profile" if len(names) == 1 else "the " + ", ".join(names[:-1]) + f" and {names[-1]} profiles"


def _facts_text(facts: Facts, lets: list[str]) -> str:
    profiles = ", ".join(f"{p[0]} {'on' if p[1:2] == ['True'] else 'off'}/{p[2] if len(p) > 2 else '?'}" for p in facts.profiles) or "none"
    rules = "; ".join(" ".join(r) for r in facts.rules) or "none"
    return f"profiles (state/default inbound): {profiles}; rule '{RULE_NAME}': {rules}; {len(facts.allows)} enabled inbound allow rules, of which these let it in: {', '.join(lets) or 'none'}"


def judge(output: str, program: Path, ports: Collection[int] = ()) -> Verdict:
    """The verdict on what the script printed for `program`, which is given `ports` (all it may be given); `problem` empty when a rule blocks inbound connections to it or, with no such rule, the Firewall is on in every
    profile with a default that blocks and no enabled inbound allow rule lets it in."""
    facts = _facts(output)
    lets = _lets_in(facts.allows, program, ports)
    exists = any(rule[:1] != ["none"] for rule in facts.rules)
    text = _facts_text(facts, lets)
    if not facts.profiles:
        return Verdict("the Windows Firewall could not be asked: it named no profile", "not_started", exists, "", f"not asked ({text})")
    off = [p[0] for p in facts.profiles if p[1:2] != ["True"]]
    if off:
        problem = f"Windows Firewall is off for {_profile_words(off)}: Mercury would be reachable from the network, and is not started. Switch Windows Firewall on; another security program that manages the firewall may have switched it off"
        return Verdict(problem, "firewall_off", exists, "", f"not shielded ({text})")
    fault = _rule_fault_of(facts.rules, program)
    if not fault:
        return Verdict("", "", exists, "", f"shielded by the block rule ({text})")
    open_by_default = [p[0] for p in facts.profiles if p[2:3] not in (["Block"], ["NotConfigured"])]
    if not lets and not open_by_default:
        return Verdict("", "", exists, "", f"shielded by the Firewall's own default, as no rule blocks it ({text})")
    causes = [f"the rule '{name}' lets inbound connections reach it" for name in lets[:SHOWN_NAMES]]
    if open_by_default:
        causes.append(f"inbound connections are allowed by default in {_profile_words(open_by_default)}")
    problem = f"the Windows Firewall does not keep the network from Mercury: {'; '.join(causes)}; {fault}"
    return Verdict(problem, "firewall", exists, ", ".join(lets[:SHOWN_NAMES]), f"not shielded ({text})")


def check(program: Path, ports: Collection[int] = ()) -> Verdict:
    """The verdict on `program` (Mercury), which is given `ports`, from the Windows Firewall. Runs PowerShell and waits: call it from a thread. Elsewhere than Windows it answers "shielded" and runs nothing (Linux has Mercury
    listen on the loopback itself). The decision and the facts it was taken on are logged."""
    if not on_windows():
        return Verdict()
    command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", SCRIPT]
    try:
        done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT_SEC, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return _unasked(f"PowerShell did not answer in {TIMEOUT_SEC:.0f} s")
    except OSError as error:
        return _unasked(f"PowerShell could not be run ({error})")
    if done.returncode != 0:
        return _unasked(f"PowerShell ended with {done.returncode}", " | ".join(done.stderr.strip().splitlines()[:3]))
    verdict = judge(done.stdout, program, ports)
    log.info("Mercury and the Windows Firewall, asked for %s with ports %s: %s", program, ", ".join(str(p) for p in sorted(ports)) or "none", verdict.decision)
    return verdict


def _unasked(why: str, stderr: str = "") -> Verdict:
    log.warning("the Windows Firewall could not be asked: %s%s", why, f"; stderr: {stderr}" if stderr else "")
    return Verdict(f"the Windows Firewall could not be asked: {why}", "not_started", False, "", "not asked")
