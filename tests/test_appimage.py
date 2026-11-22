"""Tests for the AppImage packaging: whatever starts NeoAPRS later must start the file named by
`$APPIMAGE`, not the mount point. AppRun, the desktop entry and the build pins are read as files.
"""
import importlib.machinery
import os
import re
import subprocess
import sys
import tomllib
import types
from pathlib import Path

import pytest

from neoaprs.cli import opencmd, servicecmd, servicesystemd
from neoaprs.desktop import gtkenv
from neoaprs.desktop.autostart import app_command
from neoaprs.paths import default_data_dir
from tests.conftest import ROOT
from tests.support.ptyline import posix_only


class Image:
    """An AppImage as the runtime leaves it: the file, its mount with the interpreter inside, and
    the two variables."""

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
    # a leftover $APPIMAGE of the shell this is run from
    monkeypatch.setattr(sys, "executable", str(tmp_path / "venv" / "bin" / "python"))
    assert servicecmd.appimage_file() is None


def test_outside_an_appimage_there_is_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in ("APPIMAGE", "APPDIR"):
        monkeypatch.delenv(name, raising=False)
    assert servicecmd.appimage_file() is None
    monkeypatch.setenv("APPIMAGE", str(tmp_path / "gone.AppImage"))
    monkeypatch.setenv("APPDIR", str(Path(sys.executable).parent))
    assert servicecmd.appimage_file() is None, "a file that is not there is not an AppImage"


# an AppImage is a Linux thing (and Windows spells the temporary folder two ways)
@posix_only
def test_the_unit_starts_the_appimage_file_and_not_the_interpreter_in_the_mount(image: Image, tmp_path: Path) -> None:
    plan = servicecmd.make_plan(servicecmd.parser().parse_args(["install", "--data", str(tmp_path / "data")]))
    exec_start = next(line for line in servicesystemd.render(plan).splitlines() if line.startswith("ExecStart="))
    assert exec_start == f"ExecStart={image.file} --data {tmp_path}/data"


def test_a_path_with_a_space_is_quoted_in_the_unit(tmp_path: Path) -> None:
    plan = servicecmd.Plan("/mnt/usr/bin/python3", tmp_path / "data", appimage="/home/u/My Apps/NeoAPRS.AppImage")
    assert 'ExecStart="/home/u/My Apps/NeoAPRS.AppImage" --data ' in servicesystemd.render(plan)


# an AppImage is a Linux thing (and Windows spells the temporary folder two ways)
@posix_only
def test_the_detached_daemon_is_a_run_of_the_appimage(image: Image, tmp_path: Path) -> None:
    assert opencmd.daemon_argv(tmp_path / "data") == [str(image.file), "run", "--data", str(tmp_path / "data")]


# an AppImage is a Linux thing (and Windows spells the temporary folder two ways)
@posix_only
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


def build(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(ROOT / "scripts" / "build-appimage"), *args], capture_output=True, text=True, timeout=30)


def test_the_build_puts_mercury_at_usr_tools_without_its_simulators_after_the_cleanup_of_usr_bin() -> None:
    script = (ROOT / "scripts" / "build-appimage").read_text(encoding="utf-8")
    unpack = 'tar -xzf "$mercury" -C "$app/usr/tools" --exclude=\'mercury/dev\''
    assert unpack in script and script.index('find "$app/usr/bin" -xtype l -delete') < script.index(unpack) < script.index("prune.py")
    assert "mercury/$needed" in script and "lib/libasound.so.2 share/alsa/alsa.conf" in script, "a tarball without the program, its ALSA library and configuration is refused"
    assert not re.search(r"^MERCURY\w*_URL=", script, re.M), "no download was added: the tarball comes in"


