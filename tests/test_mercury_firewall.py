"""The Windows Firewall check of Mercury (neoaprs/mercuryfirewall.py): the judgement of what PowerShell printed, the call that is a no-op off Windows, and the installer that makes the rule."""
import subprocess
from pathlib import Path

import pytest

from neoaprs import mercuryfirewall
from neoaprs.mercuryfirewall import judge, loopback_only

PROGRAM = Path(r"C:\Users\Op Erator\AppData\Local\Programs\NeoAPRS\bin\mercury\mercury.exe")
PROFILES = "profile Domain True NotConfigured\nprofile Private True NotConfigured\nprofile Public True NotConfigured\n"
GOOD = f"rule True Inbound Block {PROGRAM}\n" + PROFILES
INSTALLER = Path(__file__).resolve().parent.parent / "packaging" / "windows" / "neoaprs.iss"


def rule_line(enabled="True", direction="Inbound", action="Block", program=PROGRAM):
    return f"rule {enabled} {direction} {action} {program}\n" + PROFILES


def test_a_blocking_rule_and_a_firewall_that_is_on_give_no_complaint():
    assert judge(GOOD, PROGRAM) == ""


def test_a_missing_rule_is_named_and_the_installer_is_the_way_out():
    text = judge("rule none\n" + PROFILES, PROGRAM)
    assert "NeoAPRS Mercury" in text and "missing" in text and "installer" in text


def test_a_rule_that_is_switched_off_is_named():
    assert "switched off" in judge(rule_line(enabled="False"), PROGRAM)


def test_an_allow_rule_does_not_count():
    assert "does not block" in judge(rule_line(action="Allow"), PROGRAM)


def test_an_outbound_rule_does_not_count():
    assert "inbound" in judge(rule_line(direction="Outbound"), PROGRAM)


def test_a_rule_for_another_program_names_both():
    text = judge(rule_line(program=r"C:\Elsewhere\mercury.exe"), PROGRAM)
    assert "another program" in text and r"C:\Elsewhere\mercury.exe" in text and str(PROGRAM) in text


def test_a_rule_with_no_program_is_not_the_one():
    assert "no program" in judge("rule True Inbound Block \n" + PROFILES, PROGRAM)


def test_a_firewall_that_is_off_in_a_profile_names_the_profile():
    text = judge(GOOD.replace("profile Private True", "profile Private False"), PROGRAM)
    assert "Private" in text and "off" in text and "not started" in text


def test_the_default_inbound_action_of_a_profile_does_not_matter():
    assert judge(GOOD.replace("NotConfigured", "Allow"), PROGRAM) == ""


def test_output_with_no_profile_is_not_taken_as_good():
    assert "could not be asked" in judge(f"rule True Inbound Block {PROGRAM}\n", PROGRAM)


def test_the_path_is_compared_without_case_and_without_a_trailing_backslash(monkeypatch):
    monkeypatch.setattr(mercuryfirewall.os.path, "normcase", lambda p: p.lower().replace("/", "\\"))
    monkeypatch.setattr(mercuryfirewall.os.path, "normpath", lambda p: p.rstrip("\\"))
    assert judge(rule_line(program=str(PROGRAM).upper() + "\\"), PROGRAM) == ""


def test_off_windows_nothing_is_run_and_the_answer_is_good(monkeypatch):
    monkeypatch.setattr(mercuryfirewall.sys, "platform", "linux")

    def refuse(*args, **kwargs):
        raise AssertionError("PowerShell must not be run off Windows")

    monkeypatch.setattr(mercuryfirewall.subprocess, "run", refuse)
    assert loopback_only(PROGRAM) == ""


def test_on_windows_the_answer_is_the_judgement_of_what_powershell_printed(monkeypatch):
    monkeypatch.setattr(mercuryfirewall.sys, "platform", "win32")
    seen = {}

    def run(command, **kwargs):
        seen.update(command=command, **kwargs)
        return subprocess.CompletedProcess(command, 0, stdout=seen.get("out", GOOD), stderr="")

    monkeypatch.setattr(mercuryfirewall.subprocess, "run", run)
    assert loopback_only(PROGRAM) == ""
    assert seen["command"][0] == "powershell.exe" and "-NoProfile" in seen["command"] and seen["capture_output"] and seen["timeout"] == 20.0
    seen["out"] = "rule none\n" + PROFILES
    assert "missing" in loopback_only(PROGRAM)


def test_a_powershell_that_cannot_be_run_gives_a_sentence(monkeypatch):
    monkeypatch.setattr(mercuryfirewall.sys, "platform", "win32")

    def missing(*args, **kwargs):
        raise OSError("no such file")

    monkeypatch.setattr(mercuryfirewall.subprocess, "run", missing)
    text = loopback_only(PROGRAM)
    assert "could not be asked" in text and "no such file" in text


def test_a_powershell_that_times_out_gives_a_sentence(monkeypatch):
    monkeypatch.setattr(mercuryfirewall.sys, "platform", "win32")

    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired("powershell.exe", 20)

    monkeypatch.setattr(mercuryfirewall.subprocess, "run", slow)
    assert "could not be asked" in loopback_only(PROGRAM)


def test_a_powershell_that_fails_gives_a_sentence(monkeypatch):
    monkeypatch.setattr(mercuryfirewall.sys, "platform", "win32")
    monkeypatch.setattr(mercuryfirewall.subprocess, "run", lambda command, **kw: subprocess.CompletedProcess(command, 1, stdout="", stderr="boom"))
    assert "could not be asked" in loopback_only(PROGRAM)


@pytest.mark.parametrize("needle", ["NeoAPRS Mercury", "advfirewall firewall add rule", "dir=in", "action=block", "runas", "advfirewall firewall delete rule"])
def test_the_installer_makes_and_removes_the_rule_with_elevation(needle):
    assert needle in INSTALLER.read_text(encoding="utf-8")
