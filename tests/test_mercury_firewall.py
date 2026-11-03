"""The Windows Firewall check of Mercury (neoaprs/mercuryfirewall.py): the judgement of what PowerShell printed (the block rule, or the Firewall's own default with nothing letting Mercury in), the comparison of paths, the
call that is a no-op off Windows, and the installer that makes the rule."""
import logging
import subprocess
import sys
from pathlib import Path

import pytest

from neoaprs import mercuryfirewall
from neoaprs.mercuryfirewall import SCRIPT, check, judge

PROGRAM = Path(r"C:\Users\Op Erator\AppData\Local\Programs\NeoAPRS\bin\mercury\mercury.exe")
PORTS = (8100, 8300, 8301)
PROFILES = "profile Domain True NotConfigured\nprofile Private True NotConfigured\nprofile Public True NotConfigured\n"
NO_RULE = "rule none\n"
GOOD = f"rule True Inbound Block {PROGRAM}\n" + PROFILES
INSTALLER = Path(__file__).resolve().parent.parent / "packaging" / "windows" / "neoaprs.iss"


def rule_line(enabled="True", direction="Inbound", action="Block", program=PROGRAM, profiles=PROFILES):
    return f"rule {enabled} {direction} {action} {program}\n" + profiles


def allow(name, program="Any", ports="Any", protocol="TCP"):
    return f"allow\t{name}\t{program}\t{protocol}\t{ports}\n"


def verdict(text, ports=PORTS):
    return judge(text, PROGRAM, ports)


OPEN = PROFILES.replace("NotConfigured", "Allow")       # every profile allows inbound connections by default


# ---- the block rule

def test_a_blocking_rule_and_a_firewall_that_is_on_give_no_complaint():
    assert verdict(GOOD).problem == "" and "block rule" in verdict(GOOD).decision


def test_a_blocking_rule_beats_an_allow_rule_for_the_program():
    assert verdict(GOOD + allow("mercury.exe", program=str(PROGRAM))).problem == ""


def test_a_missing_rule_with_the_default_open_is_named():
    done = verdict(NO_RULE + OPEN)
    assert done.reason == "firewall" and "NeoAPRS Mercury" in done.problem and "missing" in done.problem and "allowed by default" in done.problem and not done.rule


def test_a_rule_that_is_switched_off_is_named_and_is_to_be_replaced():
    done = verdict(rule_line(enabled="False") + allow("mercury.exe", program=str(PROGRAM)))
    assert "switched off" in done.problem and done.reason == "firewall" and done.rule


def test_an_allow_rule_does_not_count_as_the_block_rule():
    assert "does not block" in verdict(rule_line(action="Allow", profiles=OPEN)).problem


def test_an_outbound_rule_does_not_count():
    assert "inbound" in verdict(rule_line(direction="Outbound", profiles=OPEN)).problem


def test_a_rule_for_another_program_names_both():
    text = verdict(rule_line(program=r"C:\Elsewhere\mercury.exe", profiles=OPEN)).problem
    assert "another program" in text and r"C:\Elsewhere\mercury.exe" in text and str(PROGRAM) in text


def test_a_rule_with_no_program_is_not_the_one():
    assert "no program" in verdict("rule True Inbound Block \n" + OPEN).problem


def test_any_of_several_rules_of_the_name_that_shields_the_program_is_enough():
    old = f"rule False Inbound Block {PROGRAM}\nrule True Inbound Block C:\\Old\\mercury.exe\n"
    assert verdict(old + GOOD).problem == ""
    assert verdict(old + OPEN).problem != ""


def test_the_nearest_of_several_wrong_rules_is_the_one_named():
    text = verdict(f"rule True Inbound Block C:\\Old\\mercury.exe\nrule False Inbound Block {PROGRAM}\n" + OPEN).problem
    assert "switched off" in text and "C:\\Old" not in text


# ---- no rule: the Firewall's own default

def test_no_rule_but_every_profile_blocks_by_default_and_nothing_lets_mercury_in_is_shielded():
    for default in ("NotConfigured", "Block"):
        done = verdict(NO_RULE + PROFILES.replace("NotConfigured", default) + allow("Some app", program=r"C:\Other\app.exe", ports="8100") + allow("Web", ports="80,443"))
        assert done.problem == "" and "default" in done.decision, default


def test_an_allow_rule_for_mercury_exe_lets_it_in_and_is_named():
    done = verdict(NO_RULE + PROFILES + allow("mercury.exe", program=str(PROGRAM), ports="Any"))
    assert done.reason == "firewall" and done.lets_in == "mercury.exe" and "'mercury.exe' lets inbound connections reach it" in done.problem and not done.rule


