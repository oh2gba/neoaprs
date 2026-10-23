"""The state hub (neoaprs/web/hub.py) with pages that are lists: what a patch holds, when it is made, a page that is behind, and the window of packets and the publisher that go with it (neoaprs/web/topics.py,
neoaprs/web/outbound.py). The topics of the real daemon over a socket are tests/test_web.py."""
import json
from typing import Any

import pytest

from neoaprs.clock import utc
from neoaprs.packet import Packet, Position
from neoaprs.web import outbound
from neoaprs.web.hub import BEHIND, StateHub, Topic
from neoaprs.web.outbound import MAX_MESSAGE, ProtocolViolation, Publisher
from neoaprs.web.session import Connection
from neoaprs.web.topics import PacketWindow
from tests.support.env import idle_for, until


class Page:
    """A page as the hub sees it: a list of frames, and how much its socket holds."""

    def __init__(self) -> None:
        self.frames: list[dict[str, Any]] = []
        self.held = 0

    def send_text(self, text: str) -> None:
        self.frames.append(json.loads(text))

    def buffered(self) -> int:
        return self.held


class Seconds:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def hub_of() -> tuple[StateHub, dict[str, dict[str, Any]], Seconds]:
    """A hub with a table topic (`rows`) and a whole topic (`one`, at most every 0.25 s)."""
    clock = Seconds()
    rows: dict[str, dict[str, Any]] = {}
    hub = StateHub(clock=clock)
    hub.add(Topic("rows", lambda: dict(rows), rows.get))
    hub.add(Topic("one", lambda: {"n": 0}, interval=0.25))
    return hub, rows, clock


# ---- what a patch holds --------------------------------------------------------------------------------------------------------------------------

def test_a_page_that_opens_is_sent_every_topic_whole() -> None:
    hub, rows, _ = hub_of()
    rows["a"] = {"x": 1}
    page = Page()
    hub.attach(page)
    assert [(f["type"], f["topic"], f["rev"]) for f in page.frames] == [("state", "rows", 0), ("state", "one", 0)]
    assert page.frames[0]["value"] == {"a": {"x": 1}} and page.frames[1]["value"] == {"n": 0}


def test_a_burst_of_changes_to_a_key_is_one_op_and_the_item_is_looked_up_when_the_patch_is_made() -> None:
    hub, rows, _ = hub_of()
    page = Page()
    hub.attach(page)
    page.frames.clear()
    for n in range(50):
        rows["a"] = {"n": n}
        hub.changed("rows", "a")
    rows["b"] = {"n": 1}
    hub.changed("rows", "b")
    assert hub.flush() is None
    assert page.frames == [{"type": "patch", "topic": "rows", "rev": 1, "ops": [{"op": "set", "key": "a", "value": {"n": 49}}, {"op": "set", "key": "b", "value": {"n": 1}}]}]
    assert hub.flush() is None and len(page.frames) == 1, "nothing changed: nothing is told"


def test_an_item_that_is_gone_when_the_patch_is_made_is_a_del_and_a_whole_change_forgets_the_keys() -> None:
    hub, rows, _ = hub_of()
    page = Page()
    hub.attach(page)
    page.frames.clear()
    rows["a"] = {"n": 1}
    hub.changed("rows", "a")
    del rows["a"]
    hub.changed("rows", "a")
    hub.changed("rows", "b")
    hub.flush()
    assert page.frames[0]["ops"] == [{"op": "del", "key": "a"}, {"op": "del", "key": "b"}]
    rows["c"] = {"n": 3}
    hub.changed("rows", "c")
    hub.changed("rows")                                                                       # all of it
    hub.changed("rows", "d")                                                                  # (after a whole change the keys are not needed)
    hub.flush()
    assert page.frames[1]["ops"] == [{"op": "replace", "value": {"c": {"n": 3}}}] and page.frames[1]["rev"] == 2


def test_a_topic_may_ask_for_a_gap_between_two_patches() -> None:
    hub, _, clock = hub_of()
    page = Page()
    hub.attach(page)
    page.frames.clear()
    hub.changed("one")
    assert hub.flush() is None and len(page.frames) == 1
    hub.changed("one")
    wait = hub.flush()
    assert wait is not None and 0.2 < wait <= 0.25 and len(page.frames) == 1, "told again when the gap has passed"
    clock.now += 0.25
    assert hub.flush() is None and len(page.frames) == 2 and page.frames[1]["rev"] == 2


