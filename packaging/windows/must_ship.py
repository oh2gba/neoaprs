"""The guard against a Windows folder that is too lean: every file of
packaging/windows/must-ship.txt must be in the frozen app's folder, or the build fails, before
anything is packed. A DLL left out is not seen by any test on GitHub's runner, which has Visual C++
and much else installed; it is seen on a clean Windows, at an operator's. So the list is taken from
a real build, and a line leaves it only in the commit that removes the file on purpose, with the
clean install on the Windows 11 N machine as its proof.

    must_ship.py LIST TREE              the check: exit 1 naming each listed file that TREE
                                        (dist/NeoAPRS) lacks
    must_ship.py --write LIST TREE      LIST made from TREE: every .dll and .pyd in it, and the data
                                        files named below; refused when TREE lacks one of the
                                        never-drop files (the list
                                        the folder would give is printed all the same, so that the
                                        names a real build has can be read)
    must_ship.py --excluded WARN MODULE [IMPORTER...]
                                        a module the spec excludes (PIL) is imported only by the
                                        modules named, by PyInstaller's own record of who imports it
                                        (WARN, build/neoaprs/warn-neoaprs.txt):
                                        exit 1 naming any other importer, whose import would fail in
                                        the frozen app; exit 2 when WARN is no such record

A line of the list is a path inside the folder, with forward slashes. A line with * ? or [ is a
pattern that must match one file at least (* matches across folders). Case is ignored, as Windows
ignores it. Lines that begin with # are comments. The never-drop files (NEVER_DROP) are checked
whatever the list says. A .dll or .pyd that is in the folder and not in the list is named, without
failing: a new package's DLLs go into the list in the commit that brings them. Nothing but the
Python standard library is used."""

import fnmatch
import re
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

# What the app cannot start without, by exact name so that another architecture's copy of a DLL
# cannot stand in: runtime, Python, OpenSSL, cryptography, pythonnet, WebView2, start-up imports.
# A * stands only for a version in a name.
NEVER_DROP = (
    "_internal/vcruntime140.dll",
    "_internal/vcruntime140_1.dll",
    "_internal/python313.dll",
    "_internal/libcrypto-3*.dll",
    "_internal/libssl-3*.dll",
    "_internal/libffi-*.dll",
    "_internal/sqlite3.dll",
    "_internal/_asyncio.pyd",
    "_internal/_ctypes.pyd",
    "_internal/_hashlib.pyd",
    "_internal/_overlapped.pyd",
    "_internal/_socket.pyd",
    "_internal/_sqlite3.pyd",
    "_internal/_ssl.pyd",
    "_internal/select.pyd",
    "_internal/_cffi_backend*.pyd",
    "_internal/cryptography/hazmat/bindings/_rust.pyd",
    "_internal/pydantic_core/_pydantic_core*.pyd",
    "_internal/pythonnet/runtime/python.runtime.dll",
    "_internal/clr_loader/ffi/dlls/amd64/clrloader.dll",
    "_internal/webview/lib/microsoft.web.webview2.core.dll",
    "_internal/webview/lib/microsoft.web.webview2.winforms.dll",
    "_internal/webview/lib/runtimes/win-x64/native/webview2loader.dll",
    "_internal/base_library.zip",
    "_internal/certifi/cacert.pem",
    "_internal/neoaprs/maps/basemap-world.pmtiles",
    "_internal/neoaprs/desktop/icon.ico",
)
NATIVE = (".dll", ".pyd")
DATA = (
    "_internal/base_library.zip",
    "_internal/certifi/cacert.pem",
    "_internal/neoaprs/maps/basemap-world.pmtiles",
    "_internal/neoaprs/desktop/icon.ico",
)
HEADER = """# The files the Windows app's folder (dist/NeoAPRS) must have, checked by packaging/windows/must_ship.py after PyInstaller in the release workflow: a build that lacks one fails.
# Made from a real build (must_ship.py --write); a line goes only in the commit that removes its file on purpose, and that commit names the clean install on the Windows 11 N machine that proves it.
"""


def is_pattern(line: str) -> bool:
    return any(char in line for char in "*?[")


