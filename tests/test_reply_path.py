"""The reply path (M1): a message or an ack of ours to a station on a radio that carries no path goes by the gateway its latest packet on that radio came by (services/radioset.py `reply_path_on`,
services/prefbook.py `path_for`, neoaprs/app.py `_gateway_path`); LoRa's paths, the beacons, the objects and the answers are as they were."""
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from neoaprs import ax25, pairsetting
from neoaprs.app import Services
from neoaprs.aprsparse import parse
from neoaprs.clock import utc
from neoaprs.config import Config
from neoaprs.message import MessagingError
from neoaprs.messagelog import MessageLog
from neoaprs.packet import Message, Packet
from neoaprs.pairsetting import PairSpec
from neoaprs.radiospec import RadioSpec
from neoaprs.radiotype import FM_ID, HF_ID
from neoaprs.radiotypes import type_of
from neoaprs.services.queries import Queries
from neoaprs.services.radioset import path_on, reply_path_on
from neoaprs.stationbook import StationBook
from tests.support.env import remember_stop, until
from tests.support.stubtnc import StubTnc
from tests.support.seamshapes import frozen_air
from tests.support.storedb import log_at
from tests.test_messaging import LineAir, Rig, with_hf
from tests.test_queries import Rig as QueriesRig

STATION = "OH3ABC-9"
GATEWAY = "OH2GBA-12"
LORA_ID = 3
T0 = utc(2026, 11, 19, 12, 0, 0)


class GatewayRig(Rig):
    """The messaging rig with a station on HF, a station book that heard it there, and the app's own way of reading it (`Services._gateway_path`)."""

    def __init__(self, log: MessageLog, clock: object, **changes: object) -> None:
        super().__init__(log, clock, hf_enabled=True, station_call="OH3XYZ", **changes)       # type: ignore[arg-type]
        self.hf = with_hf(self, self.radios)
        self.radios.hf_stations = (STATION,)
        self.book = StationBook(self.clock)
        app = SimpleNamespace(stationbook=self.book, config=self.config)
        self.prefs._gateway = lambda call, radio: Services._gateway_path(app, call, radio)       # type: ignore[arg-type]
        self.app = app

    def hear(self, path: str, radio: int = HF_ID, source: str = STATION) -> None:
        """A packet of the station was heard on the radio by the path (the TNC2 form: a star on the last hop that repeated it)."""
        self.clock.advance(1)
        info = b">status"
        hops = tuple(path.split(",")) if path else ()
        self.book.take(Packet(self.clock(), "in", b"", source, "APRS", hops, info, parse(info, source, "APRS", self.clock()), radio_id=radio))      # type: ignore[arg-type]


@pytest.fixture
async def rig(tmp_path: Path) -> GatewayRig:
    log, _, clock = await log_at(tmp_path, MessageLog)
    r = GatewayRig(log, clock)
    await r.start()
    return r


async def sent_path(rig: GatewayRig, text: str = "Moi") -> str:
    await rig.m.send(STATION, text)
    return rig.hf.sent[-1].path_text


@pytest.mark.parametrize(("heard", "reply"), [
    ("OH2GBA-12*", "OH2GBA-12"),
    ("OH2RCH-2*,OH2GBA-12*", "OH2GBA-12,WIDE2-1"),
    ("OH2GBA*,OH2GBA-12*", "OH2GBA-12,WIDE2-1"),
    ("OH2GBA-2*,OH2GBA-12*", "OH2GBA-12,WIDE2-1"),
    ("WIDE1*,OH2GBA-12*", "OH2GBA-12,WIDE2-1"),
    ("", ""),
    ("WIDE1*", ""),
    ("OH2GBA-12*,WIDE1-1", "OH2GBA-12"),
], ids=["alone", "via-digi", "gateway-fill-in", "own-hill-digi", "wide-first", "direct", "alias-last", "unused-after"])
async def test_a_message_on_hf_goes_by_the_gateway_the_stations_latest_packet_came_by(rig: GatewayRig, heard: str, reply: str) -> None:
    rig.hear(heard)
    assert await sent_path(rig) == reply