async def test_the_tick_tells_the_pages_by_itself_and_stops_with_the_hub() -> None:
    hub, rows, _ = hub_of()
    page = Page()
    hub.attach(page)
    page.frames.clear()
    rows["a"] = {"n": 1}
    hub.changed("rows", "a")
    assert page.frames == [], "not at once: a burst is one patch"
    await until(lambda: page.frames)                # (the burst is told when the hub's pause is over)
    assert [f["type"] for f in page.frames] == ["patch"]
    hub.changed("rows", "a")
    hub.stop()
    await idle_for(0.25)
    assert len(page.frames) == 1, "a stopped hub tells nobody"


# ---- the pages -----------------------------------------------------------------------------------------------------------------------------------

def test_subscribe_sends_the_topic_again_and_names_the_topics_that_are_not_there_and_unsubscribe_stops_the_patches() -> None:
    hub, rows, _ = hub_of()
    page, other = Page(), Page()
    hub.attach(page)
    hub.attach(other)
    page.frames.clear()
    assert hub.subscribe(page, ["rows", "nothing", "weather"]) == ["nothing", "weather"]
    assert [f["topic"] for f in page.frames] == ["rows"]
    hub.unsubscribe(page, ["rows", "never-followed"])
    rows["a"] = {"n": 1}
    hub.changed("rows", "a")
    hub.flush()
    assert [f["type"] for f in page.frames] == ["state"] and other.frames[-1]["type"] == "patch"
    assert hub.following("rows") == 1 and hub.following("one") == 2
    hub.detach(other)
    assert hub.following("rows") == 0 and hub.subscribe(other, ["rows"]) == [], "a page that left is not followed again"


def test_a_page_that_is_behind_is_sent_no_patch_and_the_whole_topic_when_it_has_read_down() -> None:
    hub, rows, _ = hub_of()
    slow, quick = Page(), Page()
    hub.attach(slow)
    hub.attach(quick)
    for page in (slow, quick):
        page.frames.clear()
    slow.held = BEHIND + 1
    rows["a"] = {"n": 1}
    hub.changed("rows", "a")
    assert hub.flush() is not None, "the tick goes on while a page is behind"
    assert slow.frames == [] and [f["type"] for f in quick.frames] == ["patch"]
    rows["b"] = {"n": 2}
    hub.changed("rows", "b")
    hub.flush()
    assert slow.frames == [] and len(quick.frames) == 2
    slow.held = 0
    assert hub.flush() is None
    assert [(f["type"], f["topic"], f["rev"]) for f in slow.frames] == [("state", "rows", 2)] and set(slow.frames[0]["value"]) == {"a", "b"}
    rows["c"] = {"n": 3}
    hub.changed("rows", "c")
    hub.flush()
    assert slow.frames[-1]["type"] == "patch" and slow.frames[-1]["rev"] == 3, "patches again"


def test_a_socket_that_cannot_say_how_much_it_holds_is_behind() -> None:
    hub, rows, _ = hub_of()

    class Broken(Page):
        def buffered(self) -> int:
            raise RuntimeError("closed")

    page = Broken()
    hub.attach(page)
    page.frames.clear()
    rows["a"] = {"n": 1}
    hub.changed("rows", "a")
    hub.flush()
    assert page.frames == []


@pytest.mark.expects_errors
def test_a_page_whose_socket_fails_does_not_stop_the_others() -> None:
    hub, rows, _ = hub_of()

    class Failing(Page):
        def send_text(self, text: str) -> None:
            raise OSError("broken pipe")

    bad, good = Failing(), Page()
    hub.attach(good)
    hub.attach(bad)
    good.frames.clear()
    rows["a"] = {"n": 1}
    hub.changed("rows", "a")
    hub.flush()
    assert [f["type"] for f in good.frames] == ["patch"]


def test_a_topic_is_added_once() -> None:
    hub, _, _ = hub_of()
    with pytest.raises(ValueError, match="rows"):
        hub.add(Topic("rows", dict))


# ---- the window of packets -----------------------------------------------------------------------------------------------------------------------

def packet(n: int) -> Packet:
    return Packet(heard_at=utc(2026, 10, 21, 12, 0, n % 60), direction="in", raw=b"", source=f"OH2T{n}", destination="APRS", path=(), info=b"", decoded=Position(60.0, 24.0, "/", ">"))


def test_the_window_counts_the_packets_up_and_forgets_the_oldest() -> None:
    window = PacketWindow(size=3)
    assert [window.add(packet(n)) for n in range(1, 6)] == [[1], [2], [3], [4, 1], [5, 2]]
    assert list(window.whole()) == ["3", "4", "5"] and window.item("4") == window.rows[4] and window.item("1") is None and window.item("x") is None and window.item("-1") is None


