"""Getting the Mercury program (neoaprs/mercuryfetch.py) from a fake server on the loopback that serves small archives built here: a zip with a Windows Mercury's exe and DLLs, a Debian package assembled in the `ar`
format with its data part in xz or gz. The pins are the digests of those files. The fetch puts the program where mercuryhelper.find looks, refuses a file that is not the pinned one and keeps nothing of it, says a server that
is down or answers badly in plain words, tells a Mac that Mercury is installed by hand, and the modem starts the program it fetched, says meanwhile that it is fetching, and waits with the reason when it cannot."""
import asyncio
import hashlib
import io
import os
import socket
import tarfile
import threading
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs import mercuryfetch
from neoaprs.config import DEFAULTS, Config
from neoaprs.mercuryfetch import ASSETS, BY_HAND, FOLDER, Asset, MercuryFetchError, fetch, program_path
from neoaprs.mercuryhelper import find
from neoaprs.mercurymodem import Mercury
from neoaprs.pmtilestool import platform_key
from neoaprs.source import Backoff
from tests.support import fakemercury
from tests.support.env import until
from tests.support.fakehttp import FakeHttp, http_server

HF: Config = replace(DEFAULTS, tnc_profile="mercury", mercury_keying="vox", mercury_sound_card="plughw:1,0", station_call="OH2GBA")
QUICK = Backoff([0.1, 0.1])
EXE = b"MZ the exe"
DLL = b"MZ hamlib" * 1000
BINARY = b"\x7fELF the program"


def zip_of(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def windows_zip() -> bytes:
    return zip_of({f"{FOLDER}/mercury.exe": EXE, f"{FOLDER}/libhamlib-4.dll": DLL, f"{FOLDER}/libusb-1.0.dll": b"MZ usb", f"{FOLDER}/mercury-ui.exe": b"MZ the window" * 100, f"{FOLDER}/mercury.ini.example": b"[x]\n"})


def ar_of(members: list[tuple[str, bytes]]) -> bytes:
    """An `ar` archive as dpkg-deb makes one: the magic, then a 60-byte header and the bytes of each member, a member starting on an even byte."""
    out = b"!<arch>\n"
    for name, data in members:
        out += f"{name + '/':<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{len(data):<10}".encode("ascii") + b"`\n" + data + (b"\n" if len(data) % 2 else b"")
    return out


def deb_of(binary: bytes = BINARY, compression: str = "xz", data_name: str | None = None) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode=f"w:{compression}") as t:                                   # type: ignore[call-overload]
        for name, data in (("./usr/bin/mercury", binary), ("./usr/share/doc/mercury/copyright", b"GPL")):
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o644
            t.addfile(info, io.BytesIO(data))
    return ar_of([("debian-binary", b"2.0\n"), ("control.tar.xz", b"odd"), (data_name or f"data.tar.{compression}", buf.getvalue())])


def pinned(server: FakeHttp, body: bytes, kind: str, path: str = "/release") -> Asset:
    server.route(path, body=body)
    return Asset(server.url(path), hashlib.sha256(body).hexdigest(), len(body), kind)


async def fetched(data_dir: Path, system: str, asset: Asset, machine: str = "x86_64") -> list[str]:
    return await asyncio.to_thread(fetch, data_dir, system, machine, {platform_key(system, machine): asset})


async def stopped(m: Mercury) -> None:
    await m.stop()
    assert m.state == "stopped" and m.pid is None


def leftovers(data_dir: Path) -> list[str]:
    return sorted(str(p.relative_to(data_dir)) for p in data_dir.rglob("*"))


# ---- the pins

