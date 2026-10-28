"""The wire format (neoaprs/web/protocol.py and the neoaprs/web/*wire.py modules): the files generated from it are current, every message the daemon sends has an example that validates (and a field that is wrong or
extra does not), every command round-trips, and the registry of handlers is the list of commands."""
import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from pydantic import ValidationError

from neoaprs.aprsmessage import MAX_TEXT
from neoaprs.config import KEYS
from neoaprs.packetcodec import KINDS
from neoaprs.web import dispatch, handlers  # noqa: F401  (importing the handlers registers them)
from neoaprs.web.hubwire import PROTOCOL
from neoaprs.web.messagewire import MessageRow
from neoaprs.web.prefwire import StationPref
from neoaprs.web.packetwire import PacketRow
from neoaprs.web.protocol import COMMAND_NAMES, COMMAND_TYPES, COMMANDS, MESSAGE_NAMES, MESSAGE_TYPES, MESSAGES, TOPIC_ITEMS, TOPIC_NAMES, TOPIC_VALUES
from neoaprs.web.stationwire import StationRow
from neoaprs.web.tncwire import TncState

ROOT = Path(__file__).resolve().parent.parent
HINT = "run .venv/bin/python scripts/gen-protocol.py and commit the result"


def generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_protocol", ROOT / "scripts" / "gen-protocol.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---- the generated files -------------------------------------------------------------------------------------------------------------------------

def test_the_generated_files_are_current() -> None:
    """The generator is run in memory and its files are compared with the ones in the tree: change a model, run the script, commit."""
    gen = generator()
    for path, text in gen.render().items():
        assert path.read_text(encoding="utf-8") == text, f"{path.relative_to(ROOT)} is out of date: {HINT}"


def test_the_generator_with_check_says_so_and_changes_nothing(tmp_path: Path) -> None:
    import subprocess
    import sys
    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "gen-protocol.py"), "--check"], capture_output=True, text=True, timeout=120, cwd=tmp_path)
    assert done.returncode == 0 and done.stdout == "", done.stdout + done.stderr


def test_the_schema_and_the_types_carry_every_command_and_message() -> None:
    gen = generator()
    schema = json.loads(gen.SCHEMA.read_text(encoding="utf-8"))
    assert set(schema["properties"]["command"]["discriminator"]["mapping"]) == COMMAND_NAMES
    assert set(schema["properties"]["message"]["discriminator"]["mapping"]) == MESSAGE_NAMES
    assert set(schema["properties"]["topics"]["$ref"].rsplit("/")[-1:]) == {"TopicValues"} and set(schema["$defs"]["TopicValues"]["properties"]) == set(TOPIC_NAMES)
    ts = gen.TYPES.read_text(encoding="utf-8")
    for name in COMMAND_NAMES:
        assert f'cmd: "{name}";' in ts, name
    for name in MESSAGE_NAMES:
        assert f'type: "{name}";' in ts, name
    assert "export type Command =" in ts and "export type Message =" in ts and "export interface TopicValues {" in ts
    assert "track: [string, number, number][];" in ts and "decoded: DecodedPosition | DecodedMessage" in ts and "lat: number | null;" in ts and "ops: (SetOp | DelOp | ReplaceOp)[];" in ts
    assert re.search(r'export interface StatusMessage \{\n  type: "status";', ts) and "export interface AskStatusCommand" in ts, "the tag comes first; a command and a message of one name have two"


def test_the_lists_of_the_page_are_the_daemons_own() -> None:
    lists = generator().LISTS.read_text(encoding="utf-8")
    assert f"export const PROTOCOL = {PROTOCOL};" in lists
    for key in KEYS:
        assert json.dumps(key) in lists
    assert "export const LIMITS = {" in lists and "textMax: %d" % MAX_TEXT in lists
    topics = lists.split("export const TOPIC_NAMES = ", 1)[1].split(" as const;", 1)[0]
    assert re.findall(r'"(\w+)"', topics) == list(TOPIC_NAMES)


def test_the_reference_documents_every_command_message_and_model() -> None:
    gen = generator()
    doc = (ROOT / "PROTOCOL.md").read_text(encoding="utf-8")
    for name in COMMAND_NAMES | MESSAGE_NAMES:
        assert f"### `{name}`" in doc, name
    for section in ("## Connection, the host and the headers", "## Validation", "## Client to server", "## Server to client", "## Topics", "## Objects"):
        assert section in doc
    defs = json.loads(gen.SCHEMA.read_text(encoding="utf-8"))["$defs"]
    objects = doc.partition("\n## Objects\n")[2]
    documented = set(re.findall(r"^### (\w+)$", objects, re.MULTILINE))
    reached = set(defs) - {t.__name__ for t in (*COMMAND_TYPES, *MESSAGE_TYPES)} - {"TopicValues"}
    assert reached == documented, f"PROTOCOL.md lists {sorted(documented ^ reached)} wrong: {HINT}"
    for topic in TOPIC_NAMES:
        assert f"| `{topic}` |" in doc


