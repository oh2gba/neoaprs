"""NeoAPRS as a macOS app, as far as a Linux machine can see it: the layout rule that finds the shipped programs in the bundle, the launcher of packaging/macos/launcher.c built and run against this machine's Python
with a made-up Resources folder (the arguments, the home, sys.executable, the isolation), the icon made from the Windows one, the pruning of the macOS layout of Qt on a made-up tree, and what scripts/build-macos-app,
scripts/smoke-macos-app, scripts/build-mercury and the bundle's files promise. The app itself is built and tried by the `macos` job of the release workflow."""
import importlib.machinery
import importlib.util
import site
import json
import os
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import sysconfig
import types
from pathlib import Path

import pytest

from neoaprs import bundled
from tests.conftest import ROOT
from tests.support.ptyline import posix_only

pytestmark = posix_only

BUILD = ROOT / "scripts" / "build-macos-app"
SMOKE = ROOT / "scripts" / "smoke-macos-app"
PACKAGING = ROOT / "packaging" / "macos"
LANGUAGES = re.findall(r'code: "([a-zA-Z-]+)"', (ROOT / "ui" / "src" / "i18n" / "locales.ts").read_text(encoding="utf-8"))


def load(path: Path, name: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path, loader=importlib.machinery.SourceFileLoader(name, str(path)))        # (a script without .py gets no loader by itself)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_shipped_programs_are_in_tools_of_the_apps_resources_by_the_one_rule(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    resources = tmp_path / "Applications" / "NeoAPRS.app" / "Contents" / "Resources"
    monkeypatch.setattr(sys, "prefix", str(resources))
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert bundled.tools_dir() == resources / "tools"
    assert "macOS app" in (bundled.__doc__ or "") and "Contents/Resources/tools/" in (bundled.__doc__ or "")


# ---- the launcher

def compiler() -> list[str] | None:
    """How to build the launcher against this machine's Python, or None where it cannot be (no C compiler, no shared libpython, no headers)."""
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    include = sysconfig.get_paths()["include"]
    libdir = sysconfig.get_config_var("LIBDIR") or ""
    shared = sysconfig.get_config_var("LDLIBRARY") or ""
    if not cc or not Path(include, "Python.h").is_file() or not shared.endswith((".so", ".dylib")) or not Path(libdir, shared).is_file():
        return None
    name = re.sub(r"^lib|\.(so|dylib)$", "", shared)
    return [cc, "-O2", "-Wall", f"-I{include}", str(PACKAGING / "launcher.c"), f"-L{libdir}", f"-l{name}", f"-Wl,-rpath,{libdir}"]          # (the source before the libraries: GNU ld reads them in order)


def fake_bundle(tmp_path: Path) -> Path:
    """NeoAPRS.app with Contents/Resources laid out as this machine's Python (its standard library linked in, a made-up `neoaprs` package in site-packages that prints what it sees), and the launcher built in Contents/MacOS."""
    app = tmp_path / "NeoAPRS.app"
    resources = app / "Contents" / "Resources"
    lib = resources / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}"
    lib.mkdir(parents=True)
    for entry in Path(sysconfig.get_paths()["stdlib"]).iterdir():
        if entry.name != "site-packages":
            (lib / entry.name).symlink_to(entry)
    package = lib / "site-packages" / "neoaprs"
    package.mkdir(parents=True)
    for folder in site.getsitepackages([str(resources)]):           # (a distribution's Python may read dist-packages instead of site-packages: the same folder under every name this one looks in)
        if Path(folder) != package.parent and not Path(folder).exists():
            Path(folder).parent.mkdir(parents=True, exist_ok=True)
            Path(folder).symlink_to(package.parent)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__main__.py").write_text(
        "import json, os, sys\n"
        "try:\n    import planted\n    planted_seen = True\nexcept ImportError:\n    planted_seen = False\n"
        "print(json.dumps({'argv': sys.argv[1:], 'executable': sys.executable, 'prefix': sys.prefix, 'isolated': sys.flags.isolated, 'no_site': sys.flags.no_user_site, 'safe_path': sys.flags.safe_path,"
        " 'no_bytecode': sys.dont_write_bytecode, 'planted': planted_seen, 'cwd_on_path': os.getcwd() in sys.path or '' in sys.path}))\n", encoding="utf-8")
    (resources / "bin").mkdir()
    (resources / "bin" / "python3.13").symlink_to(sys.executable)
    (app / "Contents" / "MacOS").mkdir()
    (app / "Contents" / "Info.plist").write_text("<plist/>", encoding="utf-8")
    command = compiler()
    assert command is not None
    subprocess.run([*command, "-o", str(app / "Contents" / "MacOS" / "NeoAPRS")], check=True, capture_output=True, text=True, timeout=120)
    return app


