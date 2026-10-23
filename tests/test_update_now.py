"""Check now (`update_check`, answered with `update_result`): the question of the daily update check put to the version page on request, through the daemon, against a fake version page on the loopback. It works whatever
NEOAPRS_UPDATE_CHECK says (an explicit click), tells the page that asked what came of it and the newer version in a `status`, and leaves the daily schedule alone."""
import asyncio
from dataclasses import replace
from pathlib import Path

from neoaprs import VERSION
from neoaprs.config import DEFAULTS
from neoaprs.services.updatecheck import CheckResult, UpdateCheck
from neoaprs.updatefetch import fetch
from tests.support.env import Env, until
from tests.support.fakeversionpage import version_page

NEWER = {"version": "9.9.9", "url": "https://oh2gba.github.io/neoaprs/", "message": "News"}


async def started(tmp_path: Path, address: str, **settings: str) -> Env:
    e = Env(tmp_path, web=True, settings={"update/url": address, **settings})
    await e.start()
    return e


async def test_a_newer_version_is_answered_and_told_in_a_status_to_the_page_that_asked(tmp_path: Path) -> None:
    fake = await version_page(NEWER)
    e = await started(tmp_path, fake.url)
    page = await e.ws()
    other = await e.ws()
    await page.expect("status")
    await page.send({"cmd": "update_check"})
    assert await page.expect("update_result") == {"type": "update_result", "outcome": "newer", "version": "9.9.9", "text": ""}
    await page.until(lambda: page.of("status")[-1]["update"] is not None)
    assert page.of("status")[-1]["update"] == NEWER
    assert e.ctl.updatecheck.latest is not None and e.ctl.updatecheck.latest.version == "9.9.9"
    assert fake.requests[0][0].startswith(f"/version.php?v={VERSION}&os=")
    await other.quiet(0.2)
    assert other.of("update_result") == []
    await e.stop()


async def test_the_same_version_is_up_to_date_and_clears_a_newer_one_that_was_known(tmp_path: Path) -> None:
    fake = await version_page(NEWER)
    e = await started(tmp_path, fake.url)
    page = await e.ws()
    await page.send({"cmd": "update_check"})
    await page.expect("update_result")
    fake.answer = {"version": VERSION, "url": "", "message": ""}
    await page.send({"cmd": "update_check"})
    await page.until(lambda: len(page.of("update_result")) == 2)
    assert page.of("update_result")[1] == {"type": "update_result", "outcome": "current", "version": VERSION, "text": ""}
    assert e.ctl.updatecheck.latest is None
    await page.until(lambda: page.of("status")[-1]["update"] is None)
    await e.stop()


async def test_a_page_that_cannot_be_reached_or_understood_is_no_answer_with_the_reason_and_changes_nothing(tmp_path: Path) -> None:
    fake = await version_page(NEWER)
    e = await started(tmp_path, fake.url)
    page = await e.ws()
    await page.send({"cmd": "update_check"})
    await page.expect("update_result")
    fake.status = 503
    await page.send({"cmd": "update_check"})
    await page.until(lambda: len(page.of("update_result")) == 2)
    assert page.of("update_result")[1] == {"type": "update_result", "outcome": "no_answer", "version": "", "text": "the version page could not be reached"}
    fake.status, fake.body = 200, b"<html>moved</html>"
    await page.send({"cmd": "update_check"})
    await page.until(lambda: len(page.of("update_result")) == 3)
    assert page.of("update_result")[2] == {"type": "update_result", "outcome": "no_answer", "version": "", "text": "the version page gave an answer that is not a version"}
    assert e.ctl.updatecheck.latest is not None, "what was known stays"
    await e.stop()


async def test_it_asks_even_when_the_environment_switches_the_daily_check_off_and_does_not_start_the_schedule(tmp_path: Path) -> None:
    fake = await version_page(NEWER)
    e = await started(tmp_path, fake.url)
    service = e.ctl.updatecheck
    assert not service.enabled
    page = await e.ws()
    await page.send({"cmd": "update_check"})
    assert (await page.expect("update_result"))["outcome"] == "newer"
    assert len(fake.requests) == 1
    assert service.first_sec == 60.0, "the timer's first wait is not touched"
    await e.stop()


async def test_two_questions_at_once_are_asked_one_after_the_other() -> None:
    fake = await version_page(NEWER)
    service = UpdateCheck(lambda: replace(DEFAULTS, update_url=fake.url), "0.1.0", "linux", fetch, environ={})
    first, second = await asyncio.gather(service.check_now(), service.check_now())
    assert first == second == CheckResult("newer", "9.9.9")
    assert len(fake.requests) == 2


async def test_check_now_does_not_wait_for_the_timer_and_does_not_move_it() -> None:
    fake = await version_page({"version": "0.1.0", "url": "", "message": ""})
    service = UpdateCheck(lambda: replace(DEFAULTS, update_url=fake.url), "0.1.0", "linux", fetch, first_sec=3600.0, environ={"NEOAPRS_UPDATE_CHECK": "0"})
    await service.start()
    result = await service.check_now()
    assert result == CheckResult("current", "0.1.0")
    await until(lambda: len(fake.requests) == 1)
    await asyncio.sleep(0.1)
    assert len(fake.requests) == 1
    await service.stop()