# ---- the examples ---------------------------------------------------------------------------------------------------------------------------------

NOW = "2026-10-21T12:00:00Z"
POSITION = {"lat": 60.165, "lon": 24.9467, "symbol_table": "T", "symbol_code": "&", "comment": "432.500 MHz", "course_deg": None, "speed_kmh": None, "altitude_m": None, "timestamp": None,
            "messaging": False, "compressed": False, "ambiguity": 0, "weather": None, "extensions": None, "timestamp_local": False, "locator": None,
            "frequency": None, "storm": None, "sign": None}
EXTENSIONS: dict[str, Any] = {"phg": {"power_w": 25, "height_m": 6.1, "gain_db": 3, "direction_deg": 90, "range_km": 12.8}, "range_km": 80.5, "dfs": {"strength": 2, "height_m": 24.4, "gain_db": 6, "direction_deg": None},
                              "df_bearing": {"bearing_deg": 270, "hits": 7, "range_km": 6.4, "quality": 9}, "area": {"shape": "filled ellipse", "colour": "cyan", "lat_offset_deg": 1.0, "lon_offset_deg": 1.0}}
FREQUENCY: dict[str, Any] = {"mhz": 145.775, "tone_hz": 118, "tone_both": False, "tone_off": False, "dcs": None, "tone_burst": False, "narrow": False, "offset_khz": -600, "range_km": 40.2, "rx_mhz": None}
STORM: dict[str, Any] = {"storm_type": "HC", "wind_kmh": 277.8, "gust_kmh": 370.4, "pressure_hpa": 980, "hurricane_radius_km": 166.7, "storm_radius_km": 55.6, "gale_radius_km": 74.1}
LOCATOR: dict[str, Any] = {"grid": "IO91sx", "lat": 51.97917, "lon": -0.45833, "symbol_table": "/", "symbol_code": "-"}
TELEMETRY: dict[str, Any] = {"sequence": 5, "channels": [{"name": "Battery", "unit": "v/100", "raw": 199.0, "value": 1034.8}, {"name": "A2", "unit": "", "raw": 0.0, "value": 0.0}], "project": "Balloon", "comment": "",
                             "bits": [{"name": "Camra", "on": False}, {"name": "B2", "on": True}]}
WEATHER_FIELDS: dict[str, Any] = {"wind_dir": 107, "wind_kmh": 1.6, "gust_kmh": 1.6, "temp_c": 10.0, "humidity": 85, "pressure_hpa": 1028.4, "rain_1h_mm": 0.3, "rain_24h_mm": 4.1, "rain_today_mm": 3.3,
                                  "luminosity": None, "snow_mm": None}
STATION: dict[str, Any] = {
    "call": "OH2RDK-7", "kind": "station", "reported_by": "", "symbol_table": "T", "symbol_code": "&", "symbol_name": "unknown", "lat": 60.165, "lon": 24.9467, "altitude_m": None, "course_deg": None,
    "speed_kmh": None, "first_heard": NOW, "last_heard": NOW, "last_position_at": NOW, "last_status": "", "last_comment": "432.500 MHz", "packets": 1, "heard_rf": 1, "heard_rf_gated": 1, "heard_is": 2, "heard_dummy": 1, "last_dummy_at": NOW, "last_rf_at": NOW, "last_rf_gated_at": NOW, "last_is_at": NOW, "position_via": "is", "packets_hour": 1, "device": "Kenwood TH-D74", "last_path": ["OH2RCH-2*", "TRACE2-1"],
    "last_route": "via OH2RCH-2", "heard_direct": 2, "last_direct_at": NOW, "gated": 4, "igate": True, "heard_via": [["OH2RCH-2", 30], ["OH2RCH-3", 4]], "best_route": "via OH2RCH-2", "suggested_path": "OH2RCH-2", "heard_path": "OH2RCH-2", "internet_reach": {"kind": "igate", "igate": "OH2GW-10", "hops": ["OH2RCH-2"]},
    "route_marks": [{"kind": "rf", "hops": ["OH2RCH-2"], "gate": "", "at": NOW, "lat": 60.165, "lon": 24.9467}],
    "distance_km": 1.5, "bearing_deg": 90.0, "is_me": False, "can_message": True, "own": False, "weather": WEATHER_FIELDS, "weather_at": NOW, "telemetry": TELEMETRY, "telemetry_at": NOW, "locator": LOCATOR, "extensions": EXTENSIONS, "frequency": FREQUENCY, "storm": STORM, "sign": None, "track": [[NOW, 60.165, 24.9467]]}
