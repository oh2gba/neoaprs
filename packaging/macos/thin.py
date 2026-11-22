"""Cut every universal (fat) Mach-O file of the app down to its arm64 part.

Run by scripts/build-macos-app after prune.py and before signing. Needs lipo.

    thin.py APP             every fat file under APP thinned to arm64; the bytes saved are said
    thin.py --check APP     exit 1 naming every file that still has a part that is not arm64

A fat file without arm64 fails the build. Links are not followed."""
import os
import subprocess
import sys
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

FAT_MAGIC = (b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf")
KEEP = "arm64"

Run = Callable[[list[str]], subprocess.CompletedProcess[str]]


class NotThinnable(Exception):
    """A fat file with no arm64 in it, or one lipo could not cut."""


def run_lipo(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, timeout=300)


def fat_files(root: Path) -> Iterator[Path]:
    """Yield the regular files under `root` that begin with the universal header, in order."""
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
    """Return what lipo says the file holds; None if lipo rejects it (e.g. a Java class)."""
    done = run(["lipo", "-archs", str(path)])
    return done.stdout.split() if done.returncode == 0 else None


def thin(path: Path, run: Run = run_lipo) -> int:
    """Cut the file to arm64 in place, keeping its mode; return the bytes saved."""
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
    """Thin every fat file under `root`; return how many were cut and the bytes saved."""
    count = saved = 0
    for path in list(fat_files(root)):
        cut = thin(path, run)
        if cut:
            count += 1
            saved += cut
    return count, saved


def still_fat(root: Path, run: Run = run_lipo) -> list[str]:
    """Return the files under `root` that still hold more than arm64."""
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
