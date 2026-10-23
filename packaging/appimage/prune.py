#!/usr/bin/env python3
"""Takes out of the AppImage's usr/ folder what NeoAPRS does not run, so that the image is a third of the size: the parts of CPython that are tests, Tk and documentation, and almost all of Qt except the
web engine and the few modules the desktop app imports (neoaprs/desktop/qtshell.py, qtwindow.py). Run by scripts/build-appimage with the Python of the image itself:  prune.py USR
(scripts/build-deb has the same Python in /opt/neoaprs and no Qt:  prune.py --python-only PREFIX)

The Qt libraries that stay are the ones that something kept names (the files are searched for the names of libraries, so that a library loaded by name stays too), and nothing else; scripts/smoke-appimage
starts the app, which is the proof that nothing was taken that it needs."""
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
LOCALE = "en-US.pak"                                    # the web engine falls back to this one when the language of the user has none
LIBRARY = re.compile(rb"lib[A-Za-z0-9_+-]+\.so(?:\.[0-9]+)*")
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


def prune_qt(site: Path) -> None:
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
        keep = PLUGINS.get(path.name, set())
        for plugin in path.iterdir():
            if path.name not in PLUGINS or (keep is not None and plugin.name not in keep):
                remove(plugin)
        if not any(path.iterdir()):
            remove(path)
    for name in ("qml", "metatypes"):
        remove(qt / name)
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
    python_only = sys.argv[1] == "--python-only"
    usr = Path(sys.argv[-1]).resolve()
    prune_python(usr)
    if not python_only:
        prune_qt(usr / "lib" / "python3.13" / "site-packages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
