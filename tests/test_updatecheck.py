"""The daily update check (neoaprs/services/updatecheck.py): it asks the page a minute after the start and then once a day, takes a newer version into `latest` and nothing else, is off when the environment says so, and a page that
fails changes nothing. The page is a stub here; against a fake version page on the loopback, and through the daemon to the page, below."""
import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs import VERSION
from neoaprs.config import DEFAULTS, Config
from neoaprs.services.updatecheck import ENV_SWITCH, EVERY_SEC, FIRST_SEC, WHILE_OFF_SEC, UpdateCheck
from neoaprs.updatefetch import fetch
from tests.support.env import Env, remember_stop, until
from tests.support.fakeversionpage import version_page

NEWER = json.dumps({"version": "0.2.0", "url": "https://oh2gba.github.io/neoaprs/", "message": "Fixes the map download"}).encode()


class Page:
    def __init__(self, *answers: bytes | None) -> None:
        self.answers = list(answers)
        self.asked: list[tuple[str, str, str]] = []

    async def __call__(self, address: str, version: str, platform: str) -> bytes | None:
        self.asked.append((address, version, platform))
        return self.answers.pop(0) if self.answers else None


def check(page: Page, config: Config = DEFAULTS, environ: dict[str, str] | None = None, **times: float) -> UpdateCheck:
    service = UpdateCheck(lambda: config, "0.1.0", "linux", page, environ={} if environ is None else environ, **times)
    remember_stop(service.stop)
    return service


async def test_a_newer_version_is_kept_with_its_address_and_note() -> None:
    page = Page(NEWER)
    service = check(page)
    answer = await service.check()
    assert answer is not None and service.latest == answer
    assert (answer.version, answer.url, answer.message) == ("0.2.0", "https://oh2gba.github.io/neoaprs/", "Fixes the map download")
    assert page.asked == [("https://oh2gba.eu/neoaprs/version.php", "0.1.0", "linux")]


@pytest.mark.parametrize("version", ["0.1.0", "0.0.9", "0.1"])
async def test_the_same_or_an_older_version_is_not_an_update(version: str) -> None:
    service = check(Page(json.dumps({"version": version, "url": "https://x/"}).encode()))
    assert await service.check() is None and service.latest is None


async def test_a_failed_check_leaves_what_was_known_and_an_answer_that_is_not_one_is_a_failure() -> None:
    service = check(Page(NEWER, None, b"<html>moved</html>", json.dumps({"version": "0.1.0"}).encode()))
    first = await service.check()
    assert first is not None
    assert await service.check() is None and service.latest == first, "the page was not reached"
    assert await service.check() is None and service.latest == first, "the page said something else"
    assert await service.check() is None and service.latest is None, "the page says we are up to date"


async def test_it_asks_a_minute_after_the_start_and_then_every_day() -> None:
    page = Page(NEWER, NEWER, NEWER)
    service = check(page, first_sec=0.05, every_sec=0.1)
    await service.start()
    await until(lambda: len(page.asked) == 3)
    await service.stop()
    assert (FIRST_SEC, EVERY_SEC) == (60.0, 86400.0)
    assert service.latest is not None


async def test_it_does_not_ask_while_the_environment_says_no_and_asks_when_that_is_over() -> None:
    page = Page(NEWER)
    service = check(page, environ={ENV_SWITCH: "0"}, first_sec=0.02, every_sec=0.02)
    assert not service.enabled
    await service.start()
    await asyncio.sleep(0.15)
    assert page.asked == []
    assert WHILE_OFF_SEC == 3600.0
    await service.stop()
    assert not check(page, environ={ENV_SWITCH: "0"}).enabled
    assert check(page, environ={ENV_SWITCH: "1"}).enabled and check(page).enabled


async def test_the_address_and_the_platform_it_asks_are_the_settings_and_the_installation() -> None:
    page = Page(None)
    service = check(page, replace(DEFAULTS, update_url="https://example.org/v.php"))
    await service.check()
    assert page.asked == [("https://example.org/v.php", "0.1.0", "linux")]


async def test_against_a_fake_version_page_on_the_loopback(tmp_path: Path) -> None:
    fake = await version_page({"version": "9.9.9", "url": "https://oh2gba.github.io/neoaprs/", "message": ""})
    service = UpdateCheck(lambda: replace(DEFAULTS, update_url=fake.url), "0.1.0", "linux-arm", fetch, environ={})
    answer = await service.check()
    assert answer is not None and answer.version == "9.9.9"
    assert fake.requests[0][0] == "/version.php?v=0.1.0&os=linux-arm"


async def test_the_daemon_asks_its_page_and_tells_a_page_of_the_browser_the_newer_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_SWITCH, "1")
    fake = await version_page({"version": "9.9.9", "url": "https://oh2gba.github.io/neoaprs/", "message": "News"})
    e = Env(tmp_path, web=True, settings={"update/url": fake.url})
    e.ctl.updatecheck.first_sec = 0.05
    await e.start()
    page = await e.ws()
    status = await page.expect("status")
    await until(lambda: e.ctl.updatecheck.latest is not None)
    await page.send({"cmd": "status"})
    await page.until(lambda: page.of("status")[-1]["update"] is not None)
    assert page.of("status")[-1]["update"] == {"version": "9.9.9", "url": "https://oh2gba.github.io/neoaprs/", "message": "News"}
    assert status["update"] is None and status["version"] == VERSION
    assert fake.requests[0][0].startswith("/version.php?v=" + VERSION + "&os=")
    await e.stop()


async def test_a_daemon_of_the_tests_asks_nothing(tmp_path: Path) -> None:
    fake = await version_page({"version": "9.9.9", "url": "", "message": ""})
    e = Env(tmp_path, settings={"update/url": fake.url})
    e.ctl.updatecheck.first_sec = 0.01
    await e.start()
    await asyncio.sleep(0.2)
    assert fake.requests == [] and e.ctl.updatecheck.latest is None
    await e.stop()