BULLETIN_ROW: dict[str, Any] = {"sender": "OH2XYZ", "slot": "BLN3HAMS", "group": "HAMS", "kind": "group", "text": "Net tonight at 20:00", "first_heard": NOW, "last_heard": "2026-10-21T13:00:00Z", "times_heard": 3}
OWN_OBJECT_ROW: dict[str, Any] = {"name": "LEADER", "kind": "object", "lat": 60.165, "lon": 24.9467, "symbol_table": "/", "symbol_code": ">", "comment": "Rescue 1", "course_deg": 88, "speed_kmh": 66.7,
                                  "path": None, "qru_group": "", "on_request": False, "state": "live", "created_at": NOW, "updated_at": NOW, "sent": 2, "last_sent_at": NOW, "next_at": "2026-10-21T12:03:00Z"}
OWN_BULLETIN_ROW: dict[str, Any] = {"slot": "BLN3HAMS", "group": "HAMS", "kind": "group", "text": "Net tonight at 20:00", "posted_at": NOW, "sent": 1, "last_sent_at": NOW, "next_at": "2026-10-21T12:02:00Z"}
MESSAGE_ROW: dict[str, Any] = {"id": 3, "at": NOW, "direction": "out", "from_call": "OH2GBA", "to_call": "OH2RDG", "text": "hello", "msg_id": "12", "state": "sending", "attempts": 1,
                               "attempts_max": 6, "last_attempt_at": NOW, "acked_at": None, "route": "",
                               "attempts_detail": [{"sent_at": NOW, "hops": [{"call": "OH2RCH-2", "heard": True, "heard_at": NOW, "by_internet": False}, {"call": "OH2RDG", "heard": False, "heard_at": None, "by_internet": False}],
                                                    "internet": None, "acked": False}]}
PACKET: dict[str, Any] = {"id": 7, "heard_at": NOW, "direction": "in", "source": "OH2RDK-7", "destination": "APRX29", "path": ["OH2RCH-2*"], "route": "via OH2RCH-2", "via": "rf", "gate": "", "kind": "position", "summary": "position 60.1650 24.9467 T&",
                          "tnc2": "OH2RDK-7>APRX29,OH2RCH-2*:!6009.90NT02456.80E&432.500 MHz", "decoded": {"type": "position", **POSITION}}
TNC: dict[str, Any] = {"state": "connected", "problem": "", "last_error": "", "path": "/dev/brainbox_3", "baud": 9600, "dummy": False, "describe": "/dev/brainbox_3 at 9600, KISS, 4 packets", "searching": [], "silent_since": None,
                       "stats": {"opens": 1, "bytes_in": 400, "bytes_out": 18, "frames_in": 4, "packets": 4, "rejected": 0, "last_packet": NOW, "keepalive_checks": 2, "watchdog_probes": 0, "port_reopens": 1, "digipeated": 0, "digipeated_at": None, "digipeat_held": 0},
                       "last_watchdog_action": "check", "last_watchdog_at": NOW, "lines": [{"at": NOW, "text": "NeoAPRS: opened /dev/brainbox_3"}]}
CONFIG: dict[str, Any] = {"values": {"station/call": "OH2GBA"}, "defaults": {"station/call": "OH2GBA"}, "urls": [], "https": {"on": False, "port": 0, "fingerprint": "", "problem": ""}}

