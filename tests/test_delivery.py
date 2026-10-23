"""The delivery chain of a message (neoaprs/services/delivery.py, chain.py) on messaging with a stub Tnc and a real database: a copy of our own message heard back is linked to the message and to the attempt it
belongs to, shows which hops of the path were used, is kept across a restart and goes with the message; copies of anything else are not linked."""
from pathlib import Path

import pytest

from neoaprs.message import MessageRecord
from neoaprs.messagelog import MessageLog
from neoaprs.packet import Message, Packet, ThirdParty
from neoaprs.store import DB_NAME, Store
from tests.support.clock import FixedClock
from tests.support.storedb import sql, store_at
from tests.test_messaging import Rig

SEEN = tuple[int, str, bool]                    # (position, call, via_internet) of a hop that was heard


class Chain:
    """A messaging that sends by OH2RCH-2,OH2RDG (or the path given), the store under it, and the packets of our own message as the Tnc would hear them."""

    def __init__(self, store: Store, clock: FixedClock, path: str = "OH2RCH-2,OH2RDG") -> None:
        assert store.db is not None
        self.store = store
        self.rig = Rig(MessageLog(store.db, clock), clock, beacon_path=path)
        self.path = path
        self.told: list[MessageRecord] = []
        self.rig.m.changed.connect(self.told.append)

    @property
    def clock(self) -> FixedClock:
        return self.rig.clock

    def copy(self, path: str, text: str = "Hello Pekka", msg_id: str | None = "01", to: str = "OH2RDG", source: str = "OH2GBA", ack: str | None = None) -> Packet:
        """A packet heard from `source` with this path (a star on each address that has been repeated, as the radio gave them), a message to `to`."""
        return Packet(self.clock(), "in", b"", source, "APZNEO", tuple(p for p in path.split(",") if p), b"", Message(to, "" if ack else text, None if ack else msg_id, ack))

    def gated(self, inner: str, gate: str = "OH7JHF-1", text: str = "Hello Pekka", msg_id: str | None = "01", to: str = "OH2RDG") -> Packet:
        """The same message wrapped by an iGate: the frame heard is the gate's, the packet inside is ours with `inner` as its path."""
        return Packet(self.clock(), "in", b"", gate, "APRS", ("OH2RCH-3*",), b"", Message(to, text, msg_id), ThirdParty("OH2GBA", "APZNEO", tuple(p for p in inner.split(",") if p)))

    def hear(self, packet: Packet) -> None:
        self.rig.m.on_packet(packet)

    def seen(self, number: int = 1) -> list[list[SEEN]]:
        """For each attempt of the message: what was heard of it."""
        return [[(s.position, s.call, s.via_internet) for s in a.seen] for a in self.rig.m.delivery.attempts_of(number)]

    async def rows(self, table: str) -> list[tuple[object, ...]]:
        await self.rig.settled()
        return await sql(self.store, f"SELECT * FROM {table} ORDER BY 1, 2, 3")

    async def restarted(self) -> "Chain":
        """The daemon stops and starts again on the same database."""
        await self.rig.settled()
        await self.rig.m.stop()
        again = Chain(self.store, self.clock, self.path)
        await again.rig.start()
        return again


@pytest.fixture
async def chain(tmp_path: Path) -> Chain:
    clock = FixedClock()
    c = Chain(await store_at(tmp_path / DB_NAME, clock), clock)
    await c.rig.start()
    return c


async def test_every_attempt_keeps_the_time_it_was_sent_and_the_path_it_went_by(chain: Chain) -> None:
    first = chain.clock()
    await chain.rig.m.send("OH2RDG", "Hello Pekka")
    await chain.rig.pass_time(30)
    assert [(a.number, a.sent_at, a.path, a.seen) for a in chain.rig.m.delivery.attempts_of(1)] == [(1, first, ("OH2RCH-2", "OH2RDG"), ()), (2, chain.clock(), ("OH2RCH-2", "OH2RDG"), ())]
    assert [row[:2] + row[3:] for row in await chain.rows("message_attempt")] == [(1, 1, "OH2RCH-2,OH2RDG"), (1, 2, "OH2RCH-2,OH2RDG")]


