"""The release's own files, as far as a test can see them without GitHub or a Windows machine: the notes taken out of the changelog, the install script's template rendered and read by `sh -n`, the workflow's
pins and permissions, the Windows installer script's promises (per user, the tasks, the uninstaller), the bundled pmtiles that the program looks for first, and the bundled Mercury (the job that builds it, the Windows script that unpacks it, what the Linux jobs prove of it). The whole of it is run by `.github/workflows/release.yml`."""
import hashlib
import importlib.util
import io
import re
import subprocess
import sys
import types
import zipfile
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
    assert len(uploads) == 9 and all("overwrite: true" in block for block in uploads), f"an attempt that is run again uploads the same names: {uploads}"
    assemble = WORKFLOW.split("\n  assemble:\n", 1)[1].split("\n  release:\n", 1)[0]
    pattern = re.search(r'pattern: "\{([^}]+)\}"', assemble)
    assert pattern and set(pattern.group(1).split(",")) == {"dist", "windows-installer", "appimage", "deb-amd64", "deb-arm64", "install-script"}, "the release's six artifacts and no other"
    release_job = WORKFLOW.split("\n  release:\n", 1)[1]
    assert "--draft " in release_job and "--draft=false" in release_job, "a draft until every file is on it"
    assert "gh release view" in release_job and "--clobber" in release_job, "a release that is there is written over, not refused"
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


def test_the_release_has_the_installer_and_the_appimage_under_fixed_names_too() -> None:
    """The project page links to releases/latest/download/NeoAPRS-Setup.exe and NeoAPRS-x86_64.AppImage: one click, the newest, nothing between."""
    assemble = WORKFLOW.split("name: SHA256SUMS and the notes", 1)[1].split("uses: actions/upload-artifact", 1)[0]
    assert 'cp -- "NeoAPRS-Setup-$version.exe" NeoAPRS-Setup.exe' in assemble and 'cp -- "NeoAPRS-$version-x86_64.AppImage" NeoAPRS-x86_64.AppImage' in assemble
    assert assemble.index("NeoAPRS-Setup.exe") < assemble.index("sha256sum"), "the copies are in SHA256SUMS"
    assert '[ "$(ls | wc -l)" = 9 ]' in assemble


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


def test_the_wheel_and_the_sdist_are_named_by_the_pep_440_form_of_the_version_and_the_other_files_by_the_version_as_written() -> None:
    assert "from neoaprs.updateasset import wheel_version" in WORKFLOW
    assert WORKFLOW.count("wheel_version=\"$(python3 -c") == 3, "the wheel job, the install script and the assembling of the release each ask for the name once"
    assert 'neoaprs-$version-py3-none-any.whl' not in WORKFLOW and 'neoaprs-$version.tar.gz' not in WORKFLOW, "the raw version is not the wheel's"
    wheel_job = WORKFLOW.split("\n  wheel:\n", 1)[1].split("\n  windows:\n", 1)[0]
    assert 'dist/neoaprs-$wheel_version-py3-none-any.whl' in wheel_job and 'dist/neoaprs-$wheel_version.tar.gz' in wheel_job
    assert 'releases/download/v$version/neoaprs-$wheel_version-py3-none-any.whl' in WORKFLOW, "the tag has the version as written, the file the PEP 440 form"
    assert '"neoaprs-$wheel_version-py3-none-any.whl" "neoaprs-$wheel_version.tar.gz" "NeoAPRS-Setup-$version.exe" "NeoAPRS-$version-x86_64.AppImage" "neoaprs_${version}_amd64.deb"' in WORKFLOW


def job(name: str) -> str:
    """The text of one job of the workflow, from its key to the next job's."""
    return re.split(r"\n  [\w-]+:\n", WORKFLOW.split(f"\n  {name}:\n", 1)[1], maxsplit=1)[0]


