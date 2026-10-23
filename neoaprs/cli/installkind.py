"""How this copy of NeoAPRS was installed, from what the process can see (neoaprs/versions.py has the kinds): the page tells the user the steps of an update for that kind. `detect` takes the facts, `detect_here` collects them."""
import os
import platform
import sys
from collections.abc import Mapping
from pathlib import Path

from neoaprs.versions import InstallInfo, deb_architecture, install_kind

from . import servicecmd

UV_RECEIPT = "uv-receipt.toml"          # `uv tool install` writes it into the folder of the tool's environment
DEB_PREFIX = "/opt/neoaprs"             # where the .deb puts its Python (scripts/build-deb); the prefix of that Python is this folder


def uv_tool_environment(prefix: str, environ: Mapping[str, str] = os.environ) -> bool:
    """Is `prefix` (sys.prefix) the environment of a `uv tool` install: it holds uv's receipt, or it is a folder of the tool folder (`$UV_TOOL_DIR`, else `uv/tools` in the data home)?"""
    folder = Path(prefix)
    if (folder / UV_RECEIPT).is_file():
        return True
    tools = environ.get("UV_TOOL_DIR")
    return folder.parent == Path(tools) if tools else folder.parent.name == "tools" and folder.parent.parent.name == "uv"


def deb_environment(prefix: str, root: str = DEB_PREFIX) -> bool:
    """Is `prefix` (sys.prefix) the folder the .deb installs into?"""
    return os.path.realpath(prefix) == os.path.realpath(root)


def is_checkout(tree: Path | None) -> bool:
    """Is the folder the package is imported from (`servicecmd.source_tree`) a clone of the repository: a `.git` beside `pyproject.toml`?"""
    return tree is not None and (tree / ".git").exists()


def detect(frozen: bool, appimage: str | None, prefix: str, tree: Path | None, service: bool, environ: Mapping[str, str] = os.environ, machine: str | None = None) -> InstallInfo:
    kind = install_kind(frozen, appimage, deb_environment(prefix), is_checkout(tree), uv_tool_environment(prefix, environ))
    arch = deb_architecture(machine if machine is not None else platform.machine()) if kind == "deb" else ""
    return InstallInfo(kind, (appimage or "") if kind == "appimage" else "", service, arch)


def service_set(data: Path) -> bool:
    """Does a service of this user (the systemd unit, the launchd agent, the Windows Run key) start NeoAPRS? False when the system has none or cannot say."""
    try:
        return bool(servicecmd.backend_for(sys.platform).installed(servicecmd.Plan(sys.executable, data))[0])
    except Exception:                                   # (a registry or a unit that cannot be read is no service)
        return False


def detect_here(data: Path) -> InstallInfo:
    return detect(bool(getattr(sys, "frozen", False)), servicecmd.appimage_file(), sys.prefix, servicecmd.source_tree(), service_set(data))
