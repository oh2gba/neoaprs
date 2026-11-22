"""Prepare the environment for the web window on Linux, before the first `import gi`.

Adds the AppImage's carried GTK pieces where the system lacks them, and turns on WebKit's
sandbox where bubblewrap can run. Outside the AppImage (a checkout) the first part does nothing."""

import ctypes
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, MutableMapping, Sequence
from pathlib import Path

CARRIED = Path(sys.prefix) / "lib" / "neoaprs-gtk"
# In dependency order: each needs the ones before it.
LIBRARIES = (
    "libdbusmenu-glib.so.4",
    "libdbusmenu-gtk3.so.4",
    "libayatana-ido3-0.4.so.0",
    "libayatana-indicator3.so.7",
    "libayatana-appindicator3.so.1",
)
TRAY_TYPELIB = "AyatanaAppIndicator3-0.1.typelib"
WEBKIT_TYPELIB = "WebKit2-4.1.typelib"
WEBKIT_LIBRARY = "libwebkit2gtk-4.1.so.0"
# Debian and Ubuntu package name (Fedora: webkit2gtk4.1); named in the log if no window opens.
WEBKIT_PACKAGE = "libwebkit2gtk-4.1-0"
SYSTEM_TYPELIBS = tuple(
    Path(p)
    for p in (
        "/usr/lib/x86_64-linux-gnu/girepository-1.0",
        "/usr/lib/aarch64-linux-gnu/girepository-1.0",
        "/usr/lib64/girepository-1.0",
        "/usr/lib/girepository-1.0",
    )
)
SANDBOX = "WEBKIT_FORCE_SANDBOX"
SANDBOX_TOOLS = ("bwrap", "xdg-dbus-proxy")
# Run `true` in bubblewrap with every kind of namespace: what the sandbox needs of this system.
SANDBOX_TRY = ("--unshare-all", "--die-with-parent", "--ro-bind", "/", "/", "--", "true")
SANDBOX_TRY_SEC = 5.0
Loader = Callable[[str], object]

_done: list[str] | None = None


def load_global(name: str) -> object:
    """Load a shared library process-wide (RTLD_GLOBAL); raise OSError on failure."""
    return ctypes.CDLL(name, mode=ctypes.RTLD_GLOBAL)


def loads(name: str, load: Loader) -> bool:
    try:
        load(name)
    except OSError:
        return False
    return True


def carry_libraries(folder: Path, load: Loader = load_global) -> list[str]:
    """Load each carried library the system cannot load by name; return the names loaded."""
    taken: list[str] = []
    for name in LIBRARIES:
        path = folder / name
        if path.is_file() and not loads(name, load) and loads(str(path), load):
            taken.append(name)
    return taken


def has_typelib(name: str, folders: Sequence[Path]) -> bool:
    return any((folder / name).is_file() for folder in folders)


def typelib_path(carried: Path, load: Loader, system: Sequence[Path]) -> list[str]:
    """Return the carried typelib folders the system needs, to go before GI_TYPELIB_PATH."""
    folders: list[str] = []
    if (carried / "girepository-tray").is_dir() and not has_typelib(TRAY_TYPELIB, system):
        folders.append(str(carried / "girepository-tray"))
    if (
        (carried / "girepository-webkit").is_dir()
        and not has_typelib(WEBKIT_TYPELIB, system)
        and loads(WEBKIT_LIBRARY, load)
    ):
        folders.append(str(carried / "girepository-webkit"))
    return folders


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def bubblewrap_runs(bwrap: str) -> bool:
    """Return whether bubblewrap can start a program in namespaces here."""
    try:
        return (
            subprocess.run(
                [bwrap, *SANDBOX_TRY],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=SANDBOX_TRY_SEC,
                check=False,
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


def sandbox_possible(
    proc: Path = Path("/proc"),
    which: Callable[[str], str | None] = shutil.which,
    tries: Callable[[str], bool] = bubblewrap_runs,
) -> bool:
    """Return whether the web content's sandbox can run: user namespaces, tools and a trial run."""
    kernel = proc / "sys" / "kernel"
    if (
        _read(kernel / "apparmor_restrict_unprivileged_userns") == "1"
        or _read(kernel / "unprivileged_userns_clone") == "0"
        or _read(proc / "sys" / "user" / "max_user_namespaces") == "0"
    ):
        return False
    found = [which(tool) for tool in SANDBOX_TOOLS]
    return all(found) and tries(str(found[0]))


def prepare(
    carried: Path = CARRIED,
    environ: MutableMapping[str, str] = os.environ,
    load: Loader = load_global,
    system: Sequence[Path] = SYSTEM_TYPELIBS,
    proc: Path = Path("/proc"),
    which: Callable[[str], str | None] = shutil.which,
    tries: Callable[[str], bool] = bubblewrap_runs,
) -> list[str]:
    """Prepare the environment once (later calls do nothing); return what was done, for the log."""
    global _done
    if _done is not None:
        return []
    said: list[str] = []
    if carried.is_dir():
        taken = carry_libraries(carried / "lib", load)
        if taken:
            said.append(f"the carried {', '.join(taken)}")
        folders = typelib_path(carried, load, system)
        if folders:
            environ["GI_TYPELIB_PATH"] = os.pathsep.join([*folders, *filter(None, [environ.get("GI_TYPELIB_PATH")])])
            said.append(f"the carried typelibs of {', '.join(Path(f).name for f in folders)}")
    if SANDBOX in environ:
        said.append(f"{SANDBOX}={environ[SANDBOX]} as the environment has it")
    elif sandbox_possible(proc, which, tries):
        environ[SANDBOX] = "1"
        said.append("the web content in WebKit's sandbox")
    else:
        said.append(
            "the web content without WebKit's sandbox (no user namespaces here, or no bubblewrap): only NeoAPRS's own page in the window"
        )
    _done = said
    return said