def test_an_allow_rule_for_any_program_and_any_port_lets_it_in():
    assert verdict(NO_RULE + PROFILES + allow("Everything", ports="Any")).lets_in == "Everything"


@pytest.mark.parametrize("ports", ["8100", "8300", "80,8301", "8000-8200", "Any"])
def test_an_allow_rule_for_any_program_with_a_port_of_mercury_lets_it_in(ports):
    assert verdict(NO_RULE + PROFILES + allow("Ours", ports=ports)).lets_in == "Ours"


@pytest.mark.parametrize("program,ports,protocol", [("Any", "80,443", "TCP"), ("Any", "RPC,5353", "TCP"), (r"C:\Other\app.exe", "Any", "TCP"), (r"C:\Other\app.exe", "8100", "TCP"), ("Any", "Any", "UDP"), ("Any", "9000-9100", "TCP")])
def test_an_allow_rule_for_another_program_or_other_ports_or_udp_does_not_let_it_in(program, ports, protocol):
    assert verdict(NO_RULE + PROFILES + allow("Else", program=program, ports=ports, protocol=protocol)).problem == ""


def test_the_names_of_the_rules_that_let_it_in_are_up_to_three():
    text = NO_RULE + PROFILES + "".join(allow(f"Rule {n}", ports="Any") for n in range(5))
    assert verdict(text).lets_in == "Rule 0, Rule 1, Rule 2"


def test_a_default_that_allows_inbound_is_not_shielded_without_the_rule():
    done = verdict(NO_RULE + PROFILES.replace("Public True NotConfigured", "Public True Allow"))
    assert done.reason == "firewall" and "Public profile" in done.problem and done.lets_in == ""


def test_the_default_does_not_matter_with_the_rule_in_force():
    assert verdict(GOOD.replace("NotConfigured", "Allow")).problem == ""


# ---- the Firewall off, or not asked

def test_a_firewall_that_is_off_in_a_profile_is_not_shielded_and_is_not_for_the_button():
    for text in (GOOD, NO_RULE + PROFILES):
        done = verdict(text.replace("profile Private True", "profile Private False"))
        assert done.reason == "firewall_off" and "Private" in done.problem and "off" in done.problem and "not started" in done.problem and "Switch Windows Firewall on" in done.problem


def test_two_profiles_off_are_both_named():
    assert "Private and Public profiles" in verdict(GOOD.replace("Private True", "Private False").replace("Public True", "Public False")).problem


def test_output_with_no_profile_is_not_taken_as_good():
    done = verdict(f"rule True Inbound Block {PROGRAM}\n")
    assert "could not be asked" in done.problem and done.reason == "not_started"


# ---- paths

def test_the_path_is_compared_without_case_slash_kind_and_trailing_backslash():
    assert verdict(rule_line(program=str(PROGRAM).upper() + "\\")).problem == ""
    assert verdict(rule_line(program=str(PROGRAM).replace("\\", "/"))).problem == ""
    assert verdict(rule_line(program='"' + str(PROGRAM) + '"')).problem == ""
    assert verdict(rule_line(program="\\\\?\\" + str(PROGRAM))).problem == ""


