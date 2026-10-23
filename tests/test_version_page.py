"""The version page (server/version.php) under PHP's own web server on the loopback, with a fake GitHub (tests/support/fakeversionpage.py) for the releases and a stand-in status library: the answer names the latest release, the call is logged as time, version
and platform only, the status application is handed the call, GitHub is asked once an hour and the last good answer is kept while it fails. Skipped without `php`."""
import asyncio
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from tests.support.fakeversionpage import FakeVersionPage, version_page
from tests.support.ptyline import posix_only

pytestmark = posix_only

ROOT = Path(__file__).resolve().parent.parent
PHP = shutil.which("php")
LIBRARY = "<?php function status_db() { return 'db'; }\nfunction app_start_record($db, $app, $v, $os, $ip) { file_put_contents(__DIR__ . '/calls.txt', \"$app|$v|$os\\n\", FILE_APPEND); return false; }\n"


class Page:
    def __init__(self, folder: Path, github: FakeVersionPage) -> None:
        self.folder, self.github = folder, github
        self.process: subprocess.Popen[bytes] | None = None
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]

    def start(self) -> None:
        (self.folder / "site" / "log").mkdir(parents=True)
        (self.folder / "lib").mkdir()
        shutil.copy(ROOT / "server" / "version.php", self.folder / "site" / "version.php")
        (self.folder / "lib" / "starts.php").write_text(LIBRARY, encoding="utf-8")
        env = {"PATH": os.environ["PATH"], "STATUS_LIB": str(self.folder / "lib"), "RELEASES_URL": self.github.url}
        assert PHP is not None
        self.process = subprocess.Popen([PHP, "-S", f"127.0.0.1:{self.port}", "-t", str(self.folder / "site")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.2).close()
                return
            except OSError:
                time.sleep(0.05)
        raise AssertionError("php did not start")

    def stop(self) -> None:
        if self.process is not None:
            self.process.terminate()
            self.process.wait(10)

    async def ask(self, query: str = "v=0.1.0&os=linux") -> dict[str, str]:
        def get() -> dict[str, str]:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/version.php?{query}", timeout=15) as response:
                assert response.headers["Content-Type"] == "application/json; charset=utf-8" and response.headers["Cache-Control"] == "no-store"
                return json.loads(response.read())                              # type: ignore[no-any-return]
        return await asyncio.to_thread(get)

    def log(self) -> list[list[str]]:
        return [line.split("\t") for path in sorted((self.folder / "site" / "log").glob("starts-*.log")) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
async def page(tmp_path: Path) -> AsyncIterator[Page]:
    if PHP is None:
        pytest.skip("needs php")
    github = await version_page({"tag_name": "v0.2.0"})
    served = Page(tmp_path, github)
    served.start()
    yield served
    served.stop()


async def test_the_answer_names_the_latest_release_the_project_page_and_no_message(page: Page) -> None:
    assert await page.ask() == {"version": "0.2.0", "url": "https://oh2gba.github.io/neoaprs/", "message": ""}
    assert page.github.requests[0][1]["user-agent"] == "neoaprs-version-page"


async def test_the_call_is_logged_as_time_version_and_platform_and_handed_to_the_status_application(page: Page) -> None:
    await page.ask("v=0.1.0&os=linux-arm")
    await page.ask("v=0.1.0%3Cb%3E&os=")
    (when, version, os_name), second = page.log()
    assert when.endswith("Z") and len(when) == len("2026-10-23T08:45Z") and (version, os_name) == ("0.1.0", "linux-arm")
    assert second[1:] == ["0.1.0b", "-"], "what is not a letter, a digit or . _ - is dropped, nothing at all is -"
    assert (page.folder / "lib" / "calls.txt").read_text(encoding="utf-8").splitlines() == ["neoaprs|0.1.0|linux-arm", "neoaprs|0.1.0b|"]


async def test_github_is_asked_once_an_hour_and_the_last_good_answer_stands_while_it_fails(page: Page) -> None:
    await page.ask()
    page.github.answer = {"tag_name": "v0.3.0"}
    assert (await page.ask())["version"] == "0.2.0" and len(page.github.requests) == 1
    cache = page.folder / "site" / "log" / "latest.json"
    os.utime(cache, (time.time() - 7200,) * 2)
    assert (await page.ask())["version"] == "0.3.0" and len(page.github.requests) == 2
    page.github.status = 503
    os.utime(cache, (time.time() - 7200,) * 2)
    assert (await page.ask())["version"] == "0.3.0" and len(page.github.requests) == 3, "GitHub failed: the old answer"
    assert (await page.ask())["version"] == "0.3.0" and len(page.github.requests) == 3, "and it is not asked again for a few minutes"


async def test_without_a_cache_and_with_github_down_the_version_is_zero_and_the_call_is_logged_all_the_same(page: Page) -> None:
    page.github.status = 503
    assert (await page.ask())["version"] == "0.0.0" and len(page.log()) == 1


async def test_a_note_in_message_txt_is_the_message_its_first_line_cut_to_200_characters(page: Page) -> None:
    (page.folder / "site" / "message.txt").write_text("Fixes the map download\nsecond line\n", encoding="utf-8")
    assert (await page.ask())["message"] == "Fixes the map download"
    (page.folder / "site" / "message.txt").write_text("x" * 300, encoding="utf-8")
    assert (await page.ask())["message"] == "x" * 200
