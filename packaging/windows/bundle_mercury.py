"""Puts the Mercury that NeoAPRS built for Windows into the app folder: `bundle_mercury.py DIST/NeoAPRS TARBALL` makes DIST/NeoAPRS/bin/mercury/ with what the tarball holds in its folder `mercury/`: `mercury.exe` and the licences and
source offer beside it. TARBALL is the file `scripts/build-mercury --windows --tar` makes (the release workflow's job `mercury-windows` builds it from the pinned source of neoaprs/mercury.py on Linux with MinGW-w64, and the
Windows job downloads it); nothing is fetched here. The tarball is held to what it must be before anything is kept: its name is the pinned version's, its source offer names the pinned source and its SHA-256, it holds a program
(a file that begins with the DOS header of a Windows program) and nothing but plain files of a few known names, none of them a path out of the folder. Run with the Python that has NeoAPRS installed."""
import shutil
import sys
import tarfile
from pathlib import Path, PurePosixPath

from neoaprs import mercury

MAX_FILE = 64_000_000           # the biggest file taken out of the tarball (the program is 2.4 MB)
PROGRAM = "mercury.exe"


def tarball_name() -> str:
    """The name the tarball of the pinned version has (scripts/build-mercury says the same, from the same pins)."""
    return f"mercury-{mercury.VERSION}-windows-x86_64.tar.gz"


def refuse(message: str) -> SystemExit:
    return SystemExit(f"bundle_mercury: {message}")


def kept(name: str) -> bool:
    """Whether a file of the tarball's folder is one the app takes: the program, the source offer and the licences (LICENSE, LICENSE-freedv, LICENSE-hidapi.txt, ...)."""
    return name in (PROGRAM, "SOURCE.txt") or (name.startswith("LICENSE") and all(c.isalnum() or c in "._-" for c in name))


def unpack(archive: Path, folder: Path) -> list[Path]:
    """The files of `mercury/` in the tarball written to `folder`; SystemExit, with nothing kept, for a tarball that is not the pinned Mercury's for Windows."""
    if archive.name != tarball_name():
        raise refuse(f"{archive.name} is not {tarball_name()}, the file of the pinned Mercury {mercury.VERSION}")
    contents: dict[str, bytes] = {}
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or path.parts[:1] != ("mercury",):
                raise refuse(f"{member.name} is outside the folder mercury/ of the tarball")
            if member.isdir() and len(path.parts) == 1:
                continue
            if not member.isfile() or len(path.parts) != 2 or not kept(path.name):
                raise refuse(f"{member.name} is not a file the app takes from the tarball (the program, SOURCE.txt and the licences, flat in mercury/)")
            if member.size > MAX_FILE:
                raise refuse(f"{member.name} is {member.size} bytes: the tarball is not what it should be")
            handle = tar.extractfile(member)
            assert handle is not None
            contents[path.name] = handle.read()
    if PROGRAM not in contents or "SOURCE.txt" not in contents or "LICENSE" not in contents:
        raise refuse(f"the tarball lacks {PROGRAM}, SOURCE.txt or LICENSE")
    if contents[PROGRAM][:2] != b"MZ":
        raise refuse(f"{PROGRAM} is not a program for Windows")
    offer = contents["SOURCE.txt"].decode("utf-8", "replace")
    for pin in (f"Mercury {mercury.VERSION},", mercury.SOURCE_COMMIT, mercury.SOURCE_SHA256):
        if pin not in offer:
            raise refuse(f"SOURCE.txt does not name {pin}: this is not a Mercury built from the pinned source")
    folder.mkdir(parents=True)
    written: list[Path] = []
    for name, data in sorted(contents.items()):
        (folder / name).write_bytes(data)
        written.append(folder / name)
    return written


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0 if len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help") else 2
    folder = Path(sys.argv[1]) / "bin" / "mercury"
    archive = Path(sys.argv[2])
    if not archive.is_file():
        raise refuse(f"{archive} is not there")
    shutil.rmtree(folder, ignore_errors=True)
    for path in unpack(archive, folder):
        print(f"bundle_mercury: {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
