"""The command `bulletin_delete` over the socket: the entry leaves the board, the database and every page (a `del` of the topic `bulletins`), a bulletin sent again is new, and nothing else is touched."""
import json
from pathlib import Path

from tests.support.air import message_info, on_air
from tests.support.env import Env
from tests.support.wsclient import WsClient
from neoaprs.web.bulletinwire import BulletinRow
from neoaprs.web.protocol import TOPIC_NAMES


async def with_board(tmp_path: Path) -> tuple[Env, WsClient]:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    e.feed(on_air("OH2XYZ", message_info("BLN3HAMS", "Net tonight 20:00", "5")))
    e.feed(on_air("OH2ABC", message_info("QST", "Club news")))
    await page.until(lambda: {"OH2XYZ/BLN3HAMS", "OH2ABC/QST"} <= set(page.topics["bulletins"]))
    return e, page


async def test_bulletin_delete_removes_the_entry_from_every_page_and_the_database(tmp_path: Path) -> None:
    e, page = await with_board(tmp_path)
    other = await e.ws()
    await other.until(lambda: len(other.of("state")) == len(TOPIC_NAMES) and "OH2XYZ/BLN3HAMS" in other.topics["bulletins"])
    await page.send({"cmd": "bulletin_delete", "sender": "OH2XYZ", "slot": "BLN3HAMS"})
    await page.until(lambda: "OH2XYZ/BLN3HAMS" not in page.topics["bulletins"])
    await other.until(lambda: "OH2XYZ/BLN3HAMS" not in other.topics["bulletins"])
    assert page.ops("bulletins")[-1] == {"op": "del", "key": "OH2XYZ/BLN3HAMS"} and list(page.topics["bulletins"]) == ["OH2ABC/QST"]
    await e.settled()
    assert [b.key for b in await e.ctl.bulletinlog.all()] == ["OH2ABC/QST"]
    assert page.of("error") == []
    await e.stop()


async def test_a_bulletin_sent_again_after_the_delete_is_a_new_entry_heard_once(tmp_path: Path) -> None:
    e, page = await with_board(tmp_path)
    e.now.advance(60)                                                                                   # type: ignore[attr-defined]
    e.feed(on_air("OH2XYZ", message_info("BLN3HAMS", "Net tonight 20:00", "5")))
    await page.until(lambda: page.topics["bulletins"]["OH2XYZ/BLN3HAMS"]["times_heard"] == 2)
    await page.send({"cmd": "bulletin_delete", "sender": "OH2XYZ", "slot": "BLN3HAMS"})
    await page.until(lambda: "OH2XYZ/BLN3HAMS" not in page.topics["bulletins"])
    e.now.advance(60)                                                                                   # type: ignore[attr-defined]
    e.feed(on_air("OH2XYZ", message_info("BLN3HAMS", "Net tonight 20:00", "5")))
    await page.until(lambda: "OH2XYZ/BLN3HAMS" in page.topics["bulletins"])
    row = BulletinRow.model_validate_json(json.dumps(page.topics["bulletins"]["OH2XYZ/BLN3HAMS"]))
    assert row.times_heard == 1 and row.first_heard == row.last_heard
    await e.stop()


async def test_deleting_what_is_not_there_is_an_error_and_changes_nothing(tmp_path: Path) -> None:
    e, page = await with_board(tmp_path)
    await page.send({"cmd": "bulletin_delete", "sender": "OH2NONE", "slot": "BLN1"})
    assert (await page.expect("error"))["text"] == "bulletin_delete: there is no entry OH2NONE/BLN1 on the board"
    await page.send({"cmd": "bulletin_delete", "sender": "OH2XYZ"})
    assert "slot" in (await page.expect("error"))["text"]
    assert len(page.topics["bulletins"]) == 2
    await e.stop()