MESSAGE_EXAMPLES: dict[str, list[dict[str, Any]]] = {
    "hello": [{"type": "hello", "protocol": PROTOCOL, "version": "0.1.0", "page": "index-DefyaO5x.js", "install": {"kind": "uv-tool", "appimage": "", "service": True, "arch": ""}, "topics": list(TOPIC_NAMES)},
              {"type": "hello", "protocol": PROTOCOL, "version": "0.1.0", "page": "index-DefyaO5x.js", "install": {"kind": "appimage", "appimage": "/home/u/NeoAPRS-0.1.0-x86_64.AppImage", "service": False, "arch": ""}, "topics": []},
              {"type": "hello", "protocol": PROTOCOL, "version": "0.1.0", "page": "", "install": {"kind": "deb", "appimage": "", "service": True, "arch": "arm64"}, "topics": []}],
    "status": [{"type": "status", "version": "0.1.0", "started_at": NOW, "packets": 12, "stations": 5, "call": "OH2GBA", "lat": 60.17, "lon": 24.94,
                "beacon_interval_min": 30, "beacon_last_sent": NOW, "beacon_next_due": "2026-10-21T12:30:00Z",
                "station_status": "QRV 14.074 MHz USB", "station_status_last_sent": NOW, "rig_state": "on",
                "cpu_percent": 0.3, "rss_mb": 42.4, "uptime_sec": 10800,
                "update": {"version": "0.2.0", "url": "https://oh2gba.github.io/neoaprs/", "message": "Fixes the map download"}},
               {"type": "status", "version": "0.1.0", "started_at": NOW, "packets": 0, "stations": 1, "call": "OH2GBA", "lat": 60.17, "lon": 24.94,
                "beacon_interval_min": 0, "beacon_last_sent": None, "beacon_next_due": None,
                "station_status": "", "station_status_last_sent": None, "rig_state": "unused",
                "cpu_percent": 0.0, "rss_mb": 31.0, "uptime_sec": 0, "update": None}],
    "pong": [{"type": "pong", "now": NOW}],
    "ports": [{"type": "ports", "search": False, "find": True, "ports": [{"device": "COM3", "description": "USB Serial Port (COM3)", "hwid": "USB VID:PID=0403:6001 SER=A1", "vid": 1027, "pid": 24577},
                                                           {"device": "COM4", "description": "Standard Serial over Bluetooth link (COM4)", "hwid": "BTHENUM\\{00001101}", "vid": None, "pid": None}]},
              {"type": "ports", "search": True, "find": True, "ports": []}],
    "weather_series": [{"type": "weather_series", "call": "OH2MUI", "hours": 24, "points": [[NOW, 10.0, 1028.4, 1.6, 1.6, 0.3, 85], ["2026-10-21T12:10:00Z", 10.5, None, None, None, None, None]]},
                       {"type": "weather_series", "call": "OH2NONE", "hours": 168, "points": []}],
    "packet_history": [{"type": "packet_history", "hours": 3, "start": "2026-10-21T10:00:00Z", "counts": [41, 37, 12]}],
    "update_result": [{"type": "update_result", "outcome": "newer", "version": "0.4.0", "text": ""}, {"type": "update_result", "outcome": "current", "version": "0.3.0", "text": ""},
                      {"type": "update_result", "outcome": "no_answer", "version": "", "text": "the version page could not be reached"}],
    "release_notes": [{"type": "release_notes", "version": "0.4.0", "sections": [{"version": "0.4.0", "text": "- **Fixed:** the map download."}, {"version": "0.3.1", "text": "A small release."}], "problem": ""},
                      {"type": "release_notes", "version": "0.4.0", "sections": [], "problem": "the release notes could not be fetched"}],
    "radio_search": [{"type": "radio_search", "state": "trying", "port": "/dev/ttyUSB0", "baud": 9600, "profile": "", "number": 1, "total": 14},
                     {"type": "radio_search", "state": "found", "port": "bt://AA:BB:CC:DD:EE:FF", "baud": None, "profile": "kiss", "number": 0, "total": 0},
                     {"type": "radio_search", "state": "cancelled", "port": "", "baud": None, "profile": "", "number": 0, "total": 0}],
    "alert_result": [{"type": "alert_result", "ok": True, "text": "ran"}, {"type": "alert_result", "ok": False, "text": "exit code 3: no display"}],
    "station_alert": [{"type": "station_alert", "call": "OH2XYZ", "kind": "on_air", "text": "OH2XYZ is on the air", "at": NOW, "km": None},
                      {"type": "station_alert", "call": "OH2XYZ", "kind": "within", "text": "OH2XYZ is 8.2 km from you", "at": NOW, "km": 8.2}],
    "error": [{"type": "error", "cmd": "set_config", "key": "station/lat", "code": "setting.range", "params": {"value": 95.0, "min": -90.0, "max": 90.0}, "text": "set_config: station/lat: 95 is not between -90 and 90"},
              {"type": "error", "cmd": "", "key": None, "code": "not_json", "params": {}, "text": "That is not JSON (Expecting value)"}],
    "state": [{"type": "state", "topic": "stations", "rev": 0, "value": {"OH2RDK-7": STATION}}, {"type": "state", "topic": "packets", "rev": 3, "value": {"7": PACKET}},
              {"type": "state", "topic": "tnc", "rev": 1, "value": TNC}, {"type": "state", "topic": "config", "rev": 0, "value": CONFIG},
              {"type": "state", "topic": "update", "rev": 4, "value": {"supported": True, "state": "downloading", "version": "0.7.0", "percent": 42, "downloaded": 63_000_000, "total": 150_000_000, "problem": "", "detail": ""}},
              {"type": "state", "topic": "messages", "rev": 2, "value": {"3": MESSAGE_ROW}}, {"type": "state", "topic": "bulletins", "rev": 1, "value": {"OH2XYZ/BLN3HAMS": BULLETIN_ROW}},
              {"type": "state", "topic": "own_objects", "rev": 1, "value": {"LEADER": OWN_OBJECT_ROW}}, {"type": "state", "topic": "own_bulletins", "rev": 1, "value": {"BLN3HAMS": OWN_BULLETIN_ROW}},
              {"type": "state", "topic": "station_prefs", "rev": 1,
               "value": {"OH2RDG": {"path": "WIDE2-1", "rf_only": False, "alert": None}, "OH2XYZ": {"path": "", "rf_only": True, "alert": None},
                         "OH2ABC": {"path": None, "rf_only": False, "alert": {"on_air": True, "within_km": 10, "direct": False}}, "EMAIL-2": {"path": None, "rf_only": False, "alert": None}}}],
    "patch": [{"type": "patch", "topic": "stations", "rev": 4, "ops": [{"op": "set", "key": "OH2RDK-7", "value": STATION}, {"op": "del", "key": "OH2RDG"}]},
              {"type": "patch", "topic": "packets", "rev": 5, "ops": [{"op": "set", "key": "8", "value": PACKET}, {"op": "del", "key": "1"}]},
              {"type": "patch", "topic": "tnc", "rev": 2, "ops": [{"op": "replace", "value": TNC}]}, {"type": "patch", "topic": "config", "rev": 1, "ops": [{"op": "replace", "value": CONFIG}]},
              {"type": "patch", "topic": "messages", "rev": 3, "ops": [{"op": "set", "key": "3", "value": {**MESSAGE_ROW, "state": "acked", "acked_at": NOW}}, {"op": "del", "key": "1"}]},
              {"type": "patch", "topic": "bulletins", "rev": 2, "ops": [{"op": "set", "key": "OH2XYZ/BLN3HAMS", "value": {**BULLETIN_ROW, "times_heard": 4}}, {"op": "del", "key": "OH2ABC/BLN1"}]},
              {"type": "patch", "topic": "own_objects", "rev": 2, "ops": [{"op": "set", "key": "LEADER", "value": {**OWN_OBJECT_ROW, "state": "killing", "sent": 0}}, {"op": "del", "key": "MARK"}]},
              {"type": "patch", "topic": "own_bulletins", "rev": 2, "ops": [{"op": "set", "key": "BLN3HAMS", "value": {**OWN_BULLETIN_ROW, "sent": 2, "next_at": None}}, {"op": "del", "key": "BLN1"}]},
              {"type": "patch", "topic": "station_prefs", "rev": 2, "ops": [{"op": "set", "key": "OH2RDG", "value": {"path": "OH2RCH-2,WIDE2-1", "rf_only": False, "alert": None}},
                                                                        {"op": "set", "key": "OH2XYZ", "value": {"path": "", "rf_only": True, "alert": {"on_air": False, "within_km": None, "direct": True}}}, {"op": "del", "key": "OH2ABC"}]}],
}
DECODED = [
    {"type": "position", **POSITION},
    {"type": "message", "addressee": "OH2GBA", "text": "hello", "msg_id": "12", "ack_id": None, "rej_id": None},
    {"type": "object", "name": "STORM", "alive": True, "position": POSITION, "timestamp": "2026-10-21T12:00:00.000000Z"},
    {"type": "item", "name": "MARK", "alive": False, "position": POSITION},
    {"type": "status", "text": "on the air", "timestamp": None, "locator": None, "frequency": None},
    {"type": "status", "text": "my house", "timestamp": None, "locator": LOCATOR, "frequency": None},
    {"type": "status", "text": "Rescue net", "timestamp": None, "locator": None, "frequency": FREQUENCY},
    {"type": "telemetry", "sequence": 5, "analog": [199.0, 0.0, 255.0, 73.0, 123.0], "bits": "01101001", "comment": ""},
    {"type": "other", "kind": "weather", "text": "_10090000c000s000g000t050", "weather": {**WEATHER_FIELDS, "rain_counter": None, "raw": "c000s000g000t050"}, "items": None, "timestamp": "2026-10-09T00:00:00.000000Z"},
    {"type": "other", "kind": "telemetry", "text": "T#005", "weather": None, "items": None, "timestamp": None},
    {"type": "other", "kind": "capabilities", "text": "<IGATE,MSG_CNT=2", "weather": None, "items": {"IGATE": "", "MSG_CNT": "2"}, "timestamp": None},
    {"type": "position", **POSITION, "weather": {**WEATHER_FIELDS, "rain_counter": 12, "raw": "107/001g001t050"}},
    {"type": "position", **POSITION, "extensions": EXTENSIONS, "timestamp": "2026-10-21T12:00:00.000000Z", "timestamp_local": True, "locator": LOCATOR},
    {"type": "position", **POSITION, "frequency": FREQUENCY, "storm": STORM, "sign": "55"},
    {"type": "undecoded", "error": "too short", "text": "!60"},
]

