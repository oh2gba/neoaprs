"""The web server end to end: a WebSocket client against the daemon, as the page is (tests/support/wsclient.py). The hello and the six topics, the capture through the pseudo-terminal as patches,
the commands, the files, the Host check and the security headers. Every message the daemon sends is checked against neoaprs/web/protocol.py while these run (tests/conftest.py)."""
import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from tornado.httpclient import HTTPClientError

from neoaprs import VERSION
from neoaprs.clock import iso
from neoaprs.config import DEFAULTS
from neoaprs.source import Source
from tests.support.air import ack_info, message_info, on_air, reject_info
from tests.support.env import ON_AIR, OPERATOR, Env, until
from tests.support.wsclient import WsClient
from neoaprs.web import handlers as web_handlers
from neoaprs.web import server as web_server
from neoaprs.web.protocol import TOPIC_NAMES, TOPIC_VALUES
from neoaprs.web.bulletinwire import BulletinRow
from neoaprs.web.messagewire import MessageRow
from neoaprs.web.prefwire import StationPref
from neoaprs.web.stationwire import StationRow

SECURITY = ("Content-Security-Policy", "X-Frame-Options", "Referrer-Policy", "X-Content-Type-Options", "Cross-Origin-Resource-Policy")


# ---- the hello and the topics -------------------------------------------------------------------------------------------------------------------

async def test_a_fresh_install_is_told_to_the_page_as_no_call_and_no_position(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True, operator=False)
    await e.start()
    page = await e.ws()
    status = await page.expect("status")
    assert (status["call"], status["lat"], status["lon"]) == ("", None, None)
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    assert list(page.topics["stations"]) == [] and page.topics["config"]["values"]["station/call"] == "" and page.topics["config"]["values"]["station/lat"] == ""