async def test_a_station_never_heard_on_hf_gets_no_path_there(rig: GatewayRig) -> None:
    rig.hear("OH2RCH-2*,OH2GBA-12*", radio=FM_ID)
    assert await sent_path(rig) == "", "what FM heard is not how the station reaches us on HF"


async def test_the_latest_packet_on_hf_is_the_route_now(rig: GatewayRig) -> None:
    rig.hear("OH2GBA-12*")
    rig.clock.advance(3 * 3600)
    rig.hear("OH2RCH-2*,OH2GBA-12*")
    assert await sent_path(rig) == "OH2GBA-12,WIDE2-1", "no age limit, the latest packet counts"
    rig.clock.advance(timedelta(days=2).total_seconds())
    assert await sent_path(rig, "later") == "OH2GBA-12,WIDE2-1"


async def test_a_last_hop_that_is_one_of_our_own_calls_gives_no_path(rig: GatewayRig) -> None:
    rig.app.config = rig.config = replace(rig.config, pairs=(PairSpec(FM_ID, HF_ID, True, 12),), station_call="OH2GBA")
    rig.hear("OH2GBA-12*")
    assert await sent_path(rig) == "", "our own pair call is no gateway to reply by"


async def test_an_rf_only_station_gets_rfonly_after_a_reply_path_and_nothing_after_none(rig: GatewayRig) -> None:
    await rig.prefs.set_rf_only(STATION, True)
    rig.hear("OH2GBA-12*")
    assert await sent_path(rig) == "OH2GBA-12,RFONLY"


async def test_an_rf_only_station_heard_direct_on_hf_gets_no_rfonly_either(rig: GatewayRig) -> None:
    await rig.prefs.set_rf_only(STATION, True)
    rig.hear("")
    assert await sent_path(rig) == ""


async def test_the_ack_of_a_message_heard_on_hf_goes_back_by_the_gateway(rig: GatewayRig) -> None:
    rig.hear("OH2RCH-2*,OH2GBA-12*")
    packet = replace(rig.heard(STATION, "OH3XYZ", "Moi!", "12"), radio_id=HF_ID)
    rig.m.on_packet(packet)
    assert [f.path_text for f in rig.hf.sent] == ["OH2GBA-12,WIDE2-1"] and rig.hf.sent[0].info == f":{STATION:<9}:ack12".encode()


async def test_an_ack_that_waited_is_made_with_the_path_at_its_flush(rig: GatewayRig) -> None:
    rig.hear("OH2GBA-12*")
    rig.hf.held = "the channel is busy"
    rig.m.on_packet(replace(rig.heard(STATION, "OH3XYZ", "Moi!", "12"), radio_id=HF_ID))
    assert rig.hf.sent == []
    rig.hear("OH2RCH-2*,OH2GBA-12*")
    rig.hf.held = ""
    await rig.pass_time(3)
    assert [f.path_text for f in rig.hf.sent][:1] == ["OH2GBA-12,WIDE2-1"], "the path is the one of the flush"


async def test_the_longest_message_with_a_two_hop_reply_path_and_rfonly_leaves_hf_room_for_the_longest_reply_ack(rig: GatewayRig) -> None:
    await rig.prefs.set_rf_only(STATION, True)
    rig.hear("OH2RCH-2*,OH2GBA-12*")
    with pytest.raises(MessagingError) as refused:
        await rig.m.send(STATION, "x" * 67)
    assert refused.value.params == {"length": 124, "max": 123, "cut": 1}, "the frame and the five characters of the longest reply-ack number"
    await rig.m.send(STATION, "x" * 66)
    frame = rig.hf.sent[-1]
    assert frame.path_text == "OH2GBA-12,WIDE2-1,RFONLY" and len(ax25.encode(frame)) == 118


async def test_a_message_accepted_for_hf_still_fits_when_it_carries_a_five_character_reply_ack(rig: GatewayRig) -> None:
    await rig.prefs.set_rf_only(STATION, True)
    rig.hear("OH2RCH-2*,OH2GBA-12*")
    rig.m.on_packet(replace(rig.heard(STATION, "OH3XYZ", "Moi!", "12345", reply=""), radio_id=HF_ID))
    sent = await rig.m.send(STATION, "x" * 66)
    await until(lambda: rig.hf.sent[-1].info.endswith(b"{01}12345"))
    assert len(ax25.encode(rig.hf.sent[-1])) == 123 and rig.state(sent.id).state == "sending", "the attempt with the reply-ack is the last that fits, and nothing fails"


