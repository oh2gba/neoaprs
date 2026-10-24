"""How this copy of NeoAPRS was installed, from what the process can see (neoaprs/versions.py has the kinds): the page tells the user the steps of an update for that kind. `detect` takes the facts, `detect_here` collects them.

`NEOAPRS_INSTALL_KIND` simulates a kind, for development (the screenshots of the update's steps): `deb`, `deb arm64 service`, `appimage /home/ham/NeoAPRS.AppImage`; the words after the kind are `amd64` or `arm64`, `service`
and, for an AppImage, its path. A simulated kind is never updated for real (neoaprs/services/selfinstall.py rehearses it)."""
import os
import platform
import sys
from typing import get_args
from collections.abc import Mapping
from pathlib import Path

from neoaprs import VERSION
from neoaprs.versions import InstallInfo, InstallKind, deb_architecture, install_kind

from . import servicecmd

UV_RECEIPT = "uv-receipt.toml"          # `uv tool install` writes it into the folder of the tool's environment
ENV_KIND = "NEOAPRS_INSTALL_KIND"
KINDS: tuple[InstallKind, ...] = get_args(InstallKind)
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


def simulated(text: str) -> InstallInfo | None:
    """The kind `NEOAPRS_INSTALL_KIND` names, with its words; None for an empty value or a kind that is not one."""
    kind, *words = text.split() or [""]
    found = next((k for k in KINDS if k == kind), None)
    if found is None:
        return None
    arch = next((w for w in words if w in ("amd64", "arm64")), "amd64") if found == "deb" else ""
    appimage = next((w for w in words if w.startswith("/")), str(Path.home() / f"NeoAPRS-{VERSION}-x86_64.AppImage")) if found == "appimage" else ""
    return InstallInfo(found, appimage, "service" in words, arch)


def detect_here(data: Path, environ: Mapping[str, str] = os.environ) -> InstallInfo:
    if fake := simulated(environ.get(ENV_KIND, "")):
        return fake
    return detect(bool(getattr(sys, "frozen", False)), servicecmd.appimage_file(), sys.prefix, servicecmd.source_tree(), service_set(data))
