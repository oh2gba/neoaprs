"""The release's own files, as far as a test can see them without GitHub or a Windows machine: the notes taken out of the changelog, the install script's template rendered and read by `sh -n`, the workflow's
pins and permissions, the Windows installer script's promises (per user, the tasks, the uninstaller), the bundled pmtiles that the program looks for first, and the bundled Mercury (the job that builds it, the Windows script that unpacks it, what the Linux jobs prove of it). The whole of it is run by `.github/workflows/release.yml`."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

from neoaprs import pmtilestool
from tests.conftest import ROOT

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


def test_every_action_of_the_workflow_is_pinned_by_commit_and_only_the_release_job_writes() -> None:
    uses = re.findall(r"^\s+(?:- )?uses: (\S+)(?: # (\S+))?$", WORKFLOW, re.M)
    assert uses and all(re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", action) and re.fullmatch(r"v\d+\.\d+\.\d+", tag) for action, tag in uses), uses
    assert WORKFLOW.count("contents: write") == 1
    release_job = WORKFLOW.split("\n  release:\n", 1)[1]
    assert "contents: write" in release_job and "attestations: write" in release_job and "id-token: write" in release_job
    assert re.search(r"^permissions:\n  contents: read$", WORKFLOW, re.M), "read-only by default"
    assert "startsWith(github.ref, 'refs/tags/v')" in release_job and "gh release create" in release_job and "--verify-tag" in release_job
    assert "workflow_dispatch" in WORKFLOW and 'tags: ["v*"]' in WORKFLOW
    assert "--group pyinstaller" in WORKFLOW and "pyinstaller==" not in WORKFLOW, "PyInstaller comes from the lock, not from a version of the workflow's own"
    assert re.search(r"^pyinstaller = \[$", (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M), "the group of the lock that holds PyInstaller"


def test_a_failed_tag_run_is_run_again_and_never_retagged() -> None:
    """Every artifact may be written over by a later attempt, assemble takes the release's files alone (not the logs of a failed update test), the release is a draft until scripts/release has signed it, a run on a
    tag whose draft exists writes over its files and deletes its signature, a published release is never written over, and a version with a dash (1.0.0-rc1) is a pre-release, which is never `latest`."""
    uploads = [re.split(r"\n      - |\n  \w[\w-]*:\n", block, maxsplit=1)[0] for block in re.split(r"uses: actions/upload-artifact@[0-9a-f]{40} # v[\d.]+\n", WORKFLOW)[1:]]       # each upload's `with:` up to the next step or job
    assert len(uploads) == 10 and all("overwrite: true" in block for block in uploads), f"an attempt that is run again uploads the same names: {uploads}"
    assemble = WORKFLOW.split("\n  assemble:\n", 1)[1].split("\n  release:\n", 1)[0]
    pattern = re.search(r'pattern: "\{([^}]+)\}"', assemble)
    assert pattern and set(pattern.group(1).split(",")) == {"dist", "windows-installer", "appimage", "macos-app", "deb-amd64", "deb-arm64"}, "the release's six artifacts and no other"
    release_job = WORKFLOW.split("\n  release:\n", 1)[1]
    assert "--draft " in release_job and "--draft=false" not in release_job, "a draft, which only scripts/release publishes once SHA256SUMS is signed"
    assert "gh release view" in release_job and "--clobber" in release_job, "a draft that is there is written over, not refused"
    assert "--json isDraft" in release_job and "is never written over" in release_job, "a published release is never written over: its signature would no longer hold"
    assert "delete-asset" in release_job and "SHA256SUMS.sig" in release_job, "a draft written over loses its signature, which held for the SHA256SUMS before"
    assert 'case "$version" in *-*) prerelease=true' in release_job and '--prerelease="$prerelease"' in release_job
    assert "github.ref_type == 'tag'" in WORKFLOW.split("\n  verify:\n", 1)[1].split("\n  wheel:\n", 1)[0], "a tag run by hand is verified and published like a pushed one"


def test_verify_fails_early_on_an_unfinished_changelog_a_page_that_is_not_the_source_a_commit_off_master_and_a_red_ci() -> None:
    verify = WORKFLOW.split("\n  verify:\n", 1)[1].split("\n  wheel:\n", 1)[0]
    assert "actions: read" in verify and "contents: write" not in verify
    assert "fetch-depth: 0" in verify and "git merge-base --is-ancestor" in verify and "origin/master" in verify
    assert "## Unreleased" in verify and "scripts/build-page" in verify and "git diff --exit-code -- neoaprs/page" in verify, "the committed page is what ui/ builds"
    assert "neoaprs/page/sw.js" not in verify and "const VERSION" not in verify, "the page has no version in it: a release that changed nothing in ui/ leaves it as it is"
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
    support = [line for line in INSTALLER.split("[Icons]", 1)[1].split("[Registry]", 1)[0].splitlines() if line.startswith('Name: "{group}\\NeoAPRS support logs"')]
    assert len(support) == 1 and 'Filename: "{app}\\neoaprs.exe"; Parameters: "support --show --pause"' in support[0], "the Start menu's support entry runs the console program, so that its window shows the file, and waits for Enter"
    assert "'NeoAPRS', 'Stop NeoAPRS', 'NeoAPRS support logs'" in WORKFLOW and 'neoaprs.exe" support --data $data --out $out' in WORKFLOW, "the workflow checks the entry and runs what it runs"
    registry = INSTALLER.split("[Registry]", 1)[1].split("[Run]", 1)[0]
    assert 'ValueName: "NeoAPRS"' in registry and '"{app}\\neoaprs-app.exe"" --tray' in registry and "Tasks: autostart" in registry and "uninsdeletevalue" in registry, "start at sign-in is the app in the tray, not the daemon"
    run, uninstall = INSTALLER.split("[Run]", 1)[1].split("[UninstallRun]", 1)
    assert "service install" not in run and 'Filename: "{app}\\neoaprs-app.exe"' in run and "Description: \"Open NeoAPRS now\"" in run and "postinstall" in run and "skipifsilent" in run
    uninstall = uninstall.split("[Code]", 1)[0]
    assert 'Parameters: "--quit"' in uninstall and 'Parameters: "service remove"' in uninstall and 'Parameters: "stop"' in uninstall
    assert uninstall.index("--quit") < uninstall.index('"stop"') < uninstall.index("service remove"), "the app, then the daemon that is left, then the start at sign-in of a service"
    assert "--quit" in INSTALLER.split("[Code]", 1)[1], "an update ends the app too, or its files are in use"
    code = INSTALLER.split("[Code]", 1)[1]
    assert "function PrepareToInstall(" in code and code.index("EndRunningNeoAPRS();") < code.index("procedure CurStepChanged"), "the app and the daemon are ended before Setup looks for files in use, and again before the files are replaced"
    assert "UninstallDelete" not in INSTALLER, "the data folder is not the installer's to delete"


def test_the_installer_starts_again_what_ran_after_the_silent_update_of_update_now() -> None:
    run = INSTALLER.split("[Run]", 1)[1].split("[UninstallRun]", 1)[0]
    assert 'Filename: "{app}\\neoaprs-app.exe"; Parameters: "{code:DataArgs}{code:EncryptionArg}"; Flags: nowait; Check: RestartWanted(\'app\')' in run
    assert 'Filename: "{app}\\neoaprsw.exe"; Parameters: "run {code:DataArgs}{code:EncryptionArg}"; Flags: nowait runhidden; Check: RestartWanted(\'daemon\')' in run
    code = INSTALLER.split("[Code]", 1)[1]
    assert "function RestartWanted(What: String): Boolean;" in code and "WizardSilent and" in code and "{param:NEOAPRSRESTART|}" in code
    assert "function DataArgs(Param: String): String;" in code and "{param:NEOAPRSDATA|}" in code
    assert "Trim('--quit ' + DataArgs(''))" in code and "Trim('stop ' + DataArgs(''))" in code, "the app and the daemon of that data folder are the ones ended"


def test_the_installer_keeps_encrypted_messages_through_an_update_in_the_restart_the_start_at_sign_in_and_open_neoaprs_now() -> None:
    """Update now of 0.18.0 brought OH2GAX's NeoAPRS back without --encryption, and the installer wrote the start at sign-in without it (4 Nov 2026)."""
    code = INSTALLER.split("[Code]", 1)[1]
    setup = code[code.index("function InitializeSetup(): Boolean;"):code.index("function EncryptionArg(")]
    assert "{param:NEOAPRSENCRYPTION|}" in setup, "Update now says so"
    assert "RegQueryStringValue(HKCU, 'Software\\Microsoft\\Windows\\CurrentVersion\\Run', 'NeoAPRS'" in setup and "Pos('--encryption', SignIn) > 0" in setup, "an update by hand finds it in the start at sign-in"
    arg = code[code.index("function EncryptionArg("):]
    assert "Result := ' --encryption';" in arg.split("end;", 1)[0]
    registry = INSTALLER.split("[Registry]", 1)[1].split("[Run]", 1)[0]
    assert '"{app}\\neoaprs-app.exe"" --tray{code:EncryptionArg}"' in registry
    run = INSTALLER.split("[Run]", 1)[1].split("[UninstallRun]", 1)[0]
    assert 'Parameters: "{code:EncryptionArg}"; Description: "Open NeoAPRS now"' in run
    assert run.count("{code:EncryptionArg}") == 3, "Open NeoAPRS now, and the restart of the app or of the daemon"


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


