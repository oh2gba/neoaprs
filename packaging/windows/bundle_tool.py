"""Put a program that NeoAPRS built for Windows into the app folder.

`bundle_tool.py NAME DIST/NeoAPRS TARBALL` makes DIST/NeoAPRS/bin/NAME/ from the tarball that
`scripts/build-mercury --windows --tar` or `scripts/build-direwolf --windows --tar` makes. NAME is
`mercury` or `direwolf`. The tarball must be the pinned version's, with a source offer naming the
pinned source, a Windows program and only plain files of known names. Run with the Python that has
NeoAPRS installed."""

import shutil
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import ModuleType

from neoaprs import direwolf, mercury

# Largest file taken out of a tarball (mercury.exe is 2.4 MB).
MAX_FILE = 64_000_000


@dataclass(frozen=True)
class Tool:
    name: str  # folder in the tarball and in bin/
    title: str  # how its source offer names it first: "Mercury 1.9.24,"
    pins: ModuleType  # module with VERSION, SOURCE_COMMIT and SOURCE_SHA256
    data: tuple[str, ...] = ()

    @property
    def program(self) -> str:
        return f"{self.name}.exe"


TOOLS = {
    "mercury": Tool("mercury", "Mercury", mercury),
    "direwolf": Tool("direwolf", "Direwolf", direwolf, ("data/tocalls.yaml", "data/symbols-new.txt")),
}
# A program bundled only after the other: the Sound card type lists cards with `mercury -z`.
BESIDE = {"direwolf": "mercury"}


def tarball_name(tool: Tool) -> str:
    """Return the file name of the pinned version's tarball."""
    return f"{tool.name}-{tool.pins.VERSION}-windows-x86_64.tar.gz"


def refuse(message: str, who: str = "bundle_tool") -> SystemExit:
    return SystemExit(f"{who}: {message}")


def kept(tool: Tool, name: str) -> bool:
    """Return whether the app takes this file: the program, source offer, licences and data
    files."""
    return name in (tool.program, "SOURCE.txt", *tool.data) or (
        "/" not in name and name.startswith("LICENSE") and all(c.isalnum() or c in "._-" for c in name)
    )


def unpack(tool: Tool, archive: Path, folder: Path, who: str = "bundle_tool") -> list[Path]:
    """Write the files of `NAME/` to `folder`; raise SystemExit, keeping nothing, if it is wrong."""
    if archive.name != tarball_name(tool):
        raise refuse(
            f"{archive.name} is not {tarball_name(tool)}, the file of the pinned {tool.title} {tool.pins.VERSION}", who
        )
    contents: dict[str, bytes] = {}
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or path.parts[:1] != (tool.name,):
                raise refuse(f"{member.name} is outside the folder {tool.name}/ of the tarball", who)
            inside = "/".join(path.parts[1:])
            if member.isdir() and (len(path.parts) == 1 or any(d.startswith(inside + "/") for d in tool.data)):
                continue
            if not member.isfile() or not kept(tool, inside):
                raise refuse(
                    f"{member.name} is not a file the app takes from the tarball (the program, SOURCE.txt and the licences, flat in {tool.name}/{', and its data files' if tool.data else ''})",
                    who,
                )
            if member.size > MAX_FILE:
                raise refuse(f"{member.name} is {member.size} bytes: the tarball is not what it should be", who)
            handle = tar.extractfile(member)
            assert handle is not None
            contents[inside] = handle.read()
    if (
        tool.program not in contents
        or "SOURCE.txt" not in contents
        or "LICENSE" not in contents
        or any(d not in contents for d in tool.data)
    ):
        raise refuse(
            f"the tarball lacks {tool.program}, SOURCE.txt or LICENSE" + (", or a data file" if tool.data else ""), who
        )
    if contents[tool.program][:2] != b"MZ":
        raise refuse(f"{tool.program} is not a program for Windows", who)
    offer = contents["SOURCE.txt"].decode("utf-8", "replace")
    for pin in (f"{tool.title} {tool.pins.VERSION},", tool.pins.SOURCE_COMMIT, tool.pins.SOURCE_SHA256):
        if not pin or pin not in offer:
            raise refuse(
                f"SOURCE.txt does not name {pin or 'a pinned SHA-256'}: this is not a {tool.title} built from the pinned source",
                who,
            )
    folder.mkdir(parents=True)
    written: list[Path] = []
    for name, data in sorted(contents.items()):
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(data)
        written.append(folder / name)
    return written


def bundle(tool: Tool, dist: Path, archive: Path, who: str = "bundle_tool") -> int:
    folder = dist / "bin" / tool.name
    if not archive.is_file():
        raise refuse(f"{archive} is not there", who)
    if (other := BESIDE.get(tool.name)) is not None and not (dist / "bin" / other / TOOLS[other].program).is_file():
        raise refuse(
            f"{tool.title} is bundled after {TOOLS[other].title}, which {dist} does not have yet: the Sound card type lists the sound cards with it",
            who,
        )
    shutil.rmtree(folder, ignore_errors=True)
    for path in unpack(tool, archive, folder, who):
        print(f"{who}: {path} ({path.stat().st_size} bytes)")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 3 or args[0] not in TOOLS:
        print(__doc__)
        return 0 if args[:1] in (["-h"], ["--help"]) else 2
    return bundle(TOOLS[args[0]], Path(args[1]), Path(args[2]))


if __name__ == "__main__":
    sys.exit(main())
