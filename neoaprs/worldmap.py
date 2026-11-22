"""Locate the world map shipped with NeoAPRS, so the page has a map from the first start.

`neoaprs/maps/basemap-world.pmtiles` is the world to zoom 4 (about 6 MB); `scripts/fetch-worldmap`
regenerates it. It is package data, served when the data folder has no usable file of its own.
"""

import sys
from pathlib import Path

from neoaprs.pmtilesarchive import read_header

WORLD_FILE = "basemap-world.pmtiles"
# The deepest zoom of the shipped file (zoom 5 is 15 MB, zoom 4 is 6 MB).
SHIPPED_ZOOM = 4
MAPS_DIR = "maps"


def search_folders(
    code_dir: Path | None = None, frozen: bool | None = None, bundle: str | None = None, executable: str | None = None
) -> list[Path]:
    """Return the folders the shipped map may be in: beside this module, and when frozen, in the bundle."""
    here = (code_dir if code_dir is not None else Path(__file__).resolve().parent) / MAPS_DIR
    folders = [here]
    if frozen if frozen is not None else getattr(sys, "frozen", False):
        root = bundle if bundle is not None else getattr(sys, "_MEIPASS", None)
        if root:
            folders.append(Path(root) / "neoaprs" / MAPS_DIR)
        folders.append(Path(executable or sys.executable).resolve().parent / "_internal" / "neoaprs" / MAPS_DIR)
    return list(dict.fromkeys(folders))


def usable(path: Path) -> bool:
    """Return whether it is a PMTiles archive with a readable header; a damaged file is unusable."""
    return read_header(path) is not None


def shipped_world(folders: list[Path] | None = None) -> Path | None:
    """Return the world map shipped with the program, or None if the file is missing."""
    for folder in folders if folders is not None else search_folders():
        if usable(folder / WORLD_FILE):
            return folder / WORLD_FILE
    return None


def world_file(data_dir: Path, folders: list[Path] | None = None) -> Path | None:
    """Return the world map to serve: the data folder's if usable, else the shipped one."""
    own = data_dir / WORLD_FILE
    return own if usable(own) else shipped_world(folders)
