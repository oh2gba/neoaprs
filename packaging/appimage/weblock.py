#!/usr/bin/env python3
"""Pinned requirements of the AppImage's web window (build-appimage --window web), from uv.lock.

Run with the image's Python: weblock.py UV_LOCK > requirements-web.txt; weblock.py --binary prints
the names that must come as wheels, one a line."""

import re
import sys
import tomllib

PACKAGES = ("pywebview", "proxy-tools", "bottle", "typing-extensions", "pystray", "six", "pillow")
# No wheel on PyPI; pure Python, so its sdist is as good.
SOURCE_ONLY = ("proxy-tools",)
PYTHON_TAG = "cp313"  # the image's CPython (scripts/build-appimage's PYTHON_URL)
PILLOW_URL = "https://files.pythonhosted.org/packages/ef/fe/f5cdaa2d1c4086e757430f368c271a58ee29cfe7378e7ae7b9d964015c25/pillow-13.0.0-cp313-cp313-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl"
PILLOW_SHA256 = "5f56499c1a74d2b862beb0c33b8016f99d095858455df9d21583bbbc1c15b582"
# Packages whose wheel for the image uv.lock lacks: URL and digest.
PINNED = {"pillow": (PILLOW_URL, PILLOW_SHA256)}


def runs_here(filename: str) -> bool:
    """Return whether a wheel of this name runs in the image."""
    if not filename.endswith(".whl"):
        return False
    tags = filename[:-4].split("-")[-3:]
    if len(tags) != 3:
        return False
    python, abi, platforms = tags
    if abi == "none" and platforms == "any":
        return True
    return (
        PYTHON_TAG in python.split(".")
        and abi in (PYTHON_TAG, "abi3")
        and any(p.startswith("manylinux") and p.endswith("_x86_64") for p in platforms.split("."))
    )


def binary() -> list[str]:
    return [name for name in PACKAGES if name not in SOURCE_ONLY]


def _pinned_line(name: str, version: str, url: str, digest: str) -> str:
    filename = url.rsplit("/", 1)[-1]
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise SystemExit(
            f"weblock: the digest of {filename} is not pinned yet: put the sha256 PyPI gives for it into packaging/appimage/weblock.py"
        )
    if not filename.startswith(f"{name}-{version}-") or not runs_here(filename):
        raise SystemExit(
            f"weblock: the pinned {filename} is not {name} {version} of uv.lock for the image's CPython on x86_64 Linux"
        )
    return f"{name} @ {url} --hash=sha256:{digest}"


def requirements(lock: dict[str, object], pinned: dict[str, tuple[str, str]] | None = None) -> list[str]:
    """Return one pip requirement line with digests per package; raise SystemExit if one is
    missing."""
    pinned = PINNED if pinned is None else pinned
    found = {str(p["name"]): p for p in lock["package"] if isinstance(p, dict)}  # type: ignore[attr-defined]
    lines: list[str] = []
    for name in PACKAGES:
        package = found.get(name)
        if package is None:
            raise SystemExit(f"weblock: uv.lock has no {name}")
        version = str(package["version"])
        if name in pinned:
            lines.append(_pinned_line(name, version, *pinned[name]))
            continue
        files = [a for a in package.get("wheels", []) if runs_here(str(a.get("url", "")).rsplit("/", 1)[-1])]
        if name in SOURCE_ONLY and "sdist" in package:
            files.append(package["sdist"])
        hashes = [str(a["hash"]) for a in files if str(a.get("hash", "")).startswith("sha256:")]
        if not hashes:
            raise SystemExit(
                f"weblock: uv.lock has no wheel of {name} {version} with a digest for the image's CPython on x86_64 Linux"
            )
        lines.append(f"{name}=={version} " + " ".join(f"--hash={h}" for h in hashes))
    return lines


def main() -> int:
    if sys.argv[1:] == ["--binary"]:
        print("\n".join(binary()))
        return 0
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with open(sys.argv[1], "rb") as f:
        print("\n".join(requirements(tomllib.load(f))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