COMMAND_EXAMPLES: dict[str, dict[str, Any]] = {
    "ping": {"cmd": "ping"}, "status": {"cmd": "status"}, "subscribe": {"cmd": "subscribe", "topics": ["packets", "tnc"]}, "unsubscribe": {"cmd": "unsubscribe", "topics": ["packets"]},
    "forget_station": {"cmd": "forget_station", "call": "OH2RDG"}, "forget_all_stations": {"cmd": "forget_all_stations"}, "list_ports": {"cmd": "list_ports"}, "find_radio": {"cmd": "find_radio"}, "find_radio_cancel": {"cmd": "find_radio_cancel"}, "set_config": {"cmd": "set_config", "values": {"station/lat": "61.5"}},
    "beacon_now": {"cmd": "beacon_now"}, "status_now": {"cmd": "status_now"}, "send_message": {"cmd": "send_message", "to": "OH2RDG", "text": "hello"}, "query": {"cmd": "query", "call": "OH2RDG", "kind": "status"}, "qru_ask": {"cmd": "qru_ask", "text": "RP70 150"}, "message_retry": {"cmd": "message_retry", "id": 3},
    "message_cancel": {"cmd": "message_cancel", "id": 3}, "message_delete": {"cmd": "message_delete", "id": 3}, "conversation_delete": {"cmd": "conversation_delete", "call": "OH2RDG"},
    "overheard_delete": {"cmd": "overheard_delete", "from_call": "OH2AAA", "to_call": "OH2BBB"},
    "set_station_path": {"cmd": "set_station_path", "call": "OH2RDG", "path": "OH2RCH-2,WIDE2-1"},
    "clear_station_path": {"cmd": "clear_station_path", "call": "OH2RDG"},
    "set_station_rf_only": {"cmd": "set_station_rf_only", "call": "OH2RDG", "on": True},
    "set_station_alert": {"cmd": "set_station_alert", "call": "OH2RDG", "on_air": True, "within_km": 10, "direct": False},
    "weather_series": {"cmd": "weather_series", "call": "OH2MUI", "hours": 24}, "packet_history": {"cmd": "packet_history", "hours": 24}, "alert_test": {"cmd": "alert_test"}, "update_check": {"cmd": "update_check"}, "release_notes": {"cmd": "release_notes", "version": "0.4.0"},
    "bulletin_delete": {"cmd": "bulletin_delete", "sender": "OH2XYZ", "slot": "BLN3HAMS"},
    "object_set": {"cmd": "object_set", "name": "LEADER", "kind": "object", "lat": 60, "lon": 25, "symbol_table": "/", "symbol_code": ">", "comment": "Rescue 1", "course_deg": 88, "speed_kmh": 67, "path": "WIDE1-1", "qru_group": "RP70", "on_request": True},
    "object_kill": {"cmd": "object_kill", "name": "LEADER"},
    "bulletin_post": {"cmd": "bulletin_post", "slot": "BLN3HAMS", "text": "Net tonight at 20:00"}, "bulletin_unpost": {"cmd": "bulletin_unpost", "slot": "BLN3HAMS"},
    "map_estimate": {"cmd": "map_estimate"}, "map_fetch": {"cmd": "map_fetch"}, "map_wanted": {"cmd": "map_wanted"}, "map_cancel": {"cmd": "map_cancel"},
    "update_now": {"cmd": "update_now", "version": "0.7.0"}, "update_cancel": {"cmd": "update_cancel"},
    "page_error": {"cmd": "page_error", "message": "x is undefined", "stack": "at render (Map.vue:10:5)", "source": "vue", "at": "2026-10-21T12:00:00Z", "build": "index-abc123.js"},
}


