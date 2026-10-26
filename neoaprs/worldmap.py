"""The world map that ships with NeoAPRS, so that the page has a map from the first start: `neoaprs/maps/basemap-world.pmtiles`, the world to zoom 4 (about 6 MB) cut from a Protomaps daily build, with
`basemap-world.json` beside it saying which build. `scripts/fetch-worldmap` makes it again (docs/development.md, "The world map").

It is package data, so it is wherever the package is: beside the code in a clone and in a wheel (which is also what the AppImage and the .deb hold, in their site-packages), and in the folder of the Windows
app's frozen libraries (PyInstaller's `_internal`, `sys._MEIPASS`), where the package's files are put as they are in a wheel. The daemon serves it as the world map when the data folder has no
`basemap-world.pmtiles` of its own (or one that is no PMTiles file), and nothing is copied. A file counts only when its header can be read."""
import sys
from pathlib import Path

from neoaprs.pmtilestool import read_header

WORLD_FILE = "basemap-world.pmtiles"
SHIPPED_ZOOM = 4                            # the deepest zoom of the shipped file (zoom 5 is 15 MB, zoom 4 six)
MAPS_DIR = "maps"


def search_folders(code_dir: Path | None = None, frozen: bool | None = None, bundle: str | None = None, executable: str | None = None) -> list[Path]:
    """The folders the shipped map may be in, the likeliest first: `maps/` of the package beside this module and, for a frozen program, the same folder under the bundle's own (`sys._MEIPASS`) and under `_internal`
    next to the executable."""
    here = (code_dir if code_dir is not None else Path(__file__).resolve().parent) / MAPS_DIR
    folders = [here]
    if frozen if frozen is not None else getattr(sys, "frozen", False):
        root = bundle if bundle is not None else getattr(sys, "_MEIPASS", None)
        if root:
            folders.append(Path(root) / "neoaprs" / MAPS_DIR)
        folders.append(Path(executable or sys.executable).resolve().parent / "_internal" / "neoaprs" / MAPS_DIR)
    return list(dict.fromkeys(folders))


def usable(path: Path) -> bool:
    """Is it a PMTiles archive whose header can be read? A file that is not (cut short, written over) cannot be drawn."""
    return read_header(path) is not None


def shipped_world(folders: list[Path] | None = None) -> Path | None:
    """The world map that came with the program, None when there is none (a clone that has not got the file, a package that was stripped of it)."""
    for folder in folders if folders is not None else search_folders():
        if usable(folder / WORLD_FILE):
            return folder / WORLD_FILE
    return None


def world_file(data_dir: Path, folders: list[Path] | None = None) -> Path | None:
    """The world map to serve and to describe: the data folder's own when it is a good one (a world map the daemon made, zoom 5), else the shipped one; None when there is neither."""
    own = data_dir / WORLD_FILE
    return own if usable(own) else shipped_world(folders)
