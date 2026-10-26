"""What each service does with a packet that came from the internet (`Packet.via` is `is`): nothing. Each test hands the service the very packet it acts on when it is heard on the radio, with only the
channel changed, after showing that the radio's packet makes it act (so that the test could see the action), and then the packet of the internet, and finds no frame sent, no message kept, no object
dropped, no answer, nothing remembered. The services that do take it (the packet log, the station book, the weather log) are in tests/test_packetlog.py, tests/test_station_channels.py and
tests/test_weatherlog.py; the walk over all of them is tests/test_internet_gate.py."""
from dataclasses import replace
from pathlib import Path

from neoaprs import ax25
from neoaprs.bulletinlog import BulletinLog
from neoaprs.packet import IS, Message, Other, Packet
from neoaprs.services.bulletins import Bulletins
from neoaprs.store import DB_NAME
from neoaprs.tncmode import packet_of
from tests.support.clock import FixedClock
from tests.support.env import idle_for
from tests.support.fakeaprsis import fake_aprsis
from tests.support.igateworld import iworld
from tests.support.storedb import store_at
from tests.test_delivery import Chain
from tests.test_digipeater import INFO, Rig as DigiRig, frame
from tests.test_messaging import started_rig
from tests.test_ownobjects import reported, rig_at
from tests.test_qru import Rig as QruRig
from tests.test_queries import Rig as QueryRig


def internet(packet: Packet) -> Packet:
    """The same packet as if APRS-IS had handed it on."""
    return replace(packet, via=IS)


def test_the_digipeater_repeats_a_packet_of_the_radio_and_not_the_same_packet_from_the_internet() -> None:
    rig = DigiRig()
    f = frame("WIDE1-1", info=INFO)
    on_the_radio = packet_of("in", ax25.encode(f), f, rig.clock())
    rig.digi.on_packet(internet(on_the_radio))
    assert rig.tnc.sent == [] and rig.digi._seen == {}, "nothing sent, and not remembered as heard either"
    rig.digi.on_packet(on_the_radio)
    assert rig.lines() == [f"OH2XYZ>APRS,OH2GBA*:{INFO.decode()}"], "the radio's copy is repeated, which an earlier internet copy did not prevent"


async def test_the_igate_puts_a_packet_of_the_radio_on_the_server_and_not_the_same_packet_from_the_internet_or_the_dummy_radio() -> None:
    server = await fake_aprsis()
    w = await iworld(server)
    heard = w.hear()
    w.igate.on_packet(internet(heard))
    w.igate.on_packet(replace(heard, via="dummy"))
    assert w.igate.gated == 1 and w.igate.dropped["not_air"] == 2, "only the radio's copy was gated, and the other two are counted"
    await w.until_sent(2)
    await idle_for(0.1)
    assert [line for line in server.packets if line.startswith("OH2XYZ-9>")] == ["OH2XYZ-9>APZ123,WIDE1-1*,WIDE2-1,qAO,OH2GBA-10:!6010.00N/02456.00E>Test"]


def test_the_queries_answer_a_query_from_the_radio_and_none_from_the_internet() -> None:
    rig = QueryRig()
    for text in ("?APRSP", "?APRSD", "?PING?"):
        rig.q.on_packet(internet(rig.packet("OH2RDG", Message("OH2GBA", text, "5"))))
    rig.q.on_packet(internet(rig.packet("OH2RDG", Other("query", "?APRS?", None))))
    assert rig.tnc.sent == [] and rig.q._general_until is None
    rig.ask("OH2RDG", "?APRSP")
    assert rig.tnc.sent == [rig.beacon.frame()], "the same query on the radio is answered"


async def test_the_qru_server_answers_a_request_from_the_radio_and_none_from_the_internet() -> None:
    rig = QruRig()
    rig.add("RP70", "FOOD")
    request = Message("QRU", "INFO")
    asking = Packet(rig.clock(), "in", b"", "OH2RDG", "APRS", ("OH2RCH-2*",), b"", request)
    assert rig.qru.heard(internet(asking), request) is False and rig.tnc.sent == []
    assert rig.ask("OH2RDG", "INFO") is True
    await idle_for(0.1)
    assert rig.texts() != [], "the same request on the radio is answered"


async def test_the_message_board_keeps_a_bulletin_of_the_radio_and_none_from_the_internet(tmp_path: Path) -> None:
    clock = FixedClock()
    store = await store_at(tmp_path / DB_NAME, clock)
    assert store.db is not None
    board = Bulletins(BulletinLog(store.db, clock), clock)
    await board.start()
    message = Message("BLN1", "Road closed")
    packet = Packet(clock(), "in", b"", "OH2XYZ", "APRS", (), b"", message)
    board.heard(internet(packet), message)
    assert board.records() == []
    board.heard(packet, message)
    assert [b.key for b in board.records()] == ["OH2XYZ/BLN1"]


async def test_messaging_keeps_and_acks_a_message_of_the_radio_and_neither_from_the_internet(tmp_path: Path) -> None:
    rig = await started_rig(tmp_path)
    asked = rig.heard("OH2RDG", "OH2GBA", "Moi!", "12")
    rig.m.on_packet(internet(asked))
    await rig.settled()
    assert rig.m.records() == [] and rig.tnc.sent == [] and rig.m.inbox.heard._at == {} and rig.m.inbox.heard._acked == {}
    rig.m.on_packet(asked)
    await rig.settled()
    assert [(r.from_call, r.text, r.state) for r in rig.m.records()] == [("OH2RDG", "Moi!", "received")] and len(rig.tnc.sent) == 1, "on the radio it is kept and acked"


async def test_an_ack_and_a_rej_from_the_internet_settle_no_message_of_ours(tmp_path: Path) -> None:
    rig = await started_rig(tmp_path)
    await rig.m.send("OH2RDG", "Hello")
    await rig.m.send("OH2RDG", "Again")
    rig.m.on_packet(internet(rig.heard("OH2RDG", "OH2GBA", ack="01")))
    rig.m.on_packet(internet(rig.heard("OH2RDG", "OH2GBA", rej="02")))
    assert (rig.state(1).state, rig.state(2).state) == ("sending", "sending")
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", ack="01"))
    assert rig.state(1).state == "acked", "from the radio the same ack settles it"


async def test_a_copy_of_our_message_from_the_internet_is_no_hop_of_its_chain(tmp_path: Path) -> None:
    clock = FixedClock()
    chain = Chain(await store_at(tmp_path / DB_NAME, clock), clock)
    await chain.rig.start()
    await chain.rig.m.send("OH2RDG", "Hello Pekka")
    copy = chain.copy("OH2RCH-2*", source="OH2GBA")
    told = list(chain.told)
    chain.hear(internet(copy))
    assert chain.seen() == [[]] and chain.told == told
    chain.hear(copy)
    assert chain.seen() == [[(1, "OH2RCH-2", False)]], "heard on the radio it shows the hop"


async def test_an_object_of_ours_reported_by_a_station_on_the_internet_is_not_taken_over(tmp_path: Path) -> None:
    rig = await rig_at(tmp_path)
    rig.make("LEADER")
    taken: list[str] = []
    rig.objects.removed.connect(lambda obj: taken.append(obj.name))
    rig.objects.on_packet(internet(reported("LEADER", rig.clock())))
    await idle_for(0.05)
    assert taken == [] and [o.name for o in rig.objects.records()] == ["LEADER"]
    rig.objects.on_packet(reported("LEADER", rig.clock()))
    assert taken == ["LEADER"], "reported on the radio by another station it is dropped"
