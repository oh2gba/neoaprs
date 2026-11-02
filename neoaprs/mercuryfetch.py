"""Getting the Mercury program: the release of the pinned version for this system, downloaded from the address written below, checked against the SHA-256 written with it (the pin is the trust, not the server, and no
other address is ever fetched), and put in the `bin/` folder of the data folder, where mercuryhelper.find looks.

Windows gets the release's zip, which holds `mercury.exe` with the DLLs it needs (Hamlib and the rest are vendored): the exe and the DLLs go into `bin/mercury-1.9.21/` together, because the exe finds its DLLs beside
itself; the zip's graphical `mercury-ui.exe` (27 MB, never run by NeoAPRS) and its example configuration are left out. Linux gets the Debian package of the Hermes archive (amd64 or arm64): a `.deb` is an `ar` archive that
holds `data.tar.xz` (or .gz or .bz2: what the standard library reads; zstd it cannot), and the one file `./usr/bin/mercury` of it becomes `bin/mercury`. That binary needs the system's sound libraries (libasound2, libpulse0,
libhamlib4, libhidapi-hidraw0, libssl3), which nothing here installs; when it cannot start, the modem says so. A Mac is not fetched: its release is a disk image, and Mercury is installed there by hand.
The pmtiles tool's download is the pattern (pmtilestool.py): a file into a temporary folder, moved to its place when it is whole. Blocks: run it in a thread. Nothing here imports Tornado or the settings."""
import hashlib
import http.client
import io
import logging
import lzma
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import IO
from urllib.parse import urlsplit

from .pmtilestool import TIMEOUT_SEC, USER_AGENT, platform_key, replace_file
from .source import os_error_text

log = logging.getLogger("neoaprs.mercury")

VERSION = "1.9.21"
FOLDER = f"mercury-{VERSION}"               # Windows: where the exe and its DLLs go, under the data folder's bin/
BY_HAND = "the Mercury program is not installed, and on this computer it is installed by hand and put on the PATH (see docs/RADIOS.md)"
MAX_FILE = 64_000_000                       # the biggest file taken out of an archive (the biggest real one is a DLL of 11.5 MB)
MAX_DEB_PART = 20_000_000                   # the biggest part of a Debian package taken (the real data part is 0.8 MB)
AR_MAGIC = b"!<arch>\n"
AR_HEADER = 60
PROGRAM_IN_DEB = PurePosixPath("usr/bin/mercury")


class MercuryFetchError(Exception):
    """Mercury cannot be had; the text is for the operator."""


@dataclass(frozen=True)
class Asset:
    url: str
    sha256: str
    size: int                               # the file's size: a download that is longer is stopped
    kind: str                               # "zip" or "deb"


ASSETS: dict[tuple[str, str], Asset] = {
    ("windows", "x86_64"): Asset(f"https://github.com/Rhizomatica/mercury/releases/download/v{VERSION}/mercury-{VERSION}-w64-edca701b.zip",
                                 "85163f2c2db65e03cbbeaac0b32c6a0cacf930616923c1a18d4d17730b74b806", 16_065_263, "zip"),
    ("linux", "x86_64"): Asset(f"http://debian.hermes.radio/hermes/pool/main/m/mercury/mercury_{VERSION}-1_amd64.deb",
                               "ec9fcadc615e36a6d658704cab155c1bd2874aeba5d5772bb8486d5940808167", 788_252, "deb"),
    ("linux", "arm64"): Asset(f"http://debian.hermes.radio/hermes/pool/main/m/mercury/mercury_{VERSION}-1_arm64.deb",
                              "665c5f43f73bedbbf6c92f5748249ec7c9292eb445d972bd6a7bf69eb760c661", 759_136, "deb"),
}


def program_path(bin_dir: Path, windows: bool) -> Path:
    """Where a fetched Mercury is: the exe in its folder on Windows, the one binary on Linux."""
    return bin_dir / FOLDER / "mercury.exe" if windows else bin_dir / "mercury"


def _why(e: BaseException) -> str:
    """What went wrong in a download, in words: the server's answer, the system's words for a connection, not the Python wording."""
    if isinstance(e, urllib.error.HTTPError):
        return f"the server answered {e.code}"
    if isinstance(e, urllib.error.URLError):
        return _why(e.reason) if isinstance(e.reason, BaseException) else str(e.reason)
    if isinstance(e, http.client.HTTPException):
        return "the connection broke"
    if isinstance(e, ValueError):
        return "the address is not one"
    return os_error_text(e)


def _download(asset: Asset, target: Path) -> None:
    """The file at the asset's address, written to `target`, if its digest is the pinned one; else MercuryFetchError and nothing is kept."""
    host = urlsplit(asset.url).hostname or asset.url
    digest, size = hashlib.sha256(), 0
    try:
        with urllib.request.urlopen(urllib.request.Request(asset.url, headers={"User-Agent": USER_AGENT}), timeout=TIMEOUT_SEC) as response, target.open("wb") as out:
            while chunk := response.read(1 << 16):
                size += len(chunk)
                if size > asset.size:
                    raise MercuryFetchError(f"what {host} sends is longer than the Mercury release, and was thrown away")
                digest.update(chunk)
                out.write(chunk)
            if size < int(response.headers.get("Content-Length") or 0):                # (a body that stops short is read to its end without a word)
                raise http.client.IncompleteRead(b"")
    except (OSError, ValueError, http.client.HTTPException) as e:                   # (URLError, HTTPError and a timeout are OSErrors, an address without a scheme a ValueError)
        log.warning("Mercury: %s could not be downloaded: %r", asset.url, e)
        raise MercuryFetchError(f"Mercury could not be downloaded from {host}: {_why(e)}") from None
    if digest.hexdigest() != asset.sha256:
        log.warning("Mercury: %s has the SHA-256 %s, not the pinned %s", asset.url, digest.hexdigest(), asset.sha256)
        raise MercuryFetchError(f"what came from {host} is not the Mercury {VERSION} that was expected, and was thrown away")


