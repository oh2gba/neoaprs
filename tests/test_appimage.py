"""NeoAPRS inside an AppImage: the runtime mounts the image at a path that is gone when the program ends, so whatever starts NeoAPRS later (the systemd unit, the daemon `neoaprs open` leaves behind, the
start at sign-in) has to start the AppImage file named by `$APPIMAGE`. The pieces of the image itself (AppRun, the desktop entry, the build script's pins) are read as files; the image is built by
scripts/build-appimage in CI and tried by scripts/smoke-appimage."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

from neoaprs.cli import opencmd, servicecmd, servicesystemd
from neoaprs.desktop.autostart import app_command
from neoaprs.paths import default_data_dir
from tests.conftest import ROOT
from tests.support.ptyline import posix_only


class Image:
    """An AppImage as the runtime leaves it: the file, its mount with the interpreter inside, and the two variables."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str = "NeoAPRS-0.1.0-x86_64.AppImage") -> None:
        self.file = tmp_path / "Apps" / name
        self.file.parent.mkdir()
        self.file.write_bytes(b"\x7fELF")
        self.mount = tmp_path / ".mount_NeoAPRSabc"
        (self.mount / "usr" / "bin").mkdir(parents=True)
        python = self.mount / "usr" / "bin" / "python3"
        python.write_bytes(b"")
        monkeypatch.setattr(sys, "executable", str(python))
        monkeypatch.setenv("APPIMAGE", str(self.file))
        monkeypatch.setenv("APPDIR", str(self.mount))


@pytest.fixture
def image(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Image:
    return Image(tmp_path, monkeypatch)


def test_the_file_is_known_only_to_an_interpreter_inside_the_mount(image: Image, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert servicecmd.appimage_file() == str(image.file)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "venv" / "bin" / "python"))       # a leftover $APPIMAGE of the shell this is run from
    assert servicecmd.appimage_file() is None


def test_outside_an_appimage_there_is_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in ("APPIMAGE", "APPDIR"):
        monkeypatch.delenv(name, raising=False)
    assert servicecmd.appimage_file() is None
    monkeypatch.setenv("APPIMAGE", str(tmp_path / "gone.AppImage"))
    monkeypatch.setenv("APPDIR", str(Path(sys.executable).parent))
    assert servicecmd.appimage_file() is None, "a file that is not there is not an AppImage"


def test_the_unit_starts_the_appimage_file_and_not_the_interpreter_in_the_mount(image: Image, tmp_path: Path) -> None:
    plan = servicecmd.make_plan(servicecmd.parser().parse_args(["install", "--data", str(tmp_path / "data")]))
    exec_start = next(line for line in servicesystemd.render(plan).splitlines() if line.startswith("ExecStart="))
    assert exec_start == f"ExecStart={image.file} --data {tmp_path}/data"


def test_a_path_with_a_space_is_quoted_in_the_unit(tmp_path: Path) -> None:
    plan = servicecmd.Plan("/mnt/usr/bin/python3", tmp_path / "data", appimage="/home/u/My Apps/NeoAPRS.AppImage")
    assert 'ExecStart="/home/u/My Apps/NeoAPRS.AppImage" --data ' in servicesystemd.render(plan)


def test_the_detached_daemon_is_a_run_of_the_appimage(image: Image, tmp_path: Path) -> None:
    assert opencmd.daemon_argv(tmp_path / "data") == [str(image.file), "run", "--data", str(tmp_path / "data")]


def test_start_at_sign_in_is_the_appimage_in_the_tray(image: Image, tmp_path: Path) -> None:
    assert app_command(default_data_dir(), "linux") == [str(image.file), "app", "--tray"]
    assert app_command(tmp_path / "d", "linux") == [str(image.file), "app", "--tray", "--data", str(tmp_path / "d")]
    assert app_command(tmp_path / "d", "linux", appimage=lambda: None)[0] != str(image.file)


@posix_only
def test_apprun_starts_the_app_without_arguments_and_the_command_with_them(tmp_path: Path) -> None:
    here = tmp_path / "AppDir"
    (here / "usr" / "bin").mkdir(parents=True)
    (here / "AppRun").write_bytes((ROOT / "packaging" / "appimage" / "AppRun").read_bytes())
    (here / "AppRun").chmod(0o755)
    fake = here / "usr" / "bin" / "python3"
    fake.write_text('#!/bin/sh\nprintf "%s|" "$@"\n', encoding="utf-8")
    fake.chmod(0o755)

    def run(*args: str) -> str:
        return subprocess.run([str(here / "AppRun"), *args], capture_output=True, text=True, check=True).stdout

    assert run() == "-I|-m|neoaprs|app|"
    assert run("doctor") == "-I|-m|neoaprs|doctor|"
    assert run("--data", "a b", "--web-port", "0") == "-I|-m|neoaprs|--data|a b|--web-port|0|"
    link = tmp_path / "link"
    link.symlink_to(here / "AppRun")
    assert subprocess.run([str(link), "--version"], capture_output=True, text=True, check=True).stdout == "-I|-m|neoaprs|--version|", "AppRun finds the image through a link"


def test_the_desktop_entry_names_the_icon_the_build_makes_and_runs_apprun() -> None:
    entry = dict(line.split("=", 1) for line in (ROOT / "packaging" / "appimage" / "neoaprs.desktop").read_text(encoding="utf-8").splitlines() if "=" in line)
    assert entry["Exec"] == "AppRun" and entry["Icon"] == "neoaprs" and entry["Type"] == "Application" and entry["Terminal"] == "false"
    assert re.fullmatch(r"([A-Za-z]+;)+", entry["Categories"])
    assert "/neoaprs.png" in (ROOT / "scripts" / "build-appimage").read_text(encoding="utf-8")


def test_every_download_of_the_build_is_pinned_by_version_and_digest() -> None:
    script = (ROOT / "scripts" / "build-appimage").read_text(encoding="utf-8")
    urls = dict(re.findall(r'^(\w+)_URL="([^"]+)"', script, re.M))
    digests = dict(re.findall(r'^(\w+)_SHA256="([0-9a-f]{64})"', script, re.M))
    assert set(urls) == set(digests) == {"PYTHON", "TOOL", "RUNTIME"}
    for name, url in urls.items():
        assert url.startswith("https://github.com/") and "/latest/" not in url and "continuous" not in url, f"{name} is not a fixed release: {url}"
        assert re.search(r"/download/[^/]*\d[^/]*/", url), f"{name} names no version: {url}"