@posix_only
def test_a_build_without_mercury_must_say_so(tmp_path: Path) -> None:
    refused = build("--out", str(tmp_path / "out"))
    assert refused.returncode == 2 and "--mercury TARBALL" in refused.stderr and "--no-mercury" in refused.stderr, "a release can never silently lack Mercury"
    tarball = tmp_path / "mercury-1.9.24-linux-x86_64.tar.gz"
    tarball.write_bytes(b"")
    both = build("--mercury", str(tarball), "--no-mercury")
    assert both.returncode == 2 and "exclude each other" in both.stderr
    wrong = tmp_path / "mercury-1.9.24-linux-aarch64.tar.gz"
    wrong.write_bytes(b"")
    arm = build("--mercury", str(wrong))
    assert arm.returncode == 2 and "x86_64" in arm.stderr, "the program is for the machine the AppImage is for"
    assert build("--mercury", str(tmp_path / "gone.tar.gz")).returncode == 2


def test_the_smoke_test_runs_the_bundled_mercury_unless_told_that_there_is_none() -> None:
    smoke = (ROOT / "scripts" / "smoke-appimage").read_text(encoding="utf-8")
    assert "--no-mercury) with_mercury=0" in smoke and "usr/tools/mercury" in smoke
    assert "--no-direwolf) with_direwolf=0" in smoke and "usr/tools/direwolf" in smoke, "and the bundled Direwolf, unless told that there is none"


# ---- the trial of the web window (scripts/build-appimage --window web): never a release

@posix_only
def test_the_trial_of_the_web_window_needs_the_gi_tarball_and_only_it(tmp_path: Path) -> None:
    gi = tmp_path / "gi-3.50.2-linux-x86_64.tar.gz"
    gi.write_bytes(b"")
    refused = build("--no-mercury", "--window", "web", "--out", str(tmp_path / "out"))
    assert refused.returncode == 2 and "--window web needs --gi TARBALL" in refused.stderr
    assert "--gi is for --window web" in build("--no-mercury", "--gi", str(gi)).stderr
    other = tmp_path / "mercury-1.9.24-linux-x86_64.tar.gz"
    other.write_bytes(b"")
    assert "is not the gi tarball" in build("--no-mercury", "--window", "web", "--gi", str(other)).stderr
    assert build("--no-mercury", "--window", "gtk").returncode == 2


@posix_only
def test_the_trial_must_say_whether_it_carries_direwolf_too_and_cannot_carry_it_without_mercury(tmp_path: Path) -> None:
    gi = tmp_path / "gi-3.50.2-linux-x86_64.tar.gz"
    gi.write_bytes(b"")
    direwolf = tmp_path / "direwolf-1.8.1-linux-x86_64.tar.gz"
    direwolf.write_bytes(b"")
    unsaid = build("--no-mercury", "--window", "web", "--gi", str(gi), "--out", str(tmp_path / "out"))
    assert unsaid.returncode == 2 and "--direwolf TARBALL" in unsaid.stderr, "the rules of a release's file hold for the trial's too"
    alone = build("--no-mercury", "--direwolf", str(direwolf), "--window", "web", "--gi", str(gi), "--out", str(tmp_path / "out"))
    assert alone.returncode == 2 and "--direwolf needs --mercury" in alone.stderr
    script = (ROOT / "scripts" / "build-appimage").read_text(encoding="utf-8")
    assert "(--direwolf TARBALL | --no-direwolf) [--wheel FILE] [--out DIR] [--window web --gi TARBALL]" in script


def test_the_trial_is_a_file_of_its_own_name_with_no_qt_and_the_gi_tarballs_pieces_where_gtkenv_looks() -> None:
    script = (ROOT / "scripts" / "build-appimage").read_text(encoding="utf-8")
    assert 'target="$out/NeoAPRS-$version-web-x86_64.AppImage"' in script and 'out="$ROOT/build/appimage-web"' in script, "never the name Update now and the release know"
    assert 'prune.py" --python-only "$app/usr"' in script and "AppRun-web" in script
    assert 'mv "$work/neoaprs-gtk" "$app/usr/lib/neoaprs-gtk"' in script and 'site-packages/gi"' in script
    assert gtkenv.CARRIED.parts[-2:] == ("lib", "neoaprs-gtk"), "where the image puts what gtkenv loads"
    (summary,) = [line for line in script.splitlines() if line.startswith('echo "build-appimage: $target (')]
    assert summary.endswith('else echo none; fi)$(if [ "$window" = web ]; then echo "; window: web"; fi))"'), "the Qt build's last line is as it was; only the trial's says so"