async def test_a_page_that_opens_is_sent_hello_the_status_and_every_topic_whole(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    hello = await page.expect("hello")
    assert hello["version"] == VERSION and hello["protocol"] == 1 and hello["topics"] == list(TOPIC_NAMES) == ["stations", "packets", "tnc", "config", "station_prefs", "messages", "bulletins", "own_objects", "own_bulletins", "map"]
    status = await page.expect("status")
    assert status["version"] == VERSION and status["packets"] == 0 and status["stations"] == 1 and (status["call"], status["lat"], status["lon"]) == ("OH2GBA", 60.17, 24.94)
    assert (status["beacon_interval_min"], status["beacon_last_sent"], status["beacon_next_due"]) == (0, None, None)
    states = {m["topic"]: m for m in page.of("state")}
    if len(states) < len(TOPIC_NAMES):
        await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
        states = {m["topic"]: m for m in page.of("state")}
    assert set(states) == set(TOPIC_NAMES) and all(m["rev"] == 0 for m in states.values())
    stations = states["stations"]["value"]
    assert list(stations) == ["OH2GBA"] and stations["OH2GBA"]["is_me"] is True and stations["OH2GBA"]["distance_km"] is None
    assert states["packets"]["value"] == {}
    assert states["tnc"]["value"]["state"] == "connected" and states["tnc"]["value"]["path"] == e.link
    assert states["config"]["value"] == {"values": {**DEFAULTS.to_data(), **OPERATOR}, "defaults": DEFAULTS.to_data(), "urls": []}
    assert states["messages"]["value"] == {} and states["station_prefs"]["value"] == {}
    for name, message in states.items():
        TOPIC_VALUES[name].validate_json(json.dumps(message["value"]))                       # the value is of the type TopicValues says
    StationRow.model_validate_json(json.dumps(stations["OH2GBA"]))


async def test_the_capture_comes_as_four_packets_and_the_stations_they_are_from(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    frames = await e.play()
    assert frames == 4
    await page.until(lambda: len(page.topics["packets"]) == 4 and {"OH2RDG", "OH2RDK-7", "OH2RDS", "OH2PU-9"} <= set(page.topics["stations"]))
    sets = [op for op in page.ops("packets") if op["op"] == "set"]
    assert len(sets) == 4 and [op["value"]["id"] for op in sets] == [1, 2, 3, 4] and [op["key"] for op in sets] == ["1", "2", "3", "4"]
    rows = list(page.topics["packets"].values())
    assert {r["source"] for r in rows} == {"OH2RDG", "OH2RDK-7", "OH2RDS", "OH2PU-9"} and all(r["kind"] == "position" and r["direction"] == "in" for r in rows)
    assert all(r["decoded"]["type"] == "position" and r["tnc2"].startswith(r["source"] + ">") and r["summary"].startswith("position ") for r in rows)
    station = page.topics["stations"]["OH2RDK-7"]
    row = StationRow.model_validate_json(json.dumps(station))
    assert row.kind == "station" and row.packets == 1 and row.is_me is False and row.symbol_name != "unknown"
    assert row.lat is not None and row.distance_km is not None and row.distance_km > 0 and row.bearing_deg is not None and len(row.track) == 1
    assert row.last_path and row.first_heard == row.last_heard
    for call, row_ in page.topics["stations"].items():
        StationRow.model_validate_json(json.dumps(row_))
        assert row_["call"] == call
    assert page.revs["packets"] >= 1 and page.revs["stations"] >= 1


async def test_the_state_of_the_tnc_follows_the_radio_and_comes_at_most_four_times_a_second(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    await e.play()
    await page.until(lambda: page.topics["tnc"]["stats"]["packets"] == 4)
    tnc = page.topics["tnc"]
    assert tnc["state"] == "connected" and tnc["stats"]["frames_in"] == 4 and tnc["stats"]["last_packet"] and len(tnc["lines"]) <= 100
    assert any("OH2RDK-7" in line for line in tnc["lines"])
    assert len(page.of("patch", "tnc")) <= 4, "the lines and the counters of one burst are told together, not one by one"


async def test_the_keep_alive_counters_and_the_last_action_are_in_the_tnc_topic(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True, check_pause_sec=0.05, reply_sec=0.1, answer_sec=0.1)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    tnc = page.topics["tnc"]
    assert (tnc["stats"]["keepalive_checks"], tnc["stats"]["watchdog_probes"], tnc["stats"]["port_reopens"]) == (0, 0, 0) and tnc["last_watchdog_action"] == "" and tnc["last_watchdog_at"] is None
    e.tnc.set_check(0.1)
    await page.until(lambda: page.topics["tnc"]["last_watchdog_action"] == "check")
    tnc = page.topics["tnc"]
    assert tnc["stats"]["keepalive_checks"] == 1 and tnc["last_watchdog_at"] == iso(e.now())
    await page.until(lambda: page.topics["tnc"]["state"] == "silent")
    e.tnc.set_check(0.0)
    assert page.of("error") == []


async def test_the_check_period_of_the_settings_counts_at_once_without_a_restart(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    assert e.tnc.watchdog.sec == 0.0 and page.topics["config"]["values"]["tnc/check_sec"] == "0" and page.topics["config"]["values"]["map/hide_after_min"] == "180"      # (the checks are off in the settings of an Env)
    await page.send({"cmd": "set_config", "values": {"tnc/check_sec": "300", "map/hide_after_min": "0"}})
    await page.until(lambda: page.topics["config"]["values"]["tnc/check_sec"] == "300")
    assert e.tnc.watchdog.sec == 300.0 and e.tnc.stats.opens == 1 and e.tnc._watchdog_task is not None
    await page.send({"cmd": "set_config", "values": {"tnc/check_sec": "0"}})
    await page.until(lambda: page.topics["config"]["values"]["tnc/check_sec"] == "0")
    assert e.tnc.watchdog.sec == 0.0 and e.tnc._watchdog_task is None and e.tnc.stats.opens == 1 and e.tnc.state is Source.State.CONNECTED
    await page.send({"cmd": "set_config", "values": {"tnc/check_sec": "5"}})
    assert (await page.expect("error"))["text"].startswith("set_config: tnc/check_sec")
    await e.stop()
    again = Env(tmp_path)
    await again.start()
    assert again.tnc.watchdog.sec == 0.0 and again.ctl.config.map_hide_after_min == 0, "the settings are what the next start reads"
    await again.stop()


async def test_a_page_that_comes_late_is_sent_the_packets_the_daemon_has(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    await e.play()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    assert len(page.topics["packets"]) == 4 and len(page.topics["stations"]) == 5
    again = await e.ws()
    await again.until(lambda: len(again.of("state")) == len(TOPIC_NAMES))
    assert again.topics["packets"] == page.topics["packets"]


async def test_a_restarted_daemon_opens_with_the_packets_the_database_kept(tmp_path: Path) -> None:
    first = Env(tmp_path)
    await first.start()
    await first.play()
    await first.stop()
    second = Env(tmp_path, web=True)
    await second.start()
    page = await second.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    rows = sorted(page.topics["packets"].values(), key=lambda r: r["id"])
    assert len(rows) == 4 and [r["id"] for r in rows] == [1, 2, 3, 4] and {r["source"] for r in rows} == {"OH2RDG", "OH2RDK-7", "OH2RDS", "OH2PU-9"}
    assert len(page.topics["stations"]) == 5


# ---- the commands --------------------------------------------------------------------------------------------------------------------------------

async def test_ping_is_answered_and_status_on_request(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.send({"cmd": "ping"})
    assert (await page.expect("pong"))["now"].endswith("Z")
    await e.play()
    await page.send({"cmd": "status"})
    await page.until(lambda: len(page.of("status")) == 2)
    assert page.of("status")[-1]["packets"] == 4 and page.of("status")[-1]["stations"] == 5


async def test_list_ports_is_answered_with_the_ports_of_the_machine_and_whether_the_radio_is_looked_for(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from neoaprs.serialprobe import PortInfo
    monkeypatch.setattr(web_handlers, "available_ports", lambda: [PortInfo("COM3", "USB Serial Port (COM3)", "USB VID:PID=0403:6001", 0x0403, 0x6001), PortInfo("COM4", "Bluetooth", "BTHENUM", None, None)])
    monkeypatch.setattr(web_handlers, "can_search", lambda: False)
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.send({"cmd": "list_ports"})
    assert await page.expect("ports") == {"type": "ports", "search": False, "ports": [
        {"device": "COM3", "description": "USB Serial Port (COM3)", "hwid": "USB VID:PID=0403:6001", "vid": 1027, "pid": 24577},
        {"device": "COM4", "description": "Bluetooth", "hwid": "BTHENUM", "vid": None, "pid": None}]}
    monkeypatch.setattr(web_handlers, "available_ports", lambda: [])
    await page.send({"cmd": "list_ports"})
    await page.until(lambda: len(page.of("ports")) == 2)
    assert page.of("ports")[-1]["ports"] == []


async def test_a_frame_that_is_not_a_command_is_an_error_and_changes_nothing(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    await e.play()
    await page.until(lambda: len(page.topics["packets"]) == 4)
    before = json.dumps(page.topics, sort_keys=True)
    bad = ['not json', '[1, 2]', '{"cmd": "nope"}', '{}', '{"cmd": 7}', '{"cmd": "ping", "extra": 1}', '{"cmd": "forget_station"}', '{"cmd": "forget_station", "call": 5}',
           '{"cmd": "set_config", "values": {"station/lat": 61}}', '{"cmd": "subscribe", "topics": "stations"}', '{"cmd": "set_config", "values": NaN}']
    for text in bad:
        await page.send_text(text)
    await page.until(lambda: len(page.of("error")) == len(bad))
    errors = [m["text"] for m in page.of("error")]
    assert any("That is not JSON" in t for t in errors) and any("JSON object" in t for t in errors)
    assert any("unknown command 'nope'" in t for t in errors) and any("extra" in t for t in errors) and any("call: is missing" in t for t in errors)
    assert all(isinstance(t, str) and 0 < len(t) < 300 for t in errors)
    await page.quiet(0.4)
    assert json.dumps(page.topics, sort_keys=True) == before, "nothing changed"
    assert await e.ctl.store.settings() == OPERATOR and e.ctl.stationbook.get("OH2RDK-7") is not None and e.ctl.config == ON_AIR


async def test_set_config_with_a_key_or_a_value_that_is_wrong_is_an_error_naming_the_key_and_changes_nothing(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    for values, key in (({"neoaprs/web/colour": "red"}, "neoaprs/web/colour"), ({"station/lat": "95"}, "station/lat"), ({"station/call": "oh2xyz", "web/port": "http"}, "web/port"), ({"serial/baud": "fast"}, "serial/baud")):
        await page.send({"cmd": "set_config", "values": values})
        error = await page.expect("error")
        assert error["text"].startswith("set_config: ") and key in error["text"], error
    await page.quiet(0.3)
    assert await e.ctl.store.settings() == OPERATOR and e.ctl.config == ON_AIR and page.of("patch", "config") == []
    assert page.topics["config"]["values"]["station/call"] == "OH2GBA"


async def test_set_config_changes_the_settings_and_the_page_is_told_them_again(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    await page.send({"cmd": "set_config", "values": {"station/comment": "mobile", "station/call": "oh2gba-9"}})
    await page.until(lambda: page.topics["config"]["values"]["station/comment"] == "mobile")
    assert page.topics["config"]["values"]["station/call"] == "OH2GBA-9", "the value is written the way the daemon writes it"
    assert page.topics["config"]["defaults"]["station/comment"] == "NeoAPRS"
    assert (await e.ctl.store.settings())["station/call"] == "OH2GBA-9" and e.ctl.config.station_comment == "mobile"
    await page.until(lambda: set(page.topics["stations"]) == {"OH2GBA-9", "OH2GBA"})                 # our own station is the new call; the old one is a station like any other
    assert page.topics["stations"]["OH2GBA-9"]["is_me"] is True and page.topics["stations"]["OH2GBA"]["is_me"] is False
    await page.send({"cmd": "set_config", "values": {}})                                              # nothing differs: told again all the same, the form waits for it
    await page.until(lambda: len(page.of("patch", "config")) == 2)
    # a second page is told when the first saves
    other = await e.ws()
    await other.until(lambda: len(other.of("state")) == len(TOPIC_NAMES))
    await page.send({"cmd": "set_config", "values": {"log/keep_days": "7"}})
    await other.until(lambda: other.topics["config"]["values"]["log/keep_days"] == "7")


async def test_set_config_of_the_position_moves_our_row_and_every_distance(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await e.play()
    await page.until(lambda: len(page.topics["stations"]) == 5 and len(page.topics["packets"]) == 4)
    before = {call: row["distance_km"] for call, row in page.topics["stations"].items()}
    assert page.topics["stations"]["OH2GBA"]["lat"] == 60.17
    await page.send({"cmd": "set_config", "values": {"station/lat": "61.5", "station/lon": "25.5"}})
    await page.until(lambda: page.topics["stations"]["OH2GBA"]["lat"] == 61.5)
    me = page.topics["stations"]["OH2GBA"]
    assert me["lon"] == 25.5 and me["is_me"] is True and me["distance_km"] is None
    await page.until(lambda: page.topics["stations"]["OH2RDK-7"]["distance_km"] != before["OH2RDK-7"])
    assert all(StationRow.model_validate_json(json.dumps(r)) for r in page.topics["stations"].values())
    assert e.ctl.stationbook.me is not None and e.ctl.stationbook.me.lat == 61.5


async def test_forget_station_removes_the_station_and_tells_the_pages(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    other = await e.ws()
    await e.play()
    await page.until(lambda: len(page.topics["stations"]) == 5)
    await other.until(lambda: len(other.topics["stations"]) == 5)
    await page.send({"cmd": "forget_station", "call": "OH2RDG"})
    await page.until(lambda: "OH2RDG" not in page.topics["stations"])
    await other.until(lambda: "OH2RDG" not in other.topics["stations"])
    assert {"op": "del", "key": "OH2RDG"} in page.ops("stations") and e.ctl.stationbook.get("OH2RDG") is None
    await e.settled()
    assert "OH2RDG" not in [s.call for s in await e.ctl.packetlog.stations()], "the cache in the database follows"
    await page.send({"cmd": "forget_station", "call": "OH2RDG"})
    assert "no station" in (await page.expect("error"))["text"]
    await page.send({"cmd": "forget_station", "call": "OH2GBA"})
    assert "our own station" in (await page.expect("error"))["text"]
    assert "OH2GBA" in page.topics["stations"]


async def test_subscribe_and_unsubscribe(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    await page.send({"cmd": "unsubscribe", "topics": ["packets", "nothing"]})
    await e.play()
    await page.until(lambda: len(page.topics["stations"]) == 5)
    await page.quiet(0.3)
    assert page.of("patch", "packets") == [] and page.topics["packets"] == {}
    await page.send({"cmd": "subscribe", "topics": ["packets", "weather"]})
    assert "weather" in (await page.expect("error"))["text"]
    await page.until(lambda: len(page.topics["packets"]) == 4)                                         # (told whole again)
    assert len(page.of("state", "packets")) == 2


async def test_tnc_reconnect_opens_the_line_again(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    assert e.tnc.stats.opens == 1
    await page.send({"cmd": "tnc_reconnect"})
    await until(lambda: e.tnc.stats.opens == 2 and e.tnc.state is Source.State.CONNECTED)
    await page.until(lambda: page.topics["tnc"]["stats"]["opens"] == 2 and page.topics["tnc"]["state"] == "connected")
    assert any("opened" in line for line in page.topics["tnc"]["lines"])
    frames = await e.play()
    assert frames == 4, "the line works after it"


async def test_beacon_now_sends_our_position_and_the_pages_are_told_the_packet_and_the_status(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    await asyncio.sleep(0.2)                                                                            # (the TNC has settled)
    page = await e.ws()
    other = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES) and len(page.of("status")) == 1)
    assert page.of("status")[0]["beacon_last_sent"] is None and page.of("status")[0]["beacon_next_due"] is None and page.of("status")[0]["beacon_interval_min"] == 0
    await page.send({"cmd": "beacon_now"})
    await page.until(lambda: len(page.topics["packets"]) == 1)
    [row] = page.topics["packets"].values()
    assert row["direction"] == "out" and row["source"] == "OH2GBA" and row["kind"] == "position"
    assert row["tnc2"] == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=6010.20N/02456.40E-NeoAPRS" and row["decoded"]["lat"] == 60.17 and row["decoded"]["symbol_code"] == "-"
    assert [op["op"] for op in page.ops("packets")] == ["set"]
    await other.until(lambda: len(other.topics["packets"]) == 1)
    await page.until(lambda: page.of("status")[-1]["beacon_last_sent"] is not None)                     # (told at once, not at the next ten seconds)
    await other.until(lambda: other.of("status")[-1]["beacon_last_sent"] is not None)
    assert page.of("status")[-1]["beacon_last_sent"] == iso(e.now()) and page.of("status")[-1]["packets"] == 1
    assert page.of("error") == [] and len(await e.packets()) == 1


async def test_beacon_now_while_the_tnc_is_not_connected_is_an_error_and_sends_nothing(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True, radio=False)
    await e.start(connected=False)
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    await page.send({"cmd": "beacon_now"})
    error = (await page.expect("error"))["text"]
    assert error.startswith("beacon_now: ") and "not connected" in error
    await page.quiet(0.3)
    assert page.topics["packets"] == {} and e.ctl.beacon.last_sent is None


async def test_beacon_now_with_settings_that_make_no_frame_is_an_error(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    await asyncio.sleep(0.2)
    assert await e.ctl.save_config(replace(e.ctl.config, station_comment="x" * 44))                     # (a row somebody edited by hand: the page's save would have refused it)
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    await page.send({"cmd": "beacon_now"})
    assert "comment" in (await page.expect("error"))["text"]
    assert page.topics["packets"] == {}


async def test_the_status_tells_the_interval_and_when_the_next_beacon_is_due(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    await page.send({"cmd": "set_config", "values": {"beacon/interval_min": "15", "beacon/path": "wide2-2", "beacon/destination": "apzxyz"}})
    await page.until(lambda: page.topics["config"]["values"]["beacon/interval_min"] == "15")
    assert page.topics["config"]["values"]["beacon/path"] == "WIDE2-2" and page.topics["config"]["values"]["beacon/destination"] == "APZXYZ"
    assert page.topics["config"]["defaults"]["beacon/path"] == "WIDE1-1,WIDE2-1" and page.topics["config"]["values"]["beacon/compressed"] == "false"
    await page.send({"cmd": "status"})
    await page.until(lambda: page.of("status")[-1]["beacon_interval_min"] == 15)
    assert page.of("status")[-1]["beacon_next_due"] is not None and page.of("status")[-1]["beacon_last_sent"] is None


async def test_the_beacon_settings_are_checked_by_the_settings_command(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    for key, value in (("beacon/path", "WIDE1-1,TOOLONGCALL"), ("beacon/destination", "APRS-3"), ("beacon/compressed", "perhaps"), ("beacon/interval_min", "1441")):
        await page.send({"cmd": "set_config", "values": {key: value}})
        assert key in (await page.expect("error"))["text"]
    assert await e.ctl.store.settings() == OPERATOR


async def test_the_status_is_told_every_ten_seconds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("neoaprs.web.api.STATUS_EVERY_SEC", 0.2)
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("status")) >= 3)


async def test_a_page_that_goes_away_is_forgotten(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    assert e.server is not None and len(e.server.api.clients) == 1
    await page.aclose()
    await until(lambda: len(e.server.api.clients) == 0 if e.server else False)
    await e.play()                                                                                      # nobody listens: nothing breaks


# ---- the files and the names -----------------------------------------------------------------------------------------------------------------------

async def test_the_placeholder_is_served_while_the_page_is_not_built(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web_server, "PAGE_DIR", tmp_path / "no-page")
    e = Env(tmp_path / "data", web=True)
    await e.start()
    answer = await e.fetch("/")
    assert answer.code == 200 and b"the page is not built: scripts/build-page" in answer.body and answer.headers["Cache-Control"] == "no-cache"
    assert (await e.fetch("/index.html")).code == 200


async def test_the_built_page_is_served_with_its_assets_kept_and_nothing_else(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    page = tmp_path / "page"
    (page / "assets").mkdir(parents=True)
    (page / "index.html").write_text('<div id="app"></div>')
    (page / "assets" / "index-abc123.js").write_text("console.log(1)")
    (page / ".secret").write_text("no")
    (page / "assets" / "index-abc123.js.map").write_text("{}")
    monkeypatch.setattr(web_server, "PAGE_DIR", page)
    e = Env(tmp_path / "data", web=True)
    await e.start()
    root = await e.fetch("/")
    assert root.code == 200 and b'id="app"' in root.body
    asset = await e.fetch("/assets/index-abc123.js")
    assert asset.code == 200 and asset.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    for path in ("/nothing.html", "/.secret", "/assets/index-abc123.js.map", "/../neoaprs/__init__.py", "/%2e%2e/neoaprs/__init__.py", "/assets/"):
        answer = await e.fetch(path)
        assert answer.code in (403, 404), path
        assert b"VERSION" not in answer.body and len(answer.body) < 200, "a line of text, not a page"


async def test_the_base_map_is_a_404_without_the_file_and_serves_byte_ranges_with_it(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    missing = await e.fetch("/basemap.pmtiles")
    assert missing.code == 404 and missing.headers["Content-Type"].startswith("text/plain") and len(missing.body) < 200 and b"Settings tab" in missing.reason.encode() + missing.body
    content = bytes(range(256)) * 40
    (tmp_path / "basemap.pmtiles").write_bytes(content)
    whole = await e.fetch("/basemap.pmtiles")
    assert whole.code == 200 and whole.body == content and whole.headers["Accept-Ranges"] == "bytes"
    part = await e.fetch("/basemap.pmtiles", headers={"Range": "bytes=100-299"})
    assert part.code == 206 and part.body == content[100:300] and part.headers["Content-Range"] == f"bytes 100-299/{len(content)}"
    tail = await e.fetch("/basemap.pmtiles", headers={"Range": "bytes=-16"})
    assert tail.code == 206 and tail.body == content[-16:]
    assert (await e.fetch("/basemap.pmtiles", method="HEAD")).headers["Content-Length"] == str(len(content))
    assert (await e.fetch("/basemap.pmtiles", headers={"Range": f"bytes={len(content) + 5}-"})).code == 416
    for key in SECURITY:
        assert part.headers[key]
    assert (await e.fetch("/basemap-world.pmtiles")).code == 404, "the world map is its own file"
    (tmp_path / "basemap-world.pmtiles").write_bytes(content[:500])
    world = await e.fetch("/basemap-world.pmtiles", headers={"Range": "bytes=10-19"})
    assert world.code == 206 and world.body == content[10:20]
    assert (await e.fetch("/basemap-world.pmtiles.part")).code in (403, 404) and (await e.fetch("/neoaprs.sqlite")).code in (403, 404), "no other file of the data folder is reachable"


async def test_the_security_headers_are_on_every_answer(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    (tmp_path / "basemap.pmtiles").write_bytes(b"0123456789")
    answers = [await e.fetch(p) for p in ("/", "/nothing", "/basemap.pmtiles", "/ws", "/.hidden", "/assets/x.js")]
    answers.append(await e.fetch("/", headers={"Host": "evil.example"}))
    answers.append(await e.fetch("/basemap.pmtiles", headers={"Range": "bytes=2-4"}))
    assert [a.code for a in answers][:2] == [200, 404] and 403 in [a.code for a in answers]
    for answer in answers:
        for key in SECURITY:
            assert answer.headers.get(key), (answer.request.url, answer.code, key)
        assert answer.headers["X-Frame-Options"] == "DENY" and answer.headers["X-Content-Type-Options"] == "nosniff" and answer.headers["Server"] == "NeoAPRS"
    csp = answers[0].headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "script-src 'self'" in csp and "worker-src 'self'" in csp and f"ws://127.0.0.1:{e.port}" in csp and "frame-ancestors 'none'" in csp
    assert "unsafe-eval" not in csp and "http:" not in csp and "https:" not in csp and "script-src 'self' 'unsafe" not in csp


async def test_a_foreign_host_name_is_refused_with_403_and_a_name_in_the_settings_is_not(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    for host in ("evil.example", "evil.example:7303", "127.0.0.1.evil.example", ""):
        answer = await e.fetch("/", headers={"Host": host})
        assert answer.code == 403 or host == "", host
        if answer.code == 403:
            assert b"NeoAPRS does not answer to the name" in answer.body and b"web/allowed_hosts" in answer.body
    with pytest.raises(HTTPClientError) as refused:
        await e.ws(host="evil.example")
    assert refused.value.code == 403
    for host in ("localhost", f"localhost:{e.port}", "127.0.0.1", "[::1]", "192.168.1.20:7303", "LOCALHOST."):
        assert (await e.fetch("/", headers={"Host": host})).code == 200, host
    page = await e.ws(host="localhost")
    await page.expect("hello")


async def test_names_in_web_allowed_hosts_and_the_name_of_the_machine_are_ours(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    assert e.ctl.web is not None
    assert (await e.fetch("/", headers={"Host": "aprs.example"})).code == 403
    await e.ctl.store.put_setting("web/allowed_hosts", "aprs.example, pi")
    second = Env(tmp_path, web=True)
    await e.stop()
    await second.start()
    for host in ("aprs.example", "pi:7303", "PI"):
        assert (await second.fetch("/", headers={"Host": host})).code == 200, host
    assert (await second.fetch("/", headers={"Host": "other.example"})).code == 403
    import socket
    assert (await second.fetch("/", headers={"Host": socket.gethostname()})).code == 200


async def test_a_socket_from_another_site_is_refused(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    with pytest.raises(HTTPClientError) as refused:
        await e.ws(origin="http://evil.example")
    page = await e.ws(origin=f"http://127.0.0.1:{e.port}")
    await page.expect("hello")
    assert refused.value.code == 403


async def test_a_command_that_is_too_big_closes_the_socket(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    await page.send_text('{"cmd": "ping", "pad": "' + "x" * (web_server.MAX_COMMAND + 10) + '"}')
    await page.until(lambda: page.closed_with is not None)
    assert page.closed_with is not None
    assert page.closed_with[0] == 1009 or (sys.platform == "win32" and page.closed_with[0] is None), "the close code (Windows may reset the connection before the client has read it)"


async def test_connections_are_capped_and_a_connection_over_the_cap_is_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr("neoaprs.web.connections.MAX_CONNECTIONS", 3)
    e = Env(tmp_path, web=True)
    await e.start()
    held = [await asyncio.open_connection("127.0.0.1", e.port) for _ in range(3)]
    await asyncio.sleep(0.1)                                              # (the server has taken them in)
    reader, writer = await asyncio.open_connection("127.0.0.1", e.port)
    writer.write(b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
    assert await asyncio.wait_for(reader.read(100), 5) == b"", "closed without an answer"
    assert any("too many connections" in r.getMessage() for r in caplog.records)
    writer.close()
    for _, w in held:
        w.close()


# ---- messages ------------------------------------------------------------------------------------------------------------------------------------

async def with_page(tmp_path: Path) -> tuple[Env, WsClient]:
    e = Env(tmp_path, web=True)
    e.ctl.messaging.tick_sec = 0.02
    e.ctl.bulletins.tick_sec = 0.02
    await e.start()
    await asyncio.sleep(0.2)                                                                            # (the TNC has settled)
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    return e, page


async def test_send_message_sends_it_and_the_pages_are_told_the_packet_and_the_message_as_sending(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    other = await e.ws()
    await page.send({"cmd": "send_message", "to": "oh2rdg", "text": "Hello Pekka"})
    await page.until(lambda: len(page.topics["packets"]) == 1 and any(r["attempts"] == 1 for r in page.topics["messages"].values()))
    [packet] = page.topics["packets"].values()
    assert packet["direction"] == "out" and packet["kind"] == "message" and packet["tnc2"] == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG   :Hello Pekka{01}"
    assert [op["op"] for op in page.ops("packets")] == ["set"]
    [row] = page.topics["messages"].values()
    message = MessageRow.model_validate_json(json.dumps(row))
    assert (message.id, message.direction, message.from_call, message.to_call, message.text, message.msg_id, message.state, message.attempts) == (1, "out", "OH2GBA", "OH2RDG", "Hello Pekka", "01", "sending", 1)
    assert message.at == iso(e.now()) and message.last_attempt_at == iso(e.now()) and message.acked_at is None
    sets = [op for op in page.ops("messages") if op["op"] == "set"]
    assert sets and sets[0]["key"] == "1" and all(op["key"] == "1" for op in sets) and sets[-1]["value"]["state"] == "sending"
    await other.until(lambda: other.topics["messages"].get("1", {}).get("attempts") == 1)
    assert page.of("error") == []


async def test_an_ack_through_the_line_makes_the_message_acked_on_every_page(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    await page.send({"cmd": "send_message", "to": "OH2RDG", "text": "Hello Pekka"})
    await page.until(lambda: page.topics["messages"].get("1", {}).get("attempts") == 1)
    e.feed(on_air("OH2RDG", ack_info("OH2GBA", "01")))
    await page.until(lambda: page.topics["messages"]["1"]["state"] == "acked")
    row = MessageRow.model_validate_json(json.dumps(page.topics["messages"]["1"]))
    assert row.acked_at == iso(e.now()) and row.attempts == 1
    assert len(page.topics["packets"]) == 2, "our message, and the ack that was heard"


async def test_a_copy_of_our_message_heard_back_is_a_set_of_its_row_with_the_hops_heard_and_the_ack_marks_the_attempt_it_answers(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    other = await e.ws()
    await page.send({"cmd": "set_station_path", "call": "OH2RDG", "path": "OH2RCH-2,OH2RDG"})
    await page.until(lambda: "OH2RDG" in page.topics["station_prefs"])
    await page.send({"cmd": "send_message", "to": "OH2RDG", "text": "Hello Pekka"})
    await page.until(lambda: page.topics["messages"].get("1", {}).get("attempts") == 1)
    sent = MessageRow.model_validate_json(json.dumps(page.topics["messages"]["1"]))
    assert [(a.sent_at, [(h.call, h.heard, h.heard_at, h.by_internet) for h in a.hops], a.internet, a.acked) for a in sent.attempts_detail] == [
        (iso(e.now()), [("OH2RCH-2", False, None, False), ("OH2RDG", False, None, False)], None, False)]
    sets = len([op for op in page.ops("messages") if op["op"] == "set"])
    e.feed(on_air("OH2GBA", message_info("OH2RDG", "Hello Pekka", "01"), path="OH2RCH-2*,OH2RDG"))
    await page.until(lambda: page.topics["messages"]["1"]["attempts_detail"][0]["hops"][0]["heard"])
    assert len([op for op in page.ops("messages") if op["op"] == "set"]) == sets + 1, "a hop that is heard is one more set of the row"
    row = MessageRow.model_validate_json(json.dumps(page.topics["messages"]["1"]))
    assert [(h.call, h.heard, h.heard_at, h.by_internet) for h in row.attempts_detail[0].hops] == [("OH2RCH-2", True, iso(e.now()), False), ("OH2RDG", False, None, False)] and row.attempts == 1
    e.feed(on_air("OH7JHF-1", b"}OH2GBA>APZNEO,TCPIP,OH7JHF-1*::OH2RDG   :Hello Pekka{01}", path="OH2RCH-3*"))
    await page.until(lambda: page.topics["messages"]["1"]["attempts_detail"][0]["internet"] == "OH7JHF-1")
    await other.until(lambda: other.topics["messages"]["1"]["attempts_detail"][0]["internet"] == "OH7JHF-1")
    assert other.topics["messages"] == page.topics["messages"]
    e.feed(on_air("OH2RDG", ack_info("OH2GBA", "01")))
    await page.until(lambda: page.topics["messages"]["1"]["state"] == "acked")
    assert [a["acked"] for a in page.topics["messages"]["1"]["attempts_detail"]] == [True] and len(page.topics["messages"]) == 1, "our own copies are no messages of the list"
    late = await e.ws()
    await late.until(lambda: len(late.of("state")) == len(TOPIC_NAMES))
    assert late.topics["messages"] == page.topics["messages"], "a page that comes later is sent the chain whole"
    assert page.of("error") == []


async def test_a_message_sent_to_us_is_a_row_with_state_received_and_our_ack_is_the_packet_after_it(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    e.feed(on_air("OH2RDG-7", message_info("OH2GBA", "Moi!", "12")))
    await page.until(lambda: len(page.topics["messages"]) == 1 and len(page.topics["packets"]) == 2)
    row = MessageRow.model_validate_json(json.dumps(page.topics["messages"]["1"]))
    assert (row.direction, row.from_call, row.to_call, row.text, row.msg_id, row.state, row.attempts) == ("in", "OH2RDG-7", "OH2GBA", "Moi!", "12", "received", 0)
    assert row.attempts_detail == [], "a message that came in has no attempts"
    assert sorted(r["tnc2"] for r in page.topics["packets"].values())[0].endswith("::OH2RDG-7 :ack12")
    late = await e.ws()
    await late.until(lambda: len(late.of("state")) == len(TOPIC_NAMES))
    assert late.topics["messages"] == page.topics["messages"], "a page that comes later is sent the messages whole"


@pytest.mark.parametrize("to, text, reason", [
    ("", "x", "at least 1"), ("TOOLONGCALL", "x", "call"), ("OH2 RDG", "x", "call"), ("OH2GBA", "x", "own call"), ("OH2RDG", "", "empty"), ("OH2RDG", "x" * 68, "68 characters"), ("OH2RDG", "a{b", "{"),
    ("OH2RDG", "a\nb", "control")])
async def test_a_bad_addressee_or_text_is_an_error_that_says_why_and_nothing_is_sent_or_kept(tmp_path: Path, to: str, text: str, reason: str) -> None:
    e, page = await with_page(tmp_path)
    await page.send({"cmd": "send_message", "to": to, "text": text})
    error = (await page.expect("error"))["text"]
    assert error.startswith("send_message: ") and reason in error
    await page.quiet(0.2)
    assert page.topics["messages"] == {} and page.topics["packets"] == {} and await e.ctl.messagelog.recent() == []


async def test_a_message_sent_while_the_tnc_is_not_connected_is_kept_and_goes_out_when_it_is(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    e.ctl.messaging.tick_sec = 0.02
    await e.start()
    await asyncio.sleep(0.2)
    e.unplug()
    await until(lambda: e.tnc.state is Source.State.WAITING)
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    await page.send({"cmd": "send_message", "to": "OH2RDG", "text": "later"})
    await page.until(lambda: page.topics["messages"].get("1", {}).get("state") == "sending")
    assert page.topics["messages"]["1"]["attempts"] == 0 and page.topics["messages"]["1"]["last_attempt_at"] is None and page.of("error") == []
    await e.plug()
    await e.until_connected()
    await page.until(lambda: page.topics["messages"]["1"]["attempts"] == 1)


async def test_message_cancel_and_message_retry_change_the_row_and_say_why_when_they_cannot(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    await page.send({"cmd": "send_message", "to": "OH2RDG", "text": "Hello"})
    await page.until(lambda: page.topics["messages"].get("1", {}).get("attempts") == 1)
    await page.send({"cmd": "message_retry", "id": 1})
    assert "message_retry: " in (await page.expect("error"))["text"] and "sending" in page.of("error")[-1]["text"]
    await page.send({"cmd": "message_cancel", "id": 1})
    await page.until(lambda: page.topics["messages"]["1"]["state"] == "cancelled")
    await page.send({"cmd": "message_cancel", "id": 1})
    await page.until(lambda: len(page.of("error")) == 2)
    assert "message_cancel: " in page.of("error")[-1]["text"] and "cancelled" in page.of("error")[-1]["text"]
    await page.send({"cmd": "message_retry", "id": 1})
    await page.until(lambda: page.topics["messages"]["1"]["state"] == "sending" and page.topics["messages"]["1"]["attempts"] == 1)
    await page.send({"cmd": "message_retry", "id": 99})
    await page.until(lambda: len(page.of("error")) == 3)
    assert "no message 99" in page.of("error")[-1]["text"]


async def test_message_delete_removes_the_row_from_the_database_and_every_page_and_says_why_when_it_cannot(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    other = await e.ws()
    await other.until(lambda: len(other.of("state")) == len(TOPIC_NAMES))
    await page.send({"cmd": "send_message", "to": "OH2RDG", "text": "Hello"})
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "Moi!", "3")))
    e.feed(on_air("OH2AAA", message_info("OH2BBB", "not for us", "4")))
    await page.until(lambda: len(page.topics["messages"]) == 3 and page.topics["messages"]["1"]["attempts"] == 1)
    await page.send({"cmd": "message_delete", "id": 1})
    await page.until(lambda: "1" not in page.topics["messages"])
    await other.until(lambda: "1" not in other.topics["messages"])
    assert [op for op in page.ops("messages") if op["op"] == "del"] == [{"op": "del", "key": "1"}]
    assert sorted(m.id for m in await e.ctl.messagelog.recent()) == [2] and [m.id for m in await e.ctl.messagelog.recent(overheard=True)] == [3]
    await page.send({"cmd": "message_delete", "id": 3})
    await page.send({"cmd": "message_delete", "id": 2})
    await page.until(lambda: page.topics["messages"] == {})
    await page.send({"cmd": "message_delete", "id": 2})
    assert "message_delete: " in (await page.expect("error"))["text"] and "no message 2" in page.of("error")[-1]["text"]
    await page.quiet(0.2)
    assert await e.ctl.messagelog.recent() == [] and await e.ctl.messagelog.recent(overheard=True) == []
    await page.send({"cmd": "message_delete", "id": 0})
    await page.until(lambda: len(page.of("error")) == 2)
    assert page.of("error")[-1]["text"].startswith("message_delete: id: ")


async def test_conversation_delete_removes_every_message_with_the_station_from_the_database_and_every_page(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    other = await e.ws()
    await other.until(lambda: len(other.of("state")) == len(TOPIC_NAMES))
    await page.send({"cmd": "set_station_path", "call": "OH2RDG", "path": "OH2RCH-2"})
    await page.send({"cmd": "send_message", "to": "OH2RDG", "text": "Hello"})
    await page.send({"cmd": "send_message", "to": "OH2AAA", "text": "Hello you"})
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "Moi!", "3")))
    e.feed(on_air("OH2RDG", message_info("OH2CCC", "overheard", "4")))
    await page.until(lambda: len(page.topics["messages"]) == 4 and all(r["attempts"] == 1 for r in page.topics["messages"].values() if r["state"] == "sending"))
    await other.until(lambda: len(other.topics["messages"]) == 4)
    ids = {r["text"]: key for key, r in page.topics["messages"].items()}
    await page.send({"cmd": "conversation_delete", "call": "oh2rdg"})
    kept = sorted([ids["Hello you"], ids["overheard"]])
    await page.until(lambda: sorted(page.topics["messages"]) == kept)
    await other.until(lambda: sorted(other.topics["messages"]) == kept)
    assert sorted(op["key"] for op in other.ops("messages") if op["op"] == "del") == sorted([ids["Hello"], ids["Moi!"]])
    assert page.topics["messages"][ids["overheard"]]["state"] == "overheard" and page.topics["messages"][ids["Hello you"]]["state"] == "sending"
    assert [m.text for m in await e.ctl.messagelog.recent()] == ["Hello you"] and [m.text for m in await e.ctl.messagelog.recent(overheard=True)] == ["overheard"]
    assert page.topics["station_prefs"]["OH2RDG"]["path"] == "OH2RCH-2", "the station's path is kept"
    await page.send({"cmd": "conversation_delete", "call": "OH2RDG"})
    assert "conversation_delete: " in (await page.expect("error"))["text"] and "no conversation with OH2RDG" in page.of("error")[-1]["text"]
    await page.send({"cmd": "conversation_delete", "call": ""})
    await page.until(lambda: len(page.of("error")) == 2)
    assert page.of("error")[-1]["text"].startswith("conversation_delete: call: ")


async def test_overheard_delete_removes_the_overheard_messages_of_a_pair_from_the_database_and_every_page_and_no_conversation(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    other = await e.ws()
    await other.until(lambda: len(other.of("state")) == len(TOPIC_NAMES))
    await page.send({"cmd": "send_message", "to": "OH2AAA", "text": "Hello you"})
    e.feed(on_air("OH2AAA", message_info("OH2GBA", "Moi!", "3")))
    e.feed(on_air("OH2AAA", message_info("OH2BBB", "first", "4")))
    e.feed(on_air("OH2AAA", message_info("OH2BBB", "second", "5")))
    e.feed(on_air("OH2AAA", message_info("OH2CCC", "elsewhere", "6")))
    await page.until(lambda: len(page.topics["messages"]) == 5)
    await other.until(lambda: len(other.topics["messages"]) == 5)
    ids = {r["text"]: key for key, r in page.topics["messages"].items()}
    await page.send({"cmd": "overheard_delete", "from_call": "oh2aaa", "to_call": "OH2BBB"})
    kept = sorted([ids["Hello you"], ids["Moi!"], ids["elsewhere"]])
    await page.until(lambda: sorted(page.topics["messages"]) == kept)
    await other.until(lambda: sorted(other.topics["messages"]) == kept)
    assert sorted(op["key"] for op in other.ops("messages") if op["op"] == "del") == sorted([ids["first"], ids["second"]])
    assert [m.text for m in await e.ctl.messagelog.recent(overheard=True)] == ["elsewhere"] and sorted(m.text for m in await e.ctl.messagelog.recent()) == ["Hello you", "Moi!"]
    await page.send({"cmd": "overheard_delete", "from_call": "OH2AAA", "to_call": "OH2BBB"})
    assert "overheard_delete: " in (await page.expect("error"))["text"] and "no overheard message from OH2AAA to OH2BBB" in page.of("error")[-1]["text"]
    await page.send({"cmd": "overheard_delete", "from_call": "OH2AAA", "to_call": "OH2GBA"})
    await page.until(lambda: len(page.of("error")) == 2)
    assert "no overheard message" in page.of("error")[-1]["text"] and sorted(page.topics["messages"]) == kept, "a conversation is never removed by it"
    await page.send({"cmd": "overheard_delete", "from_call": "", "to_call": "OH2BBB"})
    await page.until(lambda: len(page.of("error")) == 3)
    assert page.of("error")[-1]["text"].startswith("overheard_delete: from_call: ")


async def test_the_attempts_setting_is_the_number_a_message_is_sent_with_from_then_on(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    assert page.topics["config"]["values"]["messages/attempts"] == "6"
    await page.send({"cmd": "send_message", "to": "OH2RDG", "text": "one"})
    await page.until(lambda: page.topics["messages"].get("1", {}).get("attempts") == 1)
    await page.send({"cmd": "set_config", "values": {"messages/attempts": "3"}})
    await page.until(lambda: page.topics["config"]["values"]["messages/attempts"] == "3")
    await page.send({"cmd": "send_message", "to": "OH2RDG", "text": "two"})
    await page.until(lambda: page.topics["messages"].get("2", {}).get("attempts") == 1)
    assert (page.topics["messages"]["1"]["attempts_max"], page.topics["messages"]["2"]["attempts_max"]) == (6, 3)
    await page.send({"cmd": "set_config", "values": {"messages/attempts": "11"}})
    assert "messages/attempts" in (await page.expect("error"))["text"]


async def test_a_rej_through_the_line_is_rejected_and_the_page_can_send_it_again(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    await page.send({"cmd": "send_message", "to": "OH2RDG", "text": "Hello"})
    await page.until(lambda: page.topics["messages"].get("1", {}).get("attempts") == 1)
    e.feed(on_air("OH2RDG", reject_info("OH2GBA", "01")))
    await page.until(lambda: page.topics["messages"]["1"]["state"] == "rejected")
    await page.send({"cmd": "message_retry", "id": 1})
    await page.until(lambda: page.topics["messages"]["1"]["state"] == "sending")
    assert page.of("error") == []


async def test_a_restarted_daemon_opens_with_the_messages_the_database_kept(tmp_path: Path) -> None:
    first, page = await with_page(tmp_path)
    await page.send({"cmd": "send_message", "to": "OH2RDG", "text": "Hello"})
    await page.until(lambda: page.topics["messages"].get("1", {}).get("attempts") == 1)
    first.feed(on_air("OH2RDG", message_info("OH2GBA", "Moi!", "3")))
    await page.until(lambda: len(page.topics["messages"]) == 2)
    await first.stop()
    second = Env(tmp_path, web=True)
    await second.start()
    again = await second.ws()
    await again.until(lambda: len(again.of("state")) == len(TOPIC_NAMES))
    assert {k: (r["direction"], r["text"], r["state"]) for k, r in again.topics["messages"].items()} == {"1": ("out", "Hello", "sending"), "2": ("in", "Moi!", "received")}


def pref(path: str | None, hide_after_min: int | None, attempts: int | None = None, rf_only: bool = False) -> dict[str, object]:
    return {"path": path, "hide_after_min": hide_after_min, "attempts": attempts, "rf_only": rf_only}


async def test_set_station_path_and_clear_station_path_change_the_entry_of_the_topic_and_the_path_of_the_message(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    other = await e.ws()
    await page.send({"cmd": "set_station_path", "call": "oh2rdg", "path": "oh2rch-2, wide2-1"})
    await page.until(lambda: page.topics["station_prefs"] == {"OH2RDG": pref("OH2RCH-2,WIDE2-1", None)})
    await other.until(lambda: other.topics["station_prefs"] == {"OH2RDG": pref("OH2RCH-2,WIDE2-1", None)})
    await page.send({"cmd": "send_message", "to": "OH2RDG", "text": "Hello"})
    await page.until(lambda: any("OH2RCH-2,WIDE2-1" in r["tnc2"] for r in page.topics["packets"].values()))
    await page.send({"cmd": "set_station_path", "call": "OH2XYZ", "path": ""})
    await page.until(lambda: page.topics["station_prefs"].get("OH2XYZ") == pref("", None), timeout=5)
    await page.send({"cmd": "clear_station_path", "call": "OH2RDG"})
    await page.until(lambda: "OH2RDG" not in page.topics["station_prefs"])
    assert page.topics["station_prefs"] == {"OH2XYZ": pref("", None)} and [op["op"] for op in page.ops("station_prefs")] == ["set", "set", "del"]
    assert page.of("error") == []
    late = await e.ws()
    await late.until(lambda: len(late.of("state")) == len(TOPIC_NAMES))
    assert late.topics["station_prefs"] == {"OH2XYZ": pref("", None)}


async def test_set_station_timeout_and_clear_station_timeout_change_the_entry_and_keep_the_path_beside_it(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    other = await e.ws()
    await page.send({"cmd": "set_station_timeout", "call": "oh2rdg", "minutes": 45})
    await page.until(lambda: page.topics["station_prefs"] == {"OH2RDG": pref(None, 45)})
    await other.until(lambda: other.topics["station_prefs"] == {"OH2RDG": pref(None, 45)})
    await page.send({"cmd": "set_station_path", "call": "OH2RDG", "path": "WIDE2-1"})
    await page.until(lambda: page.topics["station_prefs"] == {"OH2RDG": pref("WIDE2-1", 45)})
    await page.send({"cmd": "set_station_timeout", "call": "OH2RDG", "minutes": 0})                  # never
    await page.send({"cmd": "set_station_timeout", "call": "STORM", "minutes": 10080})               # (an object has a name, not a call)
    await page.until(lambda: page.topics["station_prefs"] == {"OH2RDG": pref("WIDE2-1", 0), "STORM": pref(None, 10080)})
    await page.send({"cmd": "clear_station_path", "call": "OH2RDG"})
    await page.until(lambda: page.topics["station_prefs"]["OH2RDG"] == pref(None, 0))
    await page.send({"cmd": "clear_station_timeout", "call": "OH2RDG"})
    await page.until(lambda: "OH2RDG" not in page.topics["station_prefs"])
    await page.send({"cmd": "clear_station_timeout", "call": "OH2RDG"})                              # (nothing to clear: no error, no patch)
    assert page.topics["station_prefs"] == {"STORM": pref(None, 10080)} and page.of("error") == []
    assert [(op["op"], op["key"]) for op in page.ops("station_prefs")] == [("set", "OH2RDG"), ("set", "OH2RDG"), ("set", "OH2RDG"), ("set", "STORM"), ("set", "OH2RDG"), ("del", "OH2RDG")]
    late = await e.ws()
    await late.until(lambda: len(late.of("state")) == len(TOPIC_NAMES))
    assert late.topics["station_prefs"] == {"STORM": pref(None, 10080)}
    for value in late.topics["station_prefs"].values():
        StationPref.model_validate_json(json.dumps(value))


async def test_set_station_rf_only_changes_the_entry_keeps_the_rest_and_the_next_message_goes_with_rfonly_and_the_chain_shows_no_such_hop(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    other = await e.ws()
    await page.send({"cmd": "set_station_rf_only", "call": "oh2rdg", "on": True})
    await page.until(lambda: page.topics["station_prefs"] == {"OH2RDG": pref(None, None, None, True)})
    await other.until(lambda: other.topics["station_prefs"] == {"OH2RDG": pref(None, None, None, True)})
    await page.send({"cmd": "set_station_path", "call": "OH2RDG", "path": "OH2RCH-2,OH2RDG"})
    await page.until(lambda: page.topics["station_prefs"] == {"OH2RDG": pref("OH2RCH-2,OH2RDG", None, None, True)})
    await page.send({"cmd": "send_message", "to": "OH2RDG", "text": "Hello"})
    await page.until(lambda: any("OH2RCH-2,OH2RDG,RFONLY" in r["tnc2"] for r in page.topics["packets"].values()))
    row = MessageRow.model_validate_json(json.dumps(page.topics["messages"]["1"]))
    assert [h.call for h in row.attempts_detail[0].hops] == ["OH2RCH-2", "OH2RDG"], "RFONLY is no hop of the chain"
    await page.send({"cmd": "set_station_rf_only", "call": "OH2RDG", "on": False})
    await page.until(lambda: page.topics["station_prefs"] == {"OH2RDG": pref("OH2RCH-2,OH2RDG", None, None, False)})
    await page.send({"cmd": "clear_station_path", "call": "OH2RDG"})
    await page.until(lambda: page.topics["station_prefs"] == {})
    assert [(op["op"], op["key"]) for op in page.ops("station_prefs")] == [("set", "OH2RDG"), ("set", "OH2RDG"), ("set", "OH2RDG"), ("del", "OH2RDG")] and page.of("error") == []
    late = await e.ws()
    await late.until(lambda: len(late.of("state")) == len(TOPIC_NAMES))
    assert late.topics["station_prefs"] == {}


async def test_set_station_rf_only_for_the_email_gateway_is_an_error_that_says_why_and_changes_nothing(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    await page.send({"cmd": "set_station_rf_only", "call": "email-2", "on": True})
    await page.until(lambda: len(page.of("error")) == 1)
    assert page.of("error")[0]["text"] == "set_station_rf_only: EMAIL-2 cannot be RF only: the email gateway is on the internet"
    await page.send({"cmd": "set_station_rf_only", "call": "email-2", "on": False})
    await page.send({"cmd": "ping"})
    await page.until(lambda: len(page.of("pong")) == 1)
    assert page.topics["station_prefs"] == {} and len(page.of("error")) == 1 and page.ops("station_prefs") == []


async def test_set_station_attempts_and_clear_station_attempts_change_the_entry_keep_the_rest_and_the_next_message_takes_the_count(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    other = await e.ws()
    await page.send({"cmd": "set_station_attempts", "call": "email-2", "attempts": 2})
    await page.until(lambda: page.topics["station_prefs"] == {"EMAIL-2": pref(None, None, 2)})
    await other.until(lambda: other.topics["station_prefs"] == {"EMAIL-2": pref(None, None, 2)})
    await page.send({"cmd": "set_station_timeout", "call": "EMAIL-2", "minutes": 30})
    await page.until(lambda: page.topics["station_prefs"] == {"EMAIL-2": pref(None, 30, 2)})
    await page.send({"cmd": "send_message", "to": "EMAIL-2", "text": "me@example.org Hello"})
    await page.send({"cmd": "send_message", "to": "OH2RDG", "text": "Hello"})
    await page.until(lambda: len(page.topics["messages"]) == 2)
    rows = [MessageRow.model_validate_json(json.dumps(page.topics["messages"][k])) for k in ("1", "2")]
    assert [(r.to_call, r.attempts_max, r.state) for r in rows] == [("EMAIL-2", 2, "sending"), ("OH2RDG", 6, "sending")]
    await page.send({"cmd": "set_station_attempts", "call": "STORM", "attempts": 10})               # (an object has a name, not a call)
    await page.send({"cmd": "clear_station_timeout", "call": "EMAIL-2"})
    await page.until(lambda: page.topics["station_prefs"].get("EMAIL-2") == pref(None, None, 2))
    await page.send({"cmd": "clear_station_attempts", "call": "EMAIL-2"})
    await page.until(lambda: "EMAIL-2" not in page.topics["station_prefs"])
    await page.send({"cmd": "clear_station_attempts", "call": "EMAIL-2"})                            # (nothing to clear: no error, no patch)
    assert page.topics["station_prefs"] == {"STORM": pref(None, None, 10)} and page.of("error") == []
    assert [(op["op"], op["key"]) for op in page.ops("station_prefs")] == [("set", "EMAIL-2"), ("set", "EMAIL-2"), ("set", "STORM"), ("set", "EMAIL-2"), ("del", "EMAIL-2")]
    late = await e.ws()
    await late.until(lambda: len(late.of("state")) == len(TOPIC_NAMES))
    assert late.topics["station_prefs"] == {"STORM": pref(None, None, 10)}
    for value in late.topics["station_prefs"].values():
        StationPref.model_validate_json(json.dumps(value))


@pytest.mark.parametrize("attempts, reason", [(0, "at least 1"), (11, "at most 10"), ("2", "whole number"), (None, "is missing")])
async def test_attempts_out_of_range_are_refused_before_anything_is_done(tmp_path: Path, attempts: object, reason: str) -> None:
    e, page = await with_page(tmp_path)
    await page.send({"cmd": "set_station_attempts", "call": "OH2RDG", **({} if attempts is None else {"attempts": attempts})})
    error = (await page.expect("error"))["text"]
    assert error.startswith("set_station_attempts: attempts: ") and reason in error
    assert page.topics["station_prefs"] == {}


@pytest.mark.parametrize("command, reason", [
    ({"cmd": "set_station_attempts", "call": "TOOLONGNAMEFORANOBJECT", "attempts": 2}, "not a call or the name of an object"), ({"cmd": "clear_station_attempts", "call": "   "}, "not a call or the name of an object"),
    ({"cmd": "set_station_path", "call": "TOOLONGCALL", "path": ""}, "call"), ({"cmd": "set_station_path", "call": "OH2RDG", "path": "WIDE 1"}, "call"),
    ({"cmd": "set_station_path", "call": "OH2RDG", "path": ",".join(["WIDE1-1"] * 9)}, "more than the 8"), ({"cmd": "clear_station_path", "call": "TOOLONGCALL"}, "call"),
    ({"cmd": "set_station_timeout", "call": "TOOLONGNAMEFORANOBJECT", "minutes": 5}, "not a call or the name of an object"), ({"cmd": "set_station_timeout", "call": "   ", "minutes": 5}, "not a call or the name of an object"),
    ({"cmd": "clear_station_timeout", "call": "TOOLONGNAMEFORANOBJECT"}, "not a call or the name of an object")])
async def test_a_bad_path_or_call_is_an_error_that_says_why_and_changes_nothing(tmp_path: Path, command: dict[str, str], reason: str) -> None:
    e, page = await with_page(tmp_path)
    await page.send(command)
    error = (await page.expect("error"))["text"]
    assert error.startswith(command["cmd"] + ": ") and reason in error
    assert page.topics["station_prefs"] == {}


@pytest.mark.parametrize("minutes, reason", [(10081, "at most 10080"), (-1, "at least 0"), ("30", "whole number"), (None, "is missing")])
async def test_a_timeout_out_of_range_is_refused_before_anything_is_done(tmp_path: Path, minutes: object, reason: str) -> None:
    e, page = await with_page(tmp_path)
    await page.send({"cmd": "set_station_timeout", "call": "OH2RDG", **({} if minutes is None else {"minutes": minutes})})
    error = (await page.expect("error"))["text"]
    assert error.startswith("set_station_timeout: minutes: ") and reason in error
    assert page.topics["station_prefs"] == {}


async def test_an_overheard_message_is_a_row_of_the_topic_with_state_overheard_and_no_ack_goes_out(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    e.feed(on_air("OH2RDG", message_info("OH2XYZ", "not for us", "3")))
    await page.until(lambda: len(page.topics["messages"]) == 1)
    row = MessageRow.model_validate_json(json.dumps(page.topics["messages"]["1"]))
    assert (row.state, row.direction, row.from_call, row.to_call, row.attempts) == ("overheard", "in", "OH2RDG", "OH2XYZ", 0)
    await page.quiet(0.2)
    assert [r["direction"] for r in page.topics["packets"].values()] == ["in"]


# ---- how a packet reached us ----------------------------------------------------------------------------------------------------------------

async def test_the_capture_rows_say_how_each_packet_and_each_station_was_reached(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    await e.play()
    await page.until(lambda: len(page.topics["packets"]) == 4 and len(page.topics["stations"]) >= 5)
    assert {r["route"] for r in page.topics["packets"].values()} == {"via OH2RCH-2"} and {r["via"] for r in page.topics["packets"].values()} == {""}
    rdk = StationRow.model_validate_json(json.dumps(page.topics["stations"]["OH2RDK-7"]))
    assert (rdk.last_route, rdk.heard_direct, rdk.heard_gated, rdk.heard_via, rdk.best_route, rdk.suggested_path) == ("via OH2RCH-2", 0, 0, [("OH2RCH-2", 1)], "via OH2RCH-2", "OH2RCH-2")
    me = StationRow.model_validate_json(json.dumps(page.topics["stations"]["OH2GBA"]))
    assert (me.last_route, me.heard_via, me.best_route, me.suggested_path) == ("", [], "", None), "nothing is known of how we are reached"
    await e.stop()


async def test_a_message_keeps_the_route_it_came_by_and_a_page_that_comes_later_has_it(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    e.feed(on_air("OH2RDG-7", message_info("OH2GBA", "Moi!", "12"), path="WIDE1*,OH2RCH-2*"))
    e.feed(on_air("OH2RDG-7", message_info("OH2GBA", "Direct", "13"), path=""))
    await page.until(lambda: len(page.topics["messages"]) == 2)
    assert [r["route"] for r in page.topics["messages"].values()] == ["via ? → OH2RCH-2", "direct"]
    await page.send({"cmd": "send_message", "to": "OH2RDG-7", "text": "Hei"})
    await page.until(lambda: len(page.topics["messages"]) == 3)
    ours = MessageRow.model_validate_json(json.dumps(page.topics["messages"]["3"]))
    assert ours.route == "" and {r["route"] for r in page.topics["packets"].values() if r["direction"] == "out"} == {""}, "the packets we sent have no route"
    station = StationRow.model_validate_json(json.dumps(page.topics["stations"]["OH2RDG-7"]))
    assert (station.heard_direct, station.heard_via, station.best_route, station.suggested_path) == (1, [("OH2RCH-2", 1)], "direct", ""), "one direct, one through an unnamed hop and OH2RCH-2: direct wins the tie"
    await e.stop()
    again = Env(tmp_path, web=True)
    await again.start()
    late = await again.ws()
    await late.until(lambda: len(late.of("state")) == len(TOPIC_NAMES))
    assert [r["route"] for r in late.topics["messages"].values() if r["direction"] == "in"] == ["via ? → OH2RCH-2", "direct"]
    assert late.topics["stations"]["OH2RDG-7"]["heard_direct"] == 1 and late.topics["stations"]["OH2RDG-7"]["heard_via"] == [["OH2RCH-2", 1]], "the station book counts again from the packets the database kept"


async def test_a_third_party_ack_and_message_are_rows_for_the_sender_inside_and_the_gate_is_no_route_to_send_by(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    await page.send({"cmd": "send_message", "to": "OH2DPN", "text": "Hello"})
    await page.until(lambda: page.topics["messages"].get("1", {}).get("attempts") == 1)
    e.feed(on_air("OH7JHF-1", b"}OH2DPN>APJYC1,TCPIP,OH7JHF-1*::OH2GBA   :ack01", path="OH2RCH-3*"))
    e.feed(on_air("OH7JHF-1", b"}OH2BEA-9>APY300,TCPIP,OH7JHF-1*::OH2GBA   :Test ok{06", path="OH2RCH-3*"))
    await page.until(lambda: page.topics["messages"]["1"]["state"] == "acked" and "2" in page.topics["messages"])
    received = MessageRow.model_validate_json(json.dumps(page.topics["messages"]["2"]))
    assert (received.from_call, received.text, received.route) == ("OH2BEA-9", "Test ok", "via OH7JHF-1 (internet) → OH2RCH-3")
    third = [r for r in page.topics["packets"].values() if r["via"]]
    assert [r["source"] for r in third] == ["OH7JHF-1", "OH7JHF-1"] and {r["route"] for r in third} == {"via OH7JHF-1 (internet) → OH2RCH-3"}
    assert all(r["summary"].endswith(" via OH7JHF-1 (third-party)") and r["path"] == ["OH2RCH-3*"] for r in third)
    assert "OH7JHF-1" not in page.topics["stations"]
    sender = StationRow.model_validate_json(json.dumps(page.topics["stations"]["OH2BEA-9"]))
    assert (sender.heard_gated, sender.heard_direct, sender.heard_via, sender.best_route, sender.suggested_path) == (1, 0, [], "", None)
    assert sender.last_route == "via OH7JHF-1 (internet) → OH2RCH-3"
    await e.stop()


# ---- the message board -----------------------------------------------------------------------------------------------------------------------

async def test_a_bulletin_is_a_row_of_the_topic_keyed_by_sender_and_slot_and_never_ages_out(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    e.feed(on_air("OH2XYZ", message_info("BLN3HAMS", "Net tonight 20:00", "5")))
    await page.until(lambda: "OH2XYZ/BLN3HAMS" in page.topics["bulletins"])
    row = BulletinRow.model_validate_json(json.dumps(page.topics["bulletins"]["OH2XYZ/BLN3HAMS"]))
    assert (row.sender, row.slot, row.group, row.kind, row.text, row.times_heard) == ("OH2XYZ", "BLN3HAMS", "HAMS", "group", "Net tonight 20:00", 1)
    assert row.first_heard == row.last_heard == iso(e.now()) and page.topics["messages"] == {}, "it is no message of a conversation"
    e.now.advance(60)                                                                                   # type: ignore[attr-defined]
    e.feed(on_air("OH2XYZ", message_info("BLN3HAMS", "Net tonight 20:00", "5")))
    await page.until(lambda: page.topics["bulletins"]["OH2XYZ/BLN3HAMS"]["times_heard"] == 2)
    assert [op["op"] for op in page.ops("bulletins")] == ["set", "set"]
    late = await e.ws()
    await late.until(lambda: len(late.of("state")) == len(TOPIC_NAMES))
    assert late.topics["bulletins"]["OH2XYZ/BLN3HAMS"]["times_heard"] == 2, "a page that comes later is told the board whole"
    e.now.advance(30 * 86400)                                                                           # type: ignore[attr-defined]
    await page.quiet(0.3)
    assert "OH2XYZ/BLN3HAMS" in page.topics["bulletins"] and [op["op"] for op in page.ops("bulletins")] == ["set", "set"], "nothing ages out"
    assert page.of("error") == []
    await e.stop()


async def test_a_station_row_says_when_the_station_was_last_heard_direct(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    e.feed(on_air("OH2PU-9", b">hello", path=""))
    e.feed(on_air("OH2FAR", b">far", path="OH2RCH-2*"))
    await page.until(lambda: "OH2PU-9" in page.topics["stations"] and "OH2FAR" in page.topics["stations"])
    direct = StationRow.model_validate_json(json.dumps(page.topics["stations"]["OH2PU-9"]))
    far = StationRow.model_validate_json(json.dumps(page.topics["stations"]["OH2FAR"]))
    assert direct.last_direct_at == iso(e.now()) and direct.heard_direct == 1 and far.last_direct_at is None
    assert page.topics["stations"]["OH2GBA"]["last_direct_at"] is None
    await e.stop()