async def test_a_beacon_an_object_or_an_answer_on_hf_stays_without_a_path(rig: GatewayRig) -> None:
    rig.hear("OH2GBA-12*")
    air = frozen_air(rig.config.radio(HF_ID))       # type: ignore[arg-type]
    assert reply_path_on(air, rig.config, None) == (), "no reply path given: none"
    assert path_on(air, rig.config, ("OH2GBA-12",)) == (), "the answers, the queries and QRU go through path_on, which gives none on HF whatever the book says"
    assert rig.prefs.path_for(STATION, None, HF_ID) == ("OH2GBA-12",), "what the book gives for HF is the reply path"


async def test_an_answer_on_hf_to_a_station_heard_by_a_gateway_goes_without_a_path(rig: GatewayRig) -> None:
    rig.hear("OH2RCH-2*,OH2GBA-12*")
    asked = QueriesRig()
    asked.q = Queries(rig.radios, lambda: rig.config, asked.beacon, lambda radio=None: None, asked.book, rig.prefs.path_for, rig.clock)
    remember_stop(asked.q.stop)
    asked.q.on_packet(replace(asked.packet(STATION, Message("OH3XYZ", "?APRSP", None)), radio_id=HF_ID))
    await until(lambda: len(rig.hf.sent) == 1)
    assert rig.hf.sent[0].path_text == ""


async def test_loras_own_paths_are_unchanged_for_a_station_heard_by_a_gateway(rig: GatewayRig) -> None:
    lora = StubTnc(max_frame=250, rtype=type_of("lora-tcp"), id=LORA_ID)
    rig.config = replace(rig.config, radios=(*rig.config.radios, RadioSpec(LORA_ID, "lora", "lora-tcp", "", True, 2)))
    rig.app.config = rig.config
    rig.radios.radios.append(LineAir(lora, lambda: rig.config, id=LORA_ID))
    rig.radios.on.add(LORA_ID)
    rig.radios.chosen[STATION] = LORA_ID
    rig.hear("OH2GBA-12*", radio=LORA_ID)
    assert rig.prefs.path_for(STATION, 1, LORA_ID) == ("WIDE1-1",)
    await rig.m.send(STATION, "Moi")
    assert [f.path_text for f in lora.sent] == ["WIDE1-1"] and rig.hf.sent == []


def test_a_radio_that_carries_paths_takes_path_ons_path_and_a_radio_that_carries_none_the_one_given() -> None:
    config = Config.from_data({})
    fm, hf = (frozen_air(config.radio(i)) for i in (FM_ID, HF_ID))      # type: ignore[arg-type]
    assert reply_path_on(fm, config, ("A",)) == ("A",) and reply_path_on(hf, config, ("A",)) == ("A",)
    assert reply_path_on(hf, config, None) == () and reply_path_on(fm, config, None) == tuple(config.beacon_path_calls)


def test_the_app_reads_the_gateway_from_the_stations_latest_packet_on_the_radio() -> None:
    book = StationBook(lambda: T0)
    app = SimpleNamespace(stationbook=book, config=replace(Config.from_data({}), station_call="OH3XYZ", pairs=(PairSpec(1, 2, True, 12),)))
    assert Services._gateway_path(app, "OH3ABC-9", HF_ID) == ()       # type: ignore[arg-type]
    info = b">status"
    book.take(Packet(T0, "in", b"", "OH3ABC-9", "APRS", ("OH2RCH-2*", "OH2GBA-12*"), info, parse(info, "OH3ABC-9", "APRS", T0), radio_id=HF_ID))
    assert Services._gateway_path(app, "OH3ABC-9", HF_ID) == ("OH2GBA-12", "WIDE2-1") and Services._gateway_path(app, "OH3ABC-9", FM_ID) == ()       # type: ignore[arg-type]
    assert pairsetting.own_calls("OH3XYZ", app.config.pairs) == ("OH3XYZ", "OH3XYZ-12")
