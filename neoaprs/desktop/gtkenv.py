"""The web window's ground on Linux, laid before the first `import gi` (shell.choose does it): what the AppImage carries of GTK's world for the desktops that lack it, and the sandbox of the web content.

WebKitGTK and GTK themselves are the system's (a WebKitGTK inside the image would have to match the computer's graphics drivers). What the image carries (scripts/build-gi makes it, scripts/build-appimage
puts it at `<sys.prefix>/lib/neoaprs-gtk`, `CARRIED`) is what a desktop with WebKitGTK may still miss: the tray's AppIndicator library with the ones it needs (`LIBRARIES`) and its typelib, and the typelibs of
WebKitGTK 4.1, which some systems leave out though they have the library. They are found without LD_LIBRARY_PATH, which would reach the browser and every program the app starts:
- a carried library is loaded by its full path, so that a later load by its name finds it already there, and only where the system cannot load that name itself;
- GI_TYPELIB_PATH gets the carried tray typelib where the system has none, and the carried WebKit typelibs only where the system has the WebKitGTK 4.1 library and not its typelib: a typelib of the system
  always wins, as it matches the system's own library.
Outside the AppImage (a checkout) `CARRIED` is not there and nothing of this is done.

The sandbox: WebKitGTK's 4.0 and 4.1 APIs leave the web content's bubblewrap sandbox off unless asked; WEBKIT_FORCE_SANDBOX=1 asks. It is set (when not set already) where user namespaces are allowed and
bubblewrap and xdg-dbus-proxy are there, the conditions the sandbox needs, and bubblewrap, tried once, starts a program in namespaces of its own (a container's seccomp, or a kernel switch the files above do
not show, refuses them too, and a forced sandbox that cannot start is a window whose page never comes). Where they are refused (the AppArmor rule of Ubuntu 24.04, a kernel with none) the content runs
without it, and the window shows NeoAPRS's own page only (links.py sends every other address to the browser), as the Qt window does. A source run is treated the same.

GI_TYPELIB_PATH and WEBKIT_FORCE_SANDBOX (and PYSTRAY_BACKEND, which shell.py sets) are left in the environment of the programs the app starts (the browser, a daemon, what the daemon runs), on purpose:
each is read from this process's environment by the library itself (girepository when gi first loads, WebKit when it starts its web process, pystray at its import), so they cannot be kept to the app; for
a child they add only the typelibs of namespaces the system lacks, a sandbox this system can start, and a choice only pystray reads. A daemon the app starts while they are being set gets them or not, which
is the same to it."""
import ctypes
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, MutableMapping, Sequence
from pathlib import Path

CARRIED = Path(sys.prefix) / "lib" / "neoaprs-gtk"
LIBRARIES = ("libdbusmenu-glib.so.4", "libdbusmenu-gtk3.so.4", "libayatana-ido3-0.4.so.0", "libayatana-indicator3.so.7", "libayatana-appindicator3.so.1")      # in the order they need each other
TRAY_TYPELIB = "AyatanaAppIndicator3-0.1.typelib"
WEBKIT_TYPELIB = "WebKit2-4.1.typelib"
WEBKIT_LIBRARY = "libwebkit2gtk-4.1.so.0"
WEBKIT_PACKAGE = "libwebkit2gtk-4.1-0"                   # Debian's and Ubuntu's name of the package that has it (Fedora: webkit2gtk4.1), which the log names where the window cannot be had
SYSTEM_TYPELIBS = tuple(Path(p) for p in ("/usr/lib/x86_64-linux-gnu/girepository-1.0", "/usr/lib/aarch64-linux-gnu/girepository-1.0", "/usr/lib64/girepository-1.0", "/usr/lib/girepository-1.0"))
SANDBOX = "WEBKIT_FORCE_SANDBOX"
SANDBOX_TOOLS = ("bwrap", "xdg-dbus-proxy")
SANDBOX_TRY = ("--unshare-all", "--die-with-parent", "--ro-bind", "/", "/", "--", "true")        # bubblewrap in namespaces of every kind, running `true`: what the sandbox needs of this system
SANDBOX_TRY_SEC = 5.0
Loader = Callable[[str], object]

_done: list[str] | None = None


def load_global(name: str) -> object:
    """A shared library loaded for the whole process (RTLD_GLOBAL), by name or by path; OSError when it cannot be."""
    return ctypes.CDLL(name, mode=ctypes.RTLD_GLOBAL)


def loads(name: str, load: Loader) -> bool:
    try:
        load(name)
    except OSError:
        return False
    return True


def carry_libraries(folder: Path, load: Loader = load_global) -> list[str]:
    """Each carried library that the system cannot load by its name, loaded from `folder`; the names of those loaded."""
    taken: list[str] = []
    for name in LIBRARIES:
        path = folder / name
        if path.is_file() and not loads(name, load) and loads(str(path), load):
            taken.append(name)
    return taken


def has_typelib(name: str, folders: Sequence[Path]) -> bool:
    return any((folder / name).is_file() for folder in folders)


def typelib_path(carried: Path, load: Loader, system: Sequence[Path]) -> list[str]:
    """The carried typelib folders the system needs, in front of what GI_TYPELIB_PATH has."""
    folders: list[str] = []
    if (carried / "girepository-tray").is_dir() and not has_typelib(TRAY_TYPELIB, system):
        folders.append(str(carried / "girepository-tray"))
    if (carried / "girepository-webkit").is_dir() and not has_typelib(WEBKIT_TYPELIB, system) and loads(WEBKIT_LIBRARY, load):
        folders.append(str(carried / "girepository-webkit"))
    return folders


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def bubblewrap_runs(bwrap: str) -> bool:
    """Whether bubblewrap starts a program in namespaces of its own here (a fixed command, with nothing of the page or the settings in it)."""
    try:
        return subprocess.run([bwrap, *SANDBOX_TRY], stdin=subprocess.DEVNULL, capture_output=True, timeout=SANDBOX_TRY_SEC, check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def sandbox_possible(proc: Path = Path("/proc"), which: Callable[[str], str | None] = shutil.which, tries: Callable[[str], bool] = bubblewrap_runs) -> bool:
    """Whether the web content's sandbox can run here: user namespaces allowed for every user (AppArmor does not restrict them, Debian's switch does not either, the kernel has some), bubblewrap and its D-Bus
    proxy on the PATH (WebKit runs them by a path of its own build; without them its web process would not start), and bubblewrap tried once."""
    kernel = proc / "sys" / "kernel"
    if _read(kernel / "apparmor_restrict_unprivileged_userns") == "1" or _read(kernel / "unprivileged_userns_clone") == "0" or _read(proc / "sys" / "user" / "max_user_namespaces") == "0":
        return False
    found = [which(tool) for tool in SANDBOX_TOOLS]
    return all(found) and tries(str(found[0]))


def prepare(carried: Path = CARRIED, environ: MutableMapping[str, str] = os.environ, load: Loader = load_global, system: Sequence[Path] = SYSTEM_TYPELIBS, proc: Path = Path("/proc"),
            which: Callable[[str], str | None] = shutil.which, tries: Callable[[str], bool] = bubblewrap_runs) -> list[str]:
    """Lays the ground once (a second call does nothing) and says what it did, for the log."""
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
        said.append("the web content without WebKit's sandbox (no user namespaces here, or no bubblewrap): only NeoAPRS's own page in the window")
    _done = said
    return said
