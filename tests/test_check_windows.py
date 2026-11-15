"""The check on a real Windows (scripts/check-windows) as far as it can be held without the machine: what it reads from the environment and refuses, the command lines of ssh and scp, the PowerShell
of each step with names that have quotes, spaces and dollar signs in them, the choice about power for a machine that is off, running or started by this run, the lock, the folders of old runs, the
result lines and the exit code, and the script from end to end against stand-ins for `ssh`, `scp` and `VBoxManage` first on the PATH (they write down what they were asked and answer as a test lays
down) over a made-up repository: the tree that goes over never holds what an ignore rule names or a file of access tokens, a failed step is printed under its line and stops none but sync, and the
machine is shut down only by the run that started it. The machine itself, its SSH and Windows's tar and PowerShell are tried by hand (docs/development.md, "On a real Windows")."""
import base64
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from neoaprs import direwolf
from tests.support.ptyline import posix_only

pytestmark = posix_only      # (stand-ins with a shebang and a lock file for a development check, not the product)

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
WORKFLOW = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
STEP_NAMES = ["sync", "lock", "ruff", "pytest", "smoke"]
ODD_NAMES = ["plain.py", "with space.py", "it's.py", "\u2018quoted\u2019 and \u201a\u201b.py", "$env:Path", "a;b|c&d", "back`tick", "(paren)", "\u00e4\u00f6 \u5b57.py", "--flag=x y"]


