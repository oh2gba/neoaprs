"""What is new between the version this is and the latest one, read from the project's CHANGELOG.md as it is at the tag of the latest release (`changelog_url`): the sections of the versions newer than ours up to that one, the newest first, as the markdown
they are written in. The page shows them in the update dialog (What's new) instead of sending the operator to the release page. No I/O here: the daily update check fetches the file (neoaprs/services/updatecheck.py)."""
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


def sections_after(text: str, installed: str, latest: str) -> list[Section]:
    """The sections of the versions newer than `installed` and not newer than `latest`, the newest first: what is new for an operator who updates from the one to the other."""
    wanted = [s for s in sections(text) if compare_versions(s.version, installed) > 0 and compare_versions(s.version, latest) <= 0]
    return sorted(wanted, key=lambda s: [-compare_versions(s.version, other.version) for other in wanted])