def read_list(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def files_of(tree: Path) -> list[str]:
    """Every file of the folder, as a path inside it with forward slashes, in lower case."""
    return sorted(path.relative_to(tree).as_posix().lower() for path in tree.rglob("*") if path.is_file())


def missing(lines: Iterable[str], files: Sequence[str]) -> list[str]:
    """The lines that the folder does not satisfy: a path that is not there, a pattern that matches
    nothing."""
    there = set(files)
    out = []
    for line in lines:
        wanted = line.lower()
        if not (any(fnmatch.fnmatchcase(name, wanted) for name in files) if is_pattern(wanted) else wanted in there):
            out.append(line)
    return out


def unlisted(lines: Iterable[str], files: Sequence[str]) -> list[str]:
    """The .dll and .pyd files of the folder that no line names (patterns do not count: a pattern
    holds one file at least, not every one)."""
    named = {line.lower() for line in lines if not is_pattern(line)}
    return [name for name in files if name.endswith(NATIVE) and name not in named]


def covers(lines: Iterable[str], pattern: str) -> bool:
    """Whether some line of the list holds a file that `pattern` names: the pattern itself, or a
    path it matches."""
    return any(
        line.lower() == pattern or (not is_pattern(line) and fnmatch.fnmatchcase(line.lower(), pattern))
        for line in lines
    )


def made_list(tree: Path) -> str:
    """The list of a folder: its .dll and .pyd files and the data files, as they are spelled
    there."""
    names = sorted(
        path.relative_to(tree).as_posix()
        for path in tree.rglob("*")
        if path.is_file() and (path.suffix.lower() in NATIVE or path.relative_to(tree).as_posix().lower() in DATA)
    )
    return HEADER + "".join(f"{name}\n" for name in sorted(names, key=str.lower))


def check(list_text: str, tree: Path) -> tuple[list[str], list[str]]:
    """What is missing (the list's lines and the never-drop ones) and what is unlisted."""
    lines = read_list(list_text)
    files = files_of(tree)
    gone = missing(lines, files) + [
        pattern for pattern in missing(NEVER_DROP, files) if pattern not in [line.lower() for line in lines]
    ]
    return gone, unlisted(lines, files)


# A line of PyInstaller's warn file: `excluded module named PIL - imported by pystray._xorg
# (top-level), pystray._gtk (top-level)`; each importer is a module's name and, in brackets, how it
# imports.
RECORD = re.compile(r"^(?P<kind>missing|excluded) module named (?P<name>\S+) - imported by (?P<by>.*)$", re.M)
IMPORTER = re.compile(r"([\w.]+) \([^)]*\)")


class NoRecord(Exception):
    pass


def importers_of(warn: str, module: str) -> list[str]:
    """The modules that import `module` (or one of its submodules) though the spec excludes it, as
    PyInstaller recorded them; NoRecord when the text has no line of that record at all, so that a
    file of another form is never read as "nobody imports it"."""
    records = list(RECORD.finditer(warn))
    if not records:
        raise NoRecord("it holds no line 'missing module named' or 'excluded module named' of PyInstaller")
    found: list[str] = []
    for record in records:
        name = record.group("name")
        if record.group("kind") == "excluded" and (name == module or name.startswith(module + ".")):
            found += [by for by in IMPORTER.findall(record.group("by")) if by not in found]
    return found


def excluded(args: Sequence[str]) -> int:
    warn, module, allowed = Path(args[0]), args[1], set(args[2:])
    try:
        found = importers_of(warn.read_text(encoding="utf-8", errors="replace"), module)
    except (OSError, NoRecord) as error:
        print(f"must_ship: {warn} cannot tell who imports {module}: {error}", file=sys.stderr)
        return 2
    print(f"must_ship: {module} is excluded, and imported by {', '.join(found) if found else 'no module'}")
    wrong = [name for name in found if name not in allowed]
    if wrong:
        print(
            f"must_ship: {module} is left out of the app, and these import it, so their import fails in the frozen app: {', '.join(wrong)}",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["--excluded"]:
        if len(args) < 3:
            print(__doc__)
            return 2
        return excluded(args[1:])
    write = bool(args) and args[0] == "--write"
    if write:
        args = args[1:]
    if len(args) != 2 or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if args[:1] in (["-h"], ["--help"]) else 2
    listing, tree = Path(args[0]), Path(args[1])
    if not tree.is_dir():
        print(f"must_ship: {tree} is not a folder", file=sys.stderr)
        return 2
    if write:
        absent = missing(NEVER_DROP, files_of(tree))
        if absent:
            print(made_list(tree), end="")
            print(
                f"must_ship: {tree} lacks what the app cannot run without, so no list is made of it: {', '.join(absent)} (above: the list the folder would give)",
                file=sys.stderr,
            )
            return 1
        listing.write_text(made_list(tree), encoding="utf-8", newline="\n")
        print(f"must_ship: {listing} lists {len(read_list(listing.read_text(encoding='utf-8')))} files of {tree}")
        return 0
    if not listing.is_file():
        print(f"must_ship: {listing} is not there", file=sys.stderr)
        return 2
    gone, extra = check(listing.read_text(encoding="utf-8"), tree)
    for name in extra:
        print(
            f"must_ship: {name} is in the folder and not in {listing.name} (a new file: add it to the list in the commit that brings it)"
        )
    if gone:
        print(
            f"must_ship: {tree} lacks {len(gone)} file(s) the app needs, of {listing.name}:\n"
            + "\n".join(f"  {line}" for line in gone),
            file=sys.stderr,
        )
        return 1
    print(f"must_ship: every file of {listing.name} is in {tree}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