@pytest.fixture(scope="module")
def script() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("check_windows", str(SCRIPTS / "check-windows"))
    spec = importlib.util.spec_from_loader("check_windows", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def good_env(tmp_path: Path, **more: str) -> dict[str, str]:
    key, known = tmp_path / "key", tmp_path / "known_hosts"
    key.write_text("made up", encoding="utf-8")
    known.write_text("made up", encoding="utf-8")
    return {"NEOAPRS_WINVM": "Windows 11", "NEOAPRS_WINVM_SSH_PORT": "2222", "NEOAPRS_WINVM_SSH_KEY": str(key), "NEOAPRS_WINVM_KNOWN_HOSTS": str(known), **more}


# ---- the environment ----

def test_without_the_machine_the_script_says_it_is_not_set_up_and_names_the_variables(script: ModuleType) -> None:
    with pytest.raises(script.NotSetUp) as error:
        script.read_settings({})
    text = str(error.value)
    assert "not set up" in text
    for name in ("NEOAPRS_WINVM", "NEOAPRS_WINVM_SSH_PORT", "NEOAPRS_WINVM_SSH_KEY", "NEOAPRS_WINVM_KNOWN_HOSTS", "NEOAPRS_WINVM_USER"):
        assert name in text
    with pytest.raises(script.NotSetUp):
        script.read_settings({"NEOAPRS_WINVM": "  ", "NEOAPRS_WINVM_SSH_PORT": "22"})


def test_a_machine_named_without_its_ssh_says_which_variables_are_missing(script: ModuleType, tmp_path: Path) -> None:
    env = good_env(tmp_path)
    for name in ("NEOAPRS_WINVM_SSH_PORT", "NEOAPRS_WINVM_SSH_KEY", "NEOAPRS_WINVM_KNOWN_HOSTS"):
        without = {key: value for key, value in env.items() if key != name}
        with pytest.raises(script.NotSetUp, match=f"{name} is not"):
            script.read_settings(without)
    with pytest.raises(script.NotSetUp, match="NEOAPRS_WINVM_SSH_PORT and NEOAPRS_WINVM_SSH_KEY are not"):
        script.read_settings({"NEOAPRS_WINVM": "x", "NEOAPRS_WINVM_KNOWN_HOSTS": "k"})


def test_the_settings_are_read_with_john_as_the_only_default(script: ModuleType, tmp_path: Path) -> None:
    settings = script.read_settings(good_env(tmp_path))
    assert (settings.vm, settings.port, settings.user) == ("Windows 11", 2222, "John")
    assert settings.key == tmp_path / "key" and settings.known_hosts == tmp_path / "known_hosts"
    assert script.read_settings(good_env(tmp_path, NEOAPRS_WINVM_USER="mary.o-1")).user == "mary.o-1"


@pytest.mark.parametrize("name, value", [("NEOAPRS_WINVM_SSH_PORT", "0"), ("NEOAPRS_WINVM_SSH_PORT", "65536"), ("NEOAPRS_WINVM_SSH_PORT", "22x"), ("NEOAPRS_WINVM_SSH_PORT", "-1"),
                                         ("NEOAPRS_WINVM_SSH_PORT", "\u0662\u0662"), ("NEOAPRS_WINVM_USER", "two words"), ("NEOAPRS_WINVM_USER", "a'b"), ("NEOAPRS_WINVM_USER", "..\\x"),
                                         ("NEOAPRS_WINVM_USER", "-oProxyCommand=x"), ("NEOAPRS_WINVM", "-startvm"), ("NEOAPRS_WINVM_KNOWN_HOSTS", 'a"b')])
def test_a_value_that_would_be_read_as_something_else_is_refused(script: ModuleType, tmp_path: Path, name: str, value: str) -> None:
    with pytest.raises(script.NotSetUp, match=name):
        script.read_settings(good_env(tmp_path, **{name: value}))


def test_a_key_or_a_known_hosts_file_that_is_not_there_is_said(script: ModuleType, tmp_path: Path) -> None:
    settings = script.read_settings(good_env(tmp_path))
    assert script.missing_files(settings) == []
    (tmp_path / "key").unlink()
    assert [line.split(" is ")[0] for line in script.missing_files(settings)] == ["NEOAPRS_WINVM_SSH_KEY"]


def test_the_build_cache_follows_the_variable_then_xdg_then_home(script: ModuleType) -> None:
    assert script.build_cache({"NEOAPRS_BUILD_CACHE": "/c"}) == Path("/c/check-windows")
    assert script.build_cache({"XDG_CACHE_HOME": "/x"}) == Path("/x/neoaprs-build/check-windows")
    assert script.build_cache({}) == Path.home() / ".cache" / "neoaprs-build" / "check-windows"


# ---- ssh and scp ----

def test_the_ssh_line_is_the_one_that_was_tried_by_hand(script: ModuleType, tmp_path: Path) -> None:
    settings = script.read_settings(good_env(tmp_path))
    line = script.ssh_command(settings, "REMOTE")
    assert line[0] == "ssh" and line[-2:] == ["John@127.0.0.1", "REMOTE"]
    assert line[line.index("-i") + 1] == str(tmp_path / "key") and line[line.index("-p") + 1] == "2222"
    assert "BatchMode=yes" in line and f"UserKnownHostsFile={tmp_path / 'known_hosts'}" in line and "ConnectTimeout=10" in line
    assert "-tt" not in line and "-tt" in script.ssh_command(settings, "REMOTE", tty=True)


def test_a_path_with_a_space_stays_one_argument_and_is_quoted_where_ssh_reads_options(script: ModuleType, tmp_path: Path) -> None:
    folder = tmp_path / "my keys"
    folder.mkdir()
    env = good_env(tmp_path, NEOAPRS_WINVM_SSH_KEY=str(folder / "id key"), NEOAPRS_WINVM_KNOWN_HOSTS=str(folder / "known hosts"))
    settings = script.read_settings(env)
    line = script.ssh_command(settings, "R")
    assert line[line.index("-i") + 1] == str(folder / "id key")
    assert f'UserKnownHostsFile="{folder / "known hosts"}"' in line
    assert script.scp_command(settings, tmp_path / "a b.tar", "C:/Users/John/x/tree.tar")[-2] == str(tmp_path / "a b.tar")


def test_the_scp_line_takes_the_port_as_a_capital_p_and_a_path_with_forward_slashes(script: ModuleType, tmp_path: Path) -> None:
    settings = script.read_settings(good_env(tmp_path, NEOAPRS_WINVM_USER="mary"))
    line = script.scp_command(settings, tmp_path / "tree.tar", script.scp_path("C:\\Users\\mary\\neoaprs-check\\RUN-1\\tree.tar"))
    assert line[0] == "scp" and line[line.index("-P") + 1] == "2222" and "-p" not in line
    assert line[-1] == "mary@127.0.0.1:C:/Users/mary/neoaprs-check/RUN-1/tree.tar"
    assert "BatchMode=yes" in line and line[line.index("-i") + 1] == str(tmp_path / "key")


def decode_quote(quoted: str) -> str:
    """What PowerShell reads of a single-quoted string: the text between the quotes, each doubled quote as one."""
    assert quoted[0] == quoted[-1] == "'"
    body = quoted[1:-1]
    for quote in "'\u2018\u2019\u201a\u201b":
        body = body.replace(quote * 2, quote)
    return body


@pytest.mark.parametrize("name", ODD_NAMES)
def test_a_name_in_a_powershell_string_is_one_string_whatever_it_holds(script: ModuleType, name: str) -> None:
    quoted = script.ps_quote(name)
    assert decode_quote(quoted) == name
    inside = quoted[1:-1]
    for quote in "'\u2018\u2019\u201a\u201b":       # (a quote of any kind inside the string is one of a pair: PowerShell takes the typographic ones for quotes)
        assert inside.count(quote) % 2 == 0


def test_the_command_to_the_machine_is_the_script_in_base64_and_short_enough_for_cmd(script: ModuleType, tmp_path: Path) -> None:
    line = script.powershell_line("Write-Output 'a b'\nexit 3")
    assert line.startswith("powershell.exe -NoProfile -NonInteractive ") and line.isascii() and " " not in line.rsplit(" ", 1)[1]
    assert base64.b64decode(line.rsplit(" ", 1)[1]).decode("utf-16-le") == "Write-Output 'a b'\nexit 3"
    paths = script.windows_paths("a" * 40, "RUN-20261113T101010")
    longest = [script.step_script(paths, step) for step in script.steps(paths, ["tests/" + "x" * 30 + ".py"] * 8)] + [script.prepare_script(paths), script.probe_script(paths)]
    assert all(len(script.powershell_line(text)) < script.REMOTE_LINE_MAX for text in longest)


# ---- the steps ----

def test_the_paths_are_in_the_profile_of_the_user_and_the_run_has_a_folder_of_its_own(script: ModuleType) -> None:
    paths = script.windows_paths("John", "RUN-20261113T101010")
    assert paths.root == "C:\\Users\\John\\neoaprs-check" and paths.run == "C:\\Users\\John\\neoaprs-check\\RUN-20261113T101010"
    assert paths.tree == paths.run + "\\neoaprs" and paths.uv_dir == "C:\\Users\\John\\neotest\\uv"
    assert script.run_name(0) == "RUN-19700101T000000" and script.run_name(1_700_000_000) == "RUN-20231114T221320"


def test_the_steps_are_the_ci_commands_in_the_order_of_the_workflow(script: ModuleType) -> None:
    paths = script.windows_paths("John", "RUN-1")
    steps = script.steps(paths)
    assert [step.name for step in steps] == STEP_NAMES
    by_name = {step.name: [" ".join(command) for command in step.commands] for step in steps}
    assert by_name["sync"] == ["uv sync --frozen --extra app --extra ble"]
    assert by_name["lock"] == ["uv lock --check"]
    assert by_name["ruff"] == ["uv run ruff check ."]
    assert by_name["pytest"] == ["uv run pytest -n auto -p no:cacheprovider"]
    for line in ("uv sync --frozen --extra app --extra ble", "uv lock --check", "uv run ruff check .", "uv run pytest -n auto", "uv build --wheel", "uv venv ", "uv pip install --python ", "scripts/smoke.py --command "):
        assert line in WORKFLOW, line
    smoke = steps[-1].commands
    assert smoke[0] == ("uv", "build", "--wheel") and smoke[1][:2] == ("uv", "venv") and smoke[2][:4] == ("uv", "pip", "install", "--python")
    assert smoke[3][0].endswith("smoke-venv\\Scripts\\python.exe") and smoke[3][1:3] == ("scripts\\smoke.py", "--command") and smoke[3][3].endswith("smoke-venv\\Scripts\\neoaprs.exe")


def test_every_step_script_sets_the_environment_runs_in_the_tree_and_ends_with_the_exit_code_of_the_first_failure(script: ModuleType) -> None:
    paths = script.windows_paths("John", "RUN-1")
    for step in script.steps(paths):
        text = script.step_script(paths, step)
        for name, value in (("NEOAPRS_NO_DEVICES", "1"), ("NEOAPRS_UPDATE_CHECK", "0"), ("UV_PYTHON_PREFERENCE", "only-managed"), ("UV_PYTHON", script.PYTHON)):
            assert f"$env:{name} = '{value}'" in text, (step.name, name)
        assert f"Set-Location -LiteralPath '{paths.tree}'" in text
        assert text.count("if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }") == len(step.commands)
        assert text.endswith("exit 0")
        assert ("$env:UV_FROZEN = '1'" in text) == (step.name != "lock") and ("Remove-Item Env:UV_FROZEN" in text) == (step.name == "lock")
        assert text.index("Set-Location") < text.index("& ")


def test_the_arguments_for_pytest_are_each_one_quoted_string_and_only_pytest_gets_them(script: ModuleType) -> None:
    paths = script.windows_paths("John", "RUN-1")
    steps = {step.name: script.step_script(paths, step) for step in script.steps(paths, ODD_NAMES)}
    for name in ODD_NAMES:
        assert script.ps_quote(name) in steps["pytest"]
        assert all(script.ps_quote(name) not in text for key, text in steps.items() if key != "pytest")
    assert "& 'uv' 'run' 'pytest' '-n' 'auto' '-p' 'no:cacheprovider' 'plain.py' 'with space.py' 'it''s.py'" in steps["pytest"]


def test_the_smoke_step_installs_the_wheel_it_built_into_a_fresh_environment_outside_the_tree(script: ModuleType) -> None:
    paths = script.windows_paths("John", "RUN-1")
    text = script.step_script(paths, script.steps(paths)[-1])
    assert "(Get-ChildItem -LiteralPath 'dist' -Filter '*.whl').FullName" in text and "'(Get-ChildItem" not in text
    assert f"'uv' 'venv' '{paths.run}\\smoke-venv'" in text and text.index("'build'") < text.index("'venv'") < text.index("'pip'") < text.index("smoke.py")


def test_the_prepare_script_unpacks_with_windows_tar_and_makes_a_repository_only_where_git_is(script: ModuleType) -> None:
    paths = script.windows_paths("John", "RUN-1")
    text = script.prepare_script(paths)
    assert f"-xf '{paths.tar}' -C '{paths.run}'" in text and "System32\\tar.exe" in text
    assert text.index("-xf") < text.index("Get-Command git.exe") < text.index("init --quiet") < text.index("--pathspec-file-nul") < text.index("commit --quiet")
    assert "catch { } }" in text and text.endswith("exit 0")


def test_the_probe_runs_the_python_of_the_environment_and_sends_ctrl_break_to_a_child_in_its_own_group(script: ModuleType) -> None:
    paths = script.windows_paths("John", "RUN-1")
    text = script.probe_script(paths)
    assert f"{paths.tree}\\.venv\\Scripts\\python.exe" in text
    assert "CREATE_NEW_PROCESS_GROUP" in script.CONSOLE_PROBE and "CTRL_BREAK_EVENT" in script.CONSOLE_PROBE
    compile(script.CONSOLE_PROBE.replace("CREATE_NEW_PROCESS_GROUP", "CREATE_NEW_CONSOLE").replace("CTRL_BREAK_EVENT", "SIGTERM"), "probe", "exec")      # (it is Python, which the stand-ins cannot run)


def test_a_step_that_is_given_up_on_is_cleaned_up_by_the_folder_its_programs_run_from(script: ModuleType) -> None:
    text = script.stop_script("C:\\Users\\John\\neoaprs-check\\RUN-1")
    assert "'C:\\Users\\John\\neoaprs-check\\RUN-1'" in text and "Stop-Process" in text and "$PID" in text


def test_only_chooses_steps_in_the_order_of_the_ci_and_adds_sync_where_the_environment_is_needed(script: ModuleType) -> None:
    assert script.chosen_steps([]) == STEP_NAMES
    assert script.chosen_steps(["smoke", "lock"]) == ["lock", "smoke"]
    assert script.chosen_steps(["pytest"]) == ["sync", "pytest"]
    assert script.chosen_steps(["ruff", "ruff"]) == ["sync", "ruff"]
    assert script.chosen_steps(["sync"]) == ["sync"]


def test_the_arguments_after_two_dashes_are_for_pytest_and_make_it_the_one_step(script: ModuleType) -> None:
    packer = script.load_script("check-in-container")
    args, extra = script.parse(["--", "tests/test_replay.py", "-x"], packer.split_command)
    assert extra == ["tests/test_replay.py", "-x"] and args.only == ["pytest"]
    args, extra = script.parse(["--only", "pytest", "--only", "smoke", "--snapshot", "clean", "--tty"], packer.split_command)
    assert extra == [] and args.only == ["pytest", "smoke"] and args.snapshot == "clean" and args.tty
    with pytest.raises(SystemExit):
        script.parse(["--only", "ruff", "--", "-x"], packer.split_command)
    with pytest.raises(SystemExit):
        script.parse(["--only", "mypy"], packer.split_command)


# ---- power ----

def test_a_machine_that_is_off_is_started_and_shut_down_again_by_the_run_that_started_it(script: ModuleType) -> None:
    for state in ("poweroff", "aborted", "saved"):
        plan = script.plan_power(state, "")
        assert plan.start and not plan.restore


def test_a_machine_that_is_running_is_used_as_it_is_and_left_running(script: ModuleType) -> None:
    plan = script.plan_power("running", "")
    assert not plan.start and not plan.restore


def test_a_snapshot_is_put_back_only_before_a_start_and_never_under_a_running_machine(script: ModuleType) -> None:
    assert script.plan_power("poweroff", "clean") == script.PowerPlan(restore=True, start=True)
    with pytest.raises(script.Refused, match="running"):
        script.plan_power("running", "clean")


@pytest.mark.parametrize("state", ["starting", "stopping", "paused", "saving", "restoring", "gurumeditation", ""])
def test_a_machine_between_states_is_not_touched(script: ModuleType, state: str) -> None:
    with pytest.raises(script.Refused):
        script.plan_power(state, "")


def test_the_state_is_read_from_the_machine_readable_listing(script: ModuleType) -> None:
    listing = 'name="Windows 11"\nVMState="poweroff"\nVMStateChangeTime="2026-11-13T10:00:00.000000000"\nOSType="Windows11_64"\n'
    assert script.parse_vm_state(listing) == "poweroff"
    assert script.parse_vm_state("") == "" and script.parse_vm_state('name="VMState=running"\n') == ""


def test_wait_for_asks_until_yes_or_until_the_patience_is_over(script: ModuleType) -> None:
    now = [0.0]
    asked = []

    def sleep(seconds: float) -> None:
        now[0] += seconds

    def answer_on(third: int) -> Callable[[], bool]:
        def done() -> bool:
            asked.append(now[0])
            return len(asked) >= third
        return done

    assert script.wait_for(answer_on(3), 100.0, 5.0, sleep, lambda: now[0]) is True and asked == [0.0, 5.0, 10.0]
    asked.clear()
    now[0] = 0.0
    assert script.wait_for(lambda: False, 12.0, 5.0, sleep, lambda: now[0]) is False and now[0] == 15.0


# ---- the lock ----

def test_the_lock_is_one_file_for_each_machine_in_the_build_cache(script: ModuleType) -> None:
    env = {"NEOAPRS_BUILD_CACHE": "/cache"}
    assert script.lock_path(env, "Windows 11") == Path("/cache/check-windows/locks/Windows-11.lock")
    assert script.lock_path(env, "../../etc/x y") == Path("/cache/check-windows/locks/..-..-etc-x-y.lock")
    assert script.lock_path(env, "a") != script.lock_path(env, "b")


def test_a_second_run_on_a_machine_stops_and_the_lock_goes_with_the_first(script: ModuleType, tmp_path: Path) -> None:
    path = tmp_path / "deeper" / "locks" / "vm.lock"
    with script.run_lock(path):
        with pytest.raises(script.Busy, match="one run at a time"), script.run_lock(path):
            raise AssertionError("the lock was given twice")
    with script.run_lock(path):
        pass


# ---- old runs ----

def test_the_newest_two_runs_stay_and_what_is_not_a_run_is_never_named(script: ModuleType) -> None:
    names = ["RUN-20261113T090000", "RUN-20261111T090000", "notes", "RUN-20261112T090000", "RUN-20261113T100000\r", "RUN-x", "neotest", "RUN-20261110T090000"]
    assert script.runs_to_remove(names) == ["RUN-20261110T090000", "RUN-20261111T090000", "RUN-20261112T090000"]
    assert script.runs_to_remove(["RUN-20261113T090000"]) == [] and script.runs_to_remove([]) == []
    assert script.runs_to_remove(names, keep=0)[-1] == "RUN-20261113T100000" and script.runs_to_remove(names, keep=9) == []


def test_the_removal_script_names_only_runs_in_the_folder_of_the_runs(script: ModuleType) -> None:
    paths = script.windows_paths("John", "RUN-20261113T101010")
    text = script.removal_script(paths, ["RUN-20261110T090000", "..\\x", "RUN-20261111T090000\nRemove-Item C:\\"])
    assert text.count("Remove-Item") == 1 and "C:\\Users\\John\\neoaprs-check\\RUN-20261110T090000" in text and text.endswith("exit 0")


# ---- what is printed ----

def made_up(script: ModuleType, name: str, code: int, seconds: float, tail: tuple[str, ...] = ()) -> Any:
    return script.StepResult(name, code, seconds, Path("/logs") / f"{name}.log", tail)


def test_a_result_line_is_the_line_of_the_gate(script: ModuleType) -> None:
    assert script.result_line(made_up(script, "ruff", 0, 4.26)) == "ok    ruff            4.3s"
    assert script.result_line(made_up(script, "pytest", 1, 324.04)) == "FAIL  pytest        324.0s"
    assert script.result_line(made_up(script, "sync", 0, 0.04)) == "ok    sync            0.0s"


def test_a_failed_step_is_followed_by_the_tail_of_its_output_and_the_path_of_its_whole_log(script: ModuleType) -> None:
    assert script.report_lines(made_up(script, "lock", 0, 1.0, ("noise",))) == ["ok    lock            1.0s"]
    lines = script.report_lines(made_up(script, "ruff", 1, 2.0, ("one", "two")))
    assert lines == ["FAIL  ruff            2.0s", "      | one", "      | two", "      (the whole log: /logs/ruff.log)"]


def test_the_exit_code_is_one_when_any_step_failed_and_the_last_line_names_them(script: ModuleType) -> None:
    green = [made_up(script, name, 0, 1.0) for name in STEP_NAMES]
    assert script.exit_code(green) == 0 and script.summary(green, 12.9) == "all green in 12s"
    red = [made_up(script, "sync", 0, 1.0), made_up(script, "ruff", 1, 1.0), made_up(script, "pytest", 124, 1.0)]
    assert script.exit_code(red) == 1 and script.summary(red, 5.0) == "failed in 5s: ruff pytest"
    assert script.exit_code([]) == 0


def test_a_console_session_output_is_cleaned_of_escapes_carriage_returns_and_overwritten_text(script: ModuleType) -> None:
    raw = "\x1b[?25l\x1b[0mline one\r\nprogress 10%\rprogress 100%\r\n\x1b]0;title\x07\x1b[31mred\x1b[0m text\r\nlast"
    assert script.clean_output(raw) == "line one\nprogress 100%\nred text\nlast"
    assert script.clean_output("plain\nlines\n") == "plain\nlines\n"


# ---- uv ----

def test_uv_is_pinned_by_version_address_and_digest_and_recognised_by_what_it_says(script: ModuleType) -> None:
    assert script.UV.version == "0.11.26" and script.UV.sha256 == "4e1278ede866be6c0bf32d2f466cc6de7a9fb399ecf20c9ce2d186e52424be47"
    assert script.UV.url == f"https://github.com/astral-sh/uv/releases/download/0.11.26/{script.UV.file}" and script.UV.file == "uv-x86_64-pc-windows-msvc.zip"
    assert script.uv_version_ok("uv 0.11.26 (abc 2026-01-01)\r\n") and not script.uv_version_ok("uv 0.11.25 (abc)") and not script.uv_version_ok("") and not script.uv_version_ok("uv: not recognised")


def test_the_zip_of_uv_in_the_cache_is_used_when_its_digest_is_the_pin_and_fetched_when_it_is_not(script: ModuleType, tmp_path: Path) -> None:
    import hashlib
    pin = script.Pin("1.0", "https://example.invalid/uv.zip", hashlib.sha256(b"the zip").hexdigest(), "uv.zip")
    fetched: list[str] = []

    def download(url: str, target: Path, sha256: str) -> None:
        fetched.append(url)
        assert target.name.endswith(".part") and sha256 == pin.sha256
        target.write_bytes(b"the zip")

    path = script.ensure_uv_zip(tmp_path, pin, download)
    assert path == tmp_path / "uv-1.0" / "uv.zip" and path.read_bytes() == b"the zip" and fetched == [pin.url] and not list(path.parent.glob("*.part"))
    assert script.ensure_uv_zip(tmp_path, pin, download) == path and len(fetched) == 1
    path.write_bytes(b"changed on disk")
    script.ensure_uv_zip(tmp_path, pin, download)
    assert len(fetched) == 2 and path.read_bytes() == b"the zip"


def test_a_download_that_fails_leaves_no_file_in_the_cache(script: ModuleType, tmp_path: Path) -> None:
    pin = script.Pin("1.0", "https://example.invalid/uv.zip", "0" * 64, "uv.zip")

    def download(url: str, target: Path, sha256: str) -> None:
        target.write_bytes(b"half")
        raise OSError("the transfer broke off")

    with pytest.raises(OSError, match="broke off"):
        script.ensure_uv_zip(tmp_path, pin, download)
    assert not list((tmp_path / "uv-1.0").iterdir())


# ---- stand-ins for ssh, scp and VBoxManage ----

SSH = """#!@PYTHON@
import base64, json, os, sys
folder = os.environ["FAKE_DIR"]
args = sys.argv[1:]
remote = args[-1]
tty = "-tt" in args
marker = "-EncodedCommand "
script = base64.b64decode(remote.split(marker)[1]).decode("utf-16-le") if marker in remote else remote
with open(folder + "/ssh-calls", "a") as calls:
    calls.write(json.dumps({"args": args, "tty": tty, "script": script}) + "\\n")
for name in os.environ.get("FAKE_FAIL", "").split():
    if "# step: " + name + "\\n" in script:
        print(name + " said: boom")
        sys.exit(1)
first = script.split("\\n", 1)[0]
if first.startswith("# step: ") and os.path.exists(folder + "/answer-" + first[8:]):
    print(open(folder + "/answer-" + first[8:]).read())
    sys.exit(0)

def flag(name):
    return os.path.exists(folder + "/" + name)

if "LastBootUpTime" in script:
    if flag("uptimes"):
        left = open(folder + "/uptimes").read().split()
        if left:
            open(folder + "/uptimes", "w").write(" ".join(left[1:]))
            if left[0] == "away":
                sys.exit(255)
            print(left[0])
            sys.exit(0)
    print("ran fine")
    sys.exit(0)
if "shutdown.exe /s" in script:
    if not flag("stays-on") and not flag("deaf-to-shutdown"):
        open(folder + "/state", "w").write("poweroff")
    sys.exit(0)
if script == "exit 0":
    if flag("down"):
        left = int(open(folder + "/down").read() or "0")
        if left > 0:
            open(folder + "/down", "w").write(str(left - 1))
            sys.exit(255)
    sys.exit(0)
if "--version" in script:
    if flag("uv-installed") or flag("uv-present"):
        print("uv 0.11.26 (made up)")
    sys.exit(0)
if "-xf" in script and "uv-x86_64" in script:
    open(folder + "/uv-installed", "w").close()
    sys.exit(0)
if "-Directory -Name" in script:
    if flag("listing"):
        print(open(folder + "/listing").read().strip())
    sys.exit(0)
if "Ctrl+Break" in script:
    sys.exit(0 if flag("probe-tty-ok" if tty else "probe-plain-ok") else 1)
for name, mark in (("sync", "'sync'"), ("lock", "'lock'"), ("ruff", "'ruff'"), ("pytest", "'pytest'"), ("smoke", "'build'")):
    if name in os.environ.get("FAKE_FAIL", "").split() and mark in script:
        print(name + " said: boom")
        print("second line of " + name)
        sys.exit(1)
print("ran fine" + ("\\x1b[0m\\r" if tty else ""))
"""
SCP = """#!@PYTHON@
import json, os, shutil, sys
folder = os.environ["FAKE_DIR"]
args = sys.argv[1:]
with open(folder + "/scp-calls", "a") as calls:
    calls.write(json.dumps(args) + "\\n")
if os.path.exists(folder + "/scp-fails"):
    print("scp: connection lost", file=sys.stderr)
    sys.exit(1)
shutil.copy(args[-2], folder + "/copied-" + os.path.basename(args[-2]))
"""
VBOX = """#!@PYTHON@
import os, sys
folder = os.environ["FAKE_DIR"]
args = sys.argv[1:]
with open(folder + "/vbox-calls", "a") as calls:
    calls.write(" ".join(args) + "\\n")

def put(state):
    open(folder + "/state", "w").write(state)

if args[0] == "showvminfo":
    print('name="%s"' % args[1])
    print('VMState="%s"' % open(folder + "/state").read())
elif args[0] == "startvm":
    if os.path.exists(folder + "/start-fails"):
        print("VBoxManage: error: could not start", file=sys.stderr)
        sys.exit(1)
    put("running")
elif args[0] == "controlvm" and args[2] == "acpipowerbutton":
    put("running" if os.path.exists(folder + "/stays-on") else "poweroff")
elif args[0] == "snapshot":
    if os.path.exists(folder + "/restore-fails"):
        print("VBoxManage: error: no such snapshot", file=sys.stderr)
        sys.exit(1)
    put("poweroff")
"""


class Bench:
    """A folder with the three stand-ins, the files they answer from, and what they were asked."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.bin = folder / "bin"
        self.bin.mkdir(parents=True)
        for name, text in (("ssh", SSH), ("scp", SCP), ("VBoxManage", VBOX)):
            program = self.bin / name
            program.write_text(text.replace("@PYTHON@", sys.executable), encoding="utf-8")
            program.chmod(program.stat().st_mode | stat.S_IEXEC)
        (folder / "tmp").mkdir()
        self.state("poweroff")
        self.env = {"PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}", "HOME": str(folder), "TMPDIR": str(folder / "tmp"), "FAKE_DIR": str(folder), "NEOAPRS_BUILD_CACHE": str(folder / "cache"),
                    **good_env(folder, NEOAPRS_WINVM="Windows 11")}

    def state(self, state: str) -> None:
        (self.folder / "state").write_text(state, encoding="utf-8")

    def flag(self, name: str, text: str = "") -> None:
        (self.folder / name).write_text(text, encoding="utf-8")

    def ssh_calls(self) -> list[dict[str, Any]]:
        path = self.folder / "ssh-calls"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def scripts(self, containing: str) -> list[str]:
        return [call["script"] for call in self.ssh_calls() if containing in call["script"]]

    def vbox_calls(self) -> list[str]:
        path = self.folder / "vbox-calls"
        return path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    def use(self, monkeypatch: pytest.MonkeyPatch) -> "Bench":
        for name, value in self.env.items():
            monkeypatch.setenv(name, value)
        return self


@pytest.fixture
def bench(tmp_path: Path) -> Bench:
    return Bench(tmp_path / "bench")


def settings_of(script: ModuleType, bench: Bench) -> Any:
    return script.read_settings(bench.env)


def test_a_machine_that_answers_after_a_few_tries_is_waited_for_and_one_that_does_not_is_said(script: ModuleType, bench: Bench, monkeypatch: pytest.MonkeyPatch) -> None:
    bench.use(monkeypatch)
    settings = settings_of(script, bench)
    bench.flag("down", "2")
    script.wait_for_ssh(settings, patience_sec=30.0, interval_sec=0.01)
    assert len(bench.scripts("exit 0")) == 3
    bench.flag("down", "1000")
    with pytest.raises(script.Refused, match="did not answer within 0 s"):
        script.wait_for_ssh(settings, patience_sec=0.0, interval_sec=0.01)


def test_the_machine_is_started_without_a_window_and_shut_down_from_inside_and_waited_for(script: ModuleType, bench: Bench, monkeypatch: pytest.MonkeyPatch) -> None:
    bench.use(monkeypatch)
    settings = settings_of(script, bench)
    assert script.vm_state("Windows 11") == "poweroff"
    script.start_vm(settings, script.PowerPlan(restore=False, start=True), "")
    assert script.vm_state("Windows 11") == "running"
    script.power_off(settings, patience_sec=5.0, interval_sec=0.01)
    assert script.vm_state("Windows 11") == "poweroff"
    assert bench.scripts("shutdown.exe /s"), "Windows is asked from inside to shut down"
    assert not [call for call in bench.vbox_calls() if call.startswith("controlvm")], "and the power button is not needed when that turns it off"


def test_a_machine_just_started_is_waited_for_until_it_has_been_up_two_minutes_through_a_moment_without_ssh(script: ModuleType, bench: Bench, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Windows restarts its SSH service once in its first minute: a step begun then ended with "closed by remote host" (14 Nov 2026)."""
    bench.use(monkeypatch)
    settings = settings_of(script, bench)
    (bench.folder / "uptimes").write_text("25 away 70 119 121 500", encoding="utf-8")
    script.wait_until_settled(settings, patience_sec=30.0, interval_sec=0.01)
    assert (bench.folder / "uptimes").read_text(encoding="utf-8").split() == ["500"], "asked until the machine said 121 s, through the moment its SSH was away"
    assert "has just started" in capsys.readouterr().err
    (bench.folder / "uptimes").write_text("300", encoding="utf-8")
    script.wait_until_settled(settings, patience_sec=30.0, interval_sec=0.01)
    assert "has just started" not in capsys.readouterr().err, "a machine that has been up long enough is not waited for"
    (bench.folder / "uptimes").unlink()
    script.wait_until_settled(settings, patience_sec=30.0, interval_sec=0.01)                 # (a machine that says no number: nothing to wait for is known)
    assert "has just started" not in capsys.readouterr().err


def test_a_machine_that_does_not_go_off_is_left_as_it_is_and_never_powered_off_hard(script: ModuleType, bench: Bench, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    bench.use(monkeypatch)
    bench.state("running")
    bench.flag("stays-on")
    script.power_off(settings_of(script, bench), patience_sec=0.0, interval_sec=0.01)
    assert "left as it is" in capsys.readouterr().err
    assert bench.scripts("shutdown.exe /s") and [call for call in bench.vbox_calls() if call.startswith("controlvm")] == ["controlvm Windows 11 acpipowerbutton"], "asked from inside, then the button, and nothing harder"


def test_a_machine_that_does_not_shut_down_when_asked_from_inside_gets_the_power_button(script: ModuleType, bench: Bench, monkeypatch: pytest.MonkeyPatch) -> None:
    bench.use(monkeypatch)
    bench.state("running")
    bench.flag("deaf-to-shutdown")
    script.power_off(settings_of(script, bench), patience_sec=0.05, interval_sec=0.01)
    assert script.vm_state("Windows 11") == "poweroff"
    assert [call for call in bench.vbox_calls() if call.startswith("controlvm")] == ["controlvm Windows 11 acpipowerbutton"]


def test_the_snapshot_is_put_back_before_the_start_and_a_failure_of_either_is_the_users_sentence(script: ModuleType, bench: Bench, monkeypatch: pytest.MonkeyPatch) -> None:
    bench.use(monkeypatch)
    settings = settings_of(script, bench)
    script.start_vm(settings, script.PowerPlan(restore=True, start=True), "clean")
    assert bench.vbox_calls() == ["snapshot Windows 11 restore clean", "startvm Windows 11 --type headless"]
    bench.flag("restore-fails")
    with pytest.raises(script.Refused, match="snapshot clean could not be put back.*no such snapshot"):
        script.start_vm(settings, script.PowerPlan(restore=True, start=True), "clean")
    bench.flag("start-fails")
    with pytest.raises(script.Refused, match="could not be started.*could not start"):
        script.start_vm(settings, script.PowerPlan(restore=False, start=True), "")


def test_uv_that_is_there_is_left_and_uv_that_is_not_is_fetched_copied_and_unpacked(script: ModuleType, bench: Bench, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bench.use(monkeypatch)
    settings = settings_of(script, bench)
    paths = script.windows_paths("John", "RUN-1")
    bench.flag("uv-present")
    script.put_uv_there(settings, paths, tmp_path / "cache")
    assert not (bench.folder / "scp-calls").exists()
    (bench.folder / "uv-present").unlink()
    zip_file = tmp_path / "uv.zip"
    zip_file.write_bytes(b"zip")
    monkeypatch.setattr(script, "ensure_uv_zip", lambda cache: zip_file)
    script.put_uv_there(settings, paths, tmp_path / "cache")
    copied = json.loads((bench.folder / "scp-calls").read_text(encoding="utf-8"))
    assert copied[-2:] == [str(zip_file), f"John@127.0.0.1:C:/Users/John/neoaprs-check/{script.UV.file}"]
    assert bench.scripts("-xf") and "C:\\Users\\John\\neotest\\uv" in bench.scripts("-xf")[0]
    made = [text for text in bench.scripts("New-Item") if "-xf" not in text]
    assert made and "C:\\Users\\John\\neoaprs-check'" in made[0], "the folder the zip is copied into is made first: a clean machine has none"


def test_uv_that_cannot_be_fetched_or_copied_is_the_sentence_of_the_user_and_not_a_trace(script: ModuleType, bench: Bench, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bench.use(monkeypatch)
    settings = settings_of(script, bench)
    paths = script.windows_paths("John", "RUN-1")

    def fails(cache: Path) -> Path:
        raise OSError("no network")

    monkeypatch.setattr(script, "ensure_uv_zip", fails)
    with pytest.raises(script.Refused, match="could not be fetched .no network"):
        script.put_uv_there(settings, paths, tmp_path)
    zip_file = tmp_path / "uv.zip"
    zip_file.write_bytes(b"zip")
    monkeypatch.setattr(script, "ensure_uv_zip", lambda cache: zip_file)
    bench.flag("scp-fails")
    with pytest.raises(script.Refused, match="uv.zip could not be copied.*connection lost"):
        script.put_uv_there(settings, paths, tmp_path)


def test_a_step_runs_with_its_whole_log_kept_and_a_step_that_hangs_is_ended_with_code_124(script: ModuleType, bench: Bench, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bench.use(monkeypatch)
    settings = settings_of(script, bench)
    paths = script.windows_paths("John", "RUN-1")
    ruff = script.steps(paths)[2]
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    result = script.run_step(settings, paths, ruff, log_dir)
    assert (result.name, result.code, result.log, result.tail) == ("ruff", 0, log_dir / "ruff.log", ("ran fine",))
    bench.env["FAKE_FAIL"] = "ruff"
    monkeypatch.setenv("FAKE_FAIL", "ruff")
    result = script.run_step(settings, paths, ruff, log_dir)
    assert result.code == 1 and result.tail == ("ruff said: boom", "second line of ruff")
    assert (log_dir / "ruff.log").read_text(encoding="utf-8").startswith("ruff said: boom\nsecond line of ruff")
    hanging = bench.bin / "ssh"
    hanging.write_text("#!/bin/sh\nexec sleep 30\n", encoding="utf-8")
    result = script.run_step(settings, paths, script.Step("ruff", ruff.commands, timeout_sec=0.3), log_dir)
    assert result.code == 124 and "did not end in 0 s" in result.tail[-1]


def test_the_probe_decides_the_console_a_plain_session_first_then_one_with_a_pseudo_console(script: ModuleType, bench: Bench, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    bench.use(monkeypatch)
    settings = settings_of(script, bench)
    paths = script.windows_paths("John", "RUN-1")
    bench.flag("probe-plain-ok")
    assert script.choose_console(settings, paths, force_tty=False) is False and [call["tty"] for call in bench.ssh_calls()] == [False]
    (bench.folder / "probe-plain-ok").unlink()
    bench.flag("probe-tty-ok")
    assert script.choose_console(settings, paths, force_tty=False) is True and [call["tty"] for call in bench.ssh_calls()][1:] == [False, True]
    (bench.folder / "probe-tty-ok").unlink()
    assert script.choose_console(settings, paths, force_tty=False) is False and "did not pass in either" in capsys.readouterr().err
    before = len(bench.ssh_calls())
    assert script.choose_console(settings, paths, force_tty=True) is True and len(bench.ssh_calls()) == before


# ---- from end to end ----

TRACKED = {"pyproject.toml": "[project]\n", "neoaprs/__init__.py": "", "with space/it's.txt": "x", ".gitignore": "ignored.txt\n"}
UNTRACKED = {"new file.txt": "n"}
KEPT_HERE = {"ignored.txt": "i", ".secrets": "token", "sub/.secrets-prod": "token", "vault/.secrets/key": "k"}


def make_tree(folder: Path) -> Path:
    """A made-up repository with copies of the three scripts: tracked and untracked files, one an ignore rule names, and files of access tokens."""
    tree = folder / "tree"
    (tree / "scripts").mkdir(parents=True)
    for name in ("check-windows", "check-in-container", "security-tools"):
        shutil.copy(SCRIPTS / name, tree / "scripts" / name)
    for name, text in {**TRACKED, **UNTRACKED, **KEPT_HERE}.items():
        (tree / name).parent.mkdir(parents=True, exist_ok=True)
        if not (tree / name).is_dir():
            (tree / name).write_text(text, encoding="utf-8")
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    subprocess.run(["git", "-C", str(tree), "init", "-q"], check=True, env=environment)
    subprocess.run(["git", "-C", str(tree), "add", "--", "scripts", *TRACKED], check=True, env=environment)
    return tree


def run_check(tree: Path, bench: Bench, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(tree / "scripts" / "check-windows"), *args], env={**bench.env, **env}, capture_output=True, text=True, timeout=120, cwd=bench.folder)


def result_lines(output: str) -> list[str]:
    return [line for line in output.splitlines() if re.match(r"(ok|FAIL) {2,}\w", line)]


def test_without_the_machine_in_the_environment_the_script_says_so_and_touches_nothing(bench: Bench) -> None:
    tree = make_tree(bench.folder)
    done = run_check(tree, bench, NEOAPRS_WINVM="")
    assert done.returncode == 2 and "not set up on this machine" in done.stderr and "NEOAPRS_WINVM_SSH_PORT" in done.stderr and done.stdout == ""
    assert bench.vbox_calls() == [] and bench.ssh_calls() == []
    done = run_check(tree, bench, NEOAPRS_WINVM_SSH_PORT="")
    assert done.returncode == 2 and "NEOAPRS_WINVM_SSH_PORT is not" in done.stderr
    (bench.folder / "key").unlink()
    done = run_check(tree, bench)
    assert done.returncode == 2 and "NEOAPRS_WINVM_SSH_KEY" in done.stderr and bench.vbox_calls() == []


def test_a_machine_that_is_off_is_started_headless_checked_and_powered_off_again(bench: Bench) -> None:
    tree = make_tree(bench.folder)
    bench.flag("uv-present")
    done = run_check(tree, bench)
    assert done.returncode == 0, done.stderr
    assert [re.sub(r" +\d+\.\ds$", "", line) for line in result_lines(done.stdout)] == ["ok    sync", "ok    lock", "ok    ruff", "ok    pytest", "ok    smoke"]
    assert re.search(r"all green in \d+s$", done.stdout.strip())
    assert bench.vbox_calls()[0] == "showvminfo Windows 11 --machinereadable"
    assert [call for call in bench.vbox_calls() if not call.startswith("showvminfo")] == ["startvm Windows 11 --type headless"] and bench.scripts("shutdown.exe /s"), "shut down from inside"
    assert (bench.folder / "state").read_text(encoding="utf-8") == "poweroff"
    assert "starting Windows 11 without a window" in done.stderr and "waiting for the SSH" in done.stderr and "the logs are in" in done.stderr
    logs = re.search(r"the logs are in (\S+)", done.stderr)
    assert logs is not None and sorted(path.name for path in Path(logs.group(1)).iterdir()) == sorted(f"{name}.log" for name in STEP_NAMES)


def test_a_machine_that_was_running_is_left_running(bench: Bench) -> None:
    tree = make_tree(bench.folder)
    bench.state("running")
    bench.flag("uv-present")
    done = run_check(tree, bench, "--only", "ruff")
    assert done.returncode == 0, done.stderr
    assert bench.vbox_calls() == ["showvminfo Windows 11 --machinereadable"] and (bench.folder / "state").read_text(encoding="utf-8") == "running"
    assert [re.sub(r" +\d+\.\ds$", "", line) for line in result_lines(done.stdout)] == ["ok    sync", "ok    ruff"]


def test_the_tree_goes_over_as_it_is_on_disk_without_what_an_ignore_rule_names_or_a_file_of_access_tokens(bench: Bench) -> None:
    tree = make_tree(bench.folder)
    bench.flag("uv-present")
    assert run_check(tree, bench, "--only", "lock").returncode == 0
    with tarfile.open(bench.folder / "copied-tree.tar") as tar:
        names = {member.name for member in tar.getmembers()}
        listing = tar.extractfile("tracked")
        assert listing is not None
        tracked = {name for name in listing.read().decode().split("\0") if name}
    assert {"neoaprs/pyproject.toml", "neoaprs/new file.txt", "neoaprs/with space/it's.txt", "neoaprs/scripts/check-windows", "tracked"} <= names
    assert not [name for name in names if "ignored.txt" in name or ".secrets" in name]
    assert "new file.txt" not in tracked and {"pyproject.toml", "with space/it's.txt"} <= tracked
    copies = json.loads((bench.folder / "scp-calls").read_text(encoding="utf-8").splitlines()[0])
    assert re.fullmatch(r"John@127\.0\.0\.1:C:/Users/John/neoaprs-check/RUN-\d{8}T\d{6}-tree\.tar", copies[-1]) and "BatchMode=yes" in copies
    prepared = bench.scripts("tree.tar")[-1]
    assert "-xf" in prepared and "neoaprs-check" in prepared


def test_a_failed_step_is_printed_under_its_line_and_stops_none_but_sync(bench: Bench) -> None:
    tree = make_tree(bench.folder)
    bench.flag("uv-present")
    done = run_check(tree, bench, FAKE_FAIL="ruff")
    assert done.returncode == 1
    assert [line.split()[0] + " " + line.split()[1] for line in result_lines(done.stdout)] == ["ok sync", "ok lock", "FAIL ruff", "ok pytest", "ok smoke"]
    assert "      | ruff said: boom\n      | second line of ruff\n      (the whole log: " in done.stdout
    assert re.search(r"failed in \d+s: ruff$", done.stdout.strip())
    assert (bench.folder / "state").read_text(encoding="utf-8") == "poweroff"
    done = run_check(tree, bench, FAKE_FAIL="sync")
    assert done.returncode == 1 and [line.split()[1] for line in result_lines(done.stdout)] == ["sync"]
    assert re.search(r"failed in \d+s: sync$", done.stdout.strip())


def test_the_arguments_after_two_dashes_reach_pytest_and_nothing_else(bench: Bench) -> None:
    tree = make_tree(bench.folder)
    bench.flag("uv-present")
    bench.state("running")
    done = run_check(tree, bench, "--", "tests/test_a b.py", "-k", "it's")
    assert done.returncode == 0, done.stderr
    ran = bench.scripts("'pytest'")
    assert len(ran) == 1 and "'tests/test_a b.py' '-k' 'it''s'" in ran[0]
    assert [line.split()[1] for line in result_lines(done.stdout)] == ["sync", "pytest"]


def test_pytest_runs_in_a_session_with_a_console_when_only_such_a_session_can_send_ctrl_break(bench: Bench) -> None:
    tree = make_tree(bench.folder)
    bench.flag("uv-present")
    bench.state("running")
    bench.flag("probe-tty-ok")
    done = run_check(tree, bench, "--only", "pytest")
    assert done.returncode == 0 and "through ssh -tt" in done.stderr
    calls = bench.ssh_calls()
    assert [call["tty"] for call in calls if "'pytest'" in call["script"]] == [True] and not any(call["tty"] for call in calls if "'sync'" in call["script"])
    log = [path for path in (bench.folder / "tmp").glob("neoaprs-check-windows-*/pytest.log")][0]
    assert log.read_text(encoding="utf-8") == "ran fine\n\n"


def test_the_older_runs_but_the_newest_two_are_removed_at_the_end(bench: Bench) -> None:
    tree = make_tree(bench.folder)
    bench.flag("uv-present")
    bench.state("running")
    bench.flag("listing", "RUN-20261101T010101\nRUN-20261102T010101\nRUN-20261103T010101\nRUN-20261104T010101\nneotest\n")
    done = run_check(tree, bench, "--only", "lock")
    assert done.returncode == 0, done.stderr
    removal = bench.scripts("-Recurse -Force")
    assert len(removal) == 1 and removal[0].count("Remove-Item") == 2 and "RUN-20261101T010101" in removal[0] and "RUN-20261102T010101" in removal[0] and "RUN-20261103T010101" not in removal[0]


def test_a_second_run_says_so_and_stops_before_it_touches_the_machine(bench: Bench, script: ModuleType) -> None:
    tree = make_tree(bench.folder)
    bench.flag("uv-present")
    with script.run_lock(script.lock_path(bench.env, "Windows 11")):
        done = run_check(tree, bench)
    assert done.returncode == 2 and "one run at a time" in done.stderr
    assert bench.vbox_calls() == [] and bench.ssh_calls() == []
    assert (bench.folder / "state").read_text(encoding="utf-8") == "poweroff"
    assert run_check(tree, bench, "--only", "lock").returncode == 0


def test_a_snapshot_is_put_back_before_the_start_and_refused_for_a_machine_that_runs(bench: Bench) -> None:
    tree = make_tree(bench.folder)
    bench.flag("uv-present")
    done = run_check(tree, bench, "--snapshot", "clean", "--only", "lock")
    assert done.returncode == 0, done.stderr
    assert [call for call in bench.vbox_calls() if not call.startswith("showvminfo")][:2] == ["snapshot Windows 11 restore clean", "startvm Windows 11 --type headless"]
    bench.state("running")
    before = len(bench.vbox_calls())
    done = run_check(tree, bench, "--snapshot", "clean")
    assert done.returncode == 2 and "running" in done.stderr and bench.vbox_calls()[before:] == ["showvminfo Windows 11 --machinereadable"]


def test_a_machine_that_cannot_be_used_is_a_sentence_and_the_machine_is_shut_down_only_when_this_run_started_it(bench: Bench) -> None:
    tree = make_tree(bench.folder)
    bench.state("saving")
    done = run_check(tree, bench)
    assert done.returncode == 2 and "saving" in done.stderr and [call for call in bench.vbox_calls() if not call.startswith("showvminfo")] == []
    bench.state("poweroff")
    bench.flag("start-fails")
    done = run_check(tree, bench, "--only", "lock")
    assert done.returncode == 2 and "could not be started" in done.stderr


def test_a_tree_that_is_no_repository_is_said_before_the_machine_is_asked_for_anything(bench: Bench) -> None:
    tree = make_tree(bench.folder)
    shutil.rmtree(tree / ".git")
    done = run_check(tree, bench)
    assert done.returncode == 2 and "nothing was run" in done.stderr and bench.vbox_calls() == [] and bench.ssh_calls() == []


def test_the_python_of_the_steps_is_the_one_the_workflow_names(script: ModuleType) -> None:
    """Left to uv, a clean machine takes the newest Python the project allows; the workflow names one, and the Windows check runs that one."""
    named = set(re.findall(r'python-version: "([0-9.]+)"', WORKFLOW))
    assert named == {script.PYTHON}, "ci.yml names one Python, and scripts/check-windows runs its steps on it"


# ---- the install proof (--install) ----

INSTALL_STEPS = ["install", "defender", "daemon", "commands", "app", "map", "direwolf", "smoke", "mercury", "uninstall"]


def install_tree(folder: Path) -> Path:
    """The made-up repository, with what the install proof takes from it: the two smoke scripts, the capture, the Tornado pin and the Direwolf NeoAPRS ships."""
    tree = make_tree(folder)
    for name in ("scripts/smoke.py", "tests/fixtures/kiss/thd7-2026-10-21.bin", "packaging/windows/smoke_mercury.py", "neoaprs/direwolf.py"):
        (tree / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / name, tree / name)
    (tree / "pyproject.toml").write_text('[project]\ndependencies = ["tornado==6.6.1"]\n', encoding="utf-8")
    return tree


def installer(folder: Path, name: str = "NeoAPRS-Setup-0.20.0.exe") -> Path:
    path = folder / "dist-installer" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"MZ made up")
    return path


def test_the_install_proof_needs_a_snapshot_and_runs_alone(script: ModuleType) -> None:
    split = script.load_script("check-in-container").split_command
    args, _ = script.parse(["--install", "NeoAPRS-Setup-0.20.0.exe", "--snapshot", "clean"], split)
    assert (args.install, args.snapshot) == ("NeoAPRS-Setup-0.20.0.exe", "clean")
    for wrong in (["--install", "x.exe"], ["--install", "x.exe", "--snapshot", "clean", "--only", "ruff"], ["--install", "x.exe", "--snapshot", "clean", "--tty"],
                  ["--install", "x.exe", "--snapshot", "clean", "--", "-k", "x"]):
        with pytest.raises(SystemExit) as stop:
            script.parse(wrong, split)
        assert stop.value.code == 2, wrong


def test_the_installer_is_named_by_its_version_and_smoke_runs_with_the_pinned_tornado(script: ModuleType, tmp_path: Path) -> None:
    assert script.installer_version(installer(tmp_path)) == "0.20.0"
    assert script.installer_version(installer(tmp_path, "NeoAPRS-Setup-1.0.0-rc1.exe")) == "1.0.0-rc1"
    for wrong in (installer(tmp_path, "setup.exe"), tmp_path / "NeoAPRS-Setup-0.20.0-missing.exe"):
        with pytest.raises(script.NotSetUp, match="NeoAPRS-Setup-VERSION.exe"):
            script.installer_version(wrong)
    assert script.tornado_pin((ROOT / "pyproject.toml").read_text(encoding="utf-8")) == re.search(r'"tornado==([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8")).group(1)
    with pytest.raises(script.NotSetUp):
        script.tornado_pin("[project]\n")


def test_the_install_steps_are_the_proof_in_order_each_named_and_short_enough_for_cmd(script: ModuleType) -> None:
    paths = script.windows_paths("John", "RUN-20261115T101010")
    steps = script.install_steps(paths, "NeoAPRS-Setup-0.20.0.exe", "0.20.0", "6.6.1", "Dire Wolf Release 1.8.1, November 2025")      # (the banner: test_the_direwolf_the_install_proof_asks_for...)
    assert [name for name, _, _ in steps] == INSTALL_STEPS == list(script.INSTALL_STEP_NAMES)
    for name, text, timeout in steps:
        assert text.startswith(f"# step: {name}\n") and text.endswith("exit 0") and timeout >= 300
        assert "$app = Join-Path $env:LOCALAPPDATA 'Programs\\NeoAPRS'" in text
        assert len(script.powershell_line(text)) <= script.REMOTE_LINE_MAX, name
        uses_python = "uv run" in text or "neotest\\uv" in text
        assert uses_python == (name in script.NEEDS_PYTHON), f"{name}: only the smoke steps have uv and its Python"
        assert "NEOAPRS_NO_DEVICES" not in text, "the app runs as an operator's would"
    by_name = {name: text for name, text, _ in steps}
    install = by_name["install"]
    assert "-ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/LOG=" in install
    assert "/CURRENTUSER" not in install, "it does nothing: the installer is per user already"
    assert "C:\\Users\\John\\neoaprs-check\\RUN-20261115T101010\\NeoAPRS-Setup-0.20.0.exe" in install and "installed: {0:N1} MB" in install
    assert "RealTimeProtectionEnabled" in by_name["defender"] and "MpCmdRun.exe" in by_name["defender"] and "IsInRole" in by_name["defender"], "the scan only as an administrator, never through a prompt"
    assert "-ArgumentList 'run'" in by_name["daemon"] and "basemap-world.pmtiles" in by_name["daemon"] and "-ArgumentList 'stop'" in by_name["daemon"]
    assert "'NeoAPRS 0.20.0'" in by_name["commands"] and "doctor" in by_name["commands"] and "support --out" in by_name["commands"]
    assert "'--tray', '--data', $data" in by_name["app"] and "stop --data $data" in by_name["app"]
    assert "_internal\\neoaprs\\desktop\\icon.ico" in install, "the tray's icon is a file the app reads as it is"
    app = by_name["app"]
    assert app.index("$code -eq 200") < app.index("Start-Sleep 5") < app.index("'uncaught exception|Traceback'") < app.index("stop --data $data"), "a tray that failed in its own thread is in the app's log"
    assert "--dry-run" in by_name["map"]
    for f in ("bin\\direwolf\\direwolf.exe", "bin\\direwolf\\data\\tocalls.yaml"):
        assert f"(Join-Path $app '{f}')" in install, f"{f}: the installer carries the Direwolf of the type Sound card (Direwolf)"
    sound_card = by_name["direwolf"]
    assert "neoaprs.exe') db --data 'C:\\Users\\John\\neoaprs-check\\RUN-20261115T101010\\data-direwolf' radios add direwolf" in sound_card, "the installed app finds its own Direwolf, or refuses the type"
    assert sound_card.index("radios add direwolf") < sound_card.index("$LASTEXITCODE -eq 0") < sound_card.index("direwolf.exe') -h")
    assert "$said.Contains('Dire Wolf Release 1.8.1, November 2025')" in sound_card, "the installed direwolf.exe runs, as the pinned release"
    assert "--with 'tornado==6.6.1' scripts\\smoke.py --command" in by_name["smoke"] and "smoke_mercury.py" in by_name["mercury"]
    uninstall = by_name["uninstall"]
    assert "unins000.exe" in uninstall and "the uninstall left files in the program folder" in uninstall and "neoaprs.sqlite" in uninstall and "CurrentVersion\\Run" in uninstall


def test_the_direwolf_the_install_proof_asks_for_is_the_one_neoaprs_ships(script: ModuleType) -> None:
    assert script.direwolf_banner((ROOT / "neoaprs" / "direwolf.py").read_text(encoding="utf-8")) == direwolf.BANNER.replace("%d.%d.%d", direwolf.VERSION)
    with pytest.raises(script.NotSetUp):
        script.direwolf_banner('VERSION = "1.8.1"\n')


def test_the_programs_are_told_apart_by_the_descriptions_the_spec_gives_them(script: ModuleType) -> None:
    spec = (ROOT / "packaging" / "windows" / "neoaprs.spec").read_text(encoding="utf-8")
    given = dict(re.findall(r'version=version_file\("([^"]+)", "([^"]+)"\)', spec))
    assert script.DESCRIPTIONS == {name: given[name] for name in ("neoaprsw", "neoaprs-app")}


def test_the_kit_holds_the_smoke_scripts_and_the_capture_smoke_plays(script: ModuleType, tmp_path: Path) -> None:
    smoke = (ROOT / "scripts" / "smoke.py").read_text(encoding="utf-8")
    fixture = re.search(r'^FIXTURE = ROOT / (.+)$', smoke, re.M).group(1)
    assert "/".join(re.findall(r'"([^"]+)"', fixture)) in script.KIT
    tar = tmp_path / "kit.tar"
    script.pack_kit(ROOT, tar)
    with tarfile.open(tar) as packed:
        assert sorted(packed.getnames()) == sorted(script.KIT)


def test_the_install_proof_runs_on_the_clean_snapshot_with_python_only_for_the_smoke_steps(bench: Bench) -> None:
    tree = install_tree(bench.folder)
    setup = installer(bench.folder)
    bench.flag("uv-present")
    done = run_check(tree, bench, "--install", str(setup), "--snapshot", "clean")
    assert done.returncode == 0, done.stderr
    assert [re.sub(r" +\d+\.\ds$", "", line).split()[1] for line in result_lines(done.stdout)] == INSTALL_STEPS
    assert re.search(r"all green in \d+s$", done.stdout.strip())
    assert [call for call in bench.vbox_calls() if not call.startswith("showvminfo")][:2] == ["snapshot Windows 11 restore clean", "startvm Windows 11 --type headless"]
    assert (bench.folder / "state").read_text(encoding="utf-8") == "poweroff", "shut down again"
    copies = [json.loads(line)[-1] for line in (bench.folder / "scp-calls").read_text(encoding="utf-8").splitlines()]
    assert re.fullmatch(r"John@127\.0\.0\.1:C:/Users/John/neoaprs-check/RUN-\d{8}T\d{6}/NeoAPRS-Setup-0\.20\.0\.exe", copies[0])
    assert copies[1].endswith("-kit.tar") and len(copies) == 2, "the installer, then the kit; no tree"
    with tarfile.open(bench.folder / "copied-tree.tar") as kit:
        assert sorted(kit.getnames()) == sorted(["scripts/smoke.py", "tests/fixtures/kiss/thd7-2026-10-21.bin", "packaging/windows/smoke_mercury.py"])
    order = [call["script"] for call in bench.ssh_calls()]
    first_uv = next(i for i, text in enumerate(order) if "uv.exe" in text and "--version" in text)
    assert first_uv > next(i for i, text in enumerate(order) if text.startswith("# step: map\n")), "uv is asked for only after the steps that run on a machine with nothing"
    assert first_uv < next(i for i, text in enumerate(order) if text.startswith("# step: smoke\n"))


def test_nothing_follows_a_failed_install_and_any_other_failed_step_stops_none(bench: Bench) -> None:
    tree = install_tree(bench.folder)
    setup = installer(bench.folder)
    bench.flag("uv-present")
    done = run_check(tree, bench, "--install", str(setup), "--snapshot", "clean", FAKE_FAIL="install")
    assert done.returncode == 1 and [line.split()[:2] for line in result_lines(done.stdout)] == [["FAIL", "install"]]
    assert "      | install said: boom" in done.stdout and (bench.folder / "state").read_text(encoding="utf-8") == "poweroff"
    done = run_check(tree, bench, "--install", str(setup), "--snapshot", "clean", FAKE_FAIL="daemon")
    assert done.returncode == 1 and [line.split()[1] for line in result_lines(done.stdout)] == INSTALL_STEPS
    assert re.search(r"failed in \d+s: daemon$", done.stdout.strip())


def test_an_installer_that_is_not_one_is_said_before_the_machine_is_touched(bench: Bench) -> None:
    tree = install_tree(bench.folder)
    done = run_check(tree, bench, "--install", str(installer(bench.folder, "something.exe")), "--snapshot", "clean")
    assert done.returncode == 2 and "NeoAPRS-Setup-VERSION.exe" in done.stderr and bench.vbox_calls() == [] and bench.ssh_calls() == []
    done = run_check(tree, bench, "--install", str(installer(bench.folder)))
    assert done.returncode == 2 and "--snapshot" in done.stderr and bench.vbox_calls() == []



# ---- the upgrade proof (--upgrade) ----

UPGRADE_STEPS = ["old", "station", "update", "migrate", "data", "daemon", "uninstall"]
# What the machine says in the steps the proof reads, as 0.18.2 and this tree said it in a rehearsal of the same commands on Linux (15 November 2026), cut short.
STATION_SAYS = """the page http://127.0.0.1:40789/ answered 200, 2 s after the start
### old db list
tnc/profile               dummy               stored
serial/port                                   default
hf/enabled                true                stored
hf/profile                dummy-hf            stored
station/call              OH2GBA-9            stored
fm/enabled                true                default
station/lat               60.1699             stored
station/lon               24.9384             stored
station/comment           NeoAPRS upgrade proof  stored
beacon/power_w            5                   stored
beacon/interval_min       30                  stored
beacon/path               WIDE1-1             stored
beacon/last_sent_at       2026-11-15T18:11:41Z  kept by the daemon (when it last sent, how the map stands), not a setting
### old db stations
neoaprs db: 4 stations
call       kind     last heard            position           packets
OH2GBA-9   station  2026-11-15 18:12:02Z  60.1699 24.9384          0
Q1CLB      station  2026-11-15 18:11:59Z  60.1753 24.9058          4
Q1KUO      station  2026-11-15 18:11:57Z  62.8923 27.6770          1
PARKING    object   2026-11-15 18:11:54Z  60.1717 24.9023          1
"""
RADIOS_SAYS = """radio 1  FM  fm  dummy  on  (position 1)
  radio/1/beacon    true                default
  radio/1/path      WIDE1-1             stored
  radio/1/digipeat  false               default
radio 2  HF  hf  dummy-hf  on  (position 2)
  radio/2/beacon    true                default
"""
COPY_SAYS = "premigrate-v26-to-v33-20261115-181211.sqlite  2026-11-15 18:12 UTC  version 26        0.2 MB  (taken before the update to version 33: the NeoAPRS you had before opens it)\n"
DATA_SAYS = f"""### db radios
{RADIOS_SAYS}### db list
station/call              OH2GBA-9            stored
station/lat               60.1699             stored
station/lon               24.9384             stored
station/comment           NeoAPRS upgrade proof  stored
beacon/power_w            5                   stored
beacon/interval_min       30                  stored
### db restore
{COPY_SAYS}### db stations
neoaprs db: 4 stations
call       kind     last heard            position           packets
Q1CLB      station  2026-11-15 18:12:39Z  60.1753 24.9058          8
Q1KUO      station  2026-11-15 18:12:37Z  62.8923 27.6770          2
PARKING    object   2026-11-15 18:12:34Z  60.1717 24.9023          2
OH2GBA-9   station  2026-11-15 18:12:30Z  60.1699 24.9384          0
### doctor
NeoAPRS 0.20.0 on Windows 11 (AMD64)
ok    database neoaprs.sqlite, version 33 (0.2 MB)
ok    radio FM (dummy): traffic made up: nothing goes on the air
warn  no base map yet: the page shows no map
      fix: make it on the page (Settings tab, Map, Download) or with `neoaprs map`
0 to fix, 1 to look at
"""
DAEMON_SAYS = "the page http://127.0.0.1:37383/ answered 200, 1 s after the start\n### heard\nQ1ABC\nQ1CLB\nQ3TKU\nthe second start migrated nothing\n"


def upgrade_outputs(**changed: str) -> dict[str, str]:
    return {"station": STATION_SAYS, "data": DATA_SAYS, "daemon": DAEMON_SAYS, **changed}


def upgrade_bench(bench: Bench, **answers: str) -> tuple[Path, Path, Path]:
    tree = make_tree(bench.folder)
    for name, text in {"station": STATION_SAYS, "data": DATA_SAYS, "daemon": DAEMON_SAYS, **answers}.items():
        bench.flag(f"answer-{name}", text)
    return tree, installer(bench.folder / "old", "NeoAPRS-Setup-0.18.2.exe"), installer(bench.folder)


def upgrade_scripts(script: ModuleType) -> dict[str, tuple[str, ...]]:
    paths = script.windows_paths("John", "RUN-20261115T101010")
    return {name: parts for name, parts, _ in script.upgrade_steps(paths, "NeoAPRS-Setup-0.18.2.exe", "0.18.2", "NeoAPRS-Setup-0.20.0.exe", "0.20.0")}


def test_the_upgrade_proof_takes_two_installers_and_a_snapshot_and_runs_alone(script: ModuleType) -> None:
    split = script.load_script("check-in-container").split_command
    args, _ = script.parse(["--upgrade", "NeoAPRS-Setup-0.18.2.exe", "NeoAPRS-Setup-0.20.0.exe", "--snapshot", "clean"], split)
    assert (args.upgrade, args.snapshot, args.install) == (["NeoAPRS-Setup-0.18.2.exe", "NeoAPRS-Setup-0.20.0.exe"], "clean", "")
    for wrong in (["--upgrade", "a.exe", "--snapshot", "clean"], ["--upgrade", "a.exe", "b.exe"], ["--upgrade", "a.exe", "b.exe", "--snapshot", "clean", "--install", "c.exe"],
                  ["--upgrade", "a.exe", "b.exe", "--snapshot", "clean", "--only", "ruff"], ["--upgrade", "a.exe", "b.exe", "--snapshot", "clean", "--tty"],
                  ["--upgrade", "a.exe", "b.exe", "--snapshot", "clean", "--", "-k", "x"]):
        with pytest.raises(SystemExit) as stop:
            script.parse(wrong, split)
        assert stop.value.code == 2, wrong


def test_the_two_installers_are_named_by_their_versions_and_the_old_one_comes_first(script: ModuleType, tmp_path: Path) -> None:
    old, new = installer(tmp_path / "a", "NeoAPRS-Setup-0.18.2.exe"), installer(tmp_path / "b")
    assert script.upgrade_versions(old, new) == ("0.18.2", "0.20.0")
    assert script.upgrade_versions(installer(tmp_path / "c", "NeoAPRS-Setup-0.20.0-rc1.exe"), new) == ("0.20.0-rc1", "0.20.0"), "a candidate of the same release is another build"
    assert script.upgrade_versions(installer(tmp_path / "d", "NeoAPRS-Setup-0.9.1.exe"), installer(tmp_path / "e", "NeoAPRS-Setup-0.10.0.exe")) == ("0.9.1", "0.10.0"), "by number, not by letter"
    for first, second in ((new, old), (new, installer(tmp_path / "f"))):
        with pytest.raises(script.NotSetUp, match="not older than"):
            script.upgrade_versions(first, second)
    for wrong in ((installer(tmp_path / "g", "setup-old.exe"), new), (old, tmp_path / "NeoAPRS-Setup-0.21.0.exe")):
        with pytest.raises(script.NotSetUp, match="--upgrade takes .*NeoAPRS-Setup-VERSION.exe"):
            script.upgrade_versions(*wrong)


def test_the_upgrade_steps_are_in_order_each_named_and_short_enough_for_cmd(script: ModuleType) -> None:
    by_name = upgrade_scripts(script)
    assert list(by_name) == UPGRADE_STEPS == list(script.UPGRADE_STEP_NAMES)
    for name, parts in by_name.items():
        for text in parts:
            assert text.startswith(f"# step: {name}\n") and text.endswith("exit 0") and "$app = Join-Path $env:LOCALAPPDATA 'Programs\\NeoAPRS'" in text
            assert len(script.powershell_line(text)) <= script.REMOTE_LINE_MAX, name
            assert "uv" not in text.split() and "neotest" not in text, "the machine has nothing but Windows and the app"
    old, update = by_name["old"][0], by_name["update"][0]
    for text, setup, version in ((old, "NeoAPRS-Setup-0.18.2.exe", "0.18.2"), (update, "NeoAPRS-Setup-0.20.0.exe", "0.20.0")):
        assert f"$setup = 'C:\\Users\\John\\neoaprs-check\\RUN-20261115T101010\\{setup}'" in text
        assert "-ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/LOG=" in text and f"-eq 'NeoAPRS {version}'" in text
    assert "basemap-world.pmtiles" not in old, "the release before is held only to the files every release has"
    assert all(f"(Join-Path $app '{f}')" in update for f in script.INSTALLED_FILES) and "-eq '0.20.0')" in update and f"Uninstall\\{script.APP_ID}_is1" in update
    every = "\n".join(text for parts in by_name.values() for text in parts)
    assert every.count("unins000.exe') -ArgumentList") == 1 and "unins000.exe') -ArgumentList" in by_name["uninstall"][0], "the update goes over the old release: the only uninstall is the last step"


def test_the_station_is_made_with_the_old_command_line_and_its_daemon(script: ModuleType) -> None:
    station = upgrade_scripts(script)["station"]
    assert len(station) == 2
    make, record = station
    for key, value in script.STATION:
        assert f"@('{key}', '{value}')" in make
    assert "& $exe db --data $data set $kv[0] $kv[1]" in make and "the old release's command line refused" in make
    assert make.index("set $kv[0] $kv[1]") < make.index("'run', '--data', $data, '--web-port', '0'") < make.index("& $exe stop --data $data")
    assert "$env:NEOAPRS_UPDATE_CHECK = '0'" in make and "NEOAPRS_NO_DEVICES" not in make, "0.18.2 has no such switch: its Dummy radios open no device"
    assert "$data = 'C:\\Users\\John\\neoaprs-check\\RUN-20261115T101010\\data-upgrade'" in make
    assert "& $exe db --data $data list" in record and "& $exe db --data $data stations" in record
    assert "Set-Content -LiteralPath 'C:\\Users\\John\\neoaprs-check\\RUN-20261115T101010\\old-db-list.txt'" in record and "old-db-stations.txt" in record
    assert dict(script.STATION)["tnc/profile"] == "dummy" and dict(script.STATION)["hf/profile"] == "dummy-hf"
    assert [key for key, _ in script.STATION].index("hf/profile") < [key for key, _ in script.STATION].index("hf/enabled"), "the HF radio is the Dummy before it is on"


def test_the_flat_keys_of_the_station_are_where_this_release_keeps_them(script: ModuleType) -> None:
    from neoaprs.config import BY_KEY
    from neoaprs.configradios import FLAT_HOMES
    homes = {attr.replace("_", "/", 1): home for attr, home in FLAT_HOMES.items()}
    for key, (radio, column) in script.MOVED.items():
        assert homes[key][0] == radio, key
        assert column == {"type": "type", "enabled": "on"}.get(homes[key][1], f"radio/{radio}/{homes[key][1]}"), key
    assert all(key in BY_KEY for key in script.KEPT_KEYS)
    assert all(key in script.KEPT_KEYS or key in script.MOVED for key, _ in script.STATION), "every value given is compared after the update"


def test_the_app_id_of_the_apps_list_is_the_installers(script: ModuleType) -> None:
    iss = (ROOT / "packaging" / "windows" / "neoaprs.iss").read_text(encoding="utf-8")
    assert f"AppId={{{script.APP_ID}" in iss


def test_the_new_daemon_starts_twice_on_the_station_with_no_device_and_the_second_start_migrates_nothing(script: ModuleType) -> None:
    by_name = upgrade_scripts(script)
    migrate, daemon = by_name["migrate"][0], by_name["daemon"][0]
    for text in (migrate, daemon):
        assert "$env:NEOAPRS_NO_DEVICES = '1'" in text and "$env:NEOAPRS_UPDATE_CHECK = '0'" in text and "'run', '--data', $data, '--web-port', '0'" in text
        assert "Select-Object -Skip $skip | Select-String 'web page at" in text, "the address of this start, not of the runs before in the same log"
        assert "$code -eq 200" in text and "'Z  (ERROR|CRITICAL)  |Traceback'" in text and "-like '*NeoAPRS ended'" in text
    assert "brought up to date now' }).Count -eq 1" in migrate and "premigrate-v[0-9]+" in migrate
    assert "$moved.Count -eq 0" in daemon and "'### heard'" in daemon
    assert re.search(script.MIGRATED, "the database C:\\x\\neoaprs.sqlite is of version 26, this NeoAPRS needs 33: it is brought up to date now (a large file takes minutes)")
    assert re.search(script.MIGRATED, "the database C:\\x\\neoaprs.sqlite is now version 27 (was 26)") and not re.search(script.MIGRATED, "web page at http://127.0.0.1:1/")
    data = by_name["data"][0]
    assert [line for line in data.splitlines() if line.startswith("'### ")] == ["'### db radios'", "'### db list'", "'### db restore'", "'### db stations'", "'### doctor'"]


def test_the_checks_pass_what_the_rehearsal_said(script: ModuleType) -> None:
    outputs = upgrade_outputs()
    assert script.check_station(outputs)[0] == []
    problems, notes = script.check_data(outputs)
    assert problems == [] and notes == ["the copy taken before the update: premigrate-v26-to-v33-20261115-181211.sqlite (schema version 26 of the release before)"]
    assert script.check_daemon(outputs) == ([], ["heard again after the update: Q1CLB"])


def test_the_data_check_refuses_a_missing_radio_a_missing_copy_and_a_second_one(script: ModuleType) -> None:
    without_fm = DATA_SAYS.replace(RADIOS_SAYS, "radio 2" + RADIOS_SAYS.split("radio 2")[1])
    assert any("no radio 1, the FM radio that tnc/profile and fm/enabled and beacon/path made" in p for p in script.check_data(upgrade_outputs(data=without_fm))[0])
    without_hf = DATA_SAYS.replace("radio 2  HF  hf  dummy-hf  on  (position 2)\n  radio/2/beacon    true                default\n", "")
    assert any("no radio 2, the HF radio" in p for p in script.check_data(upgrade_outputs(data=without_hf))[0])
    off = STATION_SAYS.replace("hf/enabled                true", "hf/enabled                false")
    assert not any("radio 2" in p for p in script.check_data(upgrade_outputs(data=without_hf, station=off))[0]), "an HF radio that was off may be left out"
    wrong_type = DATA_SAYS.replace("radio 1  FM  fm  dummy  on", "radio 1  FM  fm  kiss  on").replace("radio/1/path      WIDE1-1", "radio/1/path      WIDE2-2")
    found = script.check_data(upgrade_outputs(data=wrong_type))[0]
    assert "radio 1 has type 'kiss', and the old tnc/profile was 'dummy'" in found and "radio 1 has radio/1/path 'WIDE2-2', and the old beacon/path was 'WIDE1-1'" in found
    assert "radio 2 has on 'false', and the old hf/enabled was 'true'" in script.check_data(upgrade_outputs(data=DATA_SAYS.replace("dummy-hf  on", "dummy-hf  off")))[0]
    assert any("lists no copy premigrate-v" in p for p in script.check_data(upgrade_outputs(data=DATA_SAYS.replace(COPY_SAYS, "")))[0])
    second = COPY_SAYS + COPY_SAYS.replace("v26-to-v33-20261115-181211", "v25-to-v26-20261101-101010").replace("  (taken before the update to version 33: the NeoAPRS you had before opens it)", "")
    assert any("lists 2 copies premigrate-v" in p for p in script.check_data(upgrade_outputs(data=DATA_SAYS.replace(COPY_SAYS, second)))[0])
    unmarked = COPY_SAYS.split("  (taken")[0] + "\n"
    assert any("does not mark premigrate-v26" in p for p in script.check_data(upgrade_outputs(data=DATA_SAYS.replace(COPY_SAYS, unmarked)))[0])
    assert script.check_data(upgrade_outputs(data=DATA_SAYS.replace(COPY_SAYS, COPY_SAYS.replace("v26", "v31"))))[0] == [], "the number is the release before's, whichever it is"


def test_the_data_check_refuses_a_changed_setting_a_lost_station_and_a_failed_doctor(script: ModuleType) -> None:
    found = script.check_data(upgrade_outputs(data=DATA_SAYS.replace("station/lat               60.1699", "station/lat               60.17")))[0]
    assert found == ["station/lat was '60.1699' and is '60.17' after the update"]
    found = script.check_data(upgrade_outputs(data=DATA_SAYS.replace("Q1KUO      station  2026-11-15 18:12:37Z  62.8923 27.6770          2\n", "")))[0]
    assert found == ["db stations has lost 1 of the stations the old release knew: Q1KUO"]
    found = script.check_data(upgrade_outputs(data=DATA_SAYS.replace("ok    database neoaprs.sqlite", "FAIL  database neoaprs.sqlite")))[0]
    assert found == ["doctor: FAIL  database neoaprs.sqlite, version 33 (0.2 MB)"]


def test_the_station_check_and_the_daemon_check_refuse_what_did_not_happen(script: ModuleType) -> None:
    found = script.check_station(upgrade_outputs(station=STATION_SAYS.replace("beacon/path               WIDE1-1", "beacon/path               ")))[0]
    assert found == ["the old release's db list has beacon/path as '', not 'WIDE1-1'"]
    alone = STATION_SAYS.split("Q1CLB")[0]
    assert any("heard no station" in p for p in script.check_station(upgrade_outputs(station=alone))[0])
    assert script.check_daemon(upgrade_outputs(daemon="### heard\nOH2GBA-9\nQ9NEW\n"))[0] == ["the new daemon heard none of the stations the old one heard: the Dummy radios did not come through the update"]


def test_the_upgrade_proof_runs_on_the_clean_snapshot_with_no_uninstall_before_the_update(bench: Bench) -> None:
    tree, old, new = upgrade_bench(bench)
    done = run_check(tree, bench, "--upgrade", str(old), str(new), "--snapshot", "clean")
    assert done.returncode == 0, done.stdout + done.stderr
    assert [re.sub(r" +\d+\.\ds$", "", line).split()[1] for line in result_lines(done.stdout)] == UPGRADE_STEPS
    assert re.search(r"all green in \d+s$", done.stdout.strip())
    assert "the copy taken before the update: premigrate-v26-to-v33-20261115-181211.sqlite" in done.stderr and "heard again after the update: Q1CLB" in done.stderr
    assert [call for call in bench.vbox_calls() if not call.startswith("showvminfo")][:2] == ["snapshot Windows 11 restore clean", "startvm Windows 11 --type headless"]
    assert (bench.folder / "state").read_text(encoding="utf-8") == "poweroff", "shut down again"
    copies = [json.loads(line)[-1] for line in (bench.folder / "scp-calls").read_text(encoding="utf-8").splitlines()]
    assert [copy.rsplit("/", 1)[1] for copy in copies] == ["NeoAPRS-Setup-0.18.2.exe", "NeoAPRS-Setup-0.20.0.exe"], "the two installers and nothing else: no tree, no uv"
    steps = [call["script"].split("\n", 1)[0][len("# step: "):] for call in bench.ssh_calls() if call["script"].startswith("# step: ")]
    assert steps == ["old", "station", "station", "update", "migrate", "data", "daemon", "uninstall"]
    logs = re.search(r"the logs are in (\S+)", done.stderr)
    assert logs is not None and sorted(path.name for path in Path(logs.group(1)).iterdir()) == sorted(f"{name}.log" for name in UPGRADE_STEPS)
    assert (Path(logs.group(1)) / "station.log").read_text(encoding="utf-8").count("### old db list") == 2, "the two parts of the station in one log"


def test_a_failed_step_stops_the_upgrade_proof_and_the_machine_is_shut_down(bench: Bench) -> None:
    tree, old, new = upgrade_bench(bench)
    done = run_check(tree, bench, "--upgrade", str(old), str(new), "--snapshot", "clean", FAKE_FAIL="update")
    assert done.returncode == 1 and [line.split()[:2] for line in result_lines(done.stdout)] == [["ok", "old"], ["ok", "station"], ["FAIL", "update"]]
    assert "      | update said: boom" in done.stdout and re.search(r"failed in \d+s: update$", done.stdout.strip())
    assert not bench.scripts("# step: migrate") and not bench.scripts("# step: uninstall")
    assert (bench.folder / "state").read_text(encoding="utf-8") == "poweroff"


def test_a_data_step_that_does_not_hold_fails_with_its_problems_and_stops_the_proof(bench: Bench) -> None:
    tree, old, new = upgrade_bench(bench, data=DATA_SAYS.replace(COPY_SAYS, ""))
    done = run_check(tree, bench, "--upgrade", str(old), str(new), "--snapshot", "clean")
    assert done.returncode == 1 and [line.split()[1] for line in result_lines(done.stdout)] == ["old", "station", "update", "migrate", "data"]
    assert "      | db restore lists no copy premigrate-v...: the migration left no copy of the database from before it" in done.stdout
    assert not bench.scripts("# step: daemon") and (bench.folder / "state").read_text(encoding="utf-8") == "poweroff"
    logs = re.search(r"the logs are in (\S+)", done.stderr)
    assert logs is not None and "lists no copy premigrate-v" in (Path(logs.group(1)) / "data.log").read_text(encoding="utf-8")


def test_installers_that_are_not_two_in_order_are_said_before_the_machine_is_touched(bench: Bench) -> None:
    tree, old, new = upgrade_bench(bench)
    done = run_check(tree, bench, "--upgrade", str(new), str(old), "--snapshot", "clean")
    assert done.returncode == 2 and "not older than" in done.stderr and bench.vbox_calls() == [] and bench.ssh_calls() == []
    done = run_check(tree, bench, "--upgrade", str(old), str(installer(bench.folder, "something.exe")), "--snapshot", "clean")
    assert done.returncode == 2 and "NeoAPRS-Setup-VERSION.exe" in done.stderr and bench.vbox_calls() == []