def test_the_pins_are_the_three_files_of_the_release_with_their_sizes_and_nothing_else_is_asked_for() -> None:
    assert sorted(ASSETS) == [("linux", "arm64"), ("linux", "x86_64"), ("windows", "x86_64")]
    assert {a.sha256 for a in ASSETS.values()} == {"85163f2c2db65e03cbbeaac0b32c6a0cacf930616923c1a18d4d17730b74b806", "ec9fcadc615e36a6d658704cab155c1bd2874aeba5d5772bb8486d5940808167",
                                                   "665c5f43f73bedbbf6c92f5748249ec7c9292eb445d972bd6a7bf69eb760c661"}
    assert ASSETS[("windows", "x86_64")].size == 16_065_263 and ASSETS[("linux", "x86_64")].size == 788_252 and ASSETS[("linux", "arm64")].size == 759_136
    assert all(a.url.startswith(("https://github.com/Rhizomatica/mercury/releases/download/v1.9.21/", "http://debian.hermes.radio/hermes/pool/main/m/mercury/")) for a in ASSETS.values())


# ---- fetching

async def test_a_windows_release_puts_the_exe_and_its_dlls_side_by_side_in_a_folder_of_the_version(tmp_path: Path) -> None:
    server = await http_server()
    command = await fetched(tmp_path, "Windows", pinned(server, windows_zip(), "zip"))
    folder = tmp_path / "bin" / FOLDER
    assert command == [str(folder / "mercury.exe")] == [str(program_path(tmp_path / "bin", True))]
    assert (folder / "mercury.exe").read_bytes() == EXE and (folder / "libhamlib-4.dll").read_bytes() == DLL
    assert sorted(p.name for p in folder.iterdir()) == ["libhamlib-4.dll", "libusb-1.0.dll", "mercury.exe"], "the window program and the example configuration are left out"
    assert leftovers(tmp_path) == ["bin", f"bin/{FOLDER}", *(f"bin/{FOLDER}/{n}" for n in ("libhamlib-4.dll", "libusb-1.0.dll", "mercury.exe"))], "no temporary folder is left"


async def test_a_windows_folder_left_without_its_exe_is_made_whole_again(tmp_path: Path) -> None:
    server = await http_server()
    folder = tmp_path / "bin" / FOLDER
    folder.mkdir(parents=True)
    (folder / "libhamlib-4.dll").write_bytes(b"old and cut")
    (folder / "stale.txt").write_text("old")
    await fetched(tmp_path, "windows", pinned(server, windows_zip(), "zip"))
    assert (folder / "mercury.exe").read_bytes() == EXE and (folder / "libhamlib-4.dll").read_bytes() == DLL and not (folder / "stale.txt").exists()


@pytest.mark.skipif(os.name == "nt", reason="the mode of a file is a POSIX thing")
@pytest.mark.parametrize("compression", ["xz", "gz"])
async def test_a_debian_package_gives_its_one_program_in_the_data_folders_bin_where_find_finds_it(tmp_path: Path, compression: str) -> None:
    server = await http_server()
    command = await fetched(tmp_path, "Linux", pinned(server, deb_of(compression=compression), "deb"), "aarch64")
    program = tmp_path / "bin" / "mercury"
    assert command == [str(program)] and program.read_bytes() == BINARY and program.stat().st_mode & 0o777 == 0o755
    assert find(tmp_path, search_path=str(tmp_path / "nowhere"), bundled=tmp_path / "nobundle") == command
    assert leftovers(tmp_path) == ["bin", "bin/mercury"], "the rest of the package is not kept, nor any temporary file"


async def test_a_file_that_is_not_the_pinned_one_is_refused_and_nothing_of_it_is_kept(tmp_path: Path) -> None:
    server = await http_server()
    asset = pinned(server, windows_zip(), "zip")
    server.route("/release", body=windows_zip()[:-1] + b"y")
    with pytest.raises(MercuryFetchError, match=r"^what came from 127\.0\.0\.1 is not the Mercury 1\.9\.21 that was expected, and was thrown away$"):
        await fetched(tmp_path, "windows", asset)
    server.route("/release", body=windows_zip()[:-1])
    with pytest.raises(MercuryFetchError, match="not the Mercury 1.9.21 that was expected"):
        await fetched(tmp_path, "windows", asset)
    assert leftovers(tmp_path) == ["bin"]


