"""Puts the pinned Mercury for Windows into the app folder: `bundle_mercury.py DIST/NeoAPRS` makes DIST/NeoAPRS/bin/mercury/ with `mercury.exe`, every DLL of the release's zip beside it (the exe finds its DLLs next to itself) and
Mercury's LICENSE, downloaded from the address that neoaprs/mercury.py pins and kept only when its SHA-256 is the pinned one and its size not over the pinned one. The zip's graphical `mercury-ui.exe` (27 MB, never run by NeoAPRS) and its
example configuration are left out. Run with the Python that has NeoAPRS installed."""
import hashlib
import http.client
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from neoaprs import mercury
from neoaprs.pmtilestool import TIMEOUT_SEC, USER_AGENT

MAX_FILE = 64_000_000           # the biggest file taken out of the zip (the biggest real one is a DLL of 11.5 MB)


def download(url: str, target: Path, sha256: str, size: int) -> None:
    """The file at `url` written to `target`; SystemExit, and nothing kept, when it is longer than `size` or its digest is not `sha256`."""
    digest, done, too_long = hashlib.sha256(), 0, False
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=TIMEOUT_SEC) as response, target.open("wb") as out:
        while chunk := response.read(1 << 16):
            done += len(chunk)
            if done > size:
                too_long = True                                                     # (the file is deleted once it is closed: Windows refuses to delete an open one)
                break
            digest.update(chunk)
            out.write(chunk)
        if not too_long and done < int(response.headers.get("Content-Length") or 0):                 # (a body that stops short is read to its end without a word)
            raise http.client.IncompleteRead(b"")
    if too_long:
        target.unlink()
        raise SystemExit(f"bundle_mercury: what {url} sends is longer than the pinned {size} bytes, and was thrown away")
    if digest.hexdigest() != sha256:
        target.unlink()
        raise SystemExit(f"bundle_mercury: {url} has the SHA-256 {digest.hexdigest()}, not the pinned {sha256}; nothing was kept")


def unpack(archive: Path, folder: Path) -> list[Path]:
    """The program, its DLLs and the licence out of the zip, side by side in `folder` whatever folders they are in inside the zip; the files written. The licence is ours when the zip has none."""
    written: list[Path] = []
    licence_found = False
    with zipfile.ZipFile(archive) as z:
        members = [(PurePosixPath(i.filename.replace("\\", "/")).name, i) for i in z.infolist() if not i.is_dir()]
        if not any(name.lower() == "mercury.exe" for name, _ in members):
            raise SystemExit("bundle_mercury: mercury.exe is not in the zip")
        for name, info in members:
            lower, upper = name.lower(), name.upper()
            if lower == "mercury.exe":
                target = folder / "mercury.exe"
            elif lower.endswith(".dll"):
                target = folder / name
            elif upper.startswith("LICENSE") and not licence_found:
                target, licence_found = folder / "LICENSE", True
            else:
                continue
            if info.file_size > MAX_FILE:
                raise SystemExit(f"bundle_mercury: {info.filename} is {info.file_size} bytes: the zip is not what it should be")
            target.write_bytes(z.read(info))
            written.append(target)
    if not licence_found:
        target = folder / "LICENSE.txt"
        target.write_text(f"Mercury {mercury.VERSION} is free software, licensed GPL-3.0-or-later. Copyright: Rhizomatica and the authors of Mercury.\nThe source of this version: {mercury.SOURCE_URL}\n", encoding="utf-8")
        written.append(target)
        print(f"bundle_mercury: the zip has no LICENSE file; {target.name} says Mercury is GPL-3.0-or-later and where its source is")
    return written


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0 if len(sys.argv) == 2 else 2
    folder = Path(sys.argv[1]) / "bin" / "mercury"
    with tempfile.TemporaryDirectory() as work:
        archive = Path(work) / "mercury.zip"
        download(mercury.WINDOWS_URL, archive, mercury.WINDOWS_SHA256, mercury.WINDOWS_SIZE)           # (SystemExit, and nothing kept, when the digest is not the pinned one)
        print(f"bundle_mercury: {mercury.WINDOWS_URL} ({archive.stat().st_size} bytes), SHA-256 {mercury.WINDOWS_SHA256} checked")
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
        for path in unpack(archive, folder):
            print(f"bundle_mercury: {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
