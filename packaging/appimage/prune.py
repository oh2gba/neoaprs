#!/usr/bin/env python3
"""Takes out of the AppImage's usr/ folder what NeoAPRS does not run, so that the image is a third of the size: the parts of CPython that are tests, Tk and documentation, and almost all of Qt except the
web engine and the few modules the desktop app imports (neoaprs/desktop/qtshell.py, qtwindow.py). Run by scripts/build-appimage with the Python of the image itself:  prune.py USR
(scripts/build-deb has the same Python in /opt/neoaprs and no Qt:  prune.py --python-only PREFIX; scripts/build-macos-app has it as Contents/Resources of the app, with Qt as frameworks and .dylib
plugins:  prune.py --macos RESOURCES)

The Qt libraries that stay are the ones that something kept names (the files are searched for the names of libraries, so that a library loaded by name stays too), and nothing else; scripts/smoke-appimage
and scripts/smoke-macos-app start the app, which is the proof that nothing was taken that it needs."""
import re
import shutil
import sys
from pathlib import Path

PYTHON_MODULES = {"QtCore", "QtGui", "QtWidgets", "QtNetwork", "QtWebEngineCore", "QtWebEngineWidgets", "QtWebChannel", "QtPrintSupport"}          # the ones the web engine's module imports in turn
PLUGINS = {
    "platforms": {"libqxcb.so", "libqoffscreen.so", "libqwayland.so"},
    "platformthemes": None, "platforminputcontexts": {"libcomposeplatforminputcontextplugin.so", "libibusplatforminputcontextplugin.so"},
    "imageformats": {"libqgif.so", "libqico.so", "libqjpeg.so", "libqsvg.so", "libqwebp.so"}, "iconengines": None, "tls": None, "networkinformation": None,
    "xcbglintegrations": None, "egldeviceintegrations": None, "wayland-decoration-client": None, "wayland-graphics-integration-client": None, "wayland-shell-integration": None,
}                                                       # a folder of plugins: the files that stay (None: all of them)
MAC_PLUGINS = {
    "platforms": {"libqcocoa.dylib", "libqoffscreen.dylib"}, "styles": None,
    "imageformats": {"libqgif.dylib", "libqicns.dylib", "libqico.dylib", "libqjpeg.dylib", "libqsvg.dylib", "libqwebp.dylib"}, "iconengines": None, "tls": None, "networkinformation": None,
}                                                       # the same for the macOS layout, whose plugins are .dylib files and whose one window system is Cocoa
LOCALE = "en-US.pak"                                    # the web engine falls back to this one when the language of the user has none
LIBRARY = re.compile(rb"lib[A-Za-z0-9_+-]+\.so(?:\.[0-9]+)*")
MAC_LIBRARY = re.compile(rb"(?:Qt[A-Za-z0-9]+\.framework|lib[A-Za-z0-9_.+-]+\.dylib)")           # how a Mach-O names what it loads: `@rpath/QtCore.framework/Versions/A/QtCore`, `@rpath/libpyside6.abi3.6.12.dylib`
STDLIB_DROP = ("test", "idlelib", "tkinter", "turtledemo", "ensurepip", "pydoc_data", "site-packages/pip")


def remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def prune_python(usr: Path) -> None:
    lib = usr / "lib" / "python3.13"
    for name in STDLIB_DROP:
        remove(lib / name)
    for path in list(lib.glob("lib-dynload/_tkinter*")) + list(lib.glob("config-3.13-*")):
        remove(path)
    for pattern in ("lib/tcl*", "lib/tk*", "lib/itcl*", "lib/thread*", "lib/libtcl*", "lib/pkgconfig", "include", "share", "bin/python*-config", "lib/python3.13/site-packages/pip-*"):
        for path in usr.glob(pattern):
            remove(path)
    for path in list(lib.rglob("__pycache__")) + [p for p in (lib / "site-packages").rglob("*") if p.is_dir() and p.name in ("test", "tests")]:
        remove(path)


def prune_modules(site: Path, plugins: dict[str, set[str] | None]) -> Path:
    """The Python modules of PySide6 that are not the app's, shiboken's headers, and the plugins that are not of the kinds and names kept: what Linux and macOS share. Returns Qt's own folder."""
    pyside = site / "PySide6"
    qt = pyside / "Qt"
    for path in pyside.iterdir():
        match path.name.split(".")[0]:
            case name if path.suffix in (".so", ".pyi") and name in PYTHON_MODULES:
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
    for path in (qt / "translations").iterdir():                  # the translations of Qt's own texts (NeoAPRS's are the page's) and all of the web engine's locales but one
        if path.name != "qtwebengine_locales":
            remove(path)
    for path in (qt / "translations" / "qtwebengine_locales").iterdir():
        if path.name != LOCALE:
            remove(path)
    prune_libraries(site, qt)


def prune_qt_mac(site: Path) -> None:
    """The macOS layout: Qt's libraries are frameworks in lib/ (a folder each, with the headers inside, which go), the web engine's helper and its locales live inside QtWebEngineCore.framework, libexec holds only
    the tools of QML, and translations/ only Qt's own texts."""
    qt = prune_modules(site, MAC_PLUGINS)
    for name in ("libexec", "translations"):
        remove(qt / name)
    core = qt / "lib" / "QtWebEngineCore.framework" / "Versions" / "A" / "Resources"
    remove(core / "qtwebengine_devtools_resources.pak")
    for path in (core / "qtwebengine_locales").iterdir():
        if path.name != LOCALE:
            remove(path)
    prune_frameworks(site, qt)
    for headers in qt.glob("lib/*.framework/Versions/*/Headers"):
        remove(headers)
    for headers in qt.glob("lib/*.framework/Headers"):
        remove(headers)


def prune_frameworks(site: Path, qt: Path) -> None:
    """Every framework in Qt's lib/ that no kept file names, found by looking from the files that stay (the kept Python modules, the plugins, shiboken, and the binaries of the frameworks they name in turn).
    The web engine's helper program is a root of its own once its framework stays."""
    frameworks = {path.name: path for path in (qt / "lib").glob("*.framework")}
    dylibs = {path.name: path for folder in (site / "PySide6", site / "shiboken6") for path in folder.glob("*.dylib")}
    roots = [p for pattern in ("PySide6/*.so", "PySide6/Qt/plugins/**/*.dylib", "shiboken6/*.so", "shiboken6/*.dylib", "PySide6/*.dylib") for p in site.glob(pattern)]
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
                todo.extend(p for p in (current / found.removesuffix(".framework"), *current.glob("Helpers/**/*")) if p.is_file())
            elif found in dylibs:
                needed.add(found)
                todo.append(dylibs[found])
    for name, path in frameworks.items():
        if name not in needed:
            remove(path)


def prune_libraries(site: Path, qt: Path) -> None:
    """Everything in Qt's lib/ that no kept file names, found by looking from the files that stay."""
    libs = {path.name: path for path in (qt / "lib").iterdir()}
    for other in (site / "PySide6" / "lib", site / "shiboken6"):
        libs.update({path.name: path for path in other.glob("lib*.so*")})
    roots = [p for pattern in ("PySide6/*.so", "PySide6/Qt/plugins/**/*.so", "PySide6/Qt/libexec/*", "shiboken6/*.so") for p in site.glob(pattern)]
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
    prune_python(usr)
    if mode == "--macos":
        prune_qt_mac(usr / "lib" / "python3.13" / "site-packages")
    elif mode != "--python-only":
        prune_qt(usr / "lib" / "python3.13" / "site-packages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
