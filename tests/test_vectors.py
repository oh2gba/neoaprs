"""The conformance vectors (ui/src/protocol/vectors.json): the rules that are code and not numbers, as inputs with the results the daemon gives. The page asserts the same file (ui/src/protocol/vectors.test.ts),
so a rule that one side changes alone fails a test on one side. Here: the file is what the daemon gives today, and it says what the rules are."""
import json
from typing import Any

from tests.test_protocol import ROOT, generator


def vectors() -> dict[str, list[dict[str, Any]]]:
    loaded: dict[str, list[dict[str, Any]]] = json.loads((ROOT / "ui" / "src" / "protocol" / "vectors.json").read_text(encoding="utf-8"))
    return loaded


def test_the_vectors_are_what_the_daemon_gives_today() -> None:
    gen = generator()
    assert gen.VECTORS.read_text(encoding="utf-8") == gen.vectors_text(), "run .venv/bin/python scripts/gen-protocol.py and commit the result"


def test_a_call_is_one_the_station_may_transmit_under() -> None:
    ok = {v["input"]: v["ok"] for v in vectors()["calls"]}
    assert ok["OH2GBA"] and ok[" oh2gba "] and ok["OH2GBA-15"] and ok["OH2GBA-07"] and ok["W1AW"] and ok["A1B"]
    assert not any(ok[c] for c in ("", "OH2GBA-16", "N0CALL", "n0call-5", "NOCALL", "MYCALL", "AB", "123", "ABC", "OH2GBAA", "ß1A"))
    assert {v["input"]: v["call"] for v in vectors()["calls"]}["OH2GBA-0"] == "OH2GBA", "the SSID 0 is not written"


def test_a_call_that_parses_is_not_the_same_as_a_call_that_may_transmit() -> None:
    parses = {v["input"]: v["ok"] for v in vectors()["parse_calls"]}
    assert parses["N0CALL"] and parses["WIDE1-1"] and parses["OH2GBA-00"] and parses["AB"] and parses["EMAIL-2"]
    assert not parses["OH2GBA-16"] and not parses["OH2GBA-007"] and not parses[""] and not parses["ß1A"] and not parses["OH2GBA/P"]


def test_the_rules_of_a_path_a_message_a_bulletin_and_an_object_are_pinned() -> None:
    v = vectors()
    paths = {c["input"]: c["ok"] for c in v["paths"]}
    assert paths["A,B,C,D,E,F,G,H"] and not paths["A,B,C,D,E,F,G,H,I"]
    messages = {c["input"]: c["ok"] for c in v["message_texts"]}
    assert messages["x" * 67] and not messages["x" * 68]
    texts = {c["input"]: c["ok"] for c in v["bulletin_texts"]}
    assert texts["Snow expected"] and not texts["with | bar"] and not texts["with { brace"] and not texts["åäö"]
    slots = {(c["kind"], c["id"], c["group"]): c["slot"] for c in v["bulletin_slots"]}
    assert slots[("bulletin", "1", "")] == "BLN1" and slots[("announcement", "A", "")] == "BLNA" and slots[("group", "0", "HAMS")] == "BLN0HAMS"
    assert slots[("bulletin", "A", "")] is None and slots[("group", "A", "HAMS")] is None and slots[("group", "0", "HAMS12")] is None
    names = {(c["kind"], c["name"]): c["ok"] for c in v["object_names"]}
    assert names[("object", "A")] and names[("item", "ABC")] and not names[("item", "AB")] and not names[("object", "has_under")] and not names[("object", "TENCHARS12")]
    groups = {c["group"]: (c["ok"], c["kept"]) for c in v["qru_groups"]}
    assert groups[""] == groups["  "] == (True, "") and groups[" rp70 "] == (True, "RP70") and groups["LIFEBOAT"][0] and not groups["LIFEBOATS"][0] and not groups["INFO"][0]
    assert not groups["NEXT"][0] and not groups["R P"][0] and not groups["RP-70"][0] and not groups["ÅÄ"][0] and not groups["info"][0]


def test_the_beacon_the_settings_make_is_null_where_the_daemon_would_send_none() -> None:
    beacons = vectors()["beacons"]
    texts = [b["text"] for b in beacons]
    assert texts[0] == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=6010.20N/02456.40E-NeoAPRS" and "PHG" in (texts[1] or "")
    by_symbol = {(b["values"]["station/symbol_table"], b["values"]["station/symbol_code"]): (b["text"] or "").split(":")[0] for b in beacons if b["values"]["beacon/path"] == ""}
    assert by_symbol[("/", "-")] == by_symbol[("/", "_")] == by_symbol[("\\", "#")] == "OH2GBA>APZNEO,WIDE2-1", "a house, a weather station, a digipeater: fixed"
    assert by_symbol[("/", ">")] == by_symbol[("\\", "s")] == by_symbol[("E", ">")] == by_symbol[("/", "b")] == by_symbol[("2", "k")] == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1", "a car, a boat, a bike, a truck: moving"
    assert any(b["values"]["station/call"] == "" and b["text"] is None for b in beacons)
    assert any(b["values"]["station/lat"] == "" and b["text"] is None for b in beacons)
    assert any(b["values"]["beacon/path"] == "BAD CALL" and b["text"] is None for b in beacons)


def test_every_category_has_cases_and_the_phg_and_the_positions_are_the_daemons_figures() -> None:
    v = vectors()
    assert all(v[name] for name in v)
    assert {"calls", "parse_calls", "paths", "message_texts", "bulletin_texts", "bulletin_slots", "object_names", "object_comments", "qru_groups", "settings", "phg", "positions", "beacons"} <= v.keys()
    assert {(c["power"], c["height"], c["gain"], c["direction"]): c["text"] for c in v["phg"]}[(5, 10, 3, "NE")] == "PHG2231"
    assert {(c["lat"], c["lon"]): c["text"] for c in v["positions"]}[(60.17, 24.94)] == "6010.20N/02456.40E-"