def test_mercury_is_built_for_both_architectures_in_the_oldest_system_and_the_linux_downloads_wait_for_it() -> None:
    mercury_job = job("mercury")
    assert "arch: amd64\n            runner: ubuntu-latest" in mercury_job and "arch: arm64\n            runner: ubuntu-24.04-arm" in mercury_job
    assert "container: ubuntu:22.04" in mercury_job, "glibc 2.35, the floor the AppImage and the .deb document"
    assert "python3 scripts/build-mercury --tar --out dist-mercury" in mercury_job, "run by the Python 3.10 of the container"
    assert "build-essential pkg-config libasound2-dev libasound2-data python3" in mercury_job
    assert mercury_job.index("apt-get install") < mercury_job.index("actions/checkout") < mercury_job.index("build-mercury") < mercury_job.index("mercury -V") < mercury_job.index("upload-artifact")
    assert "neoaprs/mercury.py" in mercury_job and "name: mercury-${{ matrix.arch }}" in mercury_job and "path: dist-mercury/mercury-*-linux-*.tar.gz" in mercury_job
    for linux in ("appimage", "deb"):
        assert re.search(r"needs: \[[^\]]*\bmercury\b[^\]]*\]", job(linux)), f"{linux} is built from the Mercury of its job"
    assert "name: mercury-amd64" in job("appimage") and "--mercury dist-mercury/mercury-*-linux-x86_64.tar.gz" in job("appimage")
    assert "name: mercury-${{ matrix.arch }}" in job("deb") and "--mercury dist-mercury/mercury-*-linux-*.tar.gz" in job("deb")
    pattern = re.search(r'pattern: "\{([^}]+)\}"', WORKFLOW)
    assert pattern and "mercury" not in pattern.group(1), "the tarballs are build material and not files of the release"


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


def test_the_windows_job_puts_mercury_in_after_pmtiles_and_checks_it_before_and_after_the_installer() -> None:
    windows = job("windows")
    bundle = "build-venv/Scripts/python.exe packaging/windows/bundle_mercury.py dist/NeoAPRS"
    assert windows.index("bundle_pmtiles.py dist/NeoAPRS") < windows.index(bundle) < windows.index("Smoke test of the app folder") < windows.index("Inno Setup")
    assert "test -f dist/NeoAPRS/bin/mercury/mercury.exe" in windows and "dist/NeoAPRS/bin/mercury/mercury.exe -V" in windows
    installed = windows.split("Install silently, as a user without administrator rights", 1)[1]
    assert "'bin\\mercury\\mercury.exe'" in installed.split("foreach ($l in", 1)[0], "the installer put it in the app folder"
    assert "Programs\\\\NeoAPRS\\\\bin\\\\mercury\\\\mercury.exe\" -V" in installed, "and it starts from there, its DLLs beside it"
    assert "bundle_mercury.py dist-e2e/NeoAPRS" in windows.split("bundle_pmtiles.py dist-e2e/NeoAPRS", 1)[1].split("neoaprs.exe --version", 1)[0], "the build of the next version for the update test has it too"
    assert r'Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion' in INSTALLER, "the installer packs bin\\mercury with the rest of the folder"


