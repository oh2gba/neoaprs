"""Build helpers shared by scripts/build-mercury and scripts/build-direwolf.

Fetching and patching the pinned source, ldd/readelf checks, PE import tables, socket tables and
tarballs. Python 3.10 compatible; imports nothing of the daemon."""
import hashlib
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Pattern, Sequence, Set, Tuple

PE_MACHINE_X64 = 0x8664
# DLLs a Windows program may not import because they do not come with Windows: MinGW's, a
# library's (hamlib, libusb, OpenSSL, zlib) or a runtime needing a redistributable. msvcrt.dll
# and the universal runtime are fine.
WINDOWS_DLL_NEVER = re.compile(r"^(lib|zlib|mingw|msvcr(?!t\.)|msvcp|vcruntime|vcomp|concrt|vccorlib|ucrtbased)", re.IGNORECASE)
# dsound.dll needs ResampleDmo.dll, which an "N" edition lacks; Windows then refuses to start the
# program.
WINDOWS_DLL_NOT_EVERYWHERE = {"dsound.dll"}
# 127.0.0.1 as /proc/net/tcp writes a local address.
LOOPBACK = "0100007F"

Run = Callable[[List[str]], str]


class BuildError(Exception):
    pass


def machine_name(machine: Optional[str] = None, system: str = sys.platform) -> str:
    """Return the architecture as a tarball names it: x86_64 or aarch64 on Linux, arm64 on a Mac."""
    name = (machine or platform.machine()).lower()
    if system == "win32":
        return "x86_64"
    if system == "darwin":
        return {"aarch64": "arm64", "amd64": "x86_64"}.get(name, name)
    return {"amd64": "x86_64", "arm64": "aarch64"}.get(name, name)


def cache_dir() -> Path:
    return Path(os.environ.get("NEOAPRS_BUILD_CACHE") or Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "neoaprs-build")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch_source(url: str, pinned_sha256: str, name: str, agent: str) -> Path:
    """Return the pinned source archive from the cache, downloading it if needed.

    Raise BuildError when it cannot be fetched or its digest is not the pin's (which removes it)."""
    if not re.fullmatch(r"[0-9a-f]{64}", pinned_sha256):
        raise BuildError(f"the SHA-256 of {url} is not pinned")
    cache = cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    file = cache / name
    if file.is_file() and sha256(file) == pinned_sha256:
        return file
    part = file.with_name(file.name + ".part")
    last: Optional[Exception] = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": agent}), timeout=60) as reply, part.open("wb") as out:  # noqa: S310  (pinned https address; kept only with its pinned SHA-256)
                shutil.copyfileobj(reply, out)
            last = None
            break
        except OSError as error:
            last = error
            time.sleep(2 * (attempt + 1))
    if last is not None:
        part.unlink(missing_ok=True)
        raise BuildError(f"{url} could not be fetched: {last}")
    if sha256(part) != pinned_sha256:
        part.unlink()
        raise BuildError(f"{url} is not the file with SHA-256 {pinned_sha256}")
    part.replace(file)
    return file


def _member(member: tarfile.TarInfo, dest: str) -> tarfile.TarInfo:
    """Apply tarfile's data filter, but accept a relative symlink that stays inside the tree.

    Before Python 3.12 the filter resolves such links from the destination and refuses them."""
    try:
        return tarfile.data_filter(member, dest)
    except tarfile.LinkOutsideDestinationError:
        root = os.path.realpath(dest)
        target = os.path.normpath(os.path.join(root, os.path.dirname(member.name), member.linkname))
        if member.issym() and not os.path.isabs(member.linkname) and os.path.commonpath([root, target]) == root:
            return member
        raise


def unpack(archive: Path, into: Path, marker: str, what: str) -> Path:
    """Unpack the archive under INTO (emptied first); return its one folder, holding `marker`."""
    shutil.rmtree(into, ignore_errors=True)
    into.mkdir(parents=True)
    with tarfile.open(archive) as tar:
        tar.extractall(into, filter=_member)  # noqa: S202  (data filter; the archive has the pinned digest)
    folders = [entry for entry in into.iterdir() if entry.is_dir()]
    if len(folders) != 1 or not (folders[0] / marker).is_file():
        raise BuildError(f"{archive} does not hold one {what} source folder")
    return folders[0]


