"""Detect how this copy of NeoAPRS was installed (the kinds are in neoaprs/versions.py).

`NEOAPRS_INSTALL_KIND` simulates a kind for development, e.g. `deb arm64 service`; a simulated
kind is never updated for real."""

import os
import platform
import sys
from typing import get_args
from collections.abc import Mapping
from pathlib import Path

from neoaprs import VERSION
from neoaprs.versions import InstallInfo, InstallKind, deb_architecture, install_kind, mac_architecture

from . import servicecmd
from .servicecmd import container_environment

UV_RECEIPT = "uv-receipt.toml"
ENV_KIND = "NEOAPRS_INSTALL_KIND"
KINDS: tuple[InstallKind, ...] = get_args(InstallKind)
DEB_PREFIX = "/opt/neoaprs"


def uv_tool_environment(prefix: str, environ: Mapping[str, str] = os.environ) -> bool:
    """Return whether `prefix` is a `uv tool` environment."""
    folder = Path(prefix)
    if (folder / UV_RECEIPT).is_file():
        return True
    tools = environ.get("UV_TOOL_DIR")
    return (
        folder.parent == Path(tools) if tools else folder.parent.name == "tools" and folder.parent.parent.name == "uv"
    )


def deb_environment(prefix: str, root: str = DEB_PREFIX) -> bool:
    return os.path.realpath(prefix) == os.path.realpath(root)


def app_bundle_environment(prefix: str) -> bool:
    """Return whether `prefix` is `NeoAPRS.app/Contents/Resources` (checked by its `Info.plist`)."""
    folder = Path(prefix)
    return (
        folder.name == "Resources"
        and folder.parent.name == "Contents"
        and folder.parent.parent.suffix == ".app"
        and (folder.parent / "Info.plist").is_file()
    )


def is_checkout(tree: Path | None) -> bool:
    """Return whether the package is imported from a clone of the repository."""
    return tree is not None and (tree / ".git").exists()


def developers_run(install: InstallInfo) -> bool:
    return install.kind == "source" or is_checkout(servicecmd.source_tree())


def detect(
    frozen: bool,
    appimage: str | None,
    prefix: str,
    tree: Path | None,
    service: bool,
    environ: Mapping[str, str] = os.environ,
    machine: str | None = None,
) -> InstallInfo:
    kind = install_kind(
        frozen,
        appimage,
        deb_environment(prefix),
        is_checkout(tree),
        uv_tool_environment(prefix, environ),
        app_bundle_environment(prefix),
        container_environment(environ),
    )
    found = machine if machine is not None else platform.machine()
    arch = deb_architecture(found) if kind == "deb" else mac_architecture(found) if kind == "macos-app" else ""
    return InstallInfo(kind, (appimage or "") if kind == "appimage" else "", service, arch)


def service_set(data: Path) -> bool:
    """Return whether a user service starts NeoAPRS."""
    try:
        return bool(servicecmd.backend_for(sys.platform).installed(servicecmd.Plan(sys.executable, data))[0])
    except Exception:  # an unreadable registry or unit counts as no service
        return False


def simulated(text: str) -> InstallInfo | None:
    """Return the kind `NEOAPRS_INSTALL_KIND` names, or None if it is empty or not a kind."""
    kind, *words = text.split() or [""]
    found = next((k for k in KINDS if k == kind), None)
    if found is None:
        return None
    arch = (
        next((w for w in words if w in ("amd64", "arm64")), "amd64")
        if found == "deb"
        else "arm64"
        if found == "macos-app"
        else ""
    )
    appimage = (
        next((w for w in words if w.startswith("/")), str(Path.home() / f"NeoAPRS-{VERSION}-x86_64.AppImage"))
        if found == "appimage"
        else ""
    )
    return InstallInfo(found, appimage, "service" in words, arch)


def detect_here(data: Path, environ: Mapping[str, str] = os.environ) -> InstallInfo:
    if fake := simulated(environ.get(ENV_KIND, "")):
        return fake
    return detect(
        bool(getattr(sys, "frozen", False)),
        servicecmd.appimage_file(),
        sys.prefix,
        servicecmd.source_tree(),
        service_set(data),
        environ,
    )
