"""A `set_config` that carries an `id` is answered to its page, and only to it, with `saved` or an `error` that
carries the same `id`; a request without one is answered as before, by the topic alone."""

from pathlib import Path

from tests.support.env import Env
from tests.support.wsclient import WsClient


async def two_pages(e: Env) -> tuple[WsClient, WsClient]:
    pages = (await e.ws(), await e.ws())
    for page in pages:
        await page.until(lambda page=page: "config" in page.topics)  # type: ignore[misc]
    return pages


async def test_a_save_is_answered_with_its_id_to_the_asker_only(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    try:
        a, b = await two_pages(e)
        await a.send({"cmd": "set_config", "values": {"station/comment": "A"}, "id": 7})
        saved = await a.expect("saved")
        assert saved["id"] == 7
        await b.until(lambda: b.topics["config"]["values"]["station/comment"] == "A")
        assert b.of("saved") == []
    finally:
        await e.stop()


async def test_two_pages_saving_at_once_each_get_their_own_answer(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    try:
        a, b = await two_pages(e)
        await a.send({"cmd": "set_config", "values": {"station/lat": "95"}, "id": 1})
        await b.send({"cmd": "set_config", "values": {"station/comment": "B"}, "id": 1})
        refused = await a.expect("error")
        saved = await b.expect("saved")
        assert (refused["cmd"], refused["code"], refused["id"]) == ("set_config", "setting.range", 1)
        assert saved["id"] == 1
        assert a.of("saved") == [] and b.of("error") == []
    finally:
        await e.stop()


async def test_an_invalid_request_echoes_its_id(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    try:
        page = await e.ws()
        await page.send({"cmd": "set_config", "values": "no", "id": 3})
        error = await page.expect("error")
        assert (error["code"], error["id"]) == ("invalid", 3)
    finally:
        await e.stop()


async def test_a_request_without_an_id_is_answered_without_one(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    try:
        page = await e.ws()
        await page.until(lambda: "config" in page.topics)
        await page.send({"cmd": "set_config", "values": {"station/lat": "95"}})
        assert "id" not in await page.expect("error")
        await page.send({"cmd": "set_config", "values": {"station/comment": "Q"}})
        await page.until(lambda: page.topics["config"]["values"]["station/comment"] == "Q")
        assert page.of("saved") == []
    finally:
        await e.stop()
