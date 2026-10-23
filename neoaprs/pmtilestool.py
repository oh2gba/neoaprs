"""The pmtiles tool (go-pmtiles) that cuts the base map out of a big archive: where it is, fetching it when it is not, and running it.

The tool is one program without dependencies. It is found in the `bin/` folder next to the program when NeoAPRS is a frozen one (the Windows installer bundles the pinned, checked tool there), on the PATH, or in the `bin/` folder of the data folder; when it is in none, the release of the pinned version for this system is
downloaded from GitHub, checked against the SHA-256 written below (the digest GitHub shows for each file of the release; the pin is the trust, not the server), and unpacked into `bin/`.

`extract` runs `pmtiles extract` with a subprocess in a thread, which works on every event loop (Tornado forces the selector loop on Windows, which cannot start subprocesses of its own), and reads its
output a line at a time: the percent of the bar it draws, and the sizes of a dry run. Nothing here imports Tornado or the settings."""
import asyncio
import contextlib
import hashlib
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

VERSION = "1.31.2"
RELEASE_URL = f"https://github.com/protomaps/go-pmtiles/releases/download/v{VERSION}"
USER_AGENT = "NeoAPRS (+https://github.com/oh2gba/neoaprs)"
TIMEOUT_SEC = 30.0
MAX_DOWNLOAD = 100_000_000                  # the biggest archive taken (the real ones are 16 to 18 MB)
MAX_TOOL = 300_000_000                      # the biggest program taken out of one (they are 55 to 60 MB)
HEADER_LENGTH = 127                         # the header of a PMTiles archive, version 3
REPLACE_TRIES = 8


class ToolError(Exception):
    """The tool cannot be had or does not do it; the text says why."""


@dataclass(frozen=True)
class Asset:
    name: str                               # the file of the release
    sha256: str
    kind: str                               # "tar.gz" or "zip"


ASSETS: dict[tuple[str, str], Asset] = {
    ("linux", "x86_64"): Asset("go-pmtiles_1.31.2_Linux_x86_64.tar.gz", "3ed7dbf4ec2e6dfe5e25b6f70d1ffc932729f93c86db353bf514dd71010a312f", "tar.gz"),
    ("linux", "arm64"): Asset("go-pmtiles_1.31.2_Linux_arm64.tar.gz", "f8bd47e7ea866863489cad588fbaf2f31f42e5821f7a03f009b3769f05801cb1", "tar.gz"),
    ("windows", "x86_64"): Asset("go-pmtiles_1.31.2_Windows_x86_64.zip", "a658baa4d7e55020aef6ca17bd9ff9faa1582671266b36f58c52db0ac8e785a1", "zip"),
    ("darwin", "x86_64"): Asset("go-pmtiles-1.31.2_Darwin_x86_64.zip", "1f0dc02eee6c58312dd6c509faee1b5c32f0596568af1bf51f1b034e7a88a65b", "zip"),
    ("darwin", "arm64"): Asset("go-pmtiles-1.31.2_Darwin_arm64.zip", "40528f7f616fcbf91207cd48c8fc023d213f6d86c0cbf1f748732803d1880f3d", "zip"),
}
_MACHINES = {"x86_64": "x86_64", "amd64": "x86_64", "x64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}


def platform_key(system: str | None = None, machine: str | None = None) -> tuple[str, str]:
    """The operating system (linux, windows, darwin) and the processor (x86_64, arm64) as the release names them; the processor as it came when it is none of those."""
    name = (system or platform.system()).lower()
    chip = (machine or platform.machine()).lower()
    return name, _MACHINES.get(chip, chip)


def asset_for(system: str | None = None, machine: str | None = None, assets: Mapping[tuple[str, str], Asset] = ASSETS) -> Asset:
    key = platform_key(system, machine)
    if key not in assets:
        raise ToolError(f"there is no pmtiles program for {key[0]} on {key[1]}: install go-pmtiles by hand and put it on the PATH")
    return assets[key]


def tool_file(system: str | None = None) -> str:
    return "pmtiles.exe" if platform_key(system)[0] == "windows" else "pmtiles"


def bundled_dir() -> Path | None:
    """The `bin/` folder next to the executable of a frozen program (the Windows installer's app), None for a program that is run from Python."""
    return Path(sys.executable).resolve().parent / "bin" if getattr(sys, "frozen", False) else None


def find(bin_dir: Path, system: str | None = None, search_path: str | None = None, bundled: Path | None = None) -> Path | None:
    """The pmtiles program bundled with a frozen program, else on the PATH (or in `search_path`), else the one in `bin_dir`; None when there is none."""
    name = tool_file(system)
    bundled = bundled if bundled is not None else bundled_dir()
    if bundled is not None and (bundled / name).is_file():
        return bundled / name
    on_path = shutil.which(name, path=search_path)
    if on_path:
        return Path(on_path)
    mine = bin_dir / name
    return mine if mine.is_file() and os.access(mine, os.X_OK) else None


def replace_file(source: Path, target: Path) -> None:
    """Moves the file over the other, whole or not at all. Windows refuses while a program has the target open (the page's byte ranges, a virus scanner): it is tried again for a few seconds."""
    for attempt in range(REPLACE_TRIES):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == REPLACE_TRIES - 1:
                raise
            time.sleep(0.25)


# ---- getting the tool

def _download(url: str, target: Path, sha256: str) -> None:
    """The file at the address, written to `target`, if its digest is the pinned one; else ToolError and nothing is kept."""
    digest, size = hashlib.sha256(), 0
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=TIMEOUT_SEC) as response, target.open("wb") as out:
            while chunk := response.read(1 << 16):
                size += len(chunk)
                if size > MAX_DOWNLOAD:
                    raise ToolError(f"{url} is bigger than {MAX_DOWNLOAD // 1_000_000} MB")
                digest.update(chunk)
                out.write(chunk)
    except (OSError, ValueError) as e:                                      # (URLError, HTTPError and a timeout are OSErrors, an address without a scheme a ValueError)
        raise ToolError(f"could not download {url}: {e}") from None
    if digest.hexdigest() != sha256:
        raise ToolError(f"{url} is not the file that was expected (its SHA-256 is {digest.hexdigest()}, not {sha256}); it was thrown away")