@pytest.mark.skipif(compiler() is None or sys.version_info[:2] != (3, 13), reason="needs a C compiler and the shared library and headers of this Python 3.13")
def test_the_launcher_runs_the_neoaprs_module_of_the_resources_python_isolated_with_app_as_the_default_argument(tmp_path: Path) -> None:
    app = fake_bundle(tmp_path)
    planted = tmp_path / "planted"
    planted.mkdir()
    (planted / "planted.py").write_text("", encoding="utf-8")
    (tmp_path / "planted.py").write_text("", encoding="utf-8")                   # (in the current folder too)
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env["PYTHONPATH"] = str(planted)

    def run(*args: str) -> dict[str, object]:
        done = subprocess.run([str(app / "Contents" / "MacOS" / "NeoAPRS"), *args], capture_output=True, text=True, timeout=60, cwd=tmp_path, env=env)
        assert done.returncode == 0, done.stderr
        return dict(json.loads(done.stdout.strip().splitlines()[-1]))

    seen = run()
    assert seen["argv"] == ["app"], "no arguments start the desktop app, as the AppImage's AppRun does"
    assert seen["executable"] == str(app / "Contents" / "Resources" / "bin" / "python3.13"), "what NeoAPRS starts with sys.executable is the plain Python of the bundle"
    assert seen["prefix"] == str(app / "Contents" / "Resources"), "the Python's prefix is Resources, where tools/ is (neoaprs/bundled.py)"
    assert seen["isolated"] == 1 and seen["no_site"] == 1 and seen["safe_path"] == 1 and seen["no_bytecode"] is True
    assert seen["planted"] is False and seen["cwd_on_path"] is False, "nothing of the environment or the current folder reaches the app's Python"
    assert run("doctor")["argv"] == ["doctor"]
    assert run("--data", "a b", "--web-port", "0")["argv"] == ["--data", "a b", "--web-port", "0"]
    assert run("--version")["argv"] == ["--version"], "--version is NeoAPRS's, not Python's"


def test_the_launcher_names_the_python_inside_the_bundle_and_runs_the_package() -> None:
    source = (PACKAGING / "launcher.c").read_text(encoding="utf-8")
    assert '#define PYTHON "bin/python3.13"' in source and '"/Resources"' in source and '"-m"' in source and '"neoaprs"' in source and '"app"' in source
    assert "PyConfig_InitIsolatedConfig" in source and "config.write_bytecode = 0" in source and "config.install_signal_handlers = 1" in source
    assert "@executable_path/../Resources/lib" in (BUILD.read_text(encoding="utf-8")), "the build links the launcher to the Python's own libpython through the bundle"


# ---- the icon

