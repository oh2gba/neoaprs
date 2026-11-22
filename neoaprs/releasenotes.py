"""Pick the changelog sections between two versions out of the project's CHANGELOG.md.

The page shows them as markdown in the update dialog (What's new): for the latest release, and
for the notes of an update just installed. No I/O here; the daily update check fetches the file.
"""

import re
from dataclasses import dataclass

from neoaprs.versions import compare_versions

CHANGELOG_URL = "https://raw.githubusercontent.com/oh2gba/neoaprs/v{version}/CHANGELOG.md"
# A longer changelog answer counts as a failed fetch.
MAX_BYTES = 2 * 1024 * 1024
_HEADING = re.compile(r"^## +(.*?)\s*$", re.M)
_VERSION = re.compile(r"(?<![\w.])(\d+(?:\.\d+){1,3}(?:[-+][0-9A-Za-z.]+)?)(?![\w.])", re.ASCII)


@dataclass(frozen=True)
class Section:
    version: str
    # The markdown under the heading, stripped.
    text: str


def changelog_url(version: str) -> str:
    return CHANGELOG_URL.format(version=version)


def sections(text: str) -> list[Section]:
    """Return the sections whose heading names a version (`## 0.10.2`), in file order."""
    # [before, heading, body, heading, body, ...]
    parts = _HEADING.split(text)
    found = []
    for heading, body in zip(parts[1::2], parts[2::2]):
        version = _VERSION.search(heading)
        if version is not None:
            found.append(Section(version.group(1), body.strip()))
    return found


def between(found: list[Section], after: str, upto: str) -> list[Section]:
    """Return the sections newer than `after` and not newer than `upto`, newest first."""
    wanted = [s for s in found if compare_versions(s.version, after) > 0 and compare_versions(s.version, upto) <= 0]
    return sorted(wanted, key=lambda s: [-compare_versions(s.version, other.version) for other in wanted])


def section_of(found: list[Section], version: str) -> list[Section]:
    """Return the section of `version` alone, or an empty list if there is none."""
    return [s for s in found if compare_versions(s.version, version) == 0][:1]


def sections_after(text: str, installed: str, latest: str) -> list[Section]:
    """Return the sections newer than `installed` and not newer than `latest`, newest first."""
    return between(sections(text), installed, latest)
