"""A new installation's first radio of one of the new types, as the setup guide makes it over the page's socket: a new installation has no radio, and the first one added, radio 1, is a LoRa APRS board on the
network with no address yet, a text monitor (`tnc-text`), or a Sound card radio (`direwolf`). None tells the page an error while the operator has not asked for anything; the board's row is "not connected" until
its address is typed, and then it is a radio as any other; the monitor alone makes the station receive only, every sending command is refused as RX only, and not one byte goes to its line; the Sound card radio
is offered on a station that has no radio yet, is radio 1 and the station's radio to send on, and its beacon goes out through its own Direwolf."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from neoaprs import direwolfmodem, loralist, radioregistry
from neoaprs.direwolf import CONF_FILE, adevice
from neoaprs.direwolfdriver import DirewolfDriver
from neoaprs.mercuryclaims import radio_folder
from neoaprs.source import Source
from neoaprs.web.protocol import TOPIC_NAMES
from tests.support import fakedirewolf
from tests.support.env import Env, until, until_started
from tests.support.fakelora import HEADER, Board, BoardOnTcp, ListServer
from tests.support.fakeradio import FakeRadio
from tests.support.modemports import base_of_this_test
from tests.support.wsclient import WsClient
from tests.test_radios_wire import added

ME = "OH2GBA"


async def fresh(tmp_path: Path) -> tuple[Env, WsClient]:
    """A first start of a new installation (no settings row, no radio in the database, and none written by the start) with the guide's call and place set, and the page's socket open."""
    e = Env(tmp_path, radio=False, web=True, operator=False, first_radio=False)
    await e.start(connected=False)
    page = await e.ws()
    await page.until(lambda: "radios" in page.topics and "config" in page.topics)
    await page.send({"cmd": "set_config", "values": {"station/call": ME, "station/lat": "60.17", "station/lon": "24.94", "messages/alert": "false"}})
    await page.until(lambda: page.topics["config"]["values"]["station/call"] == ME)
    return e, page


def errors(page: WsClient) -> list[dict[str, Any]]:
    return page.of("error")


async def test_a_lora_board_on_the_network_added_first_with_no_address_is_not_connected_with_no_error_and_connects_once_its_address_is_typed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    board = Board("igate")
    end, server = BoardOnTcp(board), await ListServer(board).start()
    await end.start()
    monkeypatch.setattr(loralist, "PORT", server.port)
    e, page = await fresh(tmp_path)
    try:
        assert page.topics["radios"] == {} and e.ctl.config.radios == (), "a new installation has no radio, and its first start writes none"
        id = await added(page, "lora-tcp")
        assert id == 1, "the first radio added is radio 1"
        radio = e.ctl.radios.get(id)
        assert radio is not None
        await page.until(lambda: page.topics["radios"][str(id)]["state"] != "connecting")
        row = page.topics["radios"][str(id)]
        assert (row["kind"], row["type"], row["enabled"], row["state"]) == ("lora", "lora-tcp", True, "waiting"), row          # (between two tries, which open nothing)
        assert row["problem"] is not None and row["problem"]["code"] == "radio.not_connected", "the row says not connected, in the page's words: nothing of an address or a port"
        assert page.topics["config"]["radio_values"][f"radio/{id}/tcp_host"] == "" and end.clients == 0, "a board on the network has no address until it is typed: nothing is opened, not 127.0.0.1"
        assert e.ctl.config.main_radio == id, "the board is the station's radio to send on"
        assert errors(page) == [], "no error the operator did not ask for"
        await page.send({"cmd": "set_config", "values": {f"radio/{id}/tcp_host": "127.0.0.1", f"radio/{id}/tcp_port": str(end.port)}})
        await until_started(lambda: radio.state is Source.State.CONNECTED and end.clients == 1)
        await page.until(lambda: page.topics["radios"][str(id)]["state"] == "connected" and page.topics["radios"][str(id)]["problem"] is None)
        assert radio.beacon.send_now(), radio.beacon.problem
        await until(lambda: len(board.transmitted) == 1)
        assert board.transmitted[0].startswith(HEADER + f"{ME}>".encode()) and errors(page) == []
    finally:
        await e.stop()
        await end.aclose()
        await server.stop()


async def test_a_text_monitor_alone_makes_the_station_receive_only_refuses_every_sending_command_as_rx_only_and_writes_not_one_byte(tmp_path: Path) -> None:
    line = FakeRadio()
    await line.start()
    e, page = await fresh(tmp_path)
    try:
        await page.send({"cmd": "set_config", "values": {"station/status": "QRV 145.500", "status/source": "text"}})
        await page.until(lambda: page.topics["config"]["values"]["station/status"] == "QRV 145.500")
        assert page.topics["radios"] == {}, "a new installation has no radio"
        id = await added(page, "tnc-text")
        await page.send({"cmd": "set_config", "values": {f"radio/{id}/port": line.url}})
        assert id == 1 and [row["id"] for row in page.topics["radios"].values()] == [1], "the monitor is the station's one radio"
        radio = e.ctl.radios.get(id)
        assert radio is not None
        await until_started(lambda: radio.state is Source.State.CONNECTED)
        await page.until(lambda: page.topics["radios"][str(id)]["state"] == "connected")
        row = page.topics["radios"][str(id)]
        assert (row["kind"], row["type"], row["can"]["transmit"], row["can"]["find"], row["allowed"]["paths"], row["allowed"]["digipeat"]) == ("fm", "tnc-text", False, False, False, False)
        assert e.ctl.config.listens_only and e.ctl.config.main_radio is None and errors(page) == [], "the station only receives, and nothing tells an error for it"
        line.feed(b"OH2ABC-7>APRS,WIDE1-1:!6011.00N/02457.00E>heard on the monitor\r" + f"OH2ABC-7>APRS,WIDE1-1::{ME:<9}:Hello{{12\r".encode())
        await until(lambda: (s := e.ctl.stationbook.get("OH2ABC-7")) is not None and s.heard_on(id).count > 0)
        for command in ({"cmd": "beacon_now"}, {"cmd": "status_now"}, {"cmd": "send_message", "to": "OH2ABC-7", "text": "Hello"}, {"cmd": "general_query", "kind": "aprs", "path": None, "rf_only": True}):
            await page.send(command)
            answer = await page.expect("error")
            assert (answer["cmd"], answer["code"]) == (command["cmd"], "transmit.off"), answer
        await page.send({"cmd": "find_radio", "radio": id})
        assert (await page.expect("error"))["code"] == "radio.receive_only"
        for _ in range(20):                                                       # (an hour of the station's clock: a beacon, an ack, an answer would be due)
            e.now.advance(180)                                                    # type: ignore[attr-defined]
            await asyncio.sleep(0.02)
        assert await line.said(1, 0.3) == b"" and radio.stats.bytes_out == 0, "not one byte on the monitor's line"
        assert [error["code"] for error in errors(page)] == ["transmit.off"] * 4 + ["radio.receive_only"], "and no error but the refusals of what was asked"
    finally:
        await e.stop()
        await line.aclose()


@pytest.mark.parametrize("windows", [False, True], ids=["this-systems-way", "the-windows-way"])
async def test_a_sound_card_radio_added_first_is_radio_1_the_stations_radio_to_send_on_and_its_beacon_goes_out_through_its_own_direwolf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, windows: bool) -> None:
    """With `windows`, the Windows way on every system: the card's WinMM numbers in the configuration, and the made-up Direwolf's device lists read."""
    monkeypatch.setitem(radioregistry.CARRIED, "direwolf", lambda: True)             # (an installation that carries Direwolf: the made-up one, which gives back each frame it is sent as heard)
    monkeypatch.setattr("neoaprs.direwolfprogram.find", lambda tools=None: fakedirewolf.program())
    monkeypatch.setattr(direwolfmodem, "FIRST_PORT", base_of_this_test())
    monkeypatch.setattr(direwolfmodem, "_numbers_of", lambda name: (1, 1))           # (Windows: the made-up card is the second input and output of the made-up Direwolf's WinMM lists; the machine's own name none)
    if windows:
        monkeypatch.setattr(direwolfmodem, "sys", SimpleNamespace(platform="win32"))
        monkeypatch.setattr(direwolfmodem.DirewolfModem, "_cards", lambda self: [])  # (no HF modem here lists the cards: the card is the one typed)
    e, page = await fresh(tmp_path)
    try:
        await page.until(lambda: set(TOPIC_NAMES) <= set(page.topics) and bool(page.of("status")))
        assert page.topics["radios"] == {} and e.ctl.config.radios == (), "a new installation has no radio, and the page is told so (the header waits for none)"
        assert page.of("status")[-1]["unavailable_types"] == [], "the type is offered to a station that has no radio yet"
        id = await added(page, "direwolf")
        assert id == 1, "the first radio added is radio 1"
        await page.send({"cmd": "set_config", "values": {f"radio/{id}/sound_card": "plughw:7,0", f"radio/{id}/keying": "vox"}})
        radio = e.ctl.radios.get(id)
        assert radio is not None
        await until_started(lambda: radio.usable)
        assert isinstance(radio.driver, DirewolfDriver)
        assert f"ADEVICE {'1 1' if windows else adevice('plughw:7,0', radio.driver.modem._numbers)}\n" in (radio_folder(tmp_path, id) / CONF_FILE).read_text(encoding="utf-8"), "the card as this system takes it"
        await page.until(lambda: page.topics["radios"][str(id)]["state"] == "connected" and page.topics["radios"][str(id)]["problem"] is None)
        row = page.topics["radios"][str(id)]
        assert (row["kind"], row["type"], row["enabled"], row["can"]["transmit"], row["can"]["tune"]) == ("fm", "direwolf", True, True, True), row
        assert e.ctl.config.main_radio == id and not e.ctl.config.listens_only, "the Sound card radio is the station's radio to send on"
        assert radio.beacon.send_now(), radio.beacon.problem
        await until(lambda: radio.stats.bytes_out > 0)
        assert errors(page) == [], "no error the operator did not ask for"
    finally:
        await e.stop()
