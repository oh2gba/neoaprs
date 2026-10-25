#!/usr/bin/env python3
"""Prints the notes of a release: the text of CHANGELOG.md under the newest `## ` heading that has any (an empty `## Unreleased` above the newest release is skipped), or, with a VERSION, under the
heading that names it (`## 0.1.0`); the heading line itself is left out.

  scripts/release-notes.py [VERSION] [--changelog FILE]

The release workflow gives it to `gh release create --notes-file`. Exit code 1 when the changelog has no section for the VERSION, or the section is empty: a release is not made without notes.
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def section(text: str, version: str | None) -> str | None:
    """The body of the section whose heading names `version` (the first section that has a body when there is no version: the empty Unreleased of a tree just released is passed over), or None."""
    parts = re.split(r"^## (.*)$", text, flags=re.M)             # [before, heading, body, heading, body, ...]
    for heading, body in zip(parts[1::2], parts[2::2]):
        if version is not None and re.search(rf"(?<![\w.]){re.escape(version)}(?![\w.])", heading):
            return body.strip() or None
        if version is None and body.strip():
            return body.strip()
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Print the changelog section of a release, for the notes of the GitHub release.")
    parser.add_argument("version", nargs="?", help="the version whose section to print (default: the newest section)")
    parser.add_argument("--changelog", default=str(ROOT / "CHANGELOG.md"), metavar="FILE", help="default %(default)s")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")                   # type: ignore[union-attr]  (the changelog has arrows and dashes; a Windows console is not UTF-8)
    body = section(Path(args.changelog).read_text(encoding="utf-8"), args.version)
    if body is None:
        print(f"release-notes: {args.changelog} has no non-empty section" + (f" for {args.version}" if args.version else ""), file=sys.stderr)
        return 1
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
