"""Tests that a receive-only radio type (`lora-console`, `Can.transmit` false) sends nothing: not a
beacon, message, ack or object, and every sending command is refused with `radio.receive_only`,
while it still hears every packet. With the FM radio off too, the station is RX only.
"""

import socket
from pathlib import Path

import pytest

from neoaprs import ax25, loralist
from neoaprs.loraboard import RECEIVE_ONLY
from neoaprs.radiospec import FM_ID, senders
from neoaprs.services.beacon import ONLY_RECEIVES
from neoaprs.services.radioset import ack_radio, answerable
from neoaprs.source import Source
from neoaprs.tnc2line import frame_of
from tests.support.env import Env, until, until_started
from tests.support.fakelora import Board, BoardOnTcp
from tests.test_radios_wire import added, refused

ME = "OH2GBA"
HEARD = b"OH2ABC-7>APLRT1,WIDE1-1:!6010.00N/02456.00E>tracker"
QUERY = b"OH2ABC-7>APLRT1,WIDE1-1::OH2GBA   :?APRSP{7"


@pytest.fixture(autouse=True)
def no_list(monkeypatch: pytest.MonkeyPatch) -> object:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    monkeypatch.setattr(loralist, "PORT", sock.getsockname()[1])
    yield
    sock.close()


@pytest.mark.slow("runs a daemon with its radios and services through its loop")
async def test_a_radio_that_only_receives_hears_everything_and_sends_nothing_whatever_is_asked_of_it(
    tmp_path: Path,
) -> None:
    board = Board("console")
    end = BoardOnTcp(board)
    await end.start()
    e = Env(
        tmp_path,
        radio=False,
        web=True,
        settings={
            "tnc/profile": "dummy",
            "station/call": ME,
            "station/lat": "60.17",
            "station/lon": "24.94",
            "messages/alert": "false",
        },
    )
    try:
        await e.start(connected=False)
        page = await e.ws()
        await page.until(lambda: "radios" in page.topics)
        id = await added(page, "lora-console")
        await page.send({"cmd": "set_config", "values": {f"radio/{id}/port": end.url}})
        radio = e.ctl.radios.get(id)
        assert radio is not None
        await until_started(lambda: radio.state is Source.State.CONNECTED and end.clients == 1)
        assert not radio.usable and radio.why_unusable() == RECEIVE_ONLY and not radio.rtype.can.transmit

        board.air(HEARD, rssi=-104, snr=-3.25)
        board.air(QUERY, rssi=-104, snr=-3.25)
        await until(
            lambda: any(s.call == "OH2ABC-7" and s.heard_on(id).count == 2 for s in e.ctl.stationbook.stations())
        )
        station = next(s for s in e.ctl.stationbook.stations() if s.call == "OH2ABC-7")
        assert (station.snr, station.rssi) == (-3.25, -104.0) and station.heard_on(FM_ID).count == 0

        # what the station sends: never on it
        assert (
            [r.id for r in e.ctl.radios.beaconing()] == [1]
            and not radio.beacon.send_now()
            and radio.beacon.problem == ONLY_RECEIVES
        )
        await page.until(lambda: page.topics["radios"][str(id)]["beacon"]["problem"] is not None)
        assert page.topics["radios"][str(id)]["beacon"]["problem"]["code"] == "transmit.off", (
            "the page's RX only, not a reason in English"
        )
        assert getattr(e.ctl.radios.for_station("OH2ABC-7"), "id", None) == 1, (
            "a message to a station heard only on it goes on a radio that sends"
        )
        packet = next(p for p in await e.packets() if p.source == "OH2ABC-7" and b"?APRSP" in p.info)
        assert not answerable(e.ctl.radios, packet), (
            "a query heard on it alone is not answered: the copy a radio that sends hears is"
        )
        assert getattr(ack_radio(e.ctl.radios, packet, "OH2ABC-7"), "id", None) == 1, (
            "the ack of a message heard on it goes on a radio that sends"
        )
        assert getattr(e.ctl.radios.email(), "id", None) in (1, None) and [
            s.id for s in senders(e.ctl.config.radios)
        ] == [1]
        await page.send({"cmd": "set_config", "values": {"email/radio": str(id)}})
        await page.until(lambda: page.topics["config"]["radio_values"]["email/radio"] == str(id))
        assert getattr(e.ctl.radios.email(), "id", None) == 1, (
            "chosen for email, it is none: the one radio that sends carries the mail"
        )
        assert [r.id for r in e.ctl.sender.radios_for([id])] == [1], (
            "an object set on it alone goes on the one radio that sends"
        )
        error = await refused(page, {"cmd": "qru_ask", "text": "INFO", "radio": id})
        assert (error["code"], error["params"]) == ("radio.receive_only", {"name": "LoRa", "radio": id})
        assert (
            page.topics["radios"][str(id)]["choices"]["ask"] is False
            and page.topics["radios"][str(id)]["choices"]["local_info"] is False
        ), "a radio that only receives is in no Send on"

        # its line: refused with its reason, never reported as sent
        frame = frame_of(f"{ME}>APZNEO,WIDE1-1:>tried".encode())
        assert not radio.send_frame(frame) and not await radio.line.send(ax25.encode(frame))
        assert any(f"not sent: {RECEIVE_ONLY}" in line for line in radio.line.lines) and not any(
            line.startswith("sent ") for line in radio.line.lines
        )
        assert not [p for p in await e.packets() if p.direction == "out" and p.radio_id == id]

        # the FM radio off too: nothing anywhere
        await page.send({"cmd": "radio_change", "radio": 1, "enabled": False})
        await page.until(lambda: not page.topics["radios"]["1"]["enabled"])
        assert (
            e.ctl.radios.senders() == []
            and e.ctl.radios.beaconing() == []
            and e.ctl.radios.for_station("OH2ABC-7") is None
            and e.ctl.radios.email() is None
        )
        error = await refused(page, {"cmd": "qru_ask", "text": "INFO"})
        assert error["code"] == "transmit.off", "every radio that is on only receives: RX only"
        board.air(HEARD.replace(b"tracker", b"still heard"))
        await until(
            lambda: any(s.call == "OH2ABC-7" and s.heard_on(id).count == 3 for s in e.ctl.stationbook.stations())
        )

        assert board.writes == [] and await end.said(1, 0.3) == b"", "not one byte on its line"
    finally:
        await e.stop()
        await end.aclose()