async def test_a_copy_with_the_first_digipeater_used_marks_hop_1_and_a_later_copy_with_the_second_marks_hop_2(chain: Chain) -> None:
    await chain.rig.m.send("OH2RDG", "Hello Pekka")
    chain.clock.advance(2)
    chain.hear(chain.copy("OH2RCH-2*,OH2RDG"))
    assert chain.seen() == [[(1, "OH2RCH-2", False)]]
    assert [r.id for r in chain.told][-1] == 1 and chain.rig.state().attempts == 1
    chain.clock.advance(3)
    chain.hear(chain.copy("OH2RCH-2*,OH2RDG*"))
    assert chain.seen() == [[(1, "OH2RCH-2", False), (2, "OH2RDG", False)]]
    hops = await chain.rows("message_hop")
    assert [r[2] for r in hops] == [1, 2] and hops[0][4] < hops[1][4], "each hop has the time of the first copy that showed it"


async def test_a_copy_heard_again_with_nothing_new_changes_nothing_and_tells_nobody(chain: Chain) -> None:
    await chain.rig.m.send("OH2RDG", "Hello Pekka")
    chain.hear(chain.copy("OH2RCH-2*,OH2RDG"))
    told = len(chain.told)
    chain.clock.advance(5)
    chain.hear(chain.copy("OH2RCH-2*,OH2RDG"))
    assert len(chain.told) == told and chain.seen() == [[(1, "OH2RCH-2", False)]]
    assert len(await chain.rows("message_hop")) == 1


async def test_the_tnc2_star_on_the_last_digipeater_shows_the_ones_before_it_used_too(chain: Chain) -> None:
    await chain.rig.m.send("OH2RDG", "Hello Pekka")
    chain.hear(chain.copy("OH2RCH-2,OH2RDG*"))
    assert chain.seen() == [[(1, "OH2RCH-2", False), (2, "OH2RDG", False)]]


async def test_an_alias_of_the_path_is_recorded_as_the_call_that_used_it(tmp_path: Path) -> None:
    clock = FixedClock()
    c = Chain(await store_at(tmp_path / DB_NAME, clock), clock, "WIDE1-1,WIDE2-1")
    await c.rig.start()
    await c.rig.m.send("OH2RDG", "Hello Pekka")
    c.hear(c.copy("OH2RCH-2*,WIDE2-1"))
    assert c.seen() == [[(1, "OH2RCH-2", False)]]
    c.hear(c.copy("OH2RCH-2*,OH2RDG*"))
    assert c.seen() == [[(1, "OH2RCH-2", False), (2, "OH2RDG", False)]]
    assert [tuple(r)[2:4] for r in await c.rows("message_hop")] == [(1, "OH2RCH-2"), (2, "OH2RDG")]


async def test_a_copy_belongs_to_the_latest_attempt_sent_before_it_was_heard(chain: Chain) -> None:
    await chain.rig.m.send("OH2RDG", "Hello Pekka")
    chain.clock.advance(10)
    chain.hear(chain.copy("OH2RCH-2*,OH2RDG"))                          # (attempt 1)
    await chain.rig.pass_time(20)                                      # (attempt 2 goes out at 30 s)
    chain.clock.advance(1)
    chain.hear(chain.copy("OH2RCH-2*,OH2RDG*"))
    assert chain.seen() == [[(1, "OH2RCH-2", False)], [(1, "OH2RCH-2", False), (2, "OH2RDG", False)]]


async def test_a_copy_gated_back_by_an_igate_marks_the_attempt_as_seen_over_the_internet_with_the_gates_call(chain: Chain) -> None:
    await chain.rig.m.send("OH2RDG", "Hello Pekka")
    chain.hear(chain.gated("TCPIP,OH7JHF-1*"))
    assert chain.seen() == [[(0, "OH7JHF-1", True)]], "its own path names no hop of ours: only that it came back by the gate"
    chain.clock.advance(2)
    chain.hear(chain.gated("OH2RCH-2*,OH2RDG*,qAR,OH7JHF-1", gate="OH7JHF-2"))
    assert chain.seen() == [[(0, "OH7JHF-1", True), (1, "OH2RCH-2", True), (2, "OH2RDG", True)]], "the first gate stays, and the hops the inner path names are marked over the internet"
    assert [tuple(r)[2:4] + (r[5],) for r in await chain.rows("message_hop")] == [(0, "OH7JHF-1", 1), (1, "OH2RCH-2", 1), (2, "OH2RDG", 1)]


async def test_a_hop_heard_by_radio_and_over_the_internet_is_kept_for_both(chain: Chain) -> None:
    await chain.rig.m.send("OH2RDG", "Hello Pekka")
    chain.hear(chain.copy("OH2RCH-2*,OH2RDG"))
    chain.hear(chain.gated("OH2RCH-2*,OH2RDG,qAR,OH7JHF-1"))
    assert chain.seen() == [[(1, "OH2RCH-2", False), (0, "OH7JHF-1", True), (1, "OH2RCH-2", True)]]


