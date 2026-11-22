#!/usr/bin/env python3
"""Remove from the AppImage's usr/ folder what NeoAPRS does not run.

Removed: CPython's tests, Tk, documentation, type stubs, and almost all of Qt except the web engine
and the modules the desktop app imports. Qt libraries stay only if a kept file names them.

  prune.py USR                    run by scripts/build-appimage with the image's own Python
  prune.py --python-only PREFIX   scripts/build-deb: the same Python in /opt/neoaprs, no Qt
  prune.py --macos RESOURCES      scripts/build-macos-app: Contents/Resources, Qt as frameworks and .dylib plugins

On Linux the shared libpython and `_dbm` go too; the macOS launcher needs libpython."""

import re
import shutil
import sys
from pathlib import Path

# Modules the web engine's module imports in turn.
PYTHON_MODULES = {
    "QtCore",
    "QtGui",
    "QtWidgets",
    "QtNetwork",
    "QtWebEngineCore",
    "QtWebEngineWidgets",
    "QtWebChannel",
    "QtPrintSupport",
}
PLUGINS = {
    "platforms": {"libqxcb.so", "libqoffscreen.so", "libqwayland.so"},
    "platformthemes": None,
    "platforminputcontexts": {"libcomposeplatforminputcontextplugin.so", "libibusplatforminputcontextplugin.so"},
    "imageformats": {"libqgif.so", "libqico.so", "libqjpeg.so", "libqsvg.so", "libqwebp.so"},
    "iconengines": None,
    "tls": None,
    "networkinformation": None,
    "xcbglintegrations": None,
    "wayland-decoration-client": None,
    "wayland-graphics-integration-client": None,
    "wayland-shell-integration": None,
    # Plugin folder -> files that stay (None: all). egldeviceintegrations: only eglfs loads it.
}
MAC_PLUGINS = {
    "platforms": {"libqcocoa.dylib", "libqoffscreen.dylib"},
    "styles": None,
    "imageformats": {
        "libqgif.dylib",
        "libqicns.dylib",
        "libqico.dylib",
        "libqjpeg.dylib",
        "libqsvg.dylib",
        "libqwebp.dylib",
    },
    "iconengines": None,
    "tls": None,
    "networkinformation": None,
    # The same for macOS: .dylib plugins, Cocoa only.
}
# The web engine falls back to this locale.
LOCALE = "en-US.pak"
LIBRARY = re.compile(rb"lib[A-Za-z0-9_+-]+\.so(?:\.[0-9]+)*")
# How a Mach-O names what it loads, e.g. `@rpath/QtCore.framework/Versions/A/QtCore`.
MAC_LIBRARY = re.compile(rb"(?:Qt[A-Za-z0-9]+\.framework|lib[A-Za-z0-9_.+-]+\.dylib)")
STDLIB_DROP = ("test", "idlelib", "tkinter", "turtledemo", "ensurepip", "pydoc_data", "site-packages/pip")


def remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def prune_python(usr: Path, macos: bool = False) -> None:
    lib = usr / "lib" / "python3.13"
    for name in STDLIB_DROP:
        remove(lib / name)
    for path in list(lib.glob("lib-dynload/_tkinter*")) + list(lib.glob("config-3.13-*")):
        remove(path)
    patterns = [
        "lib/tcl*",
        "lib/tk*",
        "lib/itcl*",
        "lib/thread*",
        "lib/libtcl*",
        "lib/pkgconfig",
        "include",
        "share",
        "bin/python*-config",
        "lib/python3.13/site-packages/pip-*",
    ]
    if not macos:
        patterns += ["lib/libpython3*", "lib/python3.13/lib-dynload/_dbm*"]
    for pattern in patterns:
        for path in usr.glob(pattern):
            remove(path)
    site = lib / "site-packages"
    for path in list(lib.rglob("__pycache__")) + [
        p for p in site.rglob("*") if p.is_dir() and p.name in ("test", "tests")
    ]:
        remove(path)
    for path in list(site.rglob("*.pyi")):
        remove(path)
    # PyObjC's tests and debug symbols (14 MB), brought by bleak on macOS.
    for path in [site / "PyObjCTest", *site.rglob("*.dSYM")]:
        remove(path)


def prune_modules(site: Path, plugins: dict[str, set[str] | None]) -> Path:
    """Drop PySide6 modules and plugins not kept, and shiboken's headers. Return Qt's folder."""
    pyside = site / "PySide6"
    qt = pyside / "Qt"
    for path in pyside.iterdir():
        match path.name.split(".")[0]:
            case name if path.suffix == ".so" and name in PYTHON_MODULES:
                continue
            case "Qt" | "QtAsyncio" | "__init__" | "_config" | "_git_pyside_version" | "support" | "libpyside6":
                continue
            case _:
                remove(path)
    for name in ("include", "lib"):
        remove(site / "shiboken6" / name)
    for path in (qt / "plugins").iterdir():
        keep = plugins.get(path.name, set())
        for plugin in path.iterdir():
            if path.name not in plugins or (keep is not None and plugin.name not in keep):
                remove(plugin)
        if not any(path.iterdir()):
            remove(path)
    for name in ("qml", "metatypes"):
        remove(qt / name)
    return qt


