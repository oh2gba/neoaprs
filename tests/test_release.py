"""The release's own files, as far as a test can see them without GitHub or a Windows machine: the notes taken out of the changelog, the install script's template rendered and read by `sh -n`, the workflow's
pins and permissions, the Windows installer script's promises (per user, the tasks, the uninstaller), and the bundled pmtiles that the program looks for first. The whole of it is run by `.github/workflows/release.yml`."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

from neoaprs import pmtilestool
from tests.conftest import ROOT
from tests.support.ptyline import posix_only

NOTES = ROOT / "scripts" / "release-notes.py"
WORKFLOW = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
INSTALLER = (ROOT / "packaging" / "windows" / "neoaprs.iss").read_text(encoding="utf-8")
CHANGELOG = """# Changelog

Intro.

## Unreleased

### Later
- not yet

## 0.2.0 (2026-10-24)

### Releases
- the installer

## 0.1.0 (2026-10-01)
- first
"""


def notes(*args: str, changelog: str = CHANGELOG, tmp: Path) -> subprocess.CompletedProcess[str]:
    path = tmp / "CHANGELOG.md"
    path.write_text(changelog, encoding="utf-8")
    return subprocess.run([sys.executable, str(NOTES), *args, "--changelog", str(path)], capture_output=True, text=True, encoding="utf-8", timeout=30)


def test_the_notes_are_the_section_of_the_version_or_the_newest_one(tmp_path: Path) -> None:
    assert notes("0.2.0", tmp=tmp_path).stdout == "### Releases\n- the installer\n"
    assert notes("0.1.0", tmp=tmp_path).stdout == "- first\n"
    assert notes(tmp=tmp_path).stdout == "### Later\n- not yet\n", "without a version: the newest section"
    missing = notes("0.3.0", tmp=tmp_path)
    assert missing.returncode == 1 and "0.3.0" in missing.stderr and missing.stdout == ""
    assert notes("0.2", tmp=tmp_path).returncode == 1, "0.2 is not 0.2.0"
    assert notes("0.2.0", changelog="# Changelog\n\n## 0.2.0\n\n## 0.1.0\n- x\n", tmp=tmp_path).returncode == 1, "an empty section is no notes"
    assert notes(changelog="# Changelog\n\n## Unreleased\n\n## 0.1.0\n- x\n", tmp=tmp_path).stdout == "- x\n", "without a version: the newest section that has notes (the empty Unreleased of a tree just released is passed over)"


def test_the_real_changelog_has_notes_for_its_newest_section_that_is_not_an_empty_unreleased() -> None:
    done = subprocess.run([sys.executable, str(NOTES)], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert done.returncode == 0 and done.stdout.strip(), done.stderr


@posix_only      # (sh, sed)
def test_the_install_script_renders_without_a_placeholder_and_is_valid_sh(tmp_path: Path) -> None:
    template = (ROOT / "packaging" / "install.sh.in").read_text(encoding="utf-8")
    assert template.startswith("#!/bin/sh\n") and "set -eu" in template
    rendered = tmp_path / "install.sh"
    url = "https://github.com/oh2gba/neoaprs/releases/download/v9.8.7/neoaprs-9.8.7-py3-none-any.whl"
    done = subprocess.run(["sed", "-e", "s|@VERSION@|9.8.7|g", "-e", f"s|@WHEEL_URL@|{url}|g", str(ROOT / "packaging" / "install.sh.in")], capture_output=True, text=True, check=True)
    rendered.write_text(done.stdout, encoding="utf-8")
    assert not re.search(r"@[A-Z_]+@", done.stdout) and f'WHEEL_URL="${{NEOAPRS_WHEEL_URL:-{url}}}"' in done.stdout and 'VERSION="9.8.7"' in done.stdout
    assert subprocess.run(["sh", "-n", str(rendered)]).returncode == 0
    for needed in ("astral.sh/uv/install.sh", "tool install --force --python 3.13", "service install", "usermod -aG", "doctor"):
        assert needed in done.stdout


@posix_only      # (sh)
def test_the_install_script_refuses_a_system_that_is_neither_linux_nor_macos(tmp_path: Path) -> None:
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "uname").write_text("#!/bin/sh\necho MINGW64_NT\n", encoding="utf-8")
    (fake / "uname").chmod(0o755)
    done = subprocess.run(["sh", str(ROOT / "packaging" / "install.sh.in")], env={"PATH": f"{fake}:/usr/bin:/bin", "HOME": str(tmp_path)}, capture_output=True, text=True, timeout=30)
    assert done.returncode == 1 and "NeoAPRS-Setup" in done.stderr


def test_every_action_of_the_workflow_is_pinned_by_major_version_and_only_the_release_job_writes() -> None:
    uses = re.findall(r"^\s+- uses: (\S+)$", WORKFLOW, re.M)
    assert uses and all(re.fullmatch(r"[\w./-]+@v\d+", u) for u in uses), uses
    assert WORKFLOW.count("contents: write") == 1
    release_job = WORKFLOW.split("\n  release:\n", 1)[1]
    assert "contents: write" in release_job and "attestations: write" in release_job and "id-token: write" in release_job
    assert re.search(r"^permissions:\n  contents: read$", WORKFLOW, re.M), "read-only by default"
    assert "startsWith(github.ref, 'refs/tags/v')" in release_job and "gh release create" in release_job and "--verify-tag" in release_job
    assert "workflow_dispatch" in WORKFLOW and 'tags: ["v*"]' in WORKFLOW
    assert "pyinstaller==" in WORKFLOW and "pyinstaller" not in (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()


def test_a_failed_tag_run_is_run_again_and_never_retagged() -> None:
    """Every artifact may be written over by a later attempt, assemble takes the release's files alone (not the logs of a failed update test), the release is a draft until every file is on it, a run on a tag
    whose release exists writes over its files, and a version with a dash (1.0.0-rc1) is a pre-release, which is never `latest`."""
    uploads = [re.split(r"\n      - |\n  \w[\w-]*:\n", block, maxsplit=1)[0] for block in re.split(r"uses: actions/upload-artifact@v\d+\n", WORKFLOW)[1:]]       # each upload's `with:` up to the next step or job
    assert len(uploads) == 8 and all("overwrite: true" in block for block in uploads), f"an attempt that is run again uploads the same names: {uploads}"
    assemble = WORKFLOW.split("\n  assemble:\n", 1)[1].split("\n  release:\n", 1)[0]
    pattern = re.search(r'pattern: "\{([^}]+)\}"', assemble)
    assert pattern and set(pattern.group(1).split(",")) == {"dist", "windows-installer", "appimage", "deb-amd64", "deb-arm64", "install-script"}, "the release's six artifacts and no other"
    release_job = WORKFLOW.split("\n  release:\n", 1)[1]
    assert "--draft " in release_job and "--draft=false" in release_job, "a draft until every file is on it"
    assert "gh release view" in release_job and "--clobber" in release_job, "a release that is there is written over, not refused"
    assert 'case "$version" in *-*) prerelease=true' in release_job and '--prerelease="$prerelease"' in release_job
    assert "github.ref_type == 'tag'" in WORKFLOW.split("\n  verify:\n", 1)[1].split("\n  wheel:\n", 1)[0], "a tag run by hand is verified and published like a pushed one"


def test_verify_fails_early_on_an_unfinished_changelog_a_stale_page_a_commit_off_master_and_a_red_ci() -> None:
    verify = WORKFLOW.split("\n  verify:\n", 1)[1].split("\n  wheel:\n", 1)[0]
    assert "actions: read" in verify and "contents: write" not in verify
    assert "fetch-depth: 0" in verify and "git merge-base --is-ancestor" in verify and "origin/master" in verify
    assert "## Unreleased" in verify and "neoaprs/page/sw.js" in verify
    assert "gh run list" in verify and "--workflow ci.yml" in verify and '--commit "$GITHUB_SHA"' in verify and "seq 1 40" in verify and "sleep 30" in verify, "a CI run still going is waited for, 20 minutes at most"
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "cancel-in-progress: ${{ github.ref != 'refs/heads/master' }}" in ci, "a push to master is checked to the end: the tag's verify asks for that run"


def test_the_installer_script_is_per_user_and_does_what_the_manual_says() -> None:
    assert "PrivilegesRequired=lowest" in INSTALLER and r"DefaultDirName={localappdata}\Programs\NeoAPRS" in INSTALLER
    assert "OutputBaseFilename=NeoAPRS-Setup-{#AppVersion}" in INSTALLER
    assert 'Name: "autostart"; Description: "Start NeoAPRS when I sign in"\n' in INSTALLER, "the task is on by default"
    assert 'Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked' in INSTALLER, "the desktop shortcut is a task that is off by default"
    assert 'Name: "{group}\\NeoAPRS"; Filename: "{app}\\neoaprs-app.exe"' in INSTALLER and 'Name: "{group}\\Stop NeoAPRS"' in INSTALLER, "the Start menu's NeoAPRS is the app"
    assert 'Name: "{autodesktop}\\NeoAPRS"; Filename: "{app}\\neoaprs-app.exe"; Tasks: desktopicon' in INSTALLER
    registry = INSTALLER.split("[Registry]", 1)[1].split("[Run]", 1)[0]
    assert 'ValueName: "NeoAPRS"' in registry and '"{app}\\neoaprs-app.exe"" --tray' in registry and "Tasks: autostart" in registry and "uninsdeletevalue" in registry, "start at sign-in is the app in the tray, not the daemon"
    run, uninstall = INSTALLER.split("[Run]", 1)[1].split("[UninstallRun]", 1)
    assert "service install" not in run and 'Filename: "{app}\\neoaprs-app.exe"' in run and "Description: \"Open NeoAPRS now\"" in run and "postinstall" in run and "skipifsilent" in run
    uninstall = uninstall.split("[Code]", 1)[0]
    assert 'Parameters: "--quit"' in uninstall and 'Parameters: "service remove"' in uninstall and 'Parameters: "stop"' in uninstall
    assert uninstall.index("--quit") < uninstall.index('"stop"') < uninstall.index("service remove"), "the app, then the daemon that is left, then the start at sign-in of a service"
    assert "--quit" in INSTALLER.split("[Code]", 1)[1], "an update ends the app too, or its files are in use"
    assert "UninstallDelete" not in INSTALLER, "the data folder is not the installer's to delete"


def test_the_installer_starts_again_what_ran_after_the_silent_update_of_update_now() -> None:
    run = INSTALLER.split("[Run]", 1)[1].split("[UninstallRun]", 1)[0]
    assert 'Filename: "{app}\\neoaprs-app.exe"; Parameters: "{code:DataArgs}"; Flags: nowait; Check: RestartWanted(\'app\')' in run
    assert 'Filename: "{app}\\neoaprsw.exe"; Parameters: "run {code:DataArgs}"; Flags: nowait runhidden; Check: RestartWanted(\'daemon\')' in run
    code = INSTALLER.split("[Code]", 1)[1]
    assert "function RestartWanted(What: String): Boolean;" in code and "WizardSilent and" in code and "{param:NEOAPRSRESTART|}" in code
    assert "function DataArgs(Param: String): String;" in code and "{param:NEOAPRSDATA|}" in code
    assert "Trim('--quit ' + DataArgs(''))" in code and "Trim('stop ' + DataArgs(''))" in code, "the app and the daemon of that data folder are the ones ended"


def test_the_frozen_app_has_three_programs_whose_names_differ_for_a_system_that_ignores_case() -> None:
    spec = (ROOT / "packaging" / "windows" / "neoaprs.spec").read_text(encoding="utf-8")
    names = re.findall(r'EXE\(pyz, a\.scripts, \[\], name="([^"]+)", console=(True|False)', spec)
    assert names == [("neoaprs", "True"), ("neoaprsw", "False"), ("neoaprs-app", "False")]
    assert len({name.lower() for name, _ in names}) == 3, "NeoAPRS.exe would be neoaprs.exe"
    assert "icon=icon" in spec and 'excludes=["tkinter", "PySide6", "shiboken6"]' in spec and "COLLECT(console, windowed, app," in spec


@pytest.mark.parametrize("program, calls", [("neoaprs.exe", "main"), ("neoaprsw.exe", "gui_main"), ("neoaprs-app.exe", "app_main"), ("NeoAPRS-App.EXE", "app_main")])
def test_the_entry_of_the_frozen_app_tells_its_three_programs_apart_by_name(program: str, calls: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy

    from neoaprs import cli
    from neoaprs.desktop import cmd
    called: list[str] = []
    monkeypatch.setattr(cli, "main", lambda *a: called.append("main") or 0)
    monkeypatch.setattr(cli, "gui_main", lambda *a: called.append("gui_main") or 0)
    monkeypatch.setattr(cmd, "gui_main", lambda *a: called.append("app_main") or 0)
    monkeypatch.setattr(sys, "executable", f"/Program Files/NeoAPRS/{program}")
    with pytest.raises(SystemExit) as stop:
        runpy.run_path(str(ROOT / "packaging" / "windows" / "neoaprs_entry.py"), run_name="__main__")
    assert stop.value.code == 0 and called == [calls]


def test_a_frozen_program_finds_the_pmtiles_beside_it_before_the_path(tmp_path: Path) -> None:
    bundled, on_path = tmp_path / "app" / "bin", tmp_path / "path"
    name = pmtilestool.tool_file()
    for folder in (bundled, on_path):
        folder.mkdir(parents=True)
        (folder / name).write_bytes(b"x")
        (folder / name).chmod(0o755)
    assert pmtilestool.find(tmp_path / "data", search_path=str(on_path), bundled=bundled) == bundled / name
    assert pmtilestool.find(tmp_path / "data", search_path=str(on_path), bundled=tmp_path / "empty") == on_path / name
    assert pmtilestool.bundled_dir() is None, "a program run from Python has no bundle"


def test_bundled_dir_is_bin_next_to_the_executable_of_a_frozen_program(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "NeoAPRS" / "neoaprs.exe"))
    assert pmtilestool.bundled_dir() == (tmp_path / "NeoAPRS").resolve() / "bin"
