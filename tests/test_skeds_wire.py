"""The sked board through the page socket: the topic `skeds` and the commands `skeds_wanted`,
`sked_post` and `sked_delete`, against a small local server (tests/support/fakeskeds.py).
"""

from datetime import timedelta
from pathlib import Path
from typing import Any

from neoaprs.clock import iso, utcnow
from neoaprs.services.skeds import ENV_URL
from neoaprs.versions import Frequency
from tests.support.env import Env
from tests.support.fakeskeds import FakeSkeds, skeds_server
from tests.support.wsclient import WsClient

BUILT_IN = [
    {"band": "80 m", "dial": "3.5850 MHz USB"},
    {"band": "40 m", "dial": "7.0541 MHz USB"},
    {"band": "20 m", "dial": "14.1070 MHz USB"},
    {"band": "10 m", "dial": "28.1800 MHz USB"},
    {"band": "6 m", "dial": "50.6200 MHz USB"},
]


def when(hours: float) -> str:
    return (iso(utcnow().replace(microsecond=0) + timedelta(hours=hours))) or ""


def post(**more: Any) -> dict[str, Any]:
    return {
        "cmd": "sked_post",
        "from": when(2),
        "to": when(4),
        "dial": "7.0541 MHz USB",
        "note": "Mercury, 10 W",
        **more,
    }


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


async def test_the_topic_is_off_while_the_update_check_is_off_and_has_the_dials_the_hf_box_suggests(
    tmp_path: Path,
) -> None:
    e = await started(tmp_path)
    page, value = await topic(e)
    assert value == {"state": "off", "fetched_at": None, "frequencies": BUILT_IN, "rows": [], "past": []}
    await page.send({"cmd": "skeds_wanted"})
    await page.quiet(0.2)
    assert e.ctl.skeds.asked == 0
    await page.send(post())
    error = await page.expect("error")
    assert (error["cmd"], error["code"]) == ("sked_post", "sked.unreachable")
    await e.stop()


async def test_a_page_that_shows_the_tab_has_the_board_read_and_told_to_every_page_and_a_404_is_a_board_with_no_skeds(
    tmp_path: Path,
) -> None:
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


async def test_a_post_is_told_with_ours_and_a_delete_takes_it_off_and_a_row_of_somebody_else_has_no_ours(
    tmp_path: Path,
) -> None:
    server = await skeds_server()
    server.rows = [
        {"id": "7f3a9c21d4e0", "call": "OH2XYZ", "from": when(1), "to": when(3), "dial": "14.1070 MHz USB", "note": ""}
    ]
    e = await started(tmp_path, server)
    page, _ = await topic(e)
    await page.send({"cmd": "skeds_wanted"})
    await page.until(lambda: len(page.topics["skeds"]["rows"]) == 1)
    assert page.topics["skeds"]["rows"][0]["ours"] is False
    await page.send(post())
    await page.until(lambda: len(page.topics["skeds"]["rows"]) == 2)
    mine = next(r for r in page.topics["skeds"]["rows"] if r["call"] == "OH2GBA")
    assert (
        mine["ours"] is True
        and mine["dial"] == "7.0541 MHz USB"
        and mine["note"] == "Mercury, 10 W"
        and set(mine) == {"id", "call", "from", "to", "dial", "note", "ours"}
    )
    assert [r["from"] for r in page.topics["skeds"]["rows"]] == sorted(
        r["from"] for r in page.topics["skeds"]["rows"]
    ), "the nearest first"
    await page.send({"cmd": "sked_delete", "id": mine["id"]})
    await page.until(lambda: len(page.topics["skeds"]["rows"]) == 1)
    assert page.topics["skeds"]["rows"][0]["id"] == "7f3a9c21d4e0"
    await page.send({"cmd": "sked_delete", "id": "7f3a9c21d4e0"})
    await page.quiet(0.3)
    assert [r["id"] for r in page.topics["skeds"]["rows"]] == ["7f3a9c21d4e0"], (
        "not ours: nothing is said and nothing is deleted"
    )
    await e.stop()


async def test_the_refusals_come_with_codes_and_a_closed_board_is_a_state_not_an_error(tmp_path: Path) -> None:
    server = await skeds_server()
    e = await started(tmp_path, server)
    page, _ = await topic(e)
    for reason, status, code in (
        ("rate", 429, "sked.rate"),
        ("full", 409, "sked.full"),
        ("call_full", 409, "sked.call_full"),
        ("past", 422, "sked.past"),
        ("bad_request", 400, "sked.unreachable"),
    ):
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


async def test_a_sked_that_has_ended_by_the_daemons_clock_leaves_the_topic_and_a_new_call_tells_it_again(
    tmp_path: Path,
) -> None:
    server = await skeds_server()
    server.rows = [
        {"id": "7f3a9c21d4e0", "call": "OH2XYZ", "from": when(-1), "to": when(1), "dial": "14.1070 MHz USB", "note": ""}
    ]
    e = await started(tmp_path, server)
    e.ctl.skeds.expire_sec = 0.05
    page, _ = await topic(e)
    await page.send({"cmd": "skeds_wanted"})
    await page.until(lambda: len(page.topics["skeds"]["rows"]) == 1)
    await e.ctl.skeds.start()
    e.ctl.skeds._clock = lambda: utcnow() + timedelta(hours=2)
    await page.until(lambda: page.topics["skeds"]["rows"] == [])
    await e.stop()