@posix_only
def test_apprun_of_the_trial_asks_for_the_web_window_and_keeps_a_value_given(tmp_path: Path) -> None:
    here = tmp_path / "AppDir"
    (here / "usr" / "bin").mkdir(parents=True)
    (here / "AppRun").write_bytes((ROOT / "packaging" / "appimage" / "AppRun-web").read_bytes())
    (here / "AppRun").chmod(0o755)
    fake = here / "usr" / "bin" / "python3"
    fake.write_text('#!/bin/sh\nprintf "%s|%s|" "$NEOAPRS_WINDOW" "$*"\n', encoding="utf-8")
    fake.chmod(0o755)
    environ = {k: v for k, v in os.environ.items() if k != "NEOAPRS_WINDOW"}
    run = lambda *args, **extra: subprocess.run([str(here / "AppRun"), *args], capture_output=True, text=True, check=True, env={**environ, **extra}).stdout  # noqa: E731
    assert run() == "web|-I -m neoaprs app|"
    assert run("doctor") == "web|-I -m neoaprs doctor|"
    assert run(NEOAPRS_WINDOW="qt") == "qt|-I -m neoaprs app|"
    assert "QTWEBENGINE" not in (ROOT / "packaging" / "appimage" / "AppRun-web").read_text(encoding="utf-8")


def load_weblock() -> types.ModuleType:
    loader = importlib.machinery.SourceFileLoader("weblock", str(ROOT / "packaging" / "appimage" / "weblock.py"))
    weblock = types.ModuleType("weblock")
    loader.exec_module(weblock)
    return weblock


# (a digest of the right shape: the real one is PyPI's, filled in before the first build)
DIGEST = "ab" * 32


def test_the_web_windows_packages_are_the_locked_ones_with_the_digests_of_the_files_that_run_in_the_image() -> None:
    weblock = load_weblock()
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    lines = weblock.requirements(lock, {"pillow": (weblock.PILLOW_URL, DIGEST)})
    assert [re.split(r"==| @ ", line)[0] for line in lines] == list(weblock.PACKAGES) and "python-xlib" not in weblock.PACKAGES
    assert any(line.startswith("pywebview==6.2.1 --hash=sha256:") for line in lines) and any(line.startswith("pystray==0.19.5 ") for line in lines)
    assert all(re.fullmatch(r"[\w-]+==[\w.]+( --hash=sha256:[0-9a-f]{64})+|[\w-]+ @ https://\S+\.whl --hash=sha256:[0-9a-f]{64}", line) for line in lines)
    with pytest.raises(SystemExit, match="no pywebview"):
        weblock.requirements({"package": [p for p in lock["package"] if p["name"] != "pywebview"]}, {"pillow": (weblock.PILLOW_URL, DIGEST)})


