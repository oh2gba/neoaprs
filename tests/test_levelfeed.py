"""The feed of a Sound card radio's receive level ten times a second (neoaprs/web/levelfeed.py, `radio_level`): only the pages that ask are sent it, the level now at once and then each change; a page that is
behind is skipped; a page that stops, or leaves, is sent no more, and the level is let go of once no page looks; a radio whose modem is another one is followed on the new one, one that has none any more is said
to have no level. On the wire: the daemon's own Sound card radio answers `radio_level`, and refuses it for a radio of a type without a receive level."""
from pathlib import Path
from typing import Any

import pytest

from neoaprs import radioregistry
from neoaprs.direwolfprogram import LevelNow
from neoaprs.web.levelfeed import LevelFeed, Leveled, RadioLevels
from neoaprs.web.session import Connection
from tests.support.env import until
from tests.test_radios_wire import added, refused, started


class Client:
    def __init__(self, held: int = 0) -> None:
        self.held, self.sent = held, list[dict[str, Any]]()

    def send_json(self, text: str) -> None: ...

    def send_binary(self, data: bytes) -> None: ...

    def buffered(self) -> int:
        return self.held


class Out:
    def send(self, conn: Connection, message: dict[str, Any]) -> None:
        assert isinstance(conn.client, Client)
        conn.client.sent.append(message)

    def send_frame(self, conn: Connection, text: str) -> None: ...

    def send_binary(self, conn: Connection, data: bytes) -> None: ...


class Modem:
    def __init__(self) -> None:
        self.level_now = LevelNow()


def page(held: int = 0) -> tuple[Connection, Client]:
    client = Client(held)
    return Connection(client, Out()), client


def wired() -> tuple[RadioLevels, list[tuple[Leveled, bool]]]:
    told: list[tuple[Leveled, bool]] = []

    def wire(feed: LevelFeed, modem: Leveled, on: bool) -> None:
        told.append((modem, on))
        (modem.level_now.changed.connect if on else modem.level_now.changed.disconnect)(feed.said)

    return RadioLevels(wire), told


def levels(client: Client) -> list[int | None]:
    return [m["level"] for m in client.sent if m["type"] == "radio_level"]


def test_only_the_pages_that_ask_are_sent_the_level_now_at_once_and_each_change_and_a_page_behind_is_skipped() -> None:
    feeds, told = wired()
    modem, other = Modem(), Modem()
    modem.level_now.said(31)
    (a, ca), (_, cb), (late, cl) = page(), page(), page(held=10**9)
    feeds.ask(a, 3, modem)
    feeds.ask(late, 3, modem)
    assert levels(ca) == [31] and ca.sent[0] == {"type": "radio_level", "radio": 3, "level": 31} and levels(cl) == []
    modem.level_now.said(44)
    modem.level_now.said(44)                                     # (a level that stays is not said again)
    other.level_now.said(9)                                      # (another radio's modem, which nobody looks at)
    assert levels(ca) == [31, 44] and levels(cb) == [] and levels(cl) == [] and told == [(modem, True)] and feeds.pages(3) == 2
    cl.held = 0
    modem.level_now.said(12)
    assert levels(cl) == [12], "a page that has read is sent the next level, which tells it what it missed"


def test_a_page_that_stops_or_leaves_is_sent_no_more_and_nobody_looking_lets_the_level_go() -> None:
    feeds, told = wired()
    modem = Modem()
    (a, ca), (b, cb) = page(), page()
    feeds.ask(a, 3, modem)
    feeds.ask(b, 3, modem)
    feeds.stop(a, 3)
    modem.level_now.said(5)
    assert levels(ca) == [None] and levels(cb) == [None, 5]
    feeds.forget(b)
    modem.level_now.said(6)
    assert levels(cb) == [None, 5] and told == [(modem, True), (modem, False)] and feeds.pages(3) == 0 and len(modem.level_now.changed) == 0
    feeds.stop(b, 3)                                             # (a stop for a radio nobody looks at is nothing)
    gone, cg = page()
    gone.closed = True
    feeds.ask(gone, 3, modem)
    assert cg.sent == [] and feeds.pages(3) == 0, "a page that left before its command ran is not taken"


def test_a_radio_whose_modem_is_another_is_followed_on_the_new_one_and_one_without_a_level_is_said_to_have_none() -> None:
    feeds, told = wired()
    old, new = Modem(), Modem()
    (a, ca) = page()
    feeds.ask(a, 3, old)
    feeds.keep({3: old})
    assert told == [(old, True)]
    new.level_now.said(20)
    feeds.keep({3: new})
    old.level_now.said(1)
    new.level_now.said(21)
    assert levels(ca) == [None, 20, 21] and told == [(old, True), (old, False), (new, True)]
    feeds.keep({})
    assert levels(ca)[-1] is None and feeds.pages(3) == 0
    feeds.ask(a, 3, new)
    feeds.disconnect()
    assert told[-1] == (new, False) and len(new.level_now.changed) == 0


async def test_on_the_wire_a_sound_card_radio_answers_with_its_level_and_a_radio_without_one_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(radioregistry.CARRIED, "direwolf", lambda: True)
    e, ws = await started(tmp_path)
    try:
        id = await added(ws, "direwolf")
        await ws.send({"cmd": "radio_level", "radio": id, "on": True})
        await ws.until(lambda: bool(ws.of("radio_level")))
        assert ws.of("radio_level")[-1] == {"type": "radio_level", "radio": id, "level": None}, "its Direwolf does not run here"
        await ws.send({"cmd": "radio_level", "radio": id, "on": False})
        kiss = await added(ws, "kiss")
        error = await refused(ws, {"cmd": "radio_level", "radio": kiss, "on": True})
        assert error["code"] == "radio.no_modem" and error["params"]["radio"] == kiss
        assert (await refused(ws, {"cmd": "radio_level", "radio": 99, "on": True}))["code"] == "radio.unknown"
    finally:
        await e.stop()


async def test_a_sound_card_radio_that_is_off_is_never_refused_and_one_changed_to_another_type_is_let_go_without_a_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The page asks while the box is in view, whatever the radio does: a radio switched off is answered (no level), never refused with a toast; when its type changes while a page looks, the stop the page
    sends as the box goes is not refused either, and the old modem is let go."""
    monkeypatch.setitem(radioregistry.CARRIED, "direwolf", lambda: True)
    e, ws = await started(tmp_path)
    try:
        id = await added(ws, "direwolf")
        await ws.send({"cmd": "radio_change", "radio": id, "enabled": False})
        await ws.until(lambda: ws.topics["radios"][str(id)]["enabled"] is False)
        errors = len(ws.of("error"))
        await ws.send({"cmd": "radio_level", "radio": id, "on": True})
        await ws.until(lambda: len(ws.of("radio_level")) == 1)
        assert ws.of("radio_level")[-1]["level"] is None and len(ws.of("error")) == errors
        old = e.ctl.radios.get(id).driver.modem
        await ws.send({"cmd": "radio_change", "radio": id, "type": "kiss"})
        await ws.until(lambda: ws.topics["radios"][str(id)]["type"] == "kiss")
        await ws.send({"cmd": "radio_level", "radio": id, "on": False})          # (the box of the type before goes, and its row with it)
        await until(lambda: len(old.level_now.changed) == 0)
        assert len(ws.of("error")) == errors and ws.of("radio_level")[-1]["level"] is None
    finally:
        await e.stop()
