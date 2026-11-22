#!/usr/bin/env python3
"""Check a downloaded release file as Update now does: signed SHA256SUMS gives its SHA-256.

  scripts/verify-download.py FILE [--sums SUMS] [--signature SIG] [--version VERSION]
Both are looked for beside FILE; a file name without a version needs --version. Exit 0: verified."""

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from neoaprs.updateasset import CHECKSUMS, SIGNATURE, Unverified, public_key, release_version, signed_checksum  # noqa: E402

# The release files whose name carries the version.
NAMED_FOR = re.compile(
    r"NeoAPRS-Setup-(.+)\.exe|NeoAPRS-(.+)-x86_64\.AppImage|NeoAPRS-(.+)-arm64\.dmg|neoaprs_(.+)_(?:amd64|arm64)\.deb"
)


def sha256(file: Path) -> str:
    digest = hashlib.sha256()
    with file.open("rb") as f:
        for piece in iter(lambda: f.read(1 << 20), b""):
            digest.update(piece)
    return digest.hexdigest()


def version_of(file: Path) -> str:
    """Return the version in the file's name; Unverified if there is none (fixed names)."""
    found = NAMED_FOR.fullmatch(file.name)
    version = next((part for part in found.groups() if part), "") if found else ""
    if not release_version(version):
        raise Unverified(
            f"the name {file.name} carries no version: give the version of the release it was downloaded from with --version"
        )
    return version


def check(file: Path, sums_file: Path, signature_file: Path, version: str | None) -> str:
    """Return the sentence saying the file is the release's; raise Unverified if it is not."""
    version = version or version_of(file)
    sums = sums_file.read_bytes()
    signature = signature_file.read_bytes()
    expected = signed_checksum(sums, signature, version, file.name, public_key())
    got = sha256(file)
    if got != expected:
        raise Unverified(
            f"{file.name} is not the file of the release: its SHA-256 is {got}, the signed {CHECKSUMS} of v{version} says {expected}"
        )
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