def prune_qt(site: Path) -> None:
    qt = prune_modules(site, PLUGINS)
    for path in (qt / "libexec").iterdir():
        if path.name != "QtWebEngineProcess":
            remove(path)
    remove(qt / "resources" / "qtwebengine_devtools_resources.pak")
    # Qt's own translations and all web engine locales but one.
    for path in (qt / "translations").iterdir():
        if path.name != "qtwebengine_locales":
            remove(path)
    for path in (qt / "translations" / "qtwebengine_locales").iterdir():
        if path.name != LOCALE:
            remove(path)
    prune_libraries(site, qt)


def prune_qt_mac(site: Path) -> None:
    """The macOS layout: Qt's libraries are frameworks in lib/; the web engine's helper and locales
    live inside QtWebEngineCore.framework."""
    qt = prune_modules(site, MAC_PLUGINS)
    for name in ("libexec", "translations"):
        remove(qt / name)
    for framework in qt.glob("lib/*.framework"):
        fix_framework(framework)
    core = qt / "lib" / "QtWebEngineCore.framework" / "Versions" / "A" / "Resources"
    remove(core / "qtwebengine_devtools_resources.pak")
    for path in (core / "qtwebengine_locales").glob("*.pak"):
        if path.name != LOCALE:
            remove(path)
    prune_frameworks(site, qt)
    for headers in qt.glob("lib/*.framework/Versions/*/Headers"):
        remove(headers)


def fix_framework(framework: Path) -> None:
    """Replace the wheel's flat framework copies with the standard links (Versions/Current ...).

    codesign does not accept the flat layout as a bundle."""
    current = framework / "Versions" / "A"
    if not current.is_dir():
        return
    name = framework.name.removesuffix(".framework")
    remove(framework / "Versions" / "Current")
    (framework / "Versions" / "Current").symlink_to("A")
    for entry in (name, "Resources", "Helpers", "Headers"):
        remove(framework / entry)
        if entry != "Headers" and (current / entry).exists():
            (framework / entry).symlink_to(Path("Versions") / "Current" / entry)


def prune_frameworks(site: Path, qt: Path) -> None:
    """Remove every framework in Qt's lib/ that no kept file names, directly or through another."""
    frameworks = {path.name: path for path in (qt / "lib").glob("*.framework")}
    dylibs = {path.name: path for folder in (site / "PySide6", site / "shiboken6") for path in folder.glob("*.dylib")}
    roots = [
        p
        for pattern in (
            "PySide6/*.so",
            "PySide6/Qt/plugins/**/*.dylib",
            "shiboken6/*.so",
            "shiboken6/*.dylib",
            "PySide6/*.dylib",
        )
        for p in site.glob(pattern)
    ]
    needed: set[str] = set()
    todo = list(roots)
    while todo:
        for name in MAC_LIBRARY.findall(todo.pop().read_bytes()):
            found = name.decode()
            if found in needed:
                continue
            if found in frameworks:
                needed.add(found)
                current = frameworks[found] / "Versions" / "A"
                todo.extend(
                    p
                    for p in (current / found.removesuffix(".framework"), *current.glob("Helpers/**/*"))
                    if p.is_file()
                )
            elif found in dylibs:
                needed.add(found)
                todo.append(dylibs[found])
    for name, path in frameworks.items():
        if name not in needed:
            remove(path)


def prune_libraries(site: Path, qt: Path) -> None:
    """Remove everything in Qt's lib/ that no kept file names, directly or through another."""
    libs = {path.name: path for path in (qt / "lib").iterdir()}
    for other in (site / "PySide6" / "lib", site / "shiboken6"):
        libs.update({path.name: path for path in other.glob("lib*.so*")})
    roots = [
        p
        for pattern in ("PySide6/*.so", "PySide6/Qt/plugins/**/*.so", "PySide6/Qt/libexec/*", "shiboken6/*.so")
        for p in site.glob(pattern)
    ]
    needed: set[str] = set()
    todo = list(roots)
    while todo:
        for name in LIBRARY.findall(todo.pop().read_bytes()):
            found = name.decode()
            if found in libs and found not in needed:
                needed.add(found)
                todo.append(libs[found])
    for name, path in libs.items():
        if name not in needed and path.parent == qt / "lib":
            remove(path)


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0 if len(sys.argv) == 2 else 2
    mode = sys.argv[1] if len(sys.argv) > 2 else ""
    usr = Path(sys.argv[-1]).resolve()
    prune_python(usr, macos=mode == "--macos")
    if mode == "--macos":
        prune_qt_mac(usr / "lib" / "python3.13" / "site-packages")
    elif mode != "--python-only":
        prune_qt(usr / "lib" / "python3.13" / "site-packages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