async def test_a_download_longer_than_the_release_is_stopped_and_nothing_is_kept(tmp_path: Path) -> None:
    server = await http_server()
    body = windows_zip()
    server.route("/release", body=body + b"more")
    with pytest.raises(MercuryFetchError, match="longer than the Mercury release"):
        await fetched(tmp_path, "windows", Asset(server.url("/release"), hashlib.sha256(body).hexdigest(), len(body), "zip"))
    assert leftovers(tmp_path) == ["bin"]


async def test_a_server_that_is_down_is_a_plain_problem_with_no_python_in_it(tmp_path: Path) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    with pytest.raises(MercuryFetchError) as down:
        await fetched(tmp_path, "linux", Asset(f"http://127.0.0.1:{port}/m.deb", "0" * 64, 100, "deb"))
    assert str(down.value) == "Mercury could not be downloaded from 127.0.0.1: Connection refused"
    assert leftovers(tmp_path) == ["bin"]


async def test_an_answer_that_is_not_the_file_is_said_by_its_code_and_a_body_cut_short_as_a_connection_that_broke(tmp_path: Path) -> None:
    server = await http_server()
    server.route("/gone", status=404)
    with pytest.raises(MercuryFetchError, match=r"^Mercury could not be downloaded from 127\.0\.0\.1: the server answered 404$"):
        await fetched(tmp_path, "linux", Asset(server.url("/gone"), "0" * 64, 100, "deb"))
    server.route("/cut", body=b"x" * 10, announce=100)
    with pytest.raises(MercuryFetchError, match=r"^Mercury could not be downloaded from 127\.0\.0\.1: the connection broke$"):
        await fetched(tmp_path, "linux", Asset(server.url("/cut"), "0" * 64, 100, "deb"))
    with pytest.raises(MercuryFetchError, match="the address is not one"):
        await fetched(tmp_path, "linux", Asset("not an address", "0" * 64, 100, "deb"))
    assert leftovers(tmp_path) == ["bin"]


@pytest.mark.parametrize(("body", "kind", "problem"), [
    (b"not a zip at all", "zip", "Mercury could not be unpacked into {bin}: the download is damaged"),
    (b"not a package", "deb", "the Mercury download is not a Debian package"),
    (zip_of({"readme.txt": b"hi"}), "zip", "mercury.exe is not in the Mercury download"),
    (ar_of([("debian-binary", b"2.0\n")]), "deb", "data.tar is not in the Mercury download"),
    (deb_of(data_name="data.tar.zst"), "deb", "the Mercury package is packed with zst, which this program cannot unpack"),
    (ar_of([("data.tar.xz", b"not xz")]), "deb", "Mercury could not be unpacked into {bin}: the download is damaged"),
], ids=["not a zip", "not a package", "no exe in the zip", "no data.tar", "zst", "data.tar not xz"])      # (named: a zip carries the time it was made, which differs between xdist's workers)
async def test_a_pinned_file_that_is_not_a_mercury_release_is_a_plain_problem_and_nothing_is_kept(tmp_path: Path, body: bytes, kind: str, problem: str) -> None:
    server = await http_server()
    with pytest.raises(MercuryFetchError) as bad:
        await fetched(tmp_path, "windows" if kind == "zip" else "linux", pinned(server, body, kind))
    assert str(bad.value) == problem.format(bin=tmp_path / "bin")
    assert leftovers(tmp_path) == ["bin"]


async def test_a_mac_and_a_processor_with_no_release_are_told_that_mercury_is_installed_by_hand_and_nothing_is_asked_of_a_server(tmp_path: Path) -> None:
    server = await http_server()
    asset = pinned(server, windows_zip(), "zip")
    for system, machine in (("Darwin", "arm64"), ("Darwin", "x86_64"), ("Windows", "ARM64"), ("FreeBSD", "amd64")):
        with pytest.raises(MercuryFetchError) as told:
            await asyncio.to_thread(fetch, tmp_path, system, machine, {("windows", "x86_64"): asset})
        assert str(told.value) == BY_HAND
    assert "PATH" in BY_HAND and "by hand" in BY_HAND and server.requests == [] and leftovers(tmp_path) == []


