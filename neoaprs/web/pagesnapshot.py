"""The page as the daemon took it when it started. The files of `neoaprs/page/` are read into memory once (the built page is about 3.4 MB, most of it the map library), and every request is answered from there, so
that a page rebuilt on disk, a branch switched or a package upgraded while the daemon runs changes nothing until the daemon is started again: the page and the daemon that tell each other their build in `hello`
are always the pair that was started together."""
import hashlib
import logging
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePath
from typing import Iterator, Mapping

log = logging.getLogger("neoaprs.web")

MAX_BYTES = 64 * 1024 * 1024                  # a folder bigger than this is not a page (a wrong folder was given); the real one is a twentieth of it
ATTEMPTS = 3                                  # a build swaps the folder with two renames, which a read can fall into
RETRY_SEC = 0.2
BUILD = re.compile(r"assets/(index-[\w-]+\.js)")
REFERENCE = re.compile(r'(?:src|href)="\./([^"?#]+)"')


@dataclass(frozen=True)
class PageFile:
    data: bytes
    etag: str                                 # the hash of the content, quoted as the header wants it
    modified: datetime


def is_hidden(relative: PurePath) -> bool:
    """Is the name, or a folder's above it, one that starts with a dot, or a source map? Decided on the parts of the path, so that the separator of the system does not matter."""
    return any(part.startswith(".") for part in relative.parts) or relative.name.endswith(".map")


def build_of(index_html: str) -> str:
    """The build of a page: the name of the main script its index.html loads (Vite puts the hash of the content in it); empty when there is none (the placeholder)."""
    found = BUILD.search(index_html)
    return found.group(1) if found else ""


class PageSnapshot:
    """The files of a page folder at one moment, by their path relative to it with `/` (`index.html`, `assets/index-AbCd1234.js`). Nothing in a snapshot changes."""

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
        """The files that index.html names and the snapshot does not have: a folder that was read in the middle of a build."""
        index = self.files.get("index.html")
        if index is None:
            return []
        return sorted({name for name in REFERENCE.findall(index.data.decode("utf-8", "replace")) if name not in self.files})

    @classmethod
    def take(cls, folder: Path) -> "PageSnapshot":
        """Reads every file under `folder` (not the hidden ones and not the source maps, which are never served). A folder that is swapped meanwhile, or whose index.html names a file that is not read, is read again; an empty
        snapshot, which answers 404 to everything, is what a folder that cannot be read gives."""
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
    """Index.html first: the files it names are read after it, so that a folder swapped in between shows as a missing file and not as a page of two builds."""
    total = 0
    paths = sorted((p for p in folder.rglob("*") if p.is_file() and not is_hidden(p.relative_to(folder))), key=lambda p: (p.relative_to(folder).as_posix() != "index.html", p.as_posix()))
    for path in paths:
        data = path.read_bytes()
        total += len(data)
        if total > MAX_BYTES:
            raise OSError(f"more than {MAX_BYTES} bytes")
        modified = datetime.fromtimestamp(int(path.stat().st_mtime), UTC)
        yield path.relative_to(folder).as_posix(), PageFile(data, '"' + hashlib.sha256(data).hexdigest()[:32] + '"', modified)