def test_pillow_comes_as_its_pinned_linux_wheel_never_from_the_locks_windows_wheels_or_its_sdist() -> None:
    weblock = load_weblock()
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    (pillow,) = [line for line in weblock.requirements(lock, {"pillow": (weblock.PILLOW_URL, DIGEST)}) if line.startswith("pillow")]
    assert pillow == f"pillow @ {weblock.PILLOW_URL} --hash=sha256:{DIGEST}" and re.search(r"-cp313-cp313-manylinux[\w.]*_x86_64\.whl$", weblock.PILLOW_URL)
    (locked,) = [p for p in lock["package"] if p["name"] == "pillow"]
    assert weblock.PILLOW_URL.rsplit("/", 1)[1].startswith(f"pillow-{locked['version']}-"), "the pin is uv.lock's version"
    assert weblock.PILLOW_SHA256 == "" or re.fullmatch(r"[0-9a-f]{64}", weblock.PILLOW_SHA256), "a whole digest, or not there yet (and then the build refuses to run)"
    with pytest.raises(SystemExit, match="not pinned yet"):
        weblock.requirements(lock, {"pillow": (weblock.PILLOW_URL, "")})
    with pytest.raises(SystemExit, match="no wheel of pillow 13.0.0 .* for the image"):
        # (the lock's own files of Pillow: Windows and iOS wheels and an sdist, none of them for the
        # image)
        weblock.requirements(lock, {})
    with pytest.raises(SystemExit, match="is not pillow 13.0.0"):
        weblock.requirements(lock, {"pillow": (weblock.PILLOW_URL.replace("x86_64", "aarch64"), DIGEST)})


def test_only_proxy_tools_may_come_as_an_sdist_and_every_other_package_is_installed_from_wheels_only() -> None:
    weblock = load_weblock()
    assert weblock.binary() == [name for name in weblock.PACKAGES if name != "proxy-tools"]
    assert weblock.runs_here("six-1.17.0-py2.py3-none-any.whl") and weblock.runs_here("pillow-13.0.0-cp313-cp313-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl")
    assert not weblock.runs_here("pillow-13.0.0-cp313-cp313-win_amd64.whl") and not weblock.runs_here("pillow-13.0.0-cp314-cp314-manylinux_2_28_x86_64.whl")
    assert not weblock.runs_here("pillow-13.0.0-cp313-cp313-musllinux_1_2_x86_64.whl") and not weblock.runs_here("pillow-13.0.0.tar.gz")
    sdist_only = {"package": [{"name": name, "version": "1.0", "sdist": {"hash": "sha256:" + "cd" * 32}} for name in weblock.PACKAGES]}
    with pytest.raises(SystemExit, match="no wheel of pywebview"):
        weblock.requirements(sdist_only, {})
    script = (ROOT / "scripts" / "build-appimage").read_text(encoding="utf-8")
    assert 'weblock.py" --binary)"' in script and '--no-deps "${wheels_only[@]}" -r "$work/requirements-web.txt"' in script


# ---- what the build takes out (packaging/appimage/prune.py) on a made-up tree

def needs(*names: str) -> bytes:
    """A made-up ELF file that names the libraries it loads, as the real ones do in their dynamic
    section."""
    return b"\x7fELF" + b"\0".join(name.encode() for name in names) + b"\0"