def test_every_message_type_has_examples_that_validate_and_every_example_is_of_a_type() -> None:
    assert set(MESSAGE_EXAMPLES) == MESSAGE_NAMES, "a new message needs an example here"
    for kind, examples in MESSAGE_EXAMPLES.items():
        for example in examples:
            message = MESSAGES.validate_json(json.dumps(example))
            assert message.type == kind
            assert json.loads(message.model_dump_json()) == example, "what is read is what was written"


def test_the_values_of_the_examples_are_of_the_type_of_their_topic() -> None:
    for message in MESSAGE_EXAMPLES["state"]:
        TOPIC_VALUES[message["topic"]].validate_json(json.dumps(message["value"]))
    for message in MESSAGE_EXAMPLES["patch"]:
        for op in message["ops"]:
            if op["op"] == "replace":
                TOPIC_VALUES[message["topic"]].validate_json(json.dumps(op["value"]))
            elif op["op"] == "set":
                TOPIC_ITEMS[message["topic"]].validate_json(json.dumps(op["value"]))
    assert set(TOPIC_VALUES) == set(TOPIC_NAMES) and set(TOPIC_ITEMS) == {"stations", "packets", "messages", "bulletins", "station_prefs", "own_objects", "own_bulletins"}


def test_every_kind_of_decoded_packet_has_a_model_and_the_kinds_are_the_parsers() -> None:
    assert sorted({d["type"] for d in DECODED} - {"telemetry"}, key=list(KINDS).index) == list(KINDS)             # (a telemetry report is a packet of kind "other" with a type of its own)
    for decoded in DECODED:
        row = PacketRow.model_validate_json(json.dumps({**PACKET, "kind": "other" if decoded["type"] == "telemetry" else decoded["type"], "decoded": decoded}))
        assert row.decoded.type == decoded["type"]
    with pytest.raises(ValidationError):
        PacketRow.model_validate_json(json.dumps({**PACKET, "decoded": {"type": "weather"}}))