async def test_a_test_that_ends_while_the_page_is_open_moves_from_the_board_to_the_past_tests_with_the_servers_own(
    tmp_path: Path,
) -> None:
    server = await skeds_server()
    server.rows = [
        {
            "id": "7f3a9c21d4e0",
            "call": "OH2XYZ",
            "from": when(-1),
            "to": when(1),
            "dial": "14.1070 MHz USB",
            "note": "",
        },
        {
            "id": "7f3a9c21d4e1",
            "call": "OH3ABC",
            "from": when(-1),
            "to": when(1),
            "dial": "14.1070 MHz USB",
            "note": "x",
        },
    ]
    server.past = [
        {
            "id": "0123456789ab",
            "call": "OH2GBA",
            "from": when(-30),
            "to": when(-29),
            "dial": "7.0541 MHz USB",
            "note": "",
        }
    ]
    e = await started(tmp_path, server)
    e.ctl.skeds.expire_sec = 0.05
    page, _ = await topic(e)
    await page.send({"cmd": "skeds_wanted"})
    await page.until(lambda: len(page.topics["skeds"]["rows"]) == 2)
    assert [p["id"] for p in page.topics["skeds"]["past"]] == ["0123456789ab"] and server.past_gets == 1
    assert set(page.topics["skeds"]["past"][0]) == {"id", "call", "from", "to", "dial", "note"}
    await e.ctl.skeds.start()
    e.ctl.skeds._clock = lambda: utcnow() + timedelta(hours=2)
    await page.until(lambda: page.topics["skeds"]["rows"] == [])
    past = page.topics["skeds"]["past"]
    assert [(p["id"], p["call"], p["note"]) for p in past] == [
        ("7f3a9c21d4e0", "OH2XYZ", ""),
        ("7f3a9c21d4e1", "OH3ABC", "x"),
        ("0123456789ab", "OH2GBA", ""),
    ], "the test that just ended, with the call that joined it, newest first"
    assert len(server.gets) == 1, "no new read of the board was needed"
    await e.stop()


async def test_the_dials_of_the_topic_follow_the_dials_of_the_radio(tmp_path: Path) -> None:
    e = await started(tmp_path)
    page, value = await topic(e)
    assert value["frequencies"] == BUILT_IN
    e.ctl.frequencies.listed = [Frequency("30 m", "10.1462 MHz USB")]
    e.ctl.frequencies.changed.emit()
    await page.until(lambda: page.topics["skeds"]["frequencies"] == [{"band": "30 m", "dial": "10.1462 MHz USB"}])
    assert e.ctl.suggested_frequencies == [Frequency("30 m", "10.1462 MHz USB")], (
        "the same dials as an HF radio's box: the station's"
    )
    await e.stop()


async def test_a_post_with_no_call_is_refused_and_a_command_that_is_not_right_is_refused_whole(tmp_path: Path) -> None:
    server = await skeds_server()
    e = await started(tmp_path, server, **{"station/call": ""})
    page, _ = await topic(e)
    await page.send(post())
    error = await page.expect("error")
    assert error["cmd"] == "sked_post" and "set your call first" in error["text"]
    assert (error["code"], error["params"]["why"]) == ("transmit.call", "call.none"), (
        "coded: the page says it in its language"
    )
    for broken in (
        post(dial="7.0541 MHz FM"),
        post(dial="7.0541 MHz USB\n"),
        post(**{"from": "2026-02-30T18:00:00Z"}),
        post(**{"from": when(4), "to": when(2)}),
        post(**{"from": when(2), "to": when(30)}),
        post(note="x" * 321),
        {**post(), "call": "OH2XYZ"},
        {k: v for k, v in post().items() if k != "from"},
        {**post(), "from_": when(2)},
        {"cmd": "sked_delete", "id": "7F3A9C21D4E0"},
        {"cmd": "sked_delete", "id": "../../etc/pa"},
        {"cmd": "sked_delete"},
        {"cmd": "skeds_wanted", "now": True},
    ):
        await page.send(broken)
        assert (await page.expect("error"))["code"] == "invalid", broken
    assert server.posts == []
    await e.stop()


async def test_a_past_test_taken_off_goes_for_every_page_and_nothing_is_posted_and_a_coming_or_unknown_one_is_refused(
    tmp_path: Path,
) -> None:
    server = await skeds_server()
    server.rows = [
        {"id": "7f3a9c21d4e0", "call": "OH2XYZ", "from": when(1), "to": when(3), "dial": "14.1070 MHz USB", "note": ""}
    ]
    gone = {"call": "OH2XYZ", "from": when(-30), "to": when(-29), "dial": "7.0541 MHz USB", "note": ""}
    server.past = [
        {**gone, "id": "0123456789ab"},
        {**gone, "id": "0123456789ac", "call": "OH3ABC"},
        {**gone, "id": "0123456789ad", "from": when(-50), "to": when(-49)},
    ]
    e = await started(tmp_path, server)
    page, _ = await topic(e)
    other, _ = await topic(e)
    await page.send({"cmd": "skeds_wanted"})
    await other.until(lambda: len(other.topics["skeds"]["past"]) == 3)
    for ids in (["7f3a9c21d4e0"], ["fedcba987654"], ["0123456789ad", "fedcba987654"]):
        await page.send({"cmd": "sked_past_delete", "ids": ids})
        error = await page.expect("error")
        assert (error["cmd"], error["code"]) == ("sked_past_delete", "failed"), ids
    await page.send({"cmd": "sked_past_delete", "ids": ["0123456789ab", "0123456789ac"]})
    await other.until(lambda: [p["id"] for p in other.topics["skeds"]["past"]] == ["0123456789ad"])
    assert [r["id"] for r in other.topics["skeds"]["rows"]] == ["7f3a9c21d4e0"]
    assert server.posts == [] and len(server.gets) == 1, "nothing is sent to the server"
    await e.stop()
