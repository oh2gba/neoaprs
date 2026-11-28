"""The lines the iGate has put on APRS-IS, kept for the Internet box of the page (neoaprs/services/igate.py `sent`,
neoaprs/web/igatefeed.py, `igate_look` and `igate_sent`): the ring's bound and content against the fake APRS-IS,
that nothing of the login can be in it, and that a page is sent it only while it looks.
"""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from neoaprs import ax25
from neoaprs.services.igate import SENT_KEPT
from neoaprs.tncmode import packet_of
from neoaprs.web.igatefeed import IgateLooks
from neoaprs.web.igatewire import IgateSentMsg
from tests.support.air import on_air
from tests.support.env import Env, until
from tests.support.fakeaprsis import FakeAprsIs, fake_aprsis
from tests.support.igateworld import IWorld, frame_of
from tests.test_levelfeed import page


async def quiet(server: FakeAprsIs) -> IWorld:
    """A connected iGate that has no position of its own to send, so that the ring starts empty."""
    w = IWorld(server)
    w.position_info = None
    await w.igate.start()
    await until(lambda: w.igate.state in ("connected", "unverified"))
    return w


def heard_on(w: IWorld, radio: int, source: str = "OH2XYZ-9", info: bytes = b"!6010.00N/02456.00E>Test") -> None:
    """A packet the radio with this id heard, given to the iGate."""
    f = frame_of(source=source, info=info)
    w.igate.on_packet(replace(packet_of("in", ax25.encode(f), f, w.clock()), radio_id=radio))  # type: ignore[arg-type]


async def test_the_ring_holds_each_line_as_the_server_got_it_with_its_time_and_the_radio_that_heard_it() -> None:
    server = await fake_aprsis()
    w = await quiet(server)
    assert list(w.igate.sent) == [], "empty at the start"
    start = w.clock()
    heard_on(w, 3, "OH2AAA-1", b"!6010.00N/02456.00E>one")
    await until(lambda: len(w.igate.sent) == 1)  # (kept when written)
    w.clock.advance(5)
    heard_on(w, 4, "OH2BBB-2", b"!6011.00N/02457.00E>two")
    await w.until_sent(2)
    first, second = w.igate.sent
    assert (first.at, first.radio) == (start, 3) and (second.at, second.radio) == (start + timedelta(seconds=5), 4)
    assert first.line.startswith("OH2AAA-1>APZ123,") and first.line.endswith(",OH2GBA-10:!6010.00N/02456.00E>one")
    assert [first.line, second.line] == server.packets, "exactly what the server was sent, in the order it was sent"


async def test_the_ring_keeps_the_newest_ones_and_no_more_than_its_bound() -> None:
    server = await fake_aprsis()
    w = await quiet(server)
    for n in range(SENT_KEPT + 7):
        heard_on(w, 1, "OH2AAA-1", f"!6010.00N/02456.00E>n{n}".encode())
    await w.until_sent(SENT_KEPT + 7)
    await until(lambda: w.igate.sent[-1].line.endswith(f">n{SENT_KEPT + 6}"))
    assert len(w.igate.sent) == SENT_KEPT
    assert w.igate.sent[0].line.endswith(">n7") and w.igate.sent[-1].line.endswith(f">n{SENT_KEPT + 6}")


async def test_nothing_of_the_login_or_the_server_or_a_packet_not_gated_is_ever_in_the_ring() -> None:
    server = await fake_aprsis()
    w = IWorld(server)
    await w.igate.start()
    await until(lambda: w.igate.state == "connected")
    await until(lambda: any(line.startswith("OH2GBA-10>APZ") for line in server.packets))
    server.send(b"# a comment of the server")
    server.send(b"OH2NET>APRS,TCPIP*,qAC,TESTSRV:!6011.00N/02457.00E-internet station")
    heard_on(w, 2, "OH2AAA-1", b"!6010.00N/02456.00E>one")
    heard_on(w, 2, "OH2AAA-1", b"!6010.00N/02456.00E>one")  # a duplicate
    w.hear(path="TCPIP*", info=b"!6010.00N/02456.00E>by internet")  # not gated
    await w.until_sent(2)
    text = "\n".join(s.line for s in w.igate.sent)
    for secret in ("user ", "pass", "19628", "vers ", "# a comment", "OH2NET", "by internet"):
        assert secret not in text, secret
    assert [s.line for s in w.igate.sent if s.radio is None] == [
        line for line in server.packets if line.startswith("OH2GBA-10>APZ")
    ], "our own position is there, with no radio"
    assert sum(s.radio == 2 for s in w.igate.sent) == 1


async def test_a_line_queued_but_never_written_to_the_server_is_not_in_the_ring() -> None:
    server = await fake_aprsis()
    w = await quiet(server)
    heard_on(w, 1, "OH2AAA-1", b"!6010.00N/02456.00E>lost")
    w.igate._link._drop_session()  # the connection went before the line was written
    heard_on(w, 1, "OH2BBB-2", b"!6011.00N/02457.00E>after")
    await until(lambda: w.igate.state == "connected" and w.igate._link.verified)
    heard_on(w, 1, "OH2CCC-3", b"!6012.00N/02458.00E>written")
    await until(lambda: any(line.endswith(">written") for line in server.packets))
    await until(lambda: len(w.igate.sent) >= 1 and w.igate.sent[-1].line.endswith(">written"))
    assert [s.line.rsplit(">", 1)[1] for s in w.igate.sent] == ["written"]
    assert [s.line for s in w.igate.sent] == [line for line in server.packets if not line.startswith("#")][-1:]


