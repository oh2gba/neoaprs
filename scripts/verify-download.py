#!/usr/bin/env python3
"""Checks a file downloaded from a release by hand, as Update now checks it: SHA256SUMS must carry the project's signature (SHA256SUMS.sig, with the public key of neoaprs/updateasset.py) as the list of the
release, and must give the file the SHA-256 it has.

  scripts/verify-download.py FILE [--sums SHA256SUMS] [--signature SHA256SUMS.sig] [--version VERSION]

SHA256SUMS and SHA256SUMS.sig are looked for beside FILE unless they are named. The version is the one FILE is named for (`NeoAPRS-Setup-<version>.exe`, `neoaprs_<version>_amd64.deb`), or --version; a file
whose name carries none (`NeoAPRS-Setup.exe`) needs --version. The signature holds only for the version it was made for, so a list of another release, an older one too, does not pass for this one. Nothing is fetched. Exit code 0: the file is the release's; 1: it is not, or it cannot be told, and the line says why.
"""
import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from neoaprs.updateasset import CHECKSUMS, SIGNATURE, Unverified, public_key, release_version, signed_checksum  # noqa: E402

NAMED_FOR = re.compile(r"NeoAPRS-Setup-(.+)\.exe|NeoAPRS-(.+)-x86_64\.AppImage|NeoAPRS-(.+)-arm64\.dmg|neoaprs_(.+)_(?:amd64|arm64)\.deb")       # the files of a release whose name carries its version


def sha256(file: Path) -> str:
    digest = hashlib.sha256()
    with file.open("rb") as f:
        for piece in iter(lambda: f.read(1 << 20), b""):
            digest.update(piece)
    return digest.hexdigest()


def version_of(file: Path) -> str:
    """The version the file's own name carries; Unverified for a name that carries none (the files under fixed names), since the list that came with the file cannot say which release it ought to be."""
    found = NAMED_FOR.fullmatch(file.name)
    version = next((part for part in found.groups() if part), "") if found else ""
    if not release_version(version):
        raise Unverified(f"the name {file.name} carries no version: give the version of the release it was downloaded from with --version")
    return version


def check(file: Path, sums_file: Path, signature_file: Path, version: str | None) -> str:
    """The sentence that says the file is the release's; Unverified (or OSError) when it is not, or cannot be told."""
    version = version or version_of(file)
    sums = sums_file.read_bytes()
    signature = signature_file.read_bytes()
    expected = signed_checksum(sums, signature, version, file.name, public_key())
    got = sha256(file)
    if got != expected:
        raise Unverified(f"{file.name} is not the file of the release: its SHA-256 is {got}, the signed {CHECKSUMS} of v{version} says {expected}")
    return f"{file.name} is the file of NeoAPRS {version}: {CHECKSUMS} carries the project's signature and gives it the SHA-256 {got}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a downloaded file of a release against its signed SHA256SUMS.")
    parser.add_argument("file", type=Path, help="the downloaded file, under the name the release gives it")
    parser.add_argument("--sums", type=Path, help=f"the release's {CHECKSUMS} (default: beside the file)")
    parser.add_argument("--signature", type=Path, help=f"the release's {SIGNATURE} (default: beside the file)")
    parser.add_argument("--version", help="the version of the release (default: the one the file's name carries)")
    args = parser.parse_args(argv)
    sums_file = args.sums or args.file.with_name(CHECKSUMS)
    signature_file = args.signature or args.file.with_name(SIGNATURE)
    if args.version is not None and not release_version(args.version):
        print(f"verify-download: {args.version!r} is not a version of a release", file=sys.stderr)
        return 1
    try:
        print(check(args.file, sums_file, signature_file, args.version))
    except Unverified as e:
        print(f"verify-download: NOT VERIFIED: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"verify-download: {e.filename or args.file}: {e.strerror or e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
