"""The download page (server/download.php) under PHP's own web server on the loopback, with a fake GitHub (tests/support/fakeversionpage.py) for the releases: each f answers 302 to that file of the latest release, anything else to the
release page, nothing is cached, the download is logged as time, f and version only, and the last good version stands while GitHub fails. Skipped without `php`."""
import asyncio
import http.client
import os
import shutil
import socket
import subprocess
import time
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from tests.support.fakeversionpage import FakeVersionPage, version_page
from tests.support.ptyline import posix_only

pytestmark = posix_only

ROOT = Path(__file__).resolve().parent.parent
PHP = shutil.which("php")
RELEASES = "https://github.com/oh2gba/neoaprs/releases/latest"
FILES = {
    "windows": "NeoAPRS-Setup-0.9.0.exe",
    "appimage": "NeoAPRS-0.9.0-x86_64.AppImage",
    "deb-amd64": "neoaprs_0.9.0_amd64.deb",
    "deb-arm64": "neoaprs_0.9.0_arm64.deb",
    "wheel": "neoaprs-0.9.0-py3-none-any.whl",
}


def free_port() -> int:
    """A port that was free a moment ago."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class Page:
    def __init__(self, folder: Path, github: FakeVersionPage) -> None:
        self.folder, self.github = folder, github
        self.process: subprocess.Popen[bytes] | None = None
        self.port = free_port()

    def start(self) -> None:
        (self.folder / "site" / "log").mkdir(parents=True)
        for name in ("download.php", "latest.php"):
            shutil.copy(ROOT / "server" / name, self.folder / "site" / name)
        env = {"PATH": os.environ["PATH"], "RELEASES_URL": self.github.url}
        assert PHP is not None
        for _ in range(3):                                      # (the port was free when it was probed; a test running beside this one may have taken it since: then php ends at once and another port is tried)
            self.process = subprocess.Popen([PHP, "-S", f"127.0.0.1:{self.port}", "-t", str(self.folder / "site")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and self.process.poll() is None:
                try:
                    socket.create_connection(("127.0.0.1", self.port), timeout=0.2).close()
                    return
                except OSError:
                    time.sleep(0.05)
            if self.process.poll() is None:
                break
            self.port = free_port()
        raise AssertionError("php did not start")

    def stop(self) -> None:
        if self.process is not None:
            self.process.terminate()
            self.process.wait(10)

    async def ask(self, query: str) -> tuple[int, str, str]:
        """The status, the Location and the Cache-Control of the answer; the redirect is not followed."""
        def get() -> tuple[int, str, str]:
            connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
            try:
                connection.request("GET", f"/download.php{query}")
                response = connection.getresponse()
                response.read()
                return response.status, response.getheader("Location") or "", response.getheader("Cache-Control") or ""
            finally:
                connection.close()
        return await asyncio.to_thread(get)

    def log(self) -> list[list[str]]:
        return [line.split("\t") for path in sorted((self.folder / "site" / "log").glob("downloads-*.log")) for line in path.read_text(encoding="utf-8").splitlines()]

    def expire(self) -> None:
        os.utime(self.folder / "site" / "log" / "latest.json", (time.time() - 7200,) * 2)


def release(version: str, name: str) -> str:
    return f"https://github.com/oh2gba/neoaprs/releases/download/v{version}/{name}"


@pytest.fixture
async def page(tmp_path: Path) -> AsyncIterator[Page]:
    if PHP is None:
        pytest.skip("needs php")
    github = await version_page({"tag_name": "v0.9.0"})
    served = Page(tmp_path, github)
    served.start()
    yield served
    served.stop()


@pytest.mark.parametrize("f", list(FILES))
async def test_each_file_is_a_302_to_that_file_of_the_latest_release_and_nothing_is_cached(page: Page, f: str) -> None:
    assert await page.ask(f"?f={f}") == (302, release("0.9.0", FILES[f]), "no-store")


async def test_an_unknown_f_or_none_goes_to_the_release_page_without_asking_github(page: Page) -> None:
    for query in ("", "?f=", "?f=mac", "?f=windows%00", "?f[]=windows", "?f=../../x"):
        assert await page.ask(query) == (302, RELEASES, "no-store"), query
    assert page.github.requests == []


async def test_a_new_release_is_noticed_when_the_cache_is_ten_minutes_old(page: Page) -> None:
    assert (await page.ask("?f=windows"))[1] == release("0.9.0", "NeoAPRS-Setup-0.9.0.exe")
    page.github.answer = {"tag_name": "v0.9.1"}
    assert (await page.ask("?f=windows"))[1] == release("0.9.0", "NeoAPRS-Setup-0.9.0.exe") and len(page.github.requests) == 1
    page.expire()
    assert (await page.ask("?f=appimage"))[1] == release("0.9.1", "NeoAPRS-0.9.1-x86_64.AppImage") and len(page.github.requests) == 2


async def test_with_github_down_the_last_good_version_stands(page: Page) -> None:
    await page.ask("?f=wheel")
    page.github.status = 503
    page.expire()
    assert await page.ask("?f=deb-arm64") == (302, release("0.9.0", "neoaprs_0.9.0_arm64.deb"), "no-store")
    assert len(page.github.requests) == 2


async def test_with_github_down_and_no_cache_every_f_goes_to_the_release_page(page: Page) -> None:
    page.github.status = 503
    for f in FILES:
        assert await page.ask(f"?f={f}") == (302, RELEASES, "no-store")
    assert len(page.log()) == len(FILES), "and each is logged all the same"


async def test_a_download_is_logged_as_time_f_and_version_only(page: Page) -> None:
    await page.ask("?f=windows")
    await page.ask("?f=mac%3Cb%3E")
    await page.ask("")
    (when, f, version), second, third = page.log()
    assert when.endswith("Z") and len(when) == len("2026-10-23T08:45Z") and (f, version) == ("windows", "0.9.0")
    assert second[1:] == ["macb", "-"] and third[1:] == ["-", "-"], "an unknown f is cleaned and has no version, none at all is -"
    assert len(list((page.folder / "site" / "log").glob("downloads-*.log"))) == 1
