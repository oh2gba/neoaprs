"""Put the Mercury that NeoAPRS built for Windows into the app folder.

`bundle_mercury.py DIST/NeoAPRS TARBALL` makes DIST/NeoAPRS/bin/mercury/ from the tarball that
`scripts/build-mercury --windows --tar` makes. It is `bundle_tool.py mercury` under its own name; the
checks on the tarball are in bundle_tool.py. Run with the Python that has NeoAPRS installed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bundle_tool  # noqa: E402

TOOL = bundle_tool.TOOLS["mercury"]
WHO = "bundle_mercury"
MAX_FILE = bundle_tool.MAX_FILE
PROGRAM = TOOL.program


def tarball_name() -> str:
    return bundle_tool.tarball_name(TOOL)


def refuse(message: str) -> SystemExit:
    return bundle_tool.refuse(message, WHO)


def kept(name: str) -> bool:
    return bundle_tool.kept(TOOL, name)


def unpack(archive: Path, folder: Path) -> list[Path]:
    return bundle_tool.unpack(TOOL, archive, folder, WHO)


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0 if len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help") else 2
    return bundle_tool.bundle(TOOL, Path(sys.argv[1]), Path(sys.argv[2]), WHO)


if __name__ == "__main__":
    sys.exit(main())