def _unpack(archive: Path, kind: str, name: str, target: Path) -> None:
    """The one file called `name` out of the archive, written to `target`. The names inside the archive decide nothing but which file it is."""
    try:
        if kind == "zip":
            with zipfile.ZipFile(archive) as z:
                info = next((i for i in z.infolist() if not i.is_dir() and PurePosixPath(i.filename).name == name), None)
                if info is None or info.file_size > MAX_TOOL:
                    raise ToolError(f"{name} is not in {archive.name}")
                with z.open(info) as source, target.open("wb") as out:
                    shutil.copyfileobj(source, out)
        else:
            with tarfile.open(archive, "r:gz") as t:
                member = next((m for m in t if m.isfile() and PurePosixPath(m.name).name == name), None)
                packed = t.extractfile(member) if member is not None and member.size <= MAX_TOOL else None
                if packed is None:
                    raise ToolError(f"{name} is not in {archive.name}")
                with packed, target.open("wb") as out:
                    shutil.copyfileobj(packed, out)
    except (OSError, zipfile.BadZipFile, tarfile.TarError) as e:
        raise ToolError(f"could not unpack {archive.name}: {e}") from None


def install(bin_dir: Path, asset: Asset, base_url: str = RELEASE_URL, system: str | None = None) -> Path:
    """Downloads the asset, checks it, and puts the program in `bin_dir`; its path. Blocks: run it in a thread."""
    name = tool_file(system)
    try:
        bin_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=bin_dir, prefix=".download-") as work:
            archive, program = Path(work) / asset.name, Path(work) / name
            _download(f"{base_url}/{asset.name}", archive, asset.sha256)
            _unpack(archive, asset.kind, name, program)
            program.chmod(0o755)
            replace_file(program, bin_dir / name)
    except OSError as e:
        raise ToolError(f"could not put {name} in {bin_dir}: {e}") from None
    return bin_dir / name


async def ensure(bin_dir: Path, system: str | None = None, machine: str | None = None, search_path: str | None = None,
                 base_url: str = RELEASE_URL, assets: Mapping[tuple[str, str], Asset] = ASSETS) -> Path:
    """The program, found or fetched."""
    found = find(bin_dir, system, search_path)
    if found is not None:
        return found
    asset = asset_for(system, machine, assets)
    return await asyncio.to_thread(install, bin_dir, asset, base_url, system)


# ---- reading what the tool wrote and said

@dataclass(frozen=True)
class Header:
    min_zoom: int
    max_zoom: int
    bbox: tuple[float, float, float, float]          # west, south, east, north


def read_header(path: Path) -> Header | None:
    """The zooms and the box of a PMTiles archive (version 3), None for a file that is none."""
    try:
        with path.open("rb") as f:
            data = f.read(HEADER_LENGTH)
    except OSError:
        return None
    if len(data) < HEADER_LENGTH or data[:7] != b"PMTiles" or data[7] != 3:
        return None
    low, high, west, south, east, north = struct.unpack_from("<BB4i", data, 100)
    return Header(low, high, (west / 1e7, south / 1e7, east / 1e7, north / 1e7))


