"""The sked board through the page's socket: the topic `skeds` (the state, the suggested dials, the rows with `ours`) and the commands `skeds_wanted`, `sked_post` and `sked_delete`, against a small server on this computer (tests/support/fakeskeds.py): nothing reaches
the project's. The update check is off in the tests, so the service is switched on in the one daemon that needs it and pointed at the fake server with NEOAPRS_SKEDS_URL's own mechanism; the refusals the operator can do something about come with their codes, a closed
board is no error, a command that is not right is refused whole, and the topic is told when a sked ends, when the call changes and when the radio's dials change."""
from datetime import timedelta
from pathlib import Path
from typing import Any

from neoaprs.clock import iso, utcnow
from neoaprs.services.skeds import ENV_URL
from neoaprs.versions import Frequency
from tests.support.env import Env
from tests.support.fakeskeds import FakeSkeds, skeds_server
from tests.support.wsclient import WsClient

BUILT_IN = [{"band": "40 m", "dial": "7.0541 MHz USB"}, {"band": "20 m", "dial": "14.1070 MHz USB"}, {"band": "6 m", "dial": "50.6200 MHz USB"}]


def when(hours: float) -> str:
    return (iso(utcnow().replace(microsecond=0) + timedelta(hours=hours))) or ""


def post(**more: Any) -> dict[str, Any]:
    return {"cmd": "sked_post", "from": when(2), "to": when(4), "dial": "7.0541 MHz USB", "note": "Mercury, 10 W", **more}


async def started(tmp_path: Path, server: FakeSkeds | None = None, on: bool = True, **settings: str) -> Env:
    e = Env(tmp_path / "data", web=True, settings=settings or None)
    await e.start()
    if on and server is not None:
        e.ctl.skeds._environ = {ENV_URL: server.url}
    return e


async def topic(e: Env) -> tuple[WsClient, dict[str, Any]]:
    page = await e.ws()
    value = (await page.expect("state", "skeds"))["value"]
    return page, value


async def test_the_topic_is_off_while_the_update_check_is_off_and_has_the_dials_the_hf_box_suggests(tmp_path: Path) -> None:
    e = await started(tmp_path)
    page, value = await topic(e)
    assert value == {"state": "off", "fetched_at": None, "frequencies": BUILT_IN, "rows": []}
    await page.send({"cmd": "skeds_wanted"})
    await page.quiet(0.2)
    assert e.ctl.skeds.asked == 0
    await page.send(post())
    error = await page.expect("error")
    assert (error["cmd"], error["code"]) == ("sked_post", "sked.unreachable")
    await e.stop()


async def test_a_page_that_shows_the_tab_has_the_board_read_and_told_to_every_page_and_a_404_is_a_board_with_no_skeds(tmp_path: Path) -> None:
    server = await skeds_server()
    e = await started(tmp_path, server)
    page, value = await topic(e)
    other, _ = await topic(e)
    assert value["state"] == "ok" and value["rows"] == []
    await page.send({"cmd": "skeds_wanted"})
    await other.until(lambda: other.topics["skeds"]["fetched_at"] is not None)
    assert other.topics["skeds"]["state"] == "ok" and other.topics["skeds"]["rows"] == [] and len(server.gets) == 1
    await page.send({"cmd": "skeds_wanted"})
    await page.quiet(0.3)
    assert len(server.gets) == 1, "the second asking is within the fifteen minutes"
    await e.stop()


async def test_a_post_is_told_with_ours_and_a_delete_takes_it_off_and_a_row_of_somebody_else_has_no_ours(tmp_path: Path) -> None:
    server = await skeds_server()
    server.rows = [{"id": "7f3a9c21d4e0", "call": "OH2XYZ", "from": when(1), "to": when(3), "dial": "14.1070 MHz USB", "note": ""}]
    e = await started(tmp_path, server)
    page, _ = await topic(e)
    await page.send({"cmd": "skeds_wanted"})
    await page.until(lambda: len(page.topics["skeds"]["rows"]) == 1)
    assert page.topics["skeds"]["rows"][0]["ours"] is False
    await page.send(post())
    await page.until(lambda: len(page.topics["skeds"]["rows"]) == 2)
    mine = next(r for r in page.topics["skeds"]["rows"] if r["call"] == "OH2GBA")
    assert mine["ours"] is True and mine["dial"] == "7.0541 MHz USB" and mine["note"] == "Mercury, 10 W" and set(mine) == {"id", "call", "from", "to", "dial", "note", "ours"}
    assert [r["from"] for r in page.topics["skeds"]["rows"]] == sorted(r["from"] for r in page.topics["skeds"]["rows"]), "the nearest first"
    await page.send({"cmd": "sked_delete", "id": mine["id"]})
    await page.until(lambda: len(page.topics["skeds"]["rows"]) == 1)
    assert page.topics["skeds"]["rows"][0]["id"] == "7f3a9c21d4e0"
    await page.send({"cmd": "sked_delete", "id": "7f3a9c21d4e0"})
    await page.quiet(0.3)
    assert [r["id"] for r in page.topics["skeds"]["rows"]] == ["7f3a9c21d4e0"], "not ours: nothing is said and nothing is deleted"
    await e.stop()