def linux_tree(usr: Path, qt: bool = True) -> Path:
    lib = usr / "lib" / "python3.13"
    files: dict[str, bytes] = {
        "bin/python3.13": needs("libc.so.6"), "bin/python3.13-config": b"#!/bin/sh\n", "lib/libpython3.13.so": needs("libc.so.6"), "lib/libpython3.13.so.1.0": needs("libc.so.6"),
        "lib/python3.13/os.py": b"", "lib/python3.13/dbm/__init__.py": b"", "lib/python3.13/lib-dynload/_dbm.cpython-313-x86_64-linux-gnu.so": needs("libc.so.6"),
        "lib/python3.13/lib-dynload/_ssl.cpython-313-x86_64-linux-gnu.so": needs("libc.so.6"), "lib/python3.13/lib-dynload/_tkinter.cpython-313-x86_64-linux-gnu.so": needs("libtcl9.0.so"),
        "lib/python3.13/site-packages/tornado/web.py": b"", "lib/python3.13/site-packages/tornado/speedups.pyi": b"",
        "lib/python3.13/site-packages/cryptography/hazmat/bindings/_rust/__init__.pyi": b"", "lib/python3.13/site-packages/cryptography/hazmat/bindings/_rust.abi3.so": needs("libc.so.6"),
        "lib/python3.13/site-packages/pydantic_core/core_schema.py": b"", "lib/python3.13/site-packages/pydantic_core/_pydantic_core.pyi": b"",
    }
    if qt:
        qt_dir = "lib/python3.13/site-packages/PySide6/Qt/"
        files |= {
            "lib/python3.13/site-packages/PySide6/__init__.py": b"", "lib/python3.13/site-packages/PySide6/QtCore.abi3.so": needs("libQt6Core.so.6", "libpyside6.abi3.so.6.12"),
            "lib/python3.13/site-packages/PySide6/QtCore.pyi": b"", "lib/python3.13/site-packages/PySide6/QtGui.abi3.so": needs("libQt6Gui.so.6"), "lib/python3.13/site-packages/PySide6/QtGui.pyi": b"",
            "lib/python3.13/site-packages/PySide6/QtSql.abi3.so": needs("libQt6Sql.so.6"), "lib/python3.13/site-packages/PySide6/QtSql.pyi": b"",
            "lib/python3.13/site-packages/PySide6/libpyside6.abi3.so.6.12": needs("libQt6Core.so.6"),
            "lib/python3.13/site-packages/shiboken6/Shiboken.abi3.so": needs("libshiboken6.abi3.so.6.12"), "lib/python3.13/site-packages/shiboken6/libshiboken6.abi3.so.6.12": needs("libc.so.6"),
            "lib/python3.13/site-packages/shiboken6/Shiboken.pyi": b"",
            qt_dir + "lib/libQt6Core.so.6": needs("libc.so.6"), qt_dir + "lib/libQt6Gui.so.6": needs("libQt6Core.so.6"), qt_dir + "lib/libQt6Sql.so.6": needs("libQt6Core.so.6"),
            qt_dir + "lib/libQt6XcbQpa.so.6": needs("libQt6Gui.so.6"), qt_dir + "lib/libQt6EglFSDeviceIntegration.so.6": needs("libQt6Gui.so.6"), qt_dir + "lib/libQt6EglFsKmsSupport.so.6": needs("libQt6EglFSDeviceIntegration.so.6"),
            qt_dir + "plugins/platforms/libqxcb.so": needs("libQt6XcbQpa.so.6"), qt_dir + "plugins/platforms/libqeglfs.so": needs("libQt6EglFSDeviceIntegration.so.6"),
            qt_dir + "plugins/egldeviceintegrations/libqeglfs-kms-integration.so": needs("libQt6EglFsKmsSupport.so.6", "libQt6EglFSDeviceIntegration.so.6"),
            qt_dir + "plugins/xcbglintegrations/libqxcb-glx-integration.so": needs("libQt6XcbQpa.so.6"),
            qt_dir + "libexec/QtWebEngineProcess": needs("libQt6Core.so.6"), qt_dir + "libexec/rcc": needs("libQt6Core.so.6"), qt_dir + "resources/qtwebengine_devtools_resources.pak": b"x",
            qt_dir + "resources/qtwebengine_resources.pak": b"x", qt_dir + "translations/qtwebengine_locales/en-US.pak": b"x", qt_dir + "translations/qtwebengine_locales/de.pak": b"x",
            qt_dir + "translations/qtbase_de.qm": b"x",
        }
    for name, data in files.items():
        (usr / name).parent.mkdir(parents=True, exist_ok=True)
        (usr / name).write_bytes(data)
    (usr / "lib" / "tcl9.0").mkdir()
    assert (lib / "os.py").is_file()
    return usr