def test_the_window_starts_with_the_packets_the_database_kept_oldest_first() -> None:
    window = PacketWindow(size=3)
    window.load([packet(n) for n in (9, 8, 7, 6, 5)])                       # (the newest first, as the log gives them; two fall out)
    assert [r["source"] for r in window.whole().values()] == ["OH2T7", "OH2T8", "OH2T9"] and list(window.whole()) == ["1", "2", "3"]
    assert window.add(packet(10)) == [4, 1]


# ---- the publisher -------------------------------------------------------------------------------------------------------------------------------

class Socket:
    def __init__(self) -> None:
        self.frames: list[str] = []

    def send_json(self, text: str) -> None:
        self.frames.append(text)

    def buffered(self) -> int:
        return 0


@pytest.mark.expects_errors
def test_a_message_that_does_not_fit_the_protocol_is_found_when_the_check_is_on() -> None:
    out = Publisher(validate_out=True)
    out.raise_on_invalid = False                                                            # (the tests run with the switch on)
    socket = Socket()
    conn = out.open(socket, "127.0.0.1")
    conn.send({"type": "pong", "now": "2026-10-21T12:00:00Z"})
    assert outbound.VIOLATIONS == []
    try:
        conn.send({"type": "pong", "now": "yesterday"})
        conn.send({"type": "pong", "now": "2026-10-21T12:00:00Z", "extra": 1})
        conn.send({"type": "state", "topic": "tnc", "rev": 0, "value": {"state": "connected"}})
        conn.send({"type": "state", "topic": "weather", "rev": 0, "value": {}})
        conn.send({"type": "patch", "topic": "stations", "rev": 1, "ops": [{"op": "set", "key": "OH2X", "value": {"call": "OH2X"}}]})
        found = list(outbound.VIOLATIONS)
    finally:
        outbound.VIOLATIONS.clear()
    assert len(found) == 5 and all(line.split(":")[0] in ("pong", "state", "patch") for line in found)
    assert "now" in found[0] and "extra" in found[1] and "the value of tnc" in found[2] and "problem: Field required" in found[2] and "weather" in found[3]
    assert "the item OH2X of stations" in found[4] and "kind: Field required" in found[4]
    assert len(socket.frames) == 6, "a message that does not fit is sent all the same (the check is for the tests)"


def test_with_the_raise_switch_a_message_that_does_not_fit_raises() -> None:
    out = Publisher(validate_out=True)
    out.raise_on_invalid = True
    conn = out.open(Socket(), "127.0.0.1")
    try:
        with pytest.raises(ProtocolViolation, match="pong"):
            conn.send({"type": "pong", "now": 5})
    finally:
        outbound.VIOLATIONS.clear()


def test_the_check_is_off_by_default_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEOAPRS_VALIDATE_OUT")
    out = Publisher()
    assert not out.validate_out
    out.open(Socket(), "127.0.0.1").send({"type": "nonsense"})
    assert outbound.VIOLATIONS == []
    monkeypatch.setenv("NEOAPRS_VALIDATE_OUT", "1")
    assert Publisher().validate_out


def test_a_message_too_big_to_send_is_replaced_by_an_error_that_says_so(caplog: pytest.LogCaptureFixture) -> None:
    out = Publisher(validate_out=True)
    socket = Socket()
    conn = out.open(socket, "127.0.0.1")
    conn.send_text(json.dumps({"type": "state", "topic": "stations", "rev": 1, "value": "x" * (MAX_MESSAGE + 1)}))
    (frame,) = socket.frames
    assert json.loads(frame)["type"] == "error" and "state answer" in json.loads(frame)["text"] and len(frame) < 300
    assert any("was not sent" in r.getMessage() for r in caplog.records)


def test_a_closed_connection_is_written_nothing_and_a_broadcast_reaches_the_rest() -> None:
    out = Publisher(validate_out=True)
    a, b = Socket(), Socket()
    conn_a, _ = out.open(a, "127.0.0.1"), out.open(b, "127.0.0.2")
    out.close(a)
    conn_a.send({"type": "error", "text": "late"})
    out.broadcast({"type": "error", "text": "to all"})
    assert a.frames == [] and len(b.frames) == 1 and conn_a.closed
    out.close(a)                                                                                   # again: harmless


def test_every_connection_is_a_link_of_the_hub_and_asks_the_socket_how_much_it_holds() -> None:
    socket = Socket()
    conn: Connection = Publisher(validate_out=False).open(socket, "127.0.0.1")
    hub = StateHub()
    hub.add(Topic("one", lambda: {"n": 0}))
    hub.attach(conn)
    assert json.loads(socket.frames[0])["topic"] == "one" and conn.buffered() == 0