async def test_the_refusals_come_with_codes_and_a_closed_board_is_a_state_not_an_error(tmp_path: Path) -> None:
    server = await skeds_server()
    e = await started(tmp_path, server)
    page, _ = await topic(e)
    for reason, status, code in (("rate", 429, "sked.rate"), ("full", 409, "sked.full"), ("past", 422, "sked.past"), ("bad_request", 400, "sked.unreachable")):
        server.refuse = (reason, status)
        await page.send(post())
        error = await page.expect("error")
        assert (error["cmd"], error["code"]) == ("sked_post", code), reason
    server.refuse = ("closed", 403)
    await page.send(post())
    await page.until(lambda: page.topics["skeds"]["state"] == "closed")
    await page.send({"cmd": "ping"})
    assert (await page.expect("pong"))["type"] == "pong", "no error came for the closed board"
    await e.stop()


async def test_a_sked_that_has_ended_by_the_daemons_clock_leaves_the_topic_and_a_new_call_tells_it_again(tmp_path: Path) -> None:
    server = await skeds_server()
    server.rows = [{"id": "7f3a9c21d4e0", "call": "OH2XYZ", "from": when(-1), "to": when(1), "dial": "14.1070 MHz USB", "note": ""}]
    e = await started(tmp_path, server)
    e.ctl.skeds.expire_sec = 0.05
    page, _ = await topic(e)
    await page.send({"cmd": "skeds_wanted"})
    await page.until(lambda: len(page.topics["skeds"]["rows"]) == 1)
    await e.ctl.skeds.start()
    e.ctl.skeds._clock = lambda: utcnow() + timedelta(hours=2)
    await page.until(lambda: page.topics["skeds"]["rows"] == [])
    await e.stop()


async def test_the_dials_of_the_topic_follow_the_dials_of_the_radio(tmp_path: Path) -> None:
    e = await started(tmp_path)
    page, value = await topic(e)
    assert value["frequencies"] == BUILT_IN
    e.ctl.frequencies.listed = [Frequency("30 m", "10.1462 MHz USB")]
    e.ctl.frequencies.changed.emit()
    await page.until(lambda: page.topics["skeds"]["frequencies"] == [{"band": "30 m", "dial": "10.1462 MHz USB"}])
    assert page.topics["hf"]["modem"]["frequencies"] == [{"band": "30 m", "dial": "10.1462 MHz USB"}], "the same dials as the HF box"
    await e.stop()


async def test_a_post_with_no_call_is_refused_and_a_command_that_is_not_right_is_refused_whole(tmp_path: Path) -> None:
    server = await skeds_server()
    e = await started(tmp_path, server, **{"station/call": ""})
    page, _ = await topic(e)
    await page.send(post())
    error = await page.expect("error")
    assert error["cmd"] == "sked_post" and "set your call first" in error["text"]
    for broken in (post(dial="7.0541 MHz FM"), post(dial="7.0541 MHz USB\n"), post(**{"from": "2026-02-30T18:00:00Z"}), post(**{"from": when(4), "to": when(2)}), post(**{"from": when(2), "to": when(30)}),
                   post(note="x" * 321), {**post(), "call": "OH2XYZ"}, {k: v for k, v in post().items() if k != "from"}, {**post(), "from_": when(2)}, {"cmd": "sked_delete", "id": "7F3A9C21D4E0"}, {"cmd": "sked_delete", "id": "../../etc/pa"},
                   {"cmd": "sked_delete"}, {"cmd": "skeds_wanted", "now": True}):
        await page.send(broken)
        assert (await page.expect("error"))["code"] == "invalid", broken
    assert server.posts == []
    await e.stop()
