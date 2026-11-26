"""The conformance vectors (ui/src/protocol/vectors.json): the rules that are code, as inputs with
the daemon's results. The page asserts the same file, so a rule changed on one side alone fails a
test.
"""

import json
from typing import Any

from tests.test_protocol import ROOT, generator


def vectors() -> dict[str, list[dict[str, Any]]]:
    loaded: dict[str, list[dict[str, Any]]] = json.loads(
        (ROOT / "ui" / "src" / "protocol" / "vectors.json").read_text(encoding="utf-8")
    )
    return loaded


def test_the_vectors_are_what_the_daemon_gives_today() -> None:
    gen = generator()
    assert gen.VECTORS.read_text(encoding="utf-8") == gen.vectors_text(), (
        "run .venv/bin/python scripts/gen-protocol.py and commit the result"
    )


def test_a_call_is_one_the_station_may_transmit_under() -> None:
    ok = {v["input"]: v["ok"] for v in vectors()["calls"]}
    assert ok["OH2GBA"] and ok[" oh2gba "] and ok["OH2GBA-15"] and ok["OH2GBA-07"] and ok["W1AW"] and ok["A1B"]
    assert not any(
        ok[c] for c in ("", "OH2GBA-16", "N0CALL", "n0call-5", "NOCALL", "MYCALL", "AB", "123", "ABC", "OH2GBAA", "ß1A")
    )
    assert {v["input"]: v["call"] for v in vectors()["calls"]}["OH2GBA-0"] == "OH2GBA", "the SSID 0 is not written"


def test_a_call_that_parses_is_not_the_same_as_a_call_that_may_transmit() -> None:
    parses = {v["input"]: v["ok"] for v in vectors()["parse_calls"]}
    assert parses["N0CALL"] and parses["WIDE1-1"] and parses["OH2GBA-00"] and parses["AB"] and parses["EMAIL-2"]
    assert (
        not parses["OH2GBA-16"]
        and not parses["OH2GBA-007"]
        and not parses[""]
        and not parses["ß1A"]
        and not parses["OH2GBA/P"]
    )


def test_the_rules_of_a_path_a_message_a_bulletin_and_an_object_are_pinned() -> None:
    v = vectors()
    paths = {c["input"]: c["ok"] for c in v["paths"]}
    assert paths["A,B,C,D,E,F,G,H"] and not paths["A,B,C,D,E,F,G,H,I"]
    messages = {c["input"]: c["ok"] for c in v["message_texts"]}
    assert messages["x" * 67] and not messages["x" * 68]
    texts = {c["input"]: c["ok"] for c in v["bulletin_texts"]}
    assert texts["Snow expected"] and not texts["with | bar"] and not texts["with { brace"] and not texts["åäö"]
    slots = {(c["kind"], c["group"], ",".join(c["taken"])): c["slot"] for c in v["bulletin_free_slots"]}
    assert (
        slots[("bulletin", "", "")] == "BLN0"
        and slots[("announcement", "", "")] == "BLNA"
        and slots[("group", "HAMS", "")] == "BLN0HAMS"
        and slots[("bulletin", "", "BLN0,BLN2")] == "BLN1"
        and slots[("group", "hams", "BLN0HAMS")] == "BLN1HAMS"
    )
    assert (
        slots[("bulletin", "", ",".join(f"BLN{c}" for c in "0123456789"))] is None
        and slots[("group", "HAMS12", "")] is None
        and slots[("group", "", "")] is None
    )
    names = {(c["kind"], c["name"]): c["ok"] for c in v["object_names"]}
    assert (
        names[("object", "A")]
        and names[("item", "ABC")]
        and not names[("item", "AB")]
        and not names[("object", "has_under")]
        and not names[("object", "TENCHARS12")]
    )
    groups = {c["group"]: (c["ok"], c["kept"]) for c in v["qru_groups"]}
    assert (
        groups[""] == groups["  "] == (True, "")
        and groups[" rp70 "] == (True, "RP70")
        and groups["LIFEBOAT"][0]
        and not groups["LIFEBOATS"][0]
        and not groups["INFO"][0]
    )
    assert (
        not groups["NEXT"][0]
        and not groups["R P"][0]
        and not groups["RP-70"][0]
        and not groups["ÅÄ"][0]
        and not groups["info"][0]
    )