def test_the_release_has_the_installer_the_appimage_the_macos_app_and_the_packages_under_fixed_names_too() -> None:
    """The project page links to releases/latest/download/NeoAPRS-Setup.exe, NeoAPRS-x86_64.AppImage, NeoAPRS-arm64.dmg, neoaprs_arm64.deb and neoaprs_amd64.deb: one click, the newest, nothing between."""
    assemble = WORKFLOW.split("name: SHA256SUMS and the notes", 1)[1].split("uses: actions/upload-artifact", 1)[0]
    assert 'cp -- "NeoAPRS-Setup-$version.exe" NeoAPRS-Setup.exe' in assemble and 'cp -- "NeoAPRS-$version-x86_64.AppImage" NeoAPRS-x86_64.AppImage' in assemble and 'cp -- "NeoAPRS-$version-arm64.dmg" NeoAPRS-arm64.dmg' in assemble
    assert 'cp -- "neoaprs_${version}_amd64.deb" neoaprs_amd64.deb' in assemble and 'cp -- "neoaprs_${version}_arm64.deb" neoaprs_arm64.deb' in assemble
    assert assemble.index("NeoAPRS-Setup.exe") < assemble.index("sha256sum"), "the copies are in SHA256SUMS"
    assert '[ "$(ls | wc -l)" = 13 ]' in assemble, "the eight files (the wheel and install.sh among them) and the five fixed names, before SHA256SUMS"