def test_the_icns_holds_the_png_frames_of_the_windows_icon_under_the_types_of_their_sizes(tmp_path: Path) -> None:
    module = load(PACKAGING / "make_icns.py", "make_icns")
    frames = module.png_frames((ROOT / "neoaprs" / "desktop" / "icon.ico").read_bytes())
    assert {16, 32, 128, 256} <= set(frames) and all(data.startswith(b"\x89PNG") for data in frames.values())
    data = module.icns(frames)
    assert data[:4] == b"icns" and struct.unpack(">I", data[4:8])[0] == len(data)
    entries: dict[str, bytes] = {}
    at = 8
    while at < len(data):
        kind, length = data[at:at + 4].decode("ascii"), struct.unpack(">I", data[at + 4:at + 8])[0]
        entries[kind] = data[at + 8:at + length]
        at += length
    assert {"icp4", "icp5", "ic11", "ic07", "ic08", "ic13"} <= set(entries), entries.keys()
    assert entries["ic13"] == entries["ic08"] == frames[256] and entries["ic11"] == entries["icp5"] == frames[32], "a frame doubles as the Retina one of half its size"
    out = tmp_path / "NeoAPRS.icns"
    done = subprocess.run([sys.executable, "-I", str(PACKAGING / "make_icns.py"), str(ROOT / "neoaprs" / "desktop" / "icon.ico"), str(out)], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0 and out.read_bytes() == data and "256 px" in done.stdout
    with pytest.raises(ValueError):
        module.icns({})


# ---- the pruning of Qt as the macOS wheels lay it out

def mach_o(*names: str) -> bytes:
    return b"\xcf\xfa\xed\xfe" + b"".join(f"@rpath/{n}/Versions/A/{n.removesuffix('.framework')}\0".encode() if n.endswith(".framework") else f"@rpath/{n}\0".encode() for n in names)


def mac_tree(tmp_path: Path) -> Path:
    """Contents/Resources as the build has it before the pruning: a Python with the folders the pruning drops, PySide6 with modules, frameworks, plugins and the web engine's helper and locales."""
    res = tmp_path / "Resources"
    lib = res / "lib" / "python3.13"
    site = lib / "site-packages"
    for folder in ("test", "idlelib", "tkinter", "encodings", "lib-dynload", "site-packages/pip", "site-packages/pip-26.2.2.dist-info"):
        (lib / folder).mkdir(parents=True)
    (lib / "os.py").write_text("", encoding="utf-8")
    (lib / "lib-dynload" / "_tkinter.cpython-313-darwin.so").write_bytes(b"x")
    for folder in ("include/python3.13", "share/man", "lib/tcl9.0", "lib/tk9.0", "bin"):
        (res / folder).mkdir(parents=True)
    (res / "lib" / "libtcl9.0.dylib").write_bytes(b"x")
    (res / "lib" / "libpython3.13.dylib").write_bytes(b"x")
    (res / "bin" / "python3.13-config").write_text("", encoding="utf-8")
    pyside = site / "PySide6"
    qt = pyside / "Qt"
    frameworks = {
        "QtCore": (), "QtGui": ("QtCore.framework",), "QtWidgets": ("QtGui.framework",), "QtNetwork": ("QtCore.framework",), "QtPrintSupport": ("QtWidgets.framework",), "QtWebChannel": ("QtQml.framework",),
        "QtWebEngineCore": ("QtQuick.framework", "QtWebChannel.framework", "QtPositioning.framework"), "QtWebEngineWidgets": ("QtWebEngineCore.framework", "QtPrintSupport.framework"),
        "QtQuick": ("QtQml.framework", "QtQmlModels.framework"), "QtQml": ("QtNetwork.framework",), "QtQmlModels": (), "QtPositioning": (), "QtSql": ("QtCore.framework",), "QtDesigner": (), "QtWebEngineQuick": ("QtWebEngineCore.framework",),
    }
    for name, needs in frameworks.items():
        folder = qt / "lib" / f"{name}.framework" / "Versions" / "A"
        (folder / "Headers").mkdir(parents=True)
        (folder / "Headers" / f"{name}.h").write_text("", encoding="utf-8")
        (folder / name).write_bytes(mach_o(*needs))
        for copy in (folder / "Resources", folder.parent.parent / "Resources"):               # (the wheel is flat: Resources twice, no Versions/Current, no link to the library)
            copy.mkdir()
            (copy / "Info.plist").write_text("<plist/>", encoding="utf-8")
    for top in (qt / "lib" / "QtWebEngineCore.framework", qt / "lib" / "QtWebEngineCore.framework" / "Versions" / "A"):
        helper = top / "Helpers" / "QtWebEngineProcess.app" / "Contents" / "MacOS"
        helper.mkdir(parents=True)
        (helper / "QtWebEngineProcess").write_bytes(mach_o("QtWebEngineCore.framework", "QtGui.framework"))
        resources = top / "Resources"
        (resources / "qtwebengine_locales").mkdir(parents=True)
        for locale in ("en-US", "de", "fi"):
            (resources / "qtwebengine_locales" / f"{locale}.pak").write_bytes(b"x")
        (resources / "qtwebengine_devtools_resources.pak").write_bytes(b"x")
        (resources / "qtwebengine_resources.pak").write_bytes(b"x")
        (resources / "icudtl.dat").write_bytes(b"x")
    for module, needs in {"QtCore": ("QtCore.framework", "libpyside6.abi3.6.12.dylib", "libshiboken6.abi3.6.12.dylib"), "QtGui": ("QtGui.framework",), "QtWidgets": ("QtWidgets.framework",), "QtNetwork": ("QtNetwork.framework",),
                          "QtWebEngineCore": ("QtWebEngineCore.framework",), "QtWebEngineWidgets": ("QtWebEngineWidgets.framework",), "QtWebChannel": ("QtWebChannel.framework",), "QtPrintSupport": ("QtPrintSupport.framework",),
                          "QtSql": ("QtSql.framework",), "QtQml": ("QtQml.framework", "libpyside6qml.abi3.6.12.dylib"), "QtDesigner": ("QtDesigner.framework",)}.items():
        (pyside / f"{module}.abi3.so").write_bytes(mach_o(*needs))
        (pyside / f"{module}.pyi").write_text("", encoding="utf-8")
    for name in ("__init__.py", "_config.py", "_git_pyside_version.py", "QtAsyncio", "support", "scripts", "glue", "include", "typesystems", "Designer.app", "lrelease", "qmlls"):
        (pyside / name).mkdir() if "." not in name or name.endswith(".app") else (pyside / name).write_text("", encoding="utf-8")
    (pyside / "libpyside6.abi3.6.12.dylib").write_bytes(mach_o("QtCore.framework"))
    (pyside / "libpyside6qml.abi3.6.12.dylib").write_bytes(mach_o("QtQml.framework"))
    plugins = {"platforms": ("libqcocoa.dylib", "libqoffscreen.dylib", "libqminimal.dylib"), "imageformats": ("libqjpeg.dylib", "libqtiff.dylib", "libqpdf.dylib"), "styles": ("libqmacstyle.dylib",), "tls": ("libqsecuretransportbackend.dylib",),
               "sqldrivers": ("libqsqlite.dylib",), "qmltooling": ("libqmldbg_debugger.dylib",), "designer": ("libPySidePlugin.dylib",), "generic": ("libqtuiotouchplugin.dylib",), "iconengines": ("libqsvgicon.dylib",), "networkinformation": ("libqapplenetworkinformation.dylib",)}
    for kind, names in plugins.items():
        (qt / "plugins" / kind).mkdir(parents=True)
        for name in names:
            (qt / "plugins" / kind / name).write_bytes(mach_o("QtGui.framework", "QtSvg.framework") if name == "libqsvgicon.dylib" else mach_o("QtGui.framework"))
    for folder in ("qml/QtWebEngine", "metatypes", "libexec", "translations"):
        (qt / folder).mkdir(parents=True)
    (qt / "libexec" / "qmlcachegen").write_bytes(b"x")
    (qt / "translations" / "qtbase_de.qm").write_bytes(b"x")
    shiboken = site / "shiboken6"
    (shiboken / "include").mkdir(parents=True)
    (shiboken / "Shiboken.abi3.so").write_bytes(mach_o("libshiboken6.abi3.6.12.dylib"))
    (shiboken / "libshiboken6.abi3.6.12.dylib").write_bytes(mach_o())
    return res


def test_the_macos_pruning_keeps_the_web_engine_its_helper_and_what_they_name_and_drops_the_rest(tmp_path: Path) -> None:
    res = mac_tree(tmp_path)
    done = subprocess.run([sys.executable, "-I", str(ROOT / "packaging" / "appimage" / "prune.py"), "--macos", str(res)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    lib = res / "lib" / "python3.13"
    assert (lib / "os.py").is_file() and (lib / "encodings").is_dir() and (lib / "lib-dynload").is_dir() and (res / "lib" / "libpython3.13.dylib").is_file()
    for gone in ("test", "idlelib", "tkinter", "site-packages/pip", "lib-dynload/_tkinter.cpython-313-darwin.so"):
        assert not (lib / gone).exists(), gone
    for gone in ("include", "share", "lib/tcl9.0", "lib/tk9.0", "lib/libtcl9.0.dylib", "bin/python3.13-config"):
        assert not (res / gone).exists(), gone
    pyside = lib / "site-packages" / "PySide6"
    qt = pyside / "Qt"
    kept_modules = {p.name for p in pyside.glob("*.abi3.so")}
    assert kept_modules == {"QtCore.abi3.so", "QtGui.abi3.so", "QtWidgets.abi3.so", "QtNetwork.abi3.so", "QtWebEngineCore.abi3.so", "QtWebEngineWidgets.abi3.so", "QtWebChannel.abi3.so", "QtPrintSupport.abi3.so"}
    assert (pyside / "libpyside6.abi3.6.12.dylib").is_file() and not (pyside / "libpyside6qml.abi3.6.12.dylib").exists()
    for gone in ("scripts", "glue", "include", "typesystems", "Designer.app", "lrelease", "qmlls", "QtDesigner.pyi"):
        assert not (pyside / gone).exists(), gone
    assert (pyside / "__init__.py").exists() and (pyside / "support").exists() and (pyside / "QtAsyncio").exists()
    frameworks = {p.name for p in (qt / "lib").glob("*.framework")}
    assert frameworks == {"QtCore.framework", "QtGui.framework", "QtWidgets.framework", "QtNetwork.framework", "QtPrintSupport.framework", "QtWebChannel.framework", "QtWebEngineCore.framework", "QtWebEngineWidgets.framework",
                          "QtQuick.framework", "QtQml.framework", "QtQmlModels.framework", "QtPositioning.framework"}, "what the kept modules, the plugins and the helper name, in turn; not QtSql, QtDesigner, QtWebEngineQuick"
    core = qt / "lib" / "QtWebEngineCore.framework" / "Versions" / "A"
    assert (core / "Helpers" / "QtWebEngineProcess.app" / "Contents" / "MacOS" / "QtWebEngineProcess").is_file()
    assert sorted(p.name for p in (core / "Resources" / "qtwebengine_locales").iterdir()) == ["en-US.pak"]
    assert not (core / "Resources" / "qtwebengine_devtools_resources.pak").exists() and (core / "Resources" / "qtwebengine_resources.pak").is_file() and (core / "Resources" / "icudtl.dat").is_file()
    assert not (core / "Headers").exists() and not (qt / "lib" / "QtCore.framework" / "Headers").exists() and not (qt / "lib" / "QtCore.framework" / "Versions" / "A" / "Headers").exists()
    for framework in (qt / "lib").glob("*.framework"):
        name = framework.name.removesuffix(".framework")
        assert (framework / "Versions" / "Current").is_symlink() and (framework / "Versions" / "Current").resolve() == (framework / "Versions" / "A").resolve(), framework
        assert (framework / name).is_symlink() and (framework / name).resolve() == (framework / "Versions" / "A" / name).resolve(), "the library is reached by the standard link"
        assert (framework / "Resources").is_symlink() and (framework / "Resources" / "Info.plist").is_file(), "the top-level copy of Resources gave way to the link"
    assert (qt / "lib" / "QtWebEngineCore.framework" / "Helpers").is_symlink() and (qt / "lib" / "QtWebEngineCore.framework" / "Helpers" / "QtWebEngineProcess.app" / "Contents" / "MacOS" / "QtWebEngineProcess").is_file()
    assert not (qt / "lib" / "QtCore.framework" / "Helpers").exists(), "no link to a Helpers that is not there"
    assert sorted(p.name for p in (qt / "lib" / "QtWebEngineCore.framework" / "Resources" / "qtwebengine_locales").iterdir()) == ["en-US.pak"], "through the link, the pruned one"
    plugins = {f"{p.parent.name}/{p.name}" for p in (qt / "plugins").rglob("*.dylib")}
    assert plugins == {"platforms/libqcocoa.dylib", "platforms/libqoffscreen.dylib", "imageformats/libqjpeg.dylib", "styles/libqmacstyle.dylib", "tls/libqsecuretransportbackend.dylib", "iconengines/libqsvgicon.dylib", "networkinformation/libqapplenetworkinformation.dylib"}
    for gone in ("qml", "metatypes", "libexec", "translations", "plugins/sqldrivers", "plugins/qmltooling", "plugins/designer", "plugins/generic"):
        assert not (qt / gone).exists(), gone
    shiboken = lib / "site-packages" / "shiboken6"
    assert (shiboken / "Shiboken.abi3.so").is_file() and (shiboken / "libshiboken6.abi3.6.12.dylib").is_file() and not (shiboken / "include").exists()


# ---- the build and smoke scripts, the bundle's files

def build(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(BUILD), *args], capture_output=True, text=True, timeout=30)


def test_a_build_without_mercury_must_say_so_and_the_tarball_must_be_the_macs(tmp_path: Path) -> None:
    refused = build("--out", str(tmp_path / "out"))
    assert refused.returncode == 2 and "--mercury TARBALL" in refused.stderr and "--no-mercury" in refused.stderr, "a release can never silently lack Mercury"
    tarball = tmp_path / "mercury-1.9.21-macos-arm64.tar.gz"
    tarball.write_bytes(b"")
    both = build("--mercury", str(tarball), "--no-mercury")
    assert both.returncode == 2 and "exclude each other" in both.stderr
    linux = tmp_path / "mercury-1.9.21-linux-aarch64.tar.gz"
    linux.write_bytes(b"")
    wrong = build("--mercury", str(linux))
    assert wrong.returncode == 2 and "macos-arm64" in wrong.stderr, "the program is for the machine the app is for"
    assert build("--mercury", str(tmp_path / "gone.tar.gz")).returncode == 2
    if sys.platform != "darwin":
        elsewhere = build("--mercury", str(tarball))
        assert elsewhere.returncode == 1 and "macOS" in elsewhere.stderr, "the arguments are read before the machine is looked at"


def test_the_python_of_the_app_is_pinned_by_version_and_digest_and_the_floor_is_the_one_mercury_is_built_for() -> None:
    script = BUILD.read_text(encoding="utf-8")
    url = re.search(r'^PYTHON_URL="([^"]+)"', script, re.M)
    digest = re.search(r'^PYTHON_SHA256="([0-9a-f]{64})"', script, re.M)
    assert url and digest and "aarch64-apple-darwin" in url.group(1) and url.group(1).startswith("https://github.com/astral-sh/python-build-standalone/releases/download/") and "/latest/" not in url.group(1)
    appimage = (ROOT / "scripts" / "build-appimage").read_text(encoding="utf-8")
    assert re.search(r"/download/(\d+)/", url.group(1)).group(1) == re.search(r'PYTHON_URL="[^"]*/download/(\d+)/', appimage).group(1), "the same release of python-build-standalone as the AppImage"      # type: ignore[union-attr]
    assert not re.search(r"^MERCURY\w*_URL=", script, re.M), "no download was added: the tarball comes in"
    floor = re.search(r'^MIN_OS="([0-9.]+)"', script, re.M)
    mercury = re.search(r'^MACOS_MIN = "([0-9.]+)"', (ROOT / "scripts" / "build-mercury").read_text(encoding="utf-8"), re.M)
    assert floor and mercury and floor.group(1) == mercury.group(1) == "14.0", "the floor of the Qt wheels (macosx_14_0), said once in each script"
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    assert "pyside6_essentials-6.12.0-cp310-abi3-macosx_14_0_universal2.whl" in lock
    assert "arm64.dmg" in script and 'uname -s)-$(uname -m)" = Darwin-arm64' in script


def test_the_build_lays_the_bundle_out_as_the_launcher_and_the_one_rule_expect() -> None:
    script = BUILD.read_text(encoding="utf-8")
    assert 'res="$contents/Resources"' in script and 'mv "$work/python" "$res"' in script, "the Python's prefix is Contents/Resources"
    assert 'tar -xzf "$mercury" -C "$res/tools" --exclude=\'mercury/dev\'' in script and "mercury/$needed" in script
    assert script.index("launcher.c") < script.index("prune.py --macos"), "the launcher is linked before the headers go"
    assert script.index("compileall") < script.index("codesign --force --sign -") < script.index("codesign --verify --deep --strict") < script.index("hdiutil create"), "bytecode first, then every file is signed and sealed, then the image"
    assert "codesign --force --deep" not in script and '"$res" -name \'*.framework\'' in script and "--entitlements" in script, "each piece signed once by name, the helper with its entitlements; the verification is deep"
    assert "find -L" not in script and "-exec test -e {} \\;" in script, "BSD find refuses -delete under -L"
    smoke = SMOKE.read_text(encoding="utf-8")
    assert "\\|" not in smoke and "grep -E -qv" in smoke, "BSD grep has no \\| in a basic expression"
    assert "Info.plist.in" in script and "@VERSION@" in script and "@BUILD@" in script and "make_icns.py" in script and "*.lproj" in script
    assert 'ln -s /Applications "$stage/Applications"' in script and "-format UDZO" in script


def test_the_info_plist_names_the_launcher_the_icon_the_identifier_and_the_microphone_in_every_language() -> None:
    text = (PACKAGING / "Info.plist.in").read_text(encoding="utf-8").replace("@VERSION@", "0.16.0-rc1").replace("@BUILD@", "0.16.0").replace("@MIN_OS@", "14.0")
    plist = plistlib.loads(text.encode("utf-8"))
    assert plist["CFBundleExecutable"] == "NeoAPRS" and plist["CFBundleIconFile"] == "NeoAPRS.icns" and plist["CFBundleIdentifier"] == "eu.oh2gba.neoaprs" and plist["CFBundlePackageType"] == "APPL"
    assert plist["CFBundleShortVersionString"] == "0.16.0-rc1" and plist["CFBundleVersion"] == "0.16.0" and plist["LSMinimumSystemVersion"] == "14.0" and plist["NSHighResolutionCapable"] is True
    assert plist["NSMicrophoneUsageDescription"]
    from neoaprs.cli.servicelaunchd import LABEL
    assert plist["CFBundleIdentifier"] == LABEL, "the launchd agent and the bundle are the same thing to the system"
    folders = sorted(p.name for p in (PACKAGING / "lproj").iterdir())
    assert folders == sorted(f"{code}.lproj" for code in LANGUAGES) and LANGUAGES and len(LANGUAGES) == 8
    english = ""
    for folder in folders:
        strings = (PACKAGING / "lproj" / folder / "InfoPlist.strings").read_text(encoding="utf-8")
        found = re.search(r'^"NSMicrophoneUsageDescription" = "(.+)";$', strings, re.M)
        assert found and found.group(1).strip() and "NeoAPRS" in found.group(1), folder
        if folder == "en.lproj":
            english = found.group(1)
    assert english == plist["NSMicrophoneUsageDescription"], "the plist's own sentence is the English one"


def test_the_smoke_test_opens_the_image_checks_the_signature_and_runs_the_bundled_mercury_unless_told_that_there_is_none() -> None:
    smoke = SMOKE.read_text(encoding="utf-8")
    assert "--no-mercury) with_mercury=0" in smoke and "tools/mercury" in smoke and "codesign --verify --deep --strict" in smoke and "hdiutil attach" in smoke
    assert 'export HOME="$work/home"' in smoke, "the data folder of a Mac is under the home: the test's own"
    assert "eu.oh2gba.neoaprs.plist" in smoke and "ProgramArguments.0" in smoke and "QT_QPA_PLATFORM=offscreen" in smoke
    assert '("macos-app", "arm64")' in smoke


def test_build_mercury_names_a_macs_tarball_by_apples_words_and_links_the_system_alone() -> None:
    module = load(ROOT / "scripts" / "build-mercury", "build_mercury")
    assert module.tarball_name("arm64", "darwin") == f"mercury-{module.VERSION}-macos-arm64.tar.gz" and module.tarball_name("aarch64", "darwin").endswith("-macos-arm64.tar.gz")
    assert module.tarball_name("aarch64", "linux") == f"mercury-{module.VERSION}-linux-aarch64.tar.gz" and module.machine_name("arm64", "linux") == "aarch64"
    assert module.MACOS_MIN == "14.0" and module.MACOS_NEEDED_OK == ("/System/Library/Frameworks/", "/usr/lib/libSystem.")
    source = (ROOT / "scripts" / "build-mercury").read_text(encoding="utf-8")
    assert 'env["MACOSX_DEPLOYMENT_TARGET"] = MACOS_MIN' in source and "otool" in source and "macOS 26" in source, "why Rhizomatica's own universal build is not taken"