_UNITS = {"B": 1, "kB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4, "PB": 1000**5}
_SIZE = re.compile(r"([\d.]+)\s*([kMGTP]?B)\b")
_TILES = re.compile(r"fetching (\d+) tiles")
_ARCHIVE = re.compile(r"archive size of ([\d.]+\s*[kMGTP]?B)\b")
_PERCENT = re.compile(r"(?<![\d.])(\d{1,3})%\s*\S")                     # (a bar that is cut off in the middle of its percent has no character after it yet)
_PREFIX = re.compile(r"^\d{4}/\d\d/\d\d \d\d:\d\d:\d\d \S+?: ")
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def parse_size(text: str) -> int:
    """A size as the tool writes it (`493 MB`, `1.5 GB`: thousands), in bytes; ValueError for a text that is none."""
    found = _SIZE.fullmatch(text.strip())
    if found is None:
        raise ValueError(f"{text!r} is not a size")
    return round(float(found.group(1)) * _UNITS[found.group(2)])


def percent_of(line: str) -> int | None:
    """The percent of the progress bar the tool draws (`fetching chunks  47% |███   | (230/490 MB ...`), None for any other line."""
    found = _PERCENT.search(line)
    return min(100, int(found.group(1))) if found else None


@dataclass(frozen=True)
class Sizes:
    tiles: int
    bytes: int                                       # what the archive will hold of tiles


def read_sizes(lines: list[str]) -> Sizes:
    """The tiles and the size an extract makes (what a dry run is for), from what the tool said."""
    tiles = size = None
    for line in lines:
        if found := _TILES.search(line):
            tiles = int(found.group(1))
        if found := _ARCHIVE.search(line):
            size = parse_size(found.group(1))
    if tiles is None or size is None:
        raise ToolError("the pmtiles program did not say how big the extract is" + (f": {lines[-1]}" if lines else ""))
    return Sizes(tiles, size)


def _clean(raw: bytes) -> str:
    return _PREFIX.sub("", _ANSI.sub("", raw.decode("utf-8", "replace"))).strip()


def command_line(program: Path, source: str, target: Path, bbox: tuple[float, float, float, float] | None, maxzoom: int, dry_run: bool) -> list[str]:
    line = [str(program), "extract", source, str(target), f"--maxzoom={maxzoom}"]
    if bbox is not None:
        line.append("--bbox=" + ",".join(f"{v:.5f}" for v in bbox))
    if dry_run:
        line.append("--dry-run")
    return line


class _Run:
    """One run of the program, in a thread: its output a line at a time (the bar redraws itself with a carriage return, so that ends a line too)."""

    def __init__(self, command: list[str], on_percent: Callable[[int], None]) -> None:
        self.command = command
        self.on_percent = on_percent
        self.stopped = False
        self._process: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()
        self.lines: list[str] = []
        self._percent = -1

    def stop(self) -> None:
        with self._lock:
            self.stopped = True
            if self._process is not None:
                with contextlib.suppress(OSError):
                    self._process.terminate()

    def _start(self) -> subprocess.Popen[bytes]:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)                  # (Windows: no console window for the program)
        try:
            with self._lock:
                if self.stopped:
                    raise ToolError("stopped")
                self._process = subprocess.Popen(self.command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=flags)
                return self._process
        except OSError as e:
            raise ToolError(f"could not run {self.command[0]}: {e}") from None

    def _take(self, raw: bytes) -> None:
        text = _clean(raw)
        if not text:
            return
        self.lines.append(text)
        del self.lines[:-200]
        self._report(text)

    def _report(self, text: str) -> None:
        percent = percent_of(text)
        if percent is not None and percent != self._percent:
            self._percent = percent
            self.on_percent(percent)

    def go(self) -> list[str]:
        process = self._start()
        assert process.stdout is not None
        pending, descriptor = b"", process.stdout.fileno()
        while chunk := os.read(descriptor, 4096):
            *done, pending = re.split(rb"[\r\n]", pending + chunk)
            for raw in done:
                self._take(raw)
            self._report(_clean(pending))                                   # (the bar that is drawn now is not ended until it is redrawn)
        self._take(pending)
        try:
            code = process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            code = process.wait()
        if self.stopped:
            raise ToolError("stopped")
        if code != 0:
            raise ToolError(self.lines[-1] if self.lines else f"{Path(self.command[0]).name} ended with {code}")
        return self.lines


async def extract(program: Path, source: str, target: Path, bbox: tuple[float, float, float, float] | None, maxzoom: int, dry_run: bool = False,
                  on_percent: Callable[[int], None] | None = None) -> Sizes:
    """Cuts the box (the whole world without one) down to `maxzoom` out of `source`, a web address or a file, into `target`; with `dry_run` nothing is written and the sizes are what it would make.
    `on_percent` is told the percent of the bar, on the event loop. A task that is cancelled ends the program and waits for it. ToolError for a program that fails."""
    loop = asyncio.get_running_loop()
    told = on_percent or (lambda percent: None)
    def from_thread(percent: int) -> None:
        loop.call_soon_threadsafe(told, percent)

    run = _Run(command_line(program, source, target, bbox, maxzoom, dry_run), from_thread)
    thread = asyncio.ensure_future(asyncio.to_thread(run.go))
    try:
        lines = await asyncio.shield(thread)
    except asyncio.CancelledError:
        run.stop()
        with contextlib.suppress(Exception):
            await thread
        raise
    return read_sizes(lines)


def url_exists(url: str) -> bool:
    """Whether a HEAD request for the address is answered with a success. A connection that fails is a no. Blocks: run it in a thread."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT}), timeout=20) as response:
            return bool(200 <= response.status < 300)
    except (OSError, ValueError):
        return False