def run(command: List[str]) -> str:
    """Return the output of a small tool; raise BuildError when it fails."""
    done = subprocess.run(command, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if done.returncode != 0:
        raise BuildError(f"{command[0]} failed with {done.returncode}:\n{done.stdout}")
    return done.stdout


def apply_patch(tree: Path, patch: Path) -> None:
    if not patch.is_file():
        raise BuildError(f"{patch} is missing")
    done = subprocess.run(["patch", "-p1", "--forward", "--batch", "-i", str(patch)], cwd=tree, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if done.returncode != 0:
        raise BuildError(f"{patch.name} does not apply to the pinned source (patch exited {done.returncode}):\n{done.stdout}")


def libraries(program: Path, run: Run = run) -> Dict[str, str]:
    """Return what ldd finds for PROGRAM: library name -> resolved path ('' if not found)."""
    found: Dict[str, str] = {}
    for line in run(["ldd", str(program)]).splitlines():
        name, arrow, rest = line.strip().partition(" => ")
        if not arrow:
            name = name.split(" ")[0]
            found[Path(name).name if name.startswith("/") else name] = name if name.startswith("/") else ""
            continue
        found[name] = "" if rest.startswith("not found") else rest.split(" (")[0]
    return found


def check_links(program: Path, folder: Path, needed_ok: Pattern[str], needed_never: Sequence[str], own: Sequence[str], run: Run = run) -> str:
    """Return the ldd output after checking it: only `needed_ok` libraries, none of `needed_never`,
    none missing, and each of `own` taken from the folder's lib/."""
    text = run(["ldd", str(program)])
    found = libraries(program, run)
    for name, path in found.items():
        if any(name.startswith(never) for never in needed_never):
            raise BuildError(f"{program.name} links {name}, which the bundle does not carry:\n{text}")
        if not path and not needed_ok.match(name):
            raise BuildError(f"{program.name} needs {name}, which is not found:\n{text}")
        if not needed_ok.match(name):
            raise BuildError(f"{program.name} links {name} ({path}), which is none of {', '.join(own)} and glibc:\n{text}")
    for name in own:
        path = found.get(name, "")
        if not path or Path(path).resolve() != (folder / "lib" / name).resolve():
            raise BuildError(f"{name} is not taken from {folder / 'lib'} (ldd says {path or 'nothing'}):\n{text}")
    return text


def runpath(program: Path, run: Run = run) -> str:
    for line in run(["readelf", "-d", str(program)]).splitlines():
        if "RUNPATH" in line or "RPATH" in line:
            return line.strip()
    raise BuildError(f"{program} has no RUNPATH")


def glibc_needed(path: Path, run: Run = run) -> str:
    """Return the newest glibc symbol version PATH asks for."""
    versions = {tuple(int(part) for part in found.split(".")) for found in re.findall(r"GLIBC_(\d+(?:\.\d+)+)", run(["readelf", "--dyn-syms", "--wide", str(path)]))}
    return ".".join(str(part) for part in max(versions)) if versions else "none"


def pe_imports(path: Path) -> Tuple[int, List[str]]:
    """Return the machine type and the imported DLL names (including delay-loaded) of a PE32+ file.

    Raise ValueError for a file that is not a 64-bit PE."""
    data = path.read_bytes()
    if data[:2] != b"MZ" or len(data) < 0x40:
        raise ValueError(f"{path.name} is not a program for Windows (no MZ header)")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError(f"{path.name} is not a program for Windows (no PE signature)")
    machine, count, _, _, _, optional_size, _ = struct.unpack_from("<HHIIIHH", data, pe + 4)
    optional = pe + 24
    if struct.unpack_from("<H", data, optional)[0] != 0x20B:
        raise ValueError(f"{path.name} is not a 64-bit program")
    directories = optional + 112
    sections = [struct.unpack_from("<IIII", data, optional + optional_size + 40 * index + 8) for index in range(count)]

    def offset(rva: int) -> int:
        for size, address, raw_size, raw in sections:
            if address <= rva < address + max(size, raw_size):
                return raw + rva - address
        raise ValueError(f"{path.name}: the address {rva:#x} is in no section")

    names: List[str] = []
    # The import table (20 bytes a DLL) and the delay-load table (32).
    for directory, length, name_at in ((1, 20, 12), (13, 32, 4)):
        rva = struct.unpack_from("<I", data, directories + 8 * directory)[0]
        if rva == 0:
            continue
        at = offset(rva)
        while data[at:at + length] != bytes(length):
            start = offset(struct.unpack_from("<I", data, at + name_at)[0])
            names.append(data[start:data.index(b"\0", start)].decode("ascii"))
            at += length
    return machine, names


def check_imports(program: Path, names: Sequence[str]) -> None:
    """Raise BuildError naming imports that do not come with every Windows."""
    foreign = [name for name in names if WINDOWS_DLL_NEVER.match(name)]
    if foreign:
        raise BuildError(f"{program.name} imports {', '.join(foreign)}, which do not come with Windows and would have to travel with it:\n  " + "\n  ".join(names))
    fragile = [name for name in names if name.lower() in WINDOWS_DLL_NOT_EVERYWHERE]
    if fragile:
        raise BuildError(f"{program.name} imports {', '.join(fragile)}, which stops it before it runs on a Windows without the Media Feature Pack")


def listeners(ports: Set[int], tables: Sequence[str] = ("/proc/net/tcp", "/proc/net/tcp6")) -> Dict[int, Set[str]]:
    """Return the local addresses (hex, as the kernel writes them) listening on these ports.

    With the UDP tables, every socket bound to them."""
    found: Dict[int, Set[str]] = {}
    for name in tables:
        try:
            lines = Path(name).read_text(encoding="ascii").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            # 0A is LISTEN; a UDP socket is bound or not.
            if len(fields) < 4 or ("/tcp" in name and fields[3] != "0A"):
                continue
            address, _, port = fields[1].rpartition(":")
            if int(port, 16) in ports:
                found.setdefault(int(port, 16), set()).add(address)
    return found


def folder_size(folder: Path) -> int:
    return sum(path.stat().st_size for path in folder.rglob("*") if path.is_file() and not path.is_symlink())


def megabytes(size: int) -> str:
    return f"{size:,} bytes, {size / (1 << 20):.1f} MB"


def make_tarball(folder: Path, target: Path, top: str) -> Path:
    """Make TARGET, a .tar.gz with FOLDER as top folder `top`, entries sorted and owned by no
    one."""

    def anonymous(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        return info

    with tarfile.open(target, "w:gz", compresslevel=9) as tar:
        for path in sorted([folder, *folder.rglob("*")]):
            tar.add(path, arcname=str(Path(top) / path.relative_to(folder)), recursive=False, filter=anonymous)
    return target