def test_the_path_is_compared_with_its_variables_expanded(monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\Op Erator\AppData\Local")
    assert verdict(rule_line(program=r"%LOCALAPPDATA%\Programs\NeoAPRS\bin\mercury\mercury.exe")).problem == ""
    assert verdict(rule_line(program=r"%localappdata%\Programs\NeoAPRS\bin\mercury\mercury.exe")).problem == ""
    assert verdict(rule_line(program=r"%NO_SUCH_VARIABLE%\mercury.exe", profiles=OPEN)).problem != ""
    monkeypatch.setenv("FIREWALL_TEST_HOME", r"C:\Users\Op Erator")
    assert mercuryfirewall._key(r"$FIREWALL_TEST_HOME\AppData") == mercuryfirewall._key(r"C:\Users\Op Erator\AppData")


def test_the_path_is_compared_with_its_8_3_names_spelled_out_on_both_sides(monkeypatch):
    short = r"C:\Users\OPERAT~1\AppData\Local\Programs\NeoAPRS\bin\mercury\mercury.exe"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(mercuryfirewall, "_win_long_path", lambda path: str(PROGRAM) if path.upper() == short.upper() else path)
    assert verdict(rule_line(program=short)).problem == ""
    assert judge(GOOD, Path(short), PORTS).problem == ""


def test_off_windows_a_path_is_not_asked_of_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(mercuryfirewall, "_win_long_path", lambda path: pytest.fail("Windows is not asked off Windows"))
    assert verdict(GOOD).problem == ""


# ---- running PowerShell

def test_off_windows_nothing_is_run_and_the_answer_is_good(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")

    def refuse(*args, **kwargs):
        raise AssertionError("PowerShell must not be run off Windows")

    monkeypatch.setattr(mercuryfirewall.subprocess, "run", refuse)
    assert check(PROGRAM, PORTS).problem == ""


def test_on_windows_the_answer_is_the_judgement_of_what_powershell_printed_and_the_decision_is_logged(monkeypatch, caplog):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(mercuryfirewall, "_win_long_path", lambda path: path)
    seen = {}

    def run(command, **kwargs):
        seen.update(command=command, **kwargs)
        return subprocess.CompletedProcess(command, 0, stdout=seen.get("out", GOOD), stderr="")

    monkeypatch.setattr(mercuryfirewall.subprocess, "run", run)
    with caplog.at_level(logging.INFO, logger="neoaprs.mercury"):
        assert check(PROGRAM, PORTS).problem == ""
        assert seen["command"][0] == "powershell.exe" and "-NoProfile" in seen["command"] and seen["capture_output"] and seen["timeout"] == mercuryfirewall.TIMEOUT_SEC and seen["encoding"] == "utf-8"
        seen["out"] = NO_RULE + OPEN + allow("mercury.exe", program=str(PROGRAM))
        assert "missing" in check(PROGRAM, PORTS).problem
    assert str(PROGRAM) in caplog.text and "ports 8100, 8300, 8301" in caplog.text and "shielded by the block rule" in caplog.text and "not shielded" in caplog.text
    assert "Domain on/Allow" in caplog.text and "mercury.exe" in caplog.text and "1 enabled inbound allow rules" in caplog.text


def test_a_powershell_that_cannot_be_run_gives_a_sentence(monkeypatch, caplog):
    monkeypatch.setattr(sys, "platform", "win32")

    def missing(*args, **kwargs):
        raise OSError("no such file")

    monkeypatch.setattr(mercuryfirewall.subprocess, "run", missing)
    done = check(PROGRAM, PORTS)
    assert "could not be asked" in done.problem and "no such file" in done.problem and done.reason == "not_started" and "no such file" in caplog.text


def test_a_powershell_that_times_out_gives_a_sentence(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")

    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired("powershell.exe", 20)

    monkeypatch.setattr(mercuryfirewall.subprocess, "run", slow)
    assert "could not be asked" in check(PROGRAM, PORTS).problem


def test_a_powershell_that_fails_gives_a_sentence_and_its_stderr_is_logged(monkeypatch, caplog):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(mercuryfirewall.subprocess, "run", lambda command, **kw: subprocess.CompletedProcess(command, 1, stdout="", stderr="boom\nsecond\nthird\nfourth"))
    done = check(PROGRAM, PORTS)
    assert "could not be asked" in done.problem and "ended with 1" in done.problem
    assert "ended with 1" in caplog.text and "boom | second | third" in caplog.text and "fourth" not in caplog.text


@pytest.mark.parametrize("needle", ["NeoAPRS Mercury", "advfirewall firewall add rule", "dir=in", "action=block", "runas", "advfirewall firewall delete rule"])
def test_the_installer_makes_and_removes_the_rule_with_elevation(needle):
    assert needle in INSTALLER.read_text(encoding="utf-8")


@pytest.mark.skipif(sys.platform != "win32", reason="the real Windows Firewall is asked on Windows only (CI's Windows runner)")
def test_the_real_windows_firewall_answers_the_script_in_a_form_the_judge_reads(tmp_path: Path) -> None:
    """On a real Windows (CI's runner) the script runs, PowerShell answers, every profile is named and the judge reaches a decision: not "could not be asked". What the decision is depends on the runner's Firewall."""
    from neoaprs.mercuryfirewall import _facts
    program = tmp_path / "bin" / "mercury" / "mercury.exe"
    verdict = check(program, (8100, 8300, 8301))
    assert verdict.reason != "not_started", verdict.problem
    assert verdict.decision and verdict.decision != "not asked"
    done = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", SCRIPT], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    facts = _facts(done.stdout)
    assert {p[0] for p in facts.profiles} >= {"Domain", "Private", "Public"}, done.stdout[:2000]