async def test_the_fetch_asks_for_the_release_of_this_system_by_the_names_the_system_gives(tmp_path: Path) -> None:
    server = await http_server()
    amd, arm = pinned(server, deb_of(b"amd"), "deb", "/amd64.deb"), pinned(server, deb_of(b"arm"), "deb", "/arm64.deb")
    both = {("linux", "x86_64"): amd, ("linux", "arm64"): arm}
    await asyncio.to_thread(fetch, tmp_path, "Linux", "aarch64", both)
    assert (tmp_path / "bin" / "mercury").read_bytes() == b"arm"
    await asyncio.to_thread(fetch, tmp_path, "Linux", "AMD64", both)
    assert (tmp_path / "bin" / "mercury").read_bytes() == b"amd" and server.requests == ["/arm64.deb", "/amd64.deb"]


# ---- the modem

async def test_the_modem_fetches_the_program_when_there_is_none_says_so_meanwhile_and_starts_what_it_fetched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asked, release = threading.Event(), threading.Event()

    def slow_fetch(data_dir: Path) -> list[str]:
        assert data_dir == tmp_path
        asked.set()
        assert release.wait(10)
        return fakemercury.program()

    monkeypatch.setattr(mercuryfetch, "fetch", slow_fetch)
    m = Mercury(tmp_path, finder=lambda: None, backoff=QUICK, control_backoff=Backoff([0.05, 0.05]))
    starting = asyncio.ensure_future(m.start(HF))
    try:
        await until(asked.is_set, 5.0)
        assert m.state == "starting" and m.fetching and m.describe() == "Mercury DATAC3: fetching the program" and m.starts == 0
    finally:
        release.set()
        await starting
    try:
        await until(lambda: m.state == "running", 5.0)
        assert not m.fetching and m.starts == 1 and m.problem == "" and m.describe().startswith("Mercury DATAC3 at 127.0.0.1:")
    finally:
        await stopped(m)


async def test_the_modem_does_not_fetch_a_program_it_finds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mercuryfetch, "fetch", lambda data_dir: pytest.fail("fetched a program that was there"))
    m = Mercury(tmp_path, finder=fakemercury.program, backoff=QUICK, control_backoff=Backoff([0.05, 0.05]))
    await m.start(HF)
    try:
        await until(lambda: m.state == "running", 5.0)
    finally:
        await stopped(m)


async def test_a_fetch_that_fails_leaves_the_modem_waiting_with_the_reason_and_a_later_start_tries_again_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Path] = []

    def failing(data_dir: Path) -> list[str]:
        calls.append(data_dir)
        raise MercuryFetchError("Mercury could not be downloaded from github.com: Connection refused")

    monkeypatch.setattr(mercuryfetch, "fetch", failing)
    m = Mercury(tmp_path, finder=lambda: None, backoff=QUICK, control_backoff=Backoff([0.05, 0.05]))
    await m.start(HF)
    assert m.state == "waiting" and not m.fetching and m.starts == 0 and not (tmp_path / "mercury.ini").exists()
    assert m.problem == "Mercury could not be downloaded from github.com: Connection refused" and m.describe() == f"Mercury DATAC3: {m.problem}"
    await asyncio.sleep(0.3)
    assert len(calls) == 1, "no loop of its own"
    await m.start(HF)
    assert len(calls) == 2 and m.state == "waiting"
    await stopped(m)


async def test_a_modem_stopped_while_the_fetch_runs_starts_nothing_when_it_is_over(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asked, release = threading.Event(), threading.Event()

    def slow_fetch(data_dir: Path) -> list[str]:
        asked.set()
        release.wait(10)
        return fakemercury.program()

    monkeypatch.setattr(mercuryfetch, "fetch", slow_fetch)
    m = Mercury(tmp_path, finder=lambda: None, backoff=QUICK, control_backoff=Backoff([0.05, 0.05]))
    starting = asyncio.ensure_future(m.start(HF))
    try:
        await until(asked.is_set, 5.0)
        m._generation += 1                                                  # (what a stop or a new start does to the one that waits)
    finally:
        release.set()
        await starting
    assert m.starts == 0 and not m.fetching
    await stopped(m)