@pytest.mark.parametrize("what", ["another addressee", "another id", "another text", "no id", "an ack", "a message from another station", "a message to us"])
async def test_a_copy_of_anything_but_our_message_is_not_linked(chain: Chain, what: str) -> None:
    await chain.rig.m.send("OH2RDG", "Hello Pekka")
    packet = {"another addressee": chain.copy("OH2RCH-2*", to="OH2XYZ"), "another id": chain.copy("OH2RCH-2*", msg_id="02"), "another text": chain.copy("OH2RCH-2*", text="Hello Matti"),
              "no id": chain.copy("OH2RCH-2*", msg_id=None), "an ack": chain.copy("OH2RCH-2*", ack="01"), "a message from another station": chain.copy("OH2RCH-2*", source="OH2XYZ"),
              "a message to us": chain.copy("OH2RCH-2*", to="OH2GBA")}[what]
    told = len(chain.told)
    chain.hear(packet)
    assert chain.seen() == [[]] and len(chain.told) == told and await chain.rows("message_hop") == []


async def test_a_copy_of_a_message_we_did_not_send_or_before_its_first_attempt_is_not_linked(chain: Chain) -> None:
    chain.hear(chain.copy("OH2RCH-2*"))
    assert chain.rig.m.records() == [] and await chain.rows("message_hop") == []
    chain.clock.advance(-60)
    await chain.rig.m.send("OH2RDG", "Hello Pekka")
    chain.clock.advance(-1)
    chain.hear(chain.copy("OH2RCH-2*"))
    assert chain.seen() == [[]], "a copy heard before the attempt was sent is no copy of it"


async def test_the_attempts_and_hops_are_kept_across_a_restart(chain: Chain) -> None:
    await chain.rig.m.send("OH2RDG", "Hello Pekka")
    chain.hear(chain.copy("OH2RCH-2*,OH2RDG"))
    await chain.rig.pass_time(30)
    chain.hear(chain.gated("TCPIP,OH7JHF-1*"))
    before = chain.rig.m.delivery.attempts_of(1)
    again = await chain.restarted()
    assert again.rig.m.delivery.attempts_of(1) == before and len(before) == 2
    assert again.seen() == [[(1, "OH2RCH-2", False)], [(0, "OH7JHF-1", True)]]
    again.hear(again.copy("OH2RCH-2*,OH2RDG*"))
    assert again.seen()[1][-1] == (2, "OH2RDG", False)
    await again.rig.m.stop()


async def test_a_message_that_is_deleted_takes_its_chain_with_it_and_another_messages_stays(chain: Chain) -> None:
    await chain.rig.m.send("OH2RDG", "Hello Pekka")
    await chain.rig.m.send("OH2RDG", "Second")
    chain.hear(chain.copy("OH2RCH-2*,OH2RDG"))
    chain.hear(chain.copy("OH2RCH-2*", text="Second", msg_id="02"))
    assert len(await chain.rows("message_hop")) == 2
    await chain.rig.m.delete(1)
    assert [tuple(r)[:2] for r in await chain.rows("message_hop")] == [(2, 1)] and [tuple(r)[:2] for r in await chain.rows("message_attempt")] == [(2, 1)]
    assert chain.rig.m.delivery.attempts_of(1) == ()


async def test_a_conversation_that_is_deleted_takes_the_chains_of_its_messages_with_it(chain: Chain) -> None:
    await chain.rig.m.send("OH2RDG", "Hello Pekka")
    await chain.rig.m.send("OH2AAA", "Other station")
    chain.hear(chain.copy("OH2RCH-2*,OH2RDG"))
    chain.hear(chain.copy("OH2RCH-2*", to="OH2AAA", text="Other station", msg_id="02"))
    assert await chain.rig.m.delete_conversation("OH2RDG") == 1
    assert [tuple(r)[:2] for r in await chain.rows("message_hop")] == [(2, 1)] and [tuple(r)[:2] for r in await chain.rows("message_attempt")] == [(2, 1)]


async def test_a_message_that_is_sent_again_starts_a_new_chain(chain: Chain) -> None:
    record = await chain.rig.m.send("OH2RDG", "Hello Pekka")
    chain.hear(chain.copy("OH2RCH-2*,OH2RDG"))
    chain.rig.m.cancel(record.id)
    chain.rig.m.retry(record.id)
    assert chain.seen() == [[]] and [a.number for a in chain.rig.m.delivery.attempts_of(1)] == [1]
    assert await chain.rows("message_hop") == [] and len(await chain.rows("message_attempt")) == 1