def test_the_beacon_the_settings_make_is_null_where_the_daemon_would_send_none() -> None:
    beacons = vectors()["beacons"]
    texts = [b["text"] for b in beacons]
    assert texts[0] == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=6010.20N/02456.40E-NeoAPRS" and "PHG" in (texts[1] or "")
    by_symbol = {
        (b["values"]["station/symbol_table"], b["values"]["station/symbol_code"]): (b["text"] or "").split(":")[0]
        for b in beacons
        if b["values"]["beacon/path"] == ""
    }
    assert by_symbol[("/", "-")] == by_symbol[("/", "_")] == by_symbol[("\\", "#")] == "OH2GBA>APZNEO,WIDE2-2", (
        "a house, a weather station, a digipeater: fixed"
    )
    assert (
        by_symbol[("/", ">")]
        == by_symbol[("\\", "s")]
        == by_symbol[("E", ">")]
        == by_symbol[("/", "b")]
        == by_symbol[("2", "k")]
        == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1"
    ), "a car, a boat, a bike, a truck: moving"
    assert any(b["values"]["station/call"] == "" and b["text"] is None for b in beacons)
    assert any(b["values"]["station/lat"] == "" and b["text"] is None for b in beacons)
    assert any(b["values"]["beacon/path"] == "BAD CALL" and b["text"] is None for b in beacons)


def test_an_address_for_a_reply_has_one_at_with_words_on_each_side_and_no_blank_in_254_characters() -> None:
    ok = {v["input"]: v["ok"] for v in vectors()["reply_addresses"]}
    assert ok["ham@example.org"] and ok["a@b"] and ok["pää@esimerkki.fi"] and ok["h" * 244 + "@example.o"]
    assert not any(
        ok[t] for t in ("", "@example.org", "ham@", "ham@example@org", "ham @example.org", "h" * 245 + "@example.o")
    )


def test_the_rules_of_a_sked_are_the_servers_and_the_stricter_note_is_the_rule() -> None:
    v = vectors()
    calls = {c["input"]: c["call"] for c in v["sked_calls"]}
    assert calls[" oh2gba "] == calls["OH2GBA-0"] == "OH2GBA" and calls["OH2GBA-15"] == "OH2GBA-15"
    assert not any(calls[c] for c in ("OH2GBA-16", "OH2GBA-07", "N0CALL", "\u00a0OH2GBA", "OH2GBA/P", ""))
    assert {c["input"]: c["ok"] for c in v["sked_dials"]}["7.0541 MHz LSB"]
    assert not any(c["ok"] for c in v["sked_dials"] if c["input"] != c["input"].strip() or "." not in c["input"])
    times = {c["input"]: c["ok"] for c in v["sked_times"]}
    assert times["2028-02-29T12:00:00Z"] and not times["2026-02-29T12:00:00Z"] and not times["2026-11-14T24:00:00Z"]
    notes = {c["input"]: (c["note"], c["plain"]) for c in v["sked_notes"]}
    assert notes["Mercury, 10 W"] == ("Mercury, 10 W", True)
    assert notes["5\u00b0 up \u20ac \U0001f642 x"][0] == "5 up x", "a symbol outside printable ASCII is dropped"
    assert notes["caf\u00e9 7 MHz $+^`|~<=>"][1], "the symbols of printable ASCII stay"
    assert notes["x" * 81] == ("x" * 80, False) and notes["x" * 79 + " y"][0] == "x" * 79


def test_every_category_has_cases_and_the_phg_and_the_positions_are_the_daemons_figures() -> None:
    v = vectors()
    assert all(v[name] for name in v)
    assert {
        "calls",
        "parse_calls",
        "paths",
        "message_texts",
        "bulletin_texts",
        "bulletin_free_slots",
        "object_names",
        "object_comments",
        "qru_groups",
        "settings",
        "phg",
        "positions",
        "beacons",
        "reply_addresses",
        "sked_calls",
        "sked_dials",
        "sked_times",
        "sked_notes",
    } <= v.keys()
    assert {(c["power"], c["height"], c["gain"], c["direction"]): c["text"] for c in v["phg"]}[
        (5, 10, 3, "NE")
    ] == "PHG2231"
    assert {(c["lat"], c["lon"]): c["text"] for c in v["positions"]}[(60.17, 24.94)] == "6010.20N/02456.40E-"
