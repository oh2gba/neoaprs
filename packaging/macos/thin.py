"""Cuts every universal (fat) Mach-O file of the app down to its arm64 part. The app is for Apple silicon alone (its launcher and its Python are arm64 only), but the Qt wheels are universal2: each of
their frameworks also carries an x86_64 half that no process of the app can ever load. Run by scripts/build-macos-app after prune.py and before the bytecode and the signing (thinning breaks the signatures the
wheels came with, and the ad-hoc signing after it signs every file again):

    thin.py APP             every fat file under APP thinned to arm64; the bytes saved are said
    thin.py --check APP     exit 1 naming every file that still has a part that is not arm64

A fat file begins with the universal header (cafebabe, or cafebabf for the 64-bit form); `lipo -archs` says what it holds, and a file that lipo does not take (a Java class file has the same first bytes) is
left as it is. A fat file without arm64 fails the build: it is code the app could not run. Links are not followed: the file they name is thinned where it is. Needs lipo (the command line tools of a Mac);
nothing but the Python standard library is used."""
import os
import subprocess
import sys
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

FAT_MAGIC = (b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf")
KEEP = "arm64"

Run = Callable[[list[str]], subprocess.CompletedProcess[str]]


class NotThinnable(Exception):
    """A fat file with no arm64 in it, or one lipo could not cut: the sentence of the build's failure."""


def run_lipo(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, timeout=300)


def fat_files(root: Path) -> Iterator[Path]:
    """Every regular file under `root` that begins with the universal header, in a stable order."""
    for folder, dirs, names in os.walk(root):
        dirs.sort()
        for name in sorted(names):
            path = Path(folder) / name
            if path.is_symlink() or not path.is_file():
                continue
            with path.open("rb") as handle:
                if handle.read(4) in FAT_MAGIC:
                    yield path


def archs(path: Path, run: Run = run_lipo) -> list[str] | None:
    """What lipo says the file holds; None when lipo does not take it (it is no Mach-O)."""
    done = run(["lipo", "-archs", str(path)])
    return done.stdout.split() if done.returncode == 0 else None


def thin(path: Path, run: Run = run_lipo) -> int:
    """The file cut down to arm64 in its place, with its mode; the bytes saved (0 for a file that is arm64 alone or no Mach-O)."""
    found = archs(path, run)
    if found is None or found == [KEEP]:
        return 0
    if KEEP not in found:
        raise NotThinnable(f"{path} holds {' '.join(found)} and no {KEEP}: the app could not run it")
    before = path.stat().st_size
    out = path.with_name(path.name + ".thin")
    done = run(["lipo", str(path), "-thin", KEEP, "-output", str(out)])
    if done.returncode != 0 or not out.is_file():
        out.unlink(missing_ok=True)
        raise NotThinnable(f"lipo could not cut {path} to {KEEP}: {(done.stderr or done.stdout).strip()}")
    os.chmod(out, path.stat().st_mode & 0o7777)
    out.replace(path)
    return before - path.stat().st_size


def thin_all(root: Path, run: Run = run_lipo) -> tuple[int, int]:
    """Every fat file under `root` thinned: how many were cut, and the bytes saved."""
    count = saved = 0
    for path in list(fat_files(root)):
        cut = thin(path, run)
        if cut:
            count += 1
            saved += cut
    return count, saved


def still_fat(root: Path, run: Run = run_lipo) -> list[str]:
    """The files under `root` that still hold more than arm64, each with what it holds."""
    out = []
    for path in fat_files(root):
        found = archs(path, run)
        if found is not None and found != [KEEP]:
            out.append(f"{path.relative_to(root)}: {' '.join(found)}")
    return out


def main(argv: Sequence[str] | None = None, run: Run = run_lipo) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    check = bool(args) and args[0] == "--check"
    if check:
        args = args[1:]
    if len(args) != 1 or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if args[:1] in (["-h"], ["--help"]) else 2
    root = Path(args[0])
    if not root.is_dir():
        print(f"thin: {root} is not a folder", file=sys.stderr)
        return 2
    if check:
        left = still_fat(root, run)
        if left:
            print(f"thin: {len(left)} file(s) of {root} still hold more than {KEEP}:\n" + "\n".join(f"  {line}" for line in left), file=sys.stderr)
            return 1
        print(f"thin: every Mach-O file of {root} is {KEEP} alone")
        return 0
    try:
        count, saved = thin_all(root, run)
    except NotThinnable as error:
        print(f"thin: {error}", file=sys.stderr)
        return 1
    print(f"thin: {count} file(s) cut to {KEEP}, {saved / 1_000_000:.1f} MB saved ({saved} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