def _copy(source: IO[bytes], out: IO[bytes], limit: int) -> None:
    """The bytes of `source` into `out`, at most `limit` of them (an archive's own idea of a file's size is not trusted)."""
    done = 0
    while chunk := source.read(1 << 16):
        done += len(chunk)
        if done > limit:
            raise MercuryFetchError("the Mercury download is not what it should be")
        out.write(chunk)


def _wanted(name: str) -> bool:
    return name == "mercury.exe" or name.lower().endswith(".dll")


def _unpack_zip(archive: Path, folder: Path) -> None:
    """The program and its DLLs out of the zip, side by side in `folder`, whatever folders they are in inside the zip."""
    with zipfile.ZipFile(archive) as z:
        members = [(PurePosixPath(i.filename.replace("\\", "/")).name, i) for i in z.infolist() if not i.is_dir()]
        members = [(name, info) for name, info in members if _wanted(name)]
        if not any(name == "mercury.exe" for name, _ in members):
            raise MercuryFetchError("mercury.exe is not in the Mercury download")
        for name, info in members:
            with z.open(info) as source, (folder / name).open("wb") as out:
                _copy(source, out, MAX_FILE)


def _ar_member(archive: Path, prefix: str) -> tuple[str, bytes]:
    """The first member of an `ar` archive (a .deb) whose name begins with `prefix`: its name and its bytes."""
    with archive.open("rb") as f:
        if f.read(len(AR_MAGIC)) != AR_MAGIC:
            raise MercuryFetchError("the Mercury download is not a Debian package")
        while len(header := f.read(AR_HEADER)) == AR_HEADER and header[58:60] == b"`\n":
            name, size = header[:16].decode("ascii", "replace").strip().rstrip("/"), int(header[48:58])
            if name.startswith(prefix):
                if size > MAX_DEB_PART:
                    raise MercuryFetchError("the Mercury download is not what it should be")
                return name, f.read(size)
            f.seek(size + size % 2, 1)                                                  # (members start on an even byte)
    raise MercuryFetchError(f"{prefix} is not in the Mercury download")


def _unpack_deb(archive: Path, target: Path) -> None:
    """The one file `./usr/bin/mercury` out of the package's data part, written to `target`."""
    name, data = _ar_member(archive, "data.tar")
    compression = name.rsplit(".", 1)[-1]
    if compression not in ("xz", "gz", "bz2"):
        raise MercuryFetchError(f"the Mercury package is packed with {compression}, which this program cannot unpack")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as t:
        member = next((m for m in t if m.isfile() and PurePosixPath(m.name) == PROGRAM_IN_DEB), None)
        packed = t.extractfile(member) if member is not None else None
        if packed is None:
            raise MercuryFetchError("the program is not in the Mercury package")
        with packed, target.open("wb") as out:
            _copy(packed, out, MAX_FILE)


def install(bin_dir: Path, asset: Asset) -> Path:
    """Downloads the asset, checks it, and puts the program in `bin_dir` (see program_path); its path. Nothing is put there unless the download is the pinned one and whole."""
    windows = asset.kind == "zip"
    final = program_path(bin_dir, windows)
    try:
        bin_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=bin_dir, prefix=".download-") as work:
            archive, staged = Path(work) / "download", Path(work) / (FOLDER if windows else "mercury")
            _download(asset, archive)
            if windows:
                staged.mkdir()
                _unpack_zip(archive, staged)
                shutil.rmtree(final.parent, ignore_errors=True)                         # (a folder left half-empty by something that deleted its exe)
                replace_file(staged, final.parent)
            else:
                _unpack_deb(archive, staged)
                staged.chmod(0o755)
                replace_file(staged, final)
    except (OSError, zipfile.BadZipFile, tarfile.TarError, EOFError, lzma.LZMAError, zlib.error, ValueError) as e:
        log.warning("Mercury: %s could not be put in %s: %r", asset.url, bin_dir, e)
        raise MercuryFetchError(f"Mercury could not be unpacked into {bin_dir}: {os_error_text(e) if isinstance(e, OSError) else 'the download is damaged'}") from None
    log.info("Mercury %s was fetched into %s", VERSION, final)
    return final


def fetch(data_dir: Path, system: str | None = None, machine: str | None = None, assets: Mapping[tuple[str, str], Asset] = ASSETS) -> list[str]:
    """Mercury for this system fetched into the data folder's `bin/`, as the command that runs it. MercuryFetchError, in the operator's words, when this system has none to fetch or the fetch fails. Blocks: run it in a thread."""
    key = platform_key(system, machine)
    if key not in assets:
        raise MercuryFetchError(BY_HAND)
    return [str(install(data_dir / "bin", assets[key]))]
