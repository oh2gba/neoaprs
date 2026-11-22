"""Tests for the build of the AppImage web window libraries (scripts/build-gi) without a compiler,
docker or the network: pins, the carried libraries, refusal of a wrong download, and the link check.
"""

import hashlib
import importlib.machinery
import importlib.util
import io
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from neoaprs.desktop import gtkenv
from tests.conftest import ROOT

SCRIPT = ROOT / "scripts" / "build-gi"


@pytest.fixture(scope="module")
def build() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("build_gi", str(SCRIPT))
    spec = importlib.util.spec_from_loader("build_gi", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_pygobject_is_the_pinned_3_50_2_and_meson_a_fixed_version(build: ModuleType) -> None:
    assert (
        build.GI_VERSION == "3.50.2"
        and build.PYGOBJECT_URL.endswith("/pygobject-3.50.2.tar.gz")
        and build.PYGOBJECT_URL.startswith("https://files.pythonhosted.org/")
    )
    assert build.PYGOBJECT_SHA256 == "ece6b860aab77cb649fdfc6e88d8a83765e7a62f7ffd39a628d6e2a0d397a7ff", (
        "the digest of PyPI's file (aprs-reference/window-plan.md, 2.3)"
    )
    assert re.search(r"/meson-\d+\.\d+\.\d+-py3-none-any\.whl$", build.MESON_URL) and build.MESON_URL.startswith(
        "https://"
    )
    assert build.MESON_SHA256 == "" or build.pinned(build.MESON_SHA256), (
        "Meson's pin is a whole digest, or not there yet (and then the build refuses to run)"
    )
    assert build.IMAGE == "ubuntu:22.04", "the glibc of the AppImage's floor, as Mercury's build"


def test_the_build_takes_the_carried_libraries_from_gtkenv_and_the_cpython_from_the_appimages_build(
    build: ModuleType,
) -> None:
    assert build.carried_libraries() == gtkenv.LIBRARIES
    appimage = (ROOT / "scripts" / "build-appimage").read_text(encoding="utf-8")
    url, digest = build.python_pin()
    assert f'PYTHON_URL="{url}"' in appimage and f'PYTHON_SHA256="{digest}"' in appimage
    assert build.TRAY_TYPELIBS == (gtkenv.TRAY_TYPELIB,) and build.WEBKIT_TYPELIBS[0] == gtkenv.WEBKIT_TYPELIB
    assert build.tarball_name() == "gi-3.50.2-linux-x86_64.tar.gz"


def test_a_build_without_the_meson_pin_refuses_to_run(
    build: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(build, "MESON_SHA256", "")
    assert build.main(["--out", "nowhere"]) == 2 and "MESON_SHA256 is not pinned" in capsys.readouterr().err
    with pytest.raises(build.BuildError, match="no pinned SHA-256"):
        build.fetch(build.MESON_URL, "")


def test_a_download_that_is_not_the_pinned_file_is_refused_and_not_kept(
    build: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("NEOAPRS_BUILD_CACHE", str(tmp_path))
    monkeypatch.setattr(build.urllib.request, "urlopen", lambda request, timeout: io.BytesIO(b"another file"))
    with pytest.raises(build.BuildError, match="is not the file with SHA-256"):
        build.fetch(build.PYGOBJECT_URL, build.PYGOBJECT_SHA256)
    assert list(tmp_path.iterdir()) == []
    good = b"the pinned file"
    digest = hashlib.sha256(good).hexdigest()
    monkeypatch.setattr(build.urllib.request, "urlopen", lambda request, timeout: io.BytesIO(good))
    file = build.fetch("https://example.org/a/pinned-1.0.tar.gz", digest)
    assert file == tmp_path / "pinned-1.0.tar.gz" and file.read_bytes() == good
    monkeypatch.setattr(
        build.urllib.request,
        "urlopen",
        lambda request, timeout: pytest.fail("the cached file is the pinned one: nothing is fetched"),
    )
    assert build.fetch("https://example.org/a/pinned-1.0.tar.gz", digest) == file


def test_the_link_check_refuses_what_a_desktop_with_webkitgtk_may_not_have(
    build: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    lib = tmp_path / "libayatana-appindicator3.so.1"
    gi = tmp_path / "_gi.cpython-313-x86_64-linux-gnu.so"
    names: dict[str, list[str]] = {
        lib.name: [
            "libgtk-3.so.0",
            "libgdk-3.so.0",
            "libgobject-2.0.so.0",
            "libglib-2.0.so.0",
            "libdbusmenu-gtk3.so.4",
            "libdbusmenu-glib.so.4",
            "libayatana-indicator3.so.7",
            "libc.so.6",
        ],
        gi.name: [
            "libgirepository-1.0.so.1",
            "libgobject-2.0.so.0",
            "libglib-2.0.so.0",
            "libffi.so.8",
            "libpthread.so.0",
            "libc.so.6",
        ],
    }
    monkeypatch.setattr(build, "needed", lambda path: names[path.name])
    lines = build.check_links([gi, lib], gtkenv.LIBRARIES)
    assert lines[0].startswith("_gi.cpython-313-x86_64-linux-gnu.so: libgirepository-1.0.so.1") and len(lines) == 2
    for extra in ("libwebkit2gtk-4.1.so.0", "libpython3.13.so.1.0", "libcairo-script-interpreter.so.2", "libssl.so.3"):
        names[lib.name] = [*names[lib.name], extra]
        with pytest.raises(build.BuildError, match=re.escape(extra)):
            build.check_links([gi, lib], gtkenv.LIBRARIES)
        names[lib.name].pop()


def test_readelfs_needed_lines_are_read(build: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    out = (
        " 0x0000000000000001 (NEEDED)             Shared library: [libgirepository-1.0.so.1]\n"
        " 0x0000000000000001 (NEEDED)             Shared library: [libc.so.6]\n"
        " 0x000000000000000e (SONAME)             Library soname: [_gi.so]\n"
    )
    calls: list[Any] = []
    monkeypatch.setattr(build, "run", lambda command, env=None: calls.append(command) or out)
    # (the path as the system writes it)
    assert build.needed(Path("/x/_gi.so")) == ["libgirepository-1.0.so.1", "libc.so.6"] and calls == [
        ["readelf", "-d", str(Path("/x/_gi.so"))]
    ]


def test_the_usage_prints() -> None:
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"], check=False, capture_output=True, text=True, timeout=60
    )
    assert done.returncode == 0 and "usage: build-gi" in done.stdout
    for option in ("--docker", "--out", "--source"):
        assert option in done.stdout


def test_the_output_folder_of_the_docker_build_is_given_back_whether_the_build_ends_well_or_not(
    build: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[list[str]] = []
    monkeypatch.setattr(build.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(build, "cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(
        build.subprocess,
        "run",
        lambda command, check=False: seen.append(command) or subprocess.CompletedProcess(command, 0),
    )
    assert build.in_docker(tmp_path / "out", None) == 0
    script = seen[0][-1]
    assert re.search(r"set -e; trap 'chown -R \d+:\d+ /out' EXIT;", script) and "; chown" not in script