def test_no_workflow_step_name_breaks_the_yaml() -> None:
    """An unquoted value with ": " in it is a mapping in YAML, and GitHub then reads the whole workflow as having no triggers (a tag would start nothing):
    the names of jobs and steps that say something with a colon are quoted."""
    bad = []
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            found = re.match(r"^\s*(?:- )?name: (.*)$", line)
            if found and not found.group(1).startswith(("'", '"')) and ": " in found.group(1):
                bad.append(f"{path.name}:{number}: {line.strip()}")
    assert not bad, "quote these names:\n" + "\n".join(bad)


def workflow_jobs() -> dict[str, str]:
    """Every job of every workflow, as `file:job` and its text (the workflows are read as text: no YAML parser is a dependency)."""
    jobs = {}
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        parts = re.split(r"^  ([\w-]+):$", path.read_text(encoding="utf-8").split("\njobs:\n", 1)[1], flags=re.M)
        jobs.update({f"{path.name}:{name}": text for name, text in zip(parts[1::2], parts[2::2], strict=True)})
    return jobs


def test_every_job_of_every_workflow_ends_by_itself_in_far_less_than_the_six_hour_default() -> None:
    jobs = workflow_jobs()
    assert len(jobs) >= 14, sorted(jobs)
    limits = {name: re.search(r"^    timeout-minutes: (\d+)$", text, re.M) for name, text in jobs.items()}
    assert not [name for name, found in limits.items() if found is None], "a job without timeout-minutes can hang for six hours"
    assert all(1 <= int(found.group(1)) <= 60 for found in limits.values() if found), {name: found.group(1) for name, found in limits.items() if found}