@pytest.mark.parametrize("kind", sorted(MESSAGE_EXAMPLES))
def test_a_message_with_an_extra_field_or_a_missing_one_or_a_wrong_type_is_refused(kind: str) -> None:
    example = MESSAGE_EXAMPLES[kind][0]
    broken = [{**example, "surprise": 1}, {k: v for k, v in example.items() if k != "type"}, {**example, "type": "nonsense"}]
    for field in example:
        if field != "type":
            broken += [{k: v for k, v in example.items() if k != field}] + ([] if field == "value" else [{**example, field: {"a": [object]}}])      # (the value of a state is any: the topic's type checks it)
    for message in broken:
        with pytest.raises((ValidationError, TypeError)):
            MESSAGES.validate_json(json.dumps(message, default=str))


def test_the_models_are_strict() -> None:
    for text in ('{"type": "pong", "now": 5}', '{"type": "status", "version": "1", "started_at": "2026-10-21T12:00:00Z", "packets": "5", "stations": 1, "call": "A", "lat": 0, "lon": 0}',
                 '{"type": "status", "version": "1", "started_at": "2026-10-21T12:00:00Z", "packets": 5, "stations": 1, "call": "A", "lat": NaN, "lon": 0}'):
        with pytest.raises(ValidationError):
            MESSAGES.validate_json(text)
    bad_station = {**STATION, "lat": "60.1"}
    with pytest.raises(ValidationError):
        StationRow.model_validate_json(json.dumps(bad_station))
    with pytest.raises(ValidationError):
        StationRow.model_validate_json(json.dumps({**STATION, "track": [[NOW, 60.1]]}))
    with pytest.raises(ValidationError):
        TncState.model_validate_json(json.dumps({**TNC, "state": "asleep"}))
    with pytest.raises(ValidationError):
        TncState.model_validate_json(json.dumps({**TNC, "lines": [{"at": NOW, "text": "x"}] * 101}))
    assert StationRow.model_validate_json(json.dumps({**STATION, "lat": None, "lon": None})).lat is None


def test_a_message_row_may_be_unconfirmed_and_a_station_pref_has_no_attempts_and_no_timeout() -> None:
    assert MessageRow.model_validate_json(json.dumps({**MESSAGE_ROW, "state": "unconfirmed", "attempts": 2, "attempts_max": 2})).state == "unconfirmed"
    with pytest.raises(ValidationError):
        MessageRow.model_validate_json(json.dumps({**MESSAGE_ROW, "state": "unknown"}))
    pref = {"path": None, "rf_only": False, "alert": None}
    assert not hasattr(StationPref.model_validate_json(json.dumps(pref)), "attempts")
    for extra in ({"attempts": 2}, {"hide_after_min": 90}):
        with pytest.raises(ValidationError):
            StationPref.model_validate_json(json.dumps({**pref, **extra}))
    with pytest.raises(ValidationError):
        StationPref.model_validate_json(json.dumps({"path": None}))
    for km in (0, 1001, 2.5):
        with pytest.raises(ValidationError):
            StationPref.model_validate_json(json.dumps({**pref, "alert": {"on_air": False, "within_km": km, "direct": False}}))


# ---- the commands ---------------------------------------------------------------------------------------------------------------------------------

