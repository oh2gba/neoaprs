"""Lists the Mach-O files of NeoAPRS.app that are signed by themselves, one path per line: `sign_list.py NeoAPRS.app`. Run by scripts/build-macos-app in front of `codesign --sign -`, one file at a time.

Left out is every program that is a bundle's own: the launcher in Contents/MacOS, the web engine's helper in its app's MacOS folder, and each framework's library (`X.framework/Versions/A/X`). codesign given the path of
such a program does not sign that file but seals its bundle, there and then, and the seal fails on a nested bundle that is not signed yet (the helper app inside QtWebEngineCore.framework) or, while other
files under the bundle are being replaced, on a file that is gone for a moment. The bundles are signed afterwards, from the inside out, by scripts/build-macos-app. Standard library only."""
import sys
from pathlib import Path

MAGIC = {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe"}          # Mach-O 64, 32, and a universal file


def bundle_program(path: Path) -> bool:
    """Is this the program of a bundle: a file in a MacOS folder, or the library of a framework (`X.framework/Versions/A/X`)?"""
    if path.parent.name == "MacOS":
        return True
    versions = path.parent.parent
    return versions.name == "Versions" and versions.parent.suffix == ".framework" and path.name == versions.parent.stem


def mach_o(path: Path) -> bool:
    with path.open("rb") as f:
        return f.read(4) in MAGIC


def sign_list(root: Path) -> list[Path]:
    """The Mach-O files under `root` that are signed by themselves, in path order; links and bundle programs left out."""
    return sorted(path for path in root.rglob("*") if path.is_file() and not path.is_symlink() and not bundle_program(path) and mach_o(path))


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0 if len(argv) == 2 else 2
    for path in sign_list(Path(argv[1])):
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
