"""The pmtiles tool (neoaprs/pmtilestool.py): finding it, fetching it from a local HTTP server that plays GitHub (a fake archive and its checksum; a wrong checksum refused), reading what it says, and running it
(the fake program of tests/support/fakepmtiles.py): the sizes of a dry run, the percent of the bar, a failure, a cancel that ends the program."""
import asyncio
import hashlib
import io
import re
import sys
import tarfile
import threading
import zipfile
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from neoaprs.pmtilestool import ASSETS, VERSION, Asset, ToolError, asset_for, ensure, extract, find, install, parse_size, percent_of, platform_key, read_header, read_sizes, tool_file, url_exists
from tests.support.env import until
from tests.support.fakepmtiles import alive, install_fake

FAKE_PROGRAM = b"#!/bin/sh\necho a pretend pmtiles\n"


def tar_gz(name: str, content: bytes) -> bytes:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as t:
        for member_name, data in (("LICENSE", b"BSD"), (name, content)):
            info = tarfile.TarInfo(member_name)
            info.size, info.mode = len(data), 0o755
            t.addfile(info, io.BytesIO(data))
    return out.getvalue()


def zip_of(name: str, content: bytes) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("LICENSE", "BSD")
        z.writestr(name, content)
    return out.getvalue()


class Releases:
    """A web server on the loopback that has a few files, as the release page of GitHub has them."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files
        self.asked: list[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                outer.asked.append(self.path)
                body = outer.files.get(self.path.lstrip("/"))
                self.send_response(200 if body is not None else 404)
                self.send_header("Content-Length", str(len(body or b"")))
                self.end_headers()
                self.wfile.write(body or b"")

            do_HEAD = do_GET

            def log_message(self, *args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


@pytest.fixture
def releases(monkeypatch: pytest.MonkeyPatch) -> Iterator[Releases]:
    for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        monkeypatch.delenv(name, raising=False)                      # (this machine's own proxy is not for a server on the loopback)
    server = Releases({})
    yield server
    server.close()


def asset_of(name: str, archive: bytes, kind: str) -> Asset:
    return Asset(name, hashlib.sha256(archive).hexdigest(), kind)


# ---- which tool

def test_the_pinned_table_has_the_five_systems_with_a_digest_each() -> None:
    assert set(ASSETS) == {("linux", "x86_64"), ("linux", "arm64"), ("windows", "x86_64"), ("darwin", "x86_64"), ("darwin", "arm64")}
    for asset in ASSETS.values():
        assert re.fullmatch(r"[0-9a-f]{64}", asset.sha256) and VERSION in asset.name
        assert asset.name.endswith(".zip" if asset.kind == "zip" else ".tar.gz")
    assert ASSETS[("windows", "x86_64")].kind == "zip" and ASSETS[("linux", "arm64")].kind == "tar.gz"
    assert len({a.sha256 for a in ASSETS.values()}) == 5


@pytest.mark.parametrize(("system", "machine", "key"), [
    ("Linux", "x86_64", ("linux", "x86_64")), ("Linux", "aarch64", ("linux", "arm64")), ("Windows", "AMD64", ("windows", "x86_64")),
    ("Darwin", "arm64", ("darwin", "arm64")), ("Darwin", "x86_64", ("darwin", "x86_64")),
])
def test_the_system_and_the_processor_are_named_as_the_release_names_them(system: str, machine: str, key: tuple[str, str]) -> None:
    assert platform_key(system, machine) == key
    assert asset_for(system, machine) is ASSETS[key]


def test_a_processor_without_a_release_is_refused_with_the_way_out() -> None:
    with pytest.raises(ToolError, match="no pmtiles program for linux on riscv64.*PATH"):
        asset_for("Linux", "riscv64")


def test_the_program_is_called_pmtiles_exe_on_windows() -> None:
    assert tool_file("Windows") == "pmtiles.exe" and tool_file("Linux") == "pmtiles" and tool_file("Darwin") == "pmtiles"


# ---- finding it

def test_the_program_is_found_on_the_path_before_the_data_folders_bin(tmp_path: Path) -> None:
    on_path, mine = install_fake(tmp_path / "path").path, install_fake(tmp_path / "data" / "bin").path
    assert find(tmp_path / "data" / "bin", search_path=str(tmp_path / "path")) == on_path
    assert find(tmp_path / "data" / "bin", search_path=str(tmp_path / "nothing")) == mine


def test_no_program_anywhere_is_none(tmp_path: Path) -> None:
    assert find(tmp_path / "bin", search_path=str(tmp_path / "nothing")) is None
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "pmtiles").write_text("not executable")
    assert find(tmp_path / "bin", search_path=str(tmp_path / "nothing")) is None


async def test_ensure_does_not_download_what_is_there(tmp_path: Path, releases: Releases) -> None:
    fake = install_fake(tmp_path / "bin")
    assert await ensure(tmp_path / "bin", search_path="", base_url=releases.url) == fake.path
    assert releases.asked == []


# ---- fetching it

async def test_the_release_for_this_system_is_downloaded_checked_and_unpacked_into_bin(tmp_path: Path, releases: Releases) -> None:
    archive = tar_gz("pmtiles", FAKE_PROGRAM)
    asset = asset_of("go-pmtiles_9.9.9_Linux_x86_64.tar.gz", archive, "tar.gz")
    releases.files[asset.name] = archive
    path = await ensure(tmp_path / "data" / "bin", "Linux", "x86_64", search_path="", base_url=releases.url, assets={("linux", "x86_64"): asset})
    assert path == tmp_path / "data" / "bin" / "pmtiles" and path.read_bytes() == FAKE_PROGRAM
    assert sys.platform == "win32" or path.stat().st_mode & 0o111, "the program can be run"
    assert releases.asked == ["/" + asset.name]
    assert [p.name for p in path.parent.iterdir()] == ["pmtiles"], "no download or temporary file is left behind"
    assert find(path.parent, "Linux", search_path="") == path


async def test_a_zip_with_a_windows_program_gives_pmtiles_exe(tmp_path: Path, releases: Releases) -> None:
    archive = zip_of("pmtiles.exe", b"MZ pretend")
    asset = asset_of("go-pmtiles_9.9.9_Windows_x86_64.zip", archive, "zip")
    releases.files[asset.name] = archive
    path = await ensure(tmp_path / "bin", "Windows", "AMD64", search_path="", base_url=releases.url, assets={("windows", "x86_64"): asset})
    assert path.name == "pmtiles.exe" and path.read_bytes() == b"MZ pretend"


async def test_a_file_with_another_checksum_is_refused_and_nothing_is_kept(tmp_path: Path, releases: Releases) -> None:
    archive = tar_gz("pmtiles", FAKE_PROGRAM)
    asset = Asset("go-pmtiles_9.9.9_Linux_x86_64.tar.gz", hashlib.sha256(b"what was pinned").hexdigest(), "tar.gz")
    releases.files[asset.name] = archive
    with pytest.raises(ToolError, match="not the file that was expected"):
        await ensure(tmp_path / "bin", "Linux", "x86_64", search_path="", base_url=releases.url, assets={("linux", "x86_64"): asset})
    assert list((tmp_path / "bin").iterdir()) == []


def test_a_missing_file_a_server_that_is_not_there_and_an_archive_without_the_program_are_told(tmp_path: Path, releases: Releases) -> None:
    asset = asset_of("go-pmtiles_9.9.9_Linux_x86_64.tar.gz", b"", "tar.gz")
    with pytest.raises(ToolError, match="could not download.*404"):
        install(tmp_path / "bin", asset, releases.url, "Linux")
    empty = tar_gz("something-else", b"x")
    asset = asset_of("go-pmtiles_9.9.9_Linux_x86_64.tar.gz", empty, "tar.gz")
    releases.files[asset.name] = empty
    with pytest.raises(ToolError, match="pmtiles is not in go-pmtiles"):
        install(tmp_path / "bin", asset, releases.url, "Linux")
    releases.close()
    with pytest.raises(ToolError, match="could not download"):
        install(tmp_path / "bin", asset, releases.url, "Linux")
    assert list((tmp_path / "bin").iterdir()) == []


def test_a_new_download_replaces_an_old_program(tmp_path: Path, releases: Releases) -> None:
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "pmtiles").write_bytes(b"old")
    archive = tar_gz("pmtiles", FAKE_PROGRAM)
    asset = asset_of("go-pmtiles_9.9.9_Linux_x86_64.tar.gz", archive, "tar.gz")
    releases.files[asset.name] = archive
    assert install(tmp_path / "bin", asset, releases.url, "Linux").read_bytes() == FAKE_PROGRAM


def test_a_head_request_says_whether_a_build_is_there(releases: Releases) -> None:
    releases.files["20261022.pmtiles"] = b"x"
    assert url_exists(f"{releases.url}/20261022.pmtiles") and not url_exists(f"{releases.url}/20261021.pmtiles")
    assert not url_exists("not an address")


# ---- what the tool says

@pytest.mark.parametrize(("text", "size"), [("493 MB", 493_000_000), ("1.5 GB", 1_500_000_000), ("15 kB", 15_000), ("9.5 MB", 9_500_000), ("512 B", 512), ("2 TB", 2_000_000_000_000)])
def test_a_size_as_the_tool_writes_it_is_in_bytes(text: str, size: int) -> None:
    assert parse_size(text) == size


def test_a_text_that_is_no_size_is_refused() -> None:
    with pytest.raises(ValueError):
        parse_size("about 500 megabytes")


def test_the_percent_is_that_of_the_bar_and_of_no_other_line() -> None:
    assert percent_of("fetching chunks  47% |████      | (230/490 MB, 20 MB/s) [10s:12s]") == 47
    assert percent_of("fetching chunks 100% |██████████| (490/490 MB, 20 MB/s) [24s:0s]") == 100
    assert percent_of("fetching chunks   0% |          | (0/490 MB, 0 B/s)") == 0
    assert percent_of("fetching 41233 tiles, 5000 chunks, 120 requests") is None
    assert percent_of("Extract transferred 512 MB (overfetch 0.05) for an archive size of 493 MB") is None


def test_a_dry_run_gives_the_tiles_and_the_size_of_the_archive() -> None:
    lines = ["fetching 3 dirs, 3 chunks, 1 requests", "Region tiles 83211, result tile entries 41233", "fetching 41233 tiles, 5000 chunks, 120 requests",
             "Extract transferred 512 MB (overfetch 0.05) for an archive size of 493 MB"]
    sizes = read_sizes(lines)
    assert (sizes.tiles, sizes.bytes) == (41233, 493_000_000)
    with pytest.raises(ToolError, match="did not say how big"):
        read_sizes(lines[:3])


def test_the_zooms_and_the_box_are_read_from_the_header_of_an_archive(tmp_path: Path) -> None:
    assert read_header(tmp_path / "none.pmtiles") is None
    (tmp_path / "text").write_text("not an archive")
    assert read_header(tmp_path / "text") is None
    (tmp_path / "v2").write_bytes(b"PMTiles" + bytes([2]) + bytes(200))
    assert read_header(tmp_path / "v2") is None


# ---- running it

async def test_a_dry_run_asks_for_the_box_and_the_zoom_and_gives_the_sizes(tmp_path: Path) -> None:
    fake = install_fake(tmp_path / "bin")
    sizes = await extract(fake.path, "https://build.example/20261022.pmtiles", tmp_path / "out.pmtiles", (23.5, 58.9, 26.4, 61.4), 12, dry_run=True)
    assert (sizes.tiles, sizes.bytes) == (41233, 493_000_000)
    assert fake.calls() == [["extract", "https://build.example/20261022.pmtiles", str(tmp_path / "out.pmtiles"), "--maxzoom=12", "--bbox=23.50000,58.90000,26.40000,61.40000", "--dry-run"]]
    assert not (tmp_path / "out.pmtiles").exists(), "a dry run writes nothing"


async def test_a_run_writes_the_file_and_tells_the_percent_of_the_bar_as_it_goes(tmp_path: Path) -> None:
    fake = install_fake(tmp_path / "bin")
    told: list[int] = []
    await extract(fake.path, "src", tmp_path / "out.pmtiles", (24.0, 60.0, 25.0, 61.0), 10, on_percent=told.append)
    await asyncio.sleep(0)
    assert told[0] == 0 and told[-1] == 100 and told == sorted(told) and {25, 50, 75} <= set(told)
    header = read_header(tmp_path / "out.pmtiles")
    assert header is not None and header.max_zoom == 10 and header.bbox == (24.0, 60.0, 25.0, 61.0)


async def test_the_world_is_asked_for_without_a_box(tmp_path: Path) -> None:
    fake = install_fake(tmp_path / "bin")
    await extract(fake.path, "src", tmp_path / "world.pmtiles", None, 5)
    assert not any(a.startswith("--bbox") for a in fake.calls()[0]) and "--maxzoom=5" in fake.calls()[0]


async def test_a_program_that_fails_is_told_with_its_last_line_without_the_date_and_the_place(tmp_path: Path) -> None:
    fake = install_fake(tmp_path / "bin")
    fake.mode("fail")
    with pytest.raises(ToolError, match=r'^Failed to extract, Get "src": connection refused$'):
        await extract(fake.path, "src", tmp_path / "out.pmtiles", None, 5)


async def test_a_program_that_cannot_be_started_is_told(tmp_path: Path) -> None:
    (tmp_path / "pmtiles").write_text("not a program")
    (tmp_path / "pmtiles").chmod(0o755)
    with pytest.raises(ToolError, match="could not run"):
        await extract(tmp_path / "pmtiles", "src", tmp_path / "out.pmtiles", None, 5)


async def test_a_dry_run_that_does_not_say_the_size_is_an_error(tmp_path: Path) -> None:
    fake = install_fake(tmp_path / "bin")
    fake.mode("nosize")
    with pytest.raises(ToolError, match="did not say how big"):
        await extract(fake.path, "src", tmp_path / "out.pmtiles", None, 5, dry_run=True)


async def test_a_task_that_is_cancelled_ends_the_program_and_waits_for_it(tmp_path: Path) -> None:
    fake = install_fake(tmp_path / "bin")
    fake.mode("slow")
    told: list[int] = []
    task = asyncio.ensure_future(extract(fake.path, "src", tmp_path / "out.pmtiles", None, 5, on_percent=told.append))
    await until(lambda: told == [10])
    pid = fake.pid()
    assert alive(pid)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not alive(pid), "the program is gone when the cancel returns"