def test_every_command_has_an_example_that_round_trips() -> None:
    assert set(COMMAND_EXAMPLES) == COMMAND_NAMES, "a new command needs an example here"
    for name, example in COMMAND_EXAMPLES.items():
        command = COMMANDS.validate_python(example)
        assert command.cmd == name and command.model_dump(mode="json") == example
        again = COMMANDS.validate_json(command.model_dump_json())
        assert again == command


@pytest.mark.parametrize("name", sorted(COMMAND_EXAMPLES))
def test_a_command_with_an_extra_field_or_a_missing_one_or_a_wrong_type_is_refused(name: str) -> None:
    example = COMMAND_EXAMPLES[name]
    broken = [{**example, "surprise": 1}, {k: v for k, v in example.items() if k != "cmd"}, {**example, "cmd": "nonsense"}]
    for field in example:
        if field != "cmd":
            broken += [{k: v for k, v in example.items() if k != field}, {**example, field: "7" if isinstance(example[field], int) else 7}]       # (a wrong type: text for a number, a number for the rest)
    for command in broken:
        with pytest.raises(ValidationError):
            COMMANDS.validate_python(command)


def test_the_limits_of_the_commands() -> None:
    with pytest.raises(ValidationError):
        COMMANDS.validate_python({"cmd": "subscribe", "topics": ["x"] * 17})
    with pytest.raises(ValidationError):
        COMMANDS.validate_python({"cmd": "forget_station", "call": ""})
    with pytest.raises(ValidationError):
        COMMANDS.validate_python({"cmd": "set_config", "values": {"a": 1}})
    with pytest.raises(ValidationError):
        COMMANDS.validate_python({"cmd": "set_config", "values": {f"k{n}": "v" for n in range(65)}})
    for bad in ({"cmd": "send_message", "to": "", "text": "x"}, {"cmd": "send_message", "to": "X" * 65, "text": "x"}, {"cmd": "send_message", "to": "OH2RDG", "text": "x" * 513},
                {"cmd": "query", "call": "", "kind": "status"}, {"cmd": "query", "call": "OH2RDG", "kind": "all"}, {"cmd": "query", "call": "OH2RDG"}, {"cmd": "message_retry", "id": 0}, {"cmd": "message_cancel", "id": -1}, {"cmd": "message_delete", "id": 0}, {"cmd": "conversation_delete", "call": ""}, {"cmd": "set_station_path", "call": "", "path": ""}, {"cmd": "set_station_path", "call": "X", "path": "W" * 257},
                {"cmd": "set_station_path", "call": "OH2RDG", "path": None}, {"cmd": "clear_station_path", "call": ""}, {"cmd": "set_station_timeout", "call": "OH2RDG", "minutes": 5}, {"cmd": "clear_station_timeout", "call": "OH2RDG"},
                {"cmd": "set_station_attempts", "call": "EMAIL-2", "attempts": 2}, {"cmd": "clear_station_attempts", "call": "EMAIL-2"}, {"cmd": "set_station_rf_only", "call": "", "on": True}, {"cmd": "set_station_rf_only", "call": "OH2RDG"}, {"cmd": "set_station_rf_only", "call": "OH2RDG", "on": "yes"},
                {"cmd": "set_station_alert", "call": "OH2RDG", "on_air": True, "within_km": 0, "direct": False}, {"cmd": "set_station_alert", "call": "OH2RDG", "on_air": True, "within_km": 1001, "direct": False}, {"cmd": "set_station_alert", "call": "", "on_air": True, "within_km": None, "direct": False},
                {"cmd": "overheard_delete", "from_call": "", "to_call": "OH2BBB"}, {"cmd": "overheard_delete", "from_call": "OH2AAA", "to_call": ""},
                {"cmd": "overheard_delete", "from_call": "OH2AAA"}):
        with pytest.raises(ValidationError):
            COMMANDS.validate_python(bad)
    assert COMMANDS.validate_python({"cmd": "send_message", "to": "OH2RDG", "text": ""}).text == "", "an empty text is the daemon's to refuse, with a reason"


def test_every_command_has_exactly_one_handler_and_every_handler_a_command() -> None:
    assert set(dispatch.REGISTRY) == COMMAND_NAMES
    assert {h.model for h in dispatch.REGISTRY.values()} == set(COMMAND_TYPES)


def test_a_command_with_two_handlers_is_refused() -> None:
    registry: dict[str, dispatch.Handler] = {}

    async def one(ctx: dispatch.Ctx, cmd: Any) -> None: ...

    dispatch.command(COMMAND_TYPES[0], into=registry)(one)
    with pytest.raises(ValueError, match="two handlers"):
        dispatch.command(COMMAND_TYPES[0], into=registry)(one)