def test_a_step_that_pipes_its_output_runs_in_bash_so_that_the_failure_of_the_first_command_is_the_steps() -> None:
    """GitHub runs a step with no `shell:` as `bash -e`, without pipefail: `cmd | tee log` then has the status of tee. An explicit bash is `bash -eo pipefail`."""
    piped = []
    for name, text in workflow_jobs().items():
        job_shell = re.search(r"^    defaults:\n      run:\n        shell: bash$", text, re.M) is not None
        for step in text.split("\n      - ")[1:]:
            step_shell = re.sub(r"<<'(\w+)'\n.*?^\s*\1$", "", step, flags=re.S | re.M)          # (a script given to another program, a container's sh, has its own shell)
            if re.search(r"\| tee\b", step_shell) and not job_shell and not re.search(r"^\s+shell: bash\b", step, re.M):
                piped.append(f"{name}: {step.splitlines()[0]}")
    assert not piped, "these steps pipe into tee without pipefail:\n" + "\n".join(piped)
    assert re.search(r"- name: The simulation\n\s+shell: bash\b[^\n]*\n\s+run: uv run scripts/mercury-sim .*\| tee mercury-sim.log", (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")), "a failing simulation fails the job"


def test_the_wheel_and_the_sdist_are_named_by_the_pep_440_form_of_the_version_and_the_other_files_by_the_version_as_written() -> None:
    assert "from neoaprs.updateasset import wheel_version" in WORKFLOW
    assert WORKFLOW.count("wheel_version=\"$(python3 -c") == 2, "the wheel job and the assembling of the release each ask for the name once"
    assert 'neoaprs-$version-py3-none-any.whl' not in WORKFLOW and 'neoaprs-$version.tar.gz' not in WORKFLOW, "the raw version is not the wheel's"
    wheel_job = WORKFLOW.split("\n  wheel:\n", 1)[1].split("\n  windows:\n", 1)[0]
    assert 'dist/neoaprs-$wheel_version-py3-none-any.whl' in wheel_job and 'dist/neoaprs-$wheel_version.tar.gz' in wheel_job
    assemble = WORKFLOW.split("\n  assemble:\n", 1)[1].split("\n  release:\n", 1)[0]
    assert "rm -f -- neoaprs-*.whl" not in assemble and "packaging/install.sh.in > install.sh" in assemble, "the wheel and install.sh stay files of the release: the update of a copy installed with the install line before 0.16 runs it"
    assert '"neoaprs-$wheel_version.tar.gz" "neoaprs-$wheel_version-py3-none-any.whl" install.sh "NeoAPRS-Setup-$version.exe" "NeoAPRS-$version-x86_64.AppImage" "NeoAPRS-$version-arm64.dmg" "neoaprs_${version}_amd64.deb" "neoaprs_${version}_arm64.deb"' in assemble, "the eight; with the five fixed names and SHA256SUMS, fourteen"
    assert '[ "$(ls | wc -l)" = 13 ]' in assemble


def job(name: str) -> str:
    """The text of one job of the workflow, from its key to the next job's."""
    return re.split(r"\n  [\w-]+:\n", WORKFLOW.split(f"\n  {name}:\n", 1)[1], maxsplit=1)[0]


def test_mercury_is_built_for_both_architectures_in_the_oldest_system_and_the_linux_downloads_wait_for_it() -> None:
    mercury_job = job("mercury")
    assert "arch: amd64\n            runner: ubuntu-latest" in mercury_job and "arch: arm64\n            runner: ubuntu-24.04-arm" in mercury_job
    assert "container: ubuntu:22.04" in mercury_job, "glibc 2.35, the floor the AppImage and the .deb document"
    assert "python3 scripts/build-mercury --tar --out dist-mercury" in mercury_job, "run by the Python 3.10 of the container"
    assert "build-essential pkg-config libasound2-dev libasound2-data python3" in mercury_job and " patch" in mercury_job, "patch applies packaging/mercury/loopback.patch"
    assert mercury_job.index("apt-get install") < mercury_job.index("actions/checkout") < mercury_job.index("build-mercury") < mercury_job.index("mercury -V") < mercury_job.index("upload-artifact")
    assert "neoaprs/mercury.py" in mercury_job and "name: mercury-${{ matrix.arch }}" in mercury_job and "path: dist-mercury/mercury-*-linux-*.tar.gz" in mercury_job
    for linux in ("appimage", "deb"):
        assert re.search(r"needs: \[[^\]]*\bmercury\b[^\]]*\]", job(linux)), f"{linux} is built from the Mercury of its job"
    assert "name: mercury-amd64" in job("appimage") and "--mercury dist-mercury/mercury-*-linux-x86_64.tar.gz" in job("appimage")
    assert "name: mercury-${{ matrix.arch }}" in job("deb") and "--mercury dist-mercury/mercury-*-linux-*.tar.gz" in job("deb")
    pattern = re.search(r'pattern: "\{([^}]+)\}"', WORKFLOW)
    assert pattern and "mercury" not in pattern.group(1), "the tarballs are build material and not files of the release"


def test_the_macos_app_is_built_with_its_own_mercury_on_a_mac_signed_and_tried_before_it_joins_the_release() -> None:
    macos = job("macos")
    assert "runs-on: macos-latest" in macos and re.search(r"needs: \[verify, wheel\]", macos), "the wheel of the wheel job; Mercury is built in this job (a Mac's build), not taken from the Linux ones"
    assert "scripts/build-mercury --tar --out dist-mercury" in macos and "mercury-$version-macos-arm64.tar.gz" in macos
    assert "scripts/build-macos-app --wheel dist/neoaprs-*.whl --mercury dist-mercury/mercury-*-macos-arm64.tar.gz --out dist-macos" in macos
    assert "scripts/smoke-macos-app dist-macos/NeoAPRS-*.dmg" in macos and "--no-mercury" not in macos
    steps = macos.split("steps:", 1)[1]
    assert steps.index("scripts/build-mercury --tar") < steps.index("scripts/build-macos-app --wheel") < steps.index("scripts/smoke-macos-app dist-macos") < steps.index("upload-artifact")
    assert "name: macos-app" in macos and "path: dist-macos/NeoAPRS-*.dmg" in macos and "hashFiles('scripts/build-macos-app')" in macos
    assert "wc -l | tr -d ' '" in macos, "a Mac's wc pads its count with spaces"
    assert re.search(r"needs: \[[^\]]*\bmacos\b[^\]]*\]", job("assemble")), "the release waits for the app"
    assert "arm64.dmg" in job("assemble").split("notes.md", 1)[1].split("notes.md", 1)[0], "the notes tell a Mac user what to do with the file"


def test_the_package_is_proved_to_need_nothing_of_the_system_for_mercury() -> None:
    deb = job("deb")
    assert "/opt/neoaprs/tools/mercury/mercury -V" in deb and "ALSA_CONFIG_PATH=/opt/neoaprs/tools/mercury/share/alsa/alsa.conf" in deb
    docker = deb.split("docker run", 1)[1]
    assert "debian:bookworm-slim" in docker.split("\n", 1)[0] and "/pkg/*.deb" in docker, "a system that has no libasound2 installs the package"
    assert "dpkg -s libasound2" in docker and "not found" in docker and "lib/libasound.so.2" in docker
    assert 'mercury" -V' in docker and 'mercury" -z' in docker
    smoke = (ROOT / "scripts" / "smoke-appimage").read_text(encoding="utf-8")
    assert "usr/tools/mercury" in smoke and "ALSA_CONFIG_PATH=" in smoke and "neoaprs/mercury.py" in smoke and '"$folder/mercury" -V' in smoke
    assert "smoke-appimage dist-appimage/NeoAPRS-*.AppImage" in job("appimage") and "--no-mercury" not in job("appimage")


def test_mercury_for_windows_is_built_from_the_pinned_source_on_linux_with_the_packages_of_rhizomaticas_own_workflow() -> None:
    built = job("mercury-windows")
    assert "runs-on: ubuntu-latest" in built and "container: debian:trixie" in built, "the container Mercury's own release workflow builds its Windows zip in"
    assert "gcc-mingw-w64-x86-64 mingw-w64-x86-64-dev mingw-w64-common" in built and " patch" in built and "python3" in built, "the cross compiler, its headers and runtime, and patch for the two patches"
    assert "python3 scripts/build-mercury --windows --tar --out dist-mercury-windows" in built
    assert built.index("apt-get install") < built.index("actions/checkout") < built.index("build-mercury --windows") < built.index("file dist-mercury-windows") < built.index("upload-artifact")
    assert "name: mercury-windows" in built and "path: dist-mercury-windows/mercury-*-windows-*.tar.gz" in built and "neoaprs/mercury.py" in built
    assert re.search(r"needs: \[[^\]]*\bmercury-windows\b[^\]]*\]", job("windows")), "the installer is built from the Mercury of that job"
    pattern = re.search(r'pattern: "\{([^}]+)\}"', WORKFLOW)
    assert pattern and "mercury" not in pattern.group(1), "the tarball is build material and not a file of the release"
    assert "WINDOWS_URL" not in WORKFLOW and "Rhizomatica/mercury/releases" not in WORKFLOW, "Rhizomatica's zip is not downloaded any more"


def test_the_windows_job_puts_mercury_in_after_pmtiles_and_checks_it_before_and_after_the_installer() -> None:
    windows = job("windows")
    bundle = "build-venv/Scripts/python.exe packaging/windows/bundle_mercury.py dist/NeoAPRS dist-mercury/mercury-*-windows-x86_64.tar.gz"
    assert windows.index("name: mercury-windows") < windows.index(bundle), "the tarball of the job mercury-windows is downloaded first"
    assert windows.index("bundle_pmtiles.py dist/NeoAPRS") < windows.index(bundle) < windows.index("Smoke test of the app folder") < windows.index("Inno Setup")
    assert "test -f dist/NeoAPRS/bin/mercury/mercury.exe" in windows and "dist/NeoAPRS/bin/mercury/mercury.exe -V" in windows
    folder = windows.split(bundle, 1)[1].split("Smoke test of the app folder", 1)[0]
    assert "build-venv/Scripts/python.exe packaging/windows/smoke_mercury.py dist/NeoAPRS/bin/mercury/mercury.exe" in folder, "the program of the app folder is started and its sockets read"
    installed = windows.split("Install silently, as a user without administrator rights", 1)[1]
    assert "'bin\\mercury\\mercury.exe'" in installed.split("foreach ($l in", 1)[0], "the installer put it in the app folder"
    assert "Programs\\\\NeoAPRS\\\\bin\\\\mercury\\\\mercury.exe\" -V" in installed, "and it starts from there"
    assert 'smoke_mercury.py "$LOCALAPPDATA\\\\Programs\\\\NeoAPRS\\\\bin\\\\mercury\\\\mercury.exe"' in installed, "and listens on 127.0.0.1 only from there"
    assert "bundle_mercury.py dist-e2e/NeoAPRS dist-mercury/mercury-*-windows-x86_64.tar.gz" in windows.split("bundle_pmtiles.py dist-e2e/NeoAPRS", 1)[1].split("neoaprs.exe --version", 1)[0], "the build of the next version for the update test has it too"
    assert r'Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion' in INSTALLER, "the installer packs bin\\mercury with the rest of the folder"


def test_the_installer_has_nothing_to_do_with_the_windows_firewall() -> None:
    """The Mercury it carries binds the loopback, so no rule is added, none is asked for with a prompt of Windows, and none is removed by the uninstaller (a rule an earlier version added stays: a block rule is harmless)."""
    assert not re.search(r"firewall|netsh|runas|ShellExec", INSTALLER.replace("nothing done to the Windows Firewall", ""), re.IGNORECASE), "no firewall, no netsh, no prompt for rights"
    assert "CurUninstallStepChanged" not in INSTALLER and "AddMercury" not in INSTALLER and "PrivilegesRequired=lowest" in INSTALLER


def test_the_windows_programs_do_not_look_like_malware_to_a_virus_scanners_guess() -> None:
    """Windows Defender's machine-learning guess took NeoAPRS for a trojan (Trojan:Win32/Bearfoos!ml, 3 and 4 Nov 2026): the programs are packed with a bootloader compiled for them, not the one of
    PyInstaller's wheel that every packed program shares, and each says what it is in its file properties. (The alert's PowerShell is in tests/test_alerts_runner.py.)"""
    build = WORKFLOW.split("Build environment, from the wheel", 1)[1].split("- name:", 1)[0]
    assert 'PYINSTALLER_COMPILE_BOOTLOADER: "1"' in build and "--no-binary pyinstaller" in build and "pyinstaller==" not in build
    spec = (ROOT / "packaging" / "windows" / "neoaprs.spec").read_text(encoding="utf-8")
    for name in ("neoaprs", "neoaprsw", "neoaprs-app"):
        assert f'name="{name}"' in spec and f'version=version_file("{name}"' in spec, name
    for field in ("CompanyName", "FileDescription", "ProductName", "ProductVersion", "OriginalFilename"):
        assert f'("{field}"' in spec, field
    assert "upx=False" in spec, "no packer over the programs"



def test_every_action_of_every_workflow_is_pinned_by_commit_with_its_tag_beside_it_and_dependabot_proposes_the_moves() -> None:
    """A tag is a name its owner can move to other code, among them the action that runs in every build; a commit is not. The comment says which release the commit is, which is what Dependabot rewrites."""
    for workflow in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        text = workflow.read_text(encoding="utf-8")
        lines = [line.strip() for line in text.splitlines() if re.match(r"\s+(- )?uses:", line)]
        assert lines, workflow.name
        assert all(re.fullmatch(r"(- )?uses: [\w.-]+/[\w./-]+@[0-9a-f]{40} # v\d+\.\d+\.\d+", line) for line in lines), (workflow.name, lines)
    dependabot = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    assert re.search(r'package-ecosystem: "github-actions"\n\s+directory: "/"', dependabot)


def test_the_installers_are_built_from_the_lock_with_every_hash_required() -> None:
    """The lock holds the hash of every file; an installer is built only from files that have it, so a package that PyPI serves changed cannot get into the program."""
    scripts = {name: (ROOT / "scripts" / name).read_text(encoding="utf-8") for name in ("build-appimage", "build-deb", "build-macos-app")}
    for name, text in scripts.items():
        exports = re.findall(r"uv export .*", text)
        installs = [line for line in re.findall(r"uv pip install .*", text) if " -r " in line]
        assert exports and installs, name
        assert all("--frozen" in line and "--no-hashes" not in line for line in exports), (name, exports)
        assert all("--require-hashes" in line for line in installs), (name, installs)
    assert "--no-hashes" not in WORKFLOW
    installs = [line for line in re.findall(r"uv pip install .*", WORKFLOW) if " -r " in line]
    assert installs and all("--require-hashes" in line for line in installs), installs
    assert not [line for line in re.findall(r"uv pip install .*", WORKFLOW) if "-r " not in line and "--no-deps" not in line and "smoke-venv" not in line and "e2e-venv" not in line], "a build installs only with the lock's hashes"