async def test_a_login_the_server_refused_puts_nothing_in_the_ring() -> None:
    server = await fake_aprsis(verified=False)
    w = await quiet(server)
    assert w.igate.state == "unverified"
    heard_on(w, 1)
    assert list(w.igate.sent) == []


async def test_a_page_that_looks_is_sent_the_ring_at_once_and_each_line_after_and_a_page_that_does_not_nothing() -> (
    None
):
    server = await fake_aprsis()
    w = await quiet(server)
    looks = IgateLooks(w.igate)
    w.igate.line_sent.connect(looks.told)
    heard_on(w, 1, "OH2AAA-1", b"!6010.00N/02456.00E>one")
    await until(lambda: len(w.igate.sent) == 1)
    (a, ca), (_, cb), (late, cl) = page(), page(), page(held=10**9)
    looks.look(a, True)
    looks.look(late, True)
    assert looks.pages() == 2
    assert [(m["whole"], [r["line"] for r in m["lines"]]) for m in ca.sent] == [(True, [w.igate.sent[0].line])]
    assert ca.sent[0]["type"] == "igate_sent" and ca.sent[0]["lines"][0]["radio"] == 1
    heard_on(w, 2, "OH2BBB-2", b"!6011.00N/02457.00E>two")
    await until(lambda: len(w.igate.sent) == 2)
    assert [(m["whole"], [r["line"] for r in m["lines"]]) for m in ca.sent[1:]] == [(False, [w.igate.sent[1].line])]
    assert cb.sent == [], "a page that did not ask is sent nothing"
    assert len(cl.sent) == 1, "a page that is behind is skipped"
    cl.held = 0
    heard_on(w, 2, "OH2CCC-3", b"!6012.00N/02458.00E>three")
    await until(lambda: len(w.igate.sent) == 3)
    assert [(m["whole"], len(m["lines"])) for m in cl.sent[1:]] == [(True, 3)], "and brought up to date whole"
    assert [r["line"] for r in cl.sent[-1]["lines"]] == [s.line for s in w.igate.sent]
    looks.look(a, False)
    before = len(ca.sent)
    heard_on(w, 2, "OH2DDD-4", b"!6013.00N/02459.00E>four")
    await until(lambda: len(w.igate.sent) == 4)
    assert len(ca.sent) == before and looks.pages() == 1, "the look ended: nothing more"
    looks.forget(late)
    assert looks.pages() == 0
    closed, cc = page()
    closed.closed = True
    looks.look(closed, True)
    assert cc.sent == [] and looks.pages() == 0, "a page that left before its command ran is not taken"


async def test_on_the_wire_a_page_gets_the_ring_and_the_new_lines_only_while_it_looks(tmp_path: Path) -> None:
    server = await fake_aprsis()
    e = Env(
        tmp_path,
        web=True,
        settings={"igate/enabled": "false", "igate/gate": "true", "igate/server": server.address},
    )
    await e.start()
    await e.until_usable()
    try:
        await until(lambda: e.ctl.igate.state == "connected")
        ws = await e.ws()
        await ws.until(lambda: "igate" in ws.topics)
        await ws.send({"cmd": "igate_look", "on": True})
        await ws.until(lambda: len(ws.of("igate_sent")) == 1)
        assert ws.of("igate_sent")[0]["whole"] is True
        e.feed(on_air("OH2RDG-7", b"!6010.00N/02456.00E>hello", path="WIDE1-1,WIDE2-1"))
        await ws.until(lambda: any(not m["whole"] for m in ws.of("igate_sent")))
        sent = next(m for m in ws.of("igate_sent") if not m["whole"])
        (row,) = sent["lines"]
        assert row["line"].startswith("OH2RDG-7>APRS,WIDE1-1,WIDE2-1,qAO,") and row["line"].endswith(">hello")
        assert row["line"] in server.packets and isinstance(row["radio"], int) and row["at"].endswith("Z")
        await ws.send({"cmd": "igate_look", "on": False})
        await ws.send({"cmd": "ping"})
        await until(lambda: len(ws.of("pong")) == 1)
        count = len(ws.of("igate_sent"))
        e.feed(on_air("OH2RDG-8", b"!6011.00N/02457.00E>again", path="WIDE1-1,WIDE2-1"))
        await until(lambda: any(line.endswith(">again") for line in server.packets))
        await ws.send({"cmd": "ping"})
        await until(lambda: len(ws.of("pong")) == 2)
        assert len(ws.of("igate_sent")) == count, "no more after the look ended"
        other = await e.ws()
        await other.until(lambda: "igate" in other.topics)
        await other.send({"cmd": "igate_look", "on": True})
        await other.until(lambda: bool(other.of("igate_sent")))
        lines = other.of("igate_sent")[0]["lines"]
        assert [r["line"] for r in lines if r["radio"] is not None] == [
            line for line in server.packets if line.startswith("OH2RDG")
        ], "a page that opens later is given what was sent before"
    finally:
        await e.stop()


def test_the_wire_allows_as_many_lines_as_the_ring_keeps() -> None:
    assert IgateSentMsg.model_fields["lines"].metadata[0].max_length == SENT_KEPT
