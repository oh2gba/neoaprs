"""Puts the pinned go-pmtiles for Windows into the app folder: `bundle_pmtiles.py DIST/NeoAPRS` makes DIST/NeoAPRS/bin/pmtiles.exe, downloaded from the release that neoaprs/pmtilestool.py pins and kept only when
its SHA-256 is the pinned one, and the licence text of the tool beside it (BSD-3-Clause). Run with the Python that has NeoAPRS installed."""
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from neoaprs import pmtilestool


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0 if len(sys.argv) == 2 else 2
    target = Path(sys.argv[1]) / "bin"
    target.mkdir(parents=True, exist_ok=True)
    asset = pmtilestool.asset_for("windows", "x86_64")
    with tempfile.TemporaryDirectory() as work:
        archive = Path(work) / asset.name
        pmtilestool._download(f"{pmtilestool.RELEASE_URL}/{asset.name}", archive, asset.sha256)           # (ToolError, and nothing kept, when the digest is not the pinned one)
        pmtilestool._unpack(archive, asset.kind, pmtilestool.tool_file("windows"), target / "pmtiles.exe")
        print(f"bundle_pmtiles: {target / 'pmtiles.exe'} ({(target / 'pmtiles.exe').stat().st_size} bytes) from {asset.name}, SHA-256 {asset.sha256} checked")
        with zipfile.ZipFile(archive) as z:
            licence = next((i for i in z.infolist() if PurePosixPath(i.filename).name.upper().startswith("LICENSE")), None)
            if licence is None:
                raise SystemExit(f"bundle_pmtiles: {asset.name} has no LICENSE file; the tool is BSD-3-Clause and its licence must travel with it")
            (target / "pmtiles-LICENSE.txt").write_bytes(z.read(licence))
            print(f"bundle_pmtiles: {licence.filename} -> pmtiles-LICENSE.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