def load_bundle_mercury() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("bundle_mercury", ROOT / "packaging" / "windows" / "bundle_mercury.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def release_zip(path: Path, licence: bool = True) -> None:
    names = {"mercury-1.9.21/mercury.exe": b"MZ exe", "mercury-1.9.21/mercury-ui.exe": b"MZ ui", "mercury-1.9.21/mercury.ini.example": b"[x]", "mercury-1.9.21/libhamlib-4.dll": b"MZ dll", "mercury-1.9.21/libusb-1.0.dll": b"MZ dll2"}
    if licence:
        names["mercury-1.9.21/LICENSE"] = b"GPL text"
    with zipfile.ZipFile(path, "w") as z:
        for name, data in names.items():
            z.writestr(name, data)


def test_bundle_mercury_takes_its_address_and_pins_from_the_program_and_writes_none_of_its_own() -> None:
    source = (ROOT / "packaging" / "windows" / "bundle_mercury.py").read_text(encoding="utf-8")
    assert "from neoaprs import mercury" in source and "mercury.WINDOWS_URL" in source and "mercury.WINDOWS_SHA256" in source and "mercury.WINDOWS_SIZE" in source
    assert "https://" not in source and "http://" not in source and not re.search(r"\b[0-9a-f]{64}\b", source), "the pins are in neoaprs/mercury.py and nowhere else"


def test_bundle_mercury_puts_the_exe_the_dlls_and_the_licence_in_bin_mercury_and_leaves_the_ui_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from neoaprs import mercury
    module = load_bundle_mercury()
    asked: list[tuple[str, str, int]] = []

    def fake_download(url: str, target: Path, sha256: str, size: int) -> None:
        asked.append((url, sha256, size))
        release_zip(target)

    monkeypatch.setattr(module, "download", fake_download)
    monkeypatch.setattr(sys, "argv", ["bundle_mercury.py", str(tmp_path / "NeoAPRS")])
    assert module.main() == 0
    assert asked == [(mercury.WINDOWS_URL, mercury.WINDOWS_SHA256, mercury.WINDOWS_SIZE)]
    folder = tmp_path / "NeoAPRS" / "bin" / "mercury"
    assert sorted(p.name for p in folder.iterdir()) == ["LICENSE", "libhamlib-4.dll", "libusb-1.0.dll", "mercury.exe"], "no mercury-ui.exe, no example configuration, no folder of the zip's"
    assert (folder / "mercury.exe").read_bytes() == b"MZ exe" and (folder / "LICENSE").read_bytes() == b"GPL text"
    out = capsys.readouterr().out
    assert "mercury.exe (6 bytes)" in out and "libhamlib-4.dll" in out
    (folder / "stale.dll").write_bytes(b"old")
    assert module.main() == 0 and not (folder / "stale.dll").exists(), "a folder of an earlier run is made again, not added to"


def test_bundle_mercury_writes_a_licence_text_of_its_own_when_the_zip_has_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from neoaprs import mercury
    module = load_bundle_mercury()
    monkeypatch.setattr(module, "download", lambda url, target, sha256, size: release_zip(target, licence=False))
    monkeypatch.setattr(sys, "argv", ["bundle_mercury.py", str(tmp_path)])
    assert module.main() == 0
    text = (tmp_path / "bin" / "mercury" / "LICENSE.txt").read_text(encoding="utf-8")
    assert "GPL-3.0-or-later" in text and mercury.SOURCE_URL in text
    assert "no LICENSE file" in capsys.readouterr().out, "it says that it did"


def test_bundle_mercury_refuses_a_zip_without_the_exe_and_keeps_nothing_of_a_download_that_is_not_the_pinned_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_bundle_mercury()
    empty = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty, "w") as z:
        z.writestr("readme.txt", b"x")
    with pytest.raises(SystemExit, match=r"mercury\.exe is not in the zip"):
        module.unpack(empty, tmp_path)

    class Response:
        headers: dict[str, str] = {}

        def __init__(self, body: bytes) -> None:
            self.body = io.BytesIO(body)

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def read(self, n: int) -> bytes:
            return self.body.read(n)

    body = b"not the release" * 100
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda request, timeout: Response(body))
    target = tmp_path / "download"
    with pytest.raises(SystemExit, match="not the pinned"):
        module.download("https://example.invalid/m.zip", target, hashlib.sha256(b"other").hexdigest(), len(body))
    assert not target.exists(), "nothing is kept on a digest that is not the pinned one"
    with pytest.raises(SystemExit, match="longer than the pinned"):
        module.download("https://example.invalid/m.zip", target, hashlib.sha256(body).hexdigest(), len(body) - 1)
    assert not target.exists(), "nor of a download that is longer than the pinned size"
    module.download("https://example.invalid/m.zip", target, hashlib.sha256(body).hexdigest(), len(body))
    assert target.read_bytes() == body