def prune(*args: str) -> None:
    done = subprocess.run([sys.executable, "-I", str(ROOT / "packaging" / "appimage" / "prune.py"), *args], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr


def test_the_appimage_has_no_libpython_no_type_stubs_no_dbm_and_no_eglfs_and_keeps_what_runs(tmp_path: Path) -> None:
    usr = linux_tree(tmp_path / "usr")
    prune(str(usr))
    assert not list((usr / "lib").glob("libpython3*")), "the interpreter has Python linked in; no module names the library"
    assert (usr / "bin" / "python3.13").is_file() and not (usr / "bin" / "python3.13-config").exists()
    lib = usr / "lib" / "python3.13"
    assert not list(lib.rglob("*.pyi")), "no type stubs: only an editor reads them"
    assert not list((lib / "lib-dynload").glob("_dbm*")) and not list((lib / "lib-dynload").glob("_tkinter*"))
    assert (lib / "lib-dynload" / "_ssl.cpython-313-x86_64-linux-gnu.so").is_file() and (lib / "dbm" / "__init__.py").is_file() and (lib / "os.py").is_file()
    assert (lib / "site-packages" / "cryptography" / "hazmat" / "bindings" / "_rust.abi3.so").is_file() and (lib / "site-packages" / "tornado" / "web.py").is_file()
    pyside = lib / "site-packages" / "PySide6"
    assert {p.name for p in pyside.glob("*.abi3.so")} == {"QtCore.abi3.so", "QtGui.abi3.so"} and (pyside / "libpyside6.abi3.so.6.12").is_file() and (pyside / "__init__.py").is_file()
    qt = pyside / "Qt"
    assert {p.name for p in (qt / "lib").iterdir()} == {"libQt6Core.so.6", "libQt6Gui.so.6", "libQt6XcbQpa.so.6"}, "what the kept files name, in turn: not the eglfs libraries, which only eglfs named"
    assert {f"{p.parent.name}/{p.name}" for p in (qt / "plugins").rglob("*.so")} == {"platforms/libqxcb.so", "xcbglintegrations/libqxcb-glx-integration.so"}
    assert not (qt / "plugins" / "egldeviceintegrations").exists()
    assert [p.name for p in (qt / "libexec").iterdir()] == ["QtWebEngineProcess"] and [p.name for p in (qt / "translations" / "qtwebengine_locales").iterdir()] == ["en-US.pak"]
    assert (lib / "site-packages" / "shiboken6" / "libshiboken6.abi3.so.6.12").is_file() and not (lib / "site-packages" / "shiboken6" / "Shiboken.pyi").exists()


def test_the_deb_has_no_libpython_no_type_stubs_and_no_dbm(tmp_path: Path) -> None:
    prefix = linux_tree(tmp_path / "opt" / "neoaprs", qt=False)
    prune("--python-only", str(prefix))
    lib = prefix / "lib" / "python3.13"
    assert not list((prefix / "lib").glob("libpython3*")) and not list(lib.rglob("*.pyi")) and not list((lib / "lib-dynload").glob("_dbm*"))
    assert (prefix / "bin" / "python3.13").is_file() and (lib / "lib-dynload" / "_ssl.cpython-313-x86_64-linux-gnu.so").is_file()
    assert (lib / "site-packages" / "pydantic_core" / "core_schema.py").is_file()


def test_the_build_packs_with_zstd_level_19_in_blocks_of_128_kib_and_prints_what_it_carries() -> None:
    script = (ROOT / "scripts" / "build-appimage").read_text(encoding="utf-8")
    pack = script[script.index("pack() {"):script.index("\n}\n", script.index("pack() {"))]
    assert "--comp zstd --mksquashfs-opt -Xcompression-level --mksquashfs-opt 19" in pack, "level 19: mksquashfs takes the later option"
    assert "-b" not in pack.replace("--mksquashfs-opt", ""), "the blocks stay appimagetool's 128 KiB: larger ones make every start slower"
    assert 'scripts/shipped-size" --depth 5 --title' in script and script.index("shipped-size") < script.index('pack "$app" "$target"') < script.rindex('shipped-size" "$target"')
    assert "libpython" not in script.split("prune.py", 1)[1].split("\n", 1)[0], "prune.py itself takes libpython out"
