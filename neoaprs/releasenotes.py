"""What is new between the version this is and the latest one, read from the project's CHANGELOG.md as it is at the tag of the latest release (`changelog_url`): the sections of the versions newer than ours up to that one, the newest first, as the markdown
they are written in. The page shows them in the update dialog (What's new) instead of sending the operator to the release page; and, read the other way round, at the tag of our own version, what the update the operator has had brought
(the notes of our version, or of every version after the one the browser last saw up to ours), for the same window opened from Settings and from the line a page shows once after an update. No I/O here: the daily update
check fetches the file (neoaprs/services/updatecheck.py)."""
import re
from dataclasses import dataclass

from neoaprs.versions import compare_versions

CHANGELOG_URL = "https://raw.githubusercontent.com/oh2gba/neoaprs/v{version}/CHANGELOG.md"
MAX_BYTES = 262144                   # the whole changelog, with room to grow
_HEADING = re.compile(r"^## +(.*?)\s*$", re.M)
_VERSION = re.compile(r"(?<![\w.])(\d+(?:\.\d+){1,3}(?:[-+][0-9A-Za-z.]+)?)(?![\w.])")


@dataclass(frozen=True)
class Section:
    version: str
    text: str                        # the markdown under the heading, stripped


def changelog_url(version: str) -> str:
    return CHANGELOG_URL.format(version=version)


def sections(text: str) -> list[Section]:
    """Every section of the changelog whose heading names a version (`## 0.10.2`), in the order of the file; `## Unreleased` and anything before the first heading are left out."""
    parts = _HEADING.split(text)                                         # [before, heading, body, heading, body, ...]
    found = []
    for heading, body in zip(parts[1::2], parts[2::2]):
        version = _VERSION.search(heading)
        if version is not None:
            found.append(Section(version.group(1), body.strip()))
    return found


def between(found: list[Section], after: str, upto: str) -> list[Section]:
    """The sections of `found` of the versions newer than `after` and not newer than `upto`, the newest first."""
    wanted = [s for s in found if compare_versions(s.version, after) > 0 and compare_versions(s.version, upto) <= 0]
    return sorted(wanted, key=lambda s: [-compare_versions(s.version, other.version) for other in wanted])


def section_of(found: list[Section], version: str) -> list[Section]:
    """The section of `version` alone, or none when the changelog has no heading of it."""
    return [s for s in found if compare_versions(s.version, version) == 0][:1]


def sections_after(text: str, installed: str, latest: str) -> list[Section]:
    """The sections of the versions newer than `installed` and not newer than `latest`, the newest first: what is new for an operator who updates from the one to the other."""
    return between(sections(text), installed, latest)
