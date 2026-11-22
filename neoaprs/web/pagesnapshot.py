"""The page files, read into memory once at start.

Requests are answered from memory, so a rebuilt page on disk changes nothing until the daemon
restarts; page and daemon always match.
"""
import hashlib
import logging
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePath
from typing import Iterator, Mapping

log = logging.getLogger("neoaprs.web")

# A bigger folder is not a page (a wrong folder was given).
MAX_BYTES = 64 * 1024 * 1024
# A build swaps the folder with two renames; a read can land between them.
ATTEMPTS = 3
RETRY_SEC = 0.2
BUILD = re.compile(r"assets/(index-[\w-]+\.js)")
REFERENCE = re.compile(r'(?:src|href)="\./([^"?#]+)"')


@dataclass(frozen=True)
class PageFile:
    data: bytes
    etag: str  # quoted content hash
    modified: datetime


def is_hidden(relative: PurePath) -> bool:
    """Return True if any path part starts with a dot or the file is a source map."""
    return any(part.startswith(".") for part in relative.parts) or relative.name.endswith(".map")


def build_of(index_html: str) -> str:
    """Return the main script name in index.html (it carries a content hash).

    Empty for the placeholder.
    """
    found = BUILD.search(index_html)
    return found.group(1) if found else ""


class PageSnapshot:
    """The files of a page folder at one moment, by `/` path relative to it. Immutable."""

    def __init__(self, files: Mapping[str, PageFile]) -> None:
        self.files = dict(files)
        index = self.files.get("index.html")
        self.build = build_of(index.data.decode("utf-8", "replace")) if index else ""

    @property
    def size(self) -> int:
        return sum(len(f.data) for f in self.files.values())

    def get(self, name: str) -> PageFile | None:
        return self.files.get(name)

    def missing(self) -> list[str]:
        """Return files named by index.html that the snapshot lacks (a folder read mid-build)."""
        index = self.files.get("index.html")
        if index is None:
            return []
        return sorted({name for name in REFERENCE.findall(index.data.decode("utf-8", "replace")) if name not in self.files})

    @classmethod
    def take(cls, folder: Path) -> "PageSnapshot":
        """Read every served file under `folder`, retrying if it is swapped or incomplete.

        An unreadable folder gives an empty snapshot, which answers 404 to everything.
        """
        for attempt in range(1, ATTEMPTS + 1):
            try:
                snapshot = cls(dict(_read(folder)))
            except OSError as e:
                log.warning("the page folder %s cannot be read (%s)%s", folder, e, "; reading it again" if attempt < ATTEMPTS else "")
                snapshot = cls({})
            if snapshot.files and not snapshot.missing():
                return snapshot
            if attempt < ATTEMPTS:
                time.sleep(RETRY_SEC)
        log.error("the page in %s is not whole (%s); it is served as it is", folder, ", ".join(snapshot.missing()) or "no files")
        return snapshot


def _read(folder: Path) -> Iterator[tuple[str, PageFile]]:
    """Yield the files, index.html first.

    A swap in between then shows as a missing file, not as a mix of two builds.
    """
    total = 0
    paths = sorted((p for p in folder.rglob("*") if p.is_file() and not is_hidden(p.relative_to(folder))), key=lambda p: (p.relative_to(folder).as_posix() != "index.html", p.as_posix()))
    for path in paths:
        data = path.read_bytes()
        total += len(data)
        if total > MAX_BYTES:
            raise OSError(f"more than {MAX_BYTES} bytes")
        modified = datetime.fromtimestamp(int(path.stat().st_mtime), UTC)
        yield path.relative_to(folder).as_posix(), PageFile(data, '"' + hashlib.sha256(data).hexdigest()[:32] + '"', modified)
