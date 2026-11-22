"""The radio types (neoaprs/radiotype.py, neoaprs/radiotypes/): each type is a TNC profile of its
kind with the kind's limits and rules per field, the fields have defaults, ranges and parsers, and
the page's order per kind.
"""
import re
from dataclasses import replace

import pytest

from neoaprs.config import DEFAULTS, RANGES, Config
from neoaprs.direwolf import PROFILE as DIREWOLF
from neoaprs.radiospec import KIND_WORDS
from neoaprs.radiotype import FM_ID, HF_ID, KINDS, LOCAL_KINDS, Can, Limits, RadioTypeError, radio_id_of, stored_text
from neoaprs.radiotypes import BY_KEY, COMMON_FIELDS, DEFAULT_TYPE, TYPES, kind_field, kind_fields, recommended_path, type_of, types_of, unavailable_types
from neoaprs.radiotypes.common import LISTENS, NOTHING_ALLOWED, TERMINAL_ONLY
from neoaprs.tnc import Tnc
from neoaprs.tncprofile import DEFAULT, DUMMY_HF, EVERY_BY_KEY, HF_DEFAULT, HF_PROFILES, LORA_PROFILES, PROFILES

OLD_KEY = {"port": "serial/port", "baud": "serial/baud", "tcp_host": "tcp/host", "tcp_port": "tcp/port", "sound_card": "mercury/sound_card", "keying": "mercury/keying", "tx_gain_db": "mercury/tx_gain_db",
           # The flat setting of today that each field of a radio is (the beacon is new: on, as both
           # beacons are today)
           "path": "beacon/path", "digipeat": "digi/enabled"}
# A Dummy: nothing to find or tune, and the Terminal of its made-up traffic
DUMMY_CAN = Can(False, True, False, False, False, False, False)


def test_every_type_is_todays_profile_and_the_rules_of_its_kind_field_by_field() -> None:
    profiles = {**EVERY_BY_KEY, DIREWOLF.key: DIREWOLF}
    assert set(BY_KEY) == set(profiles) and len(TYPES) == len(profiles), "one type for each entry of the lists of profiles, and the Sound card type for Direwolf's profile (neoaprs/direwolf.py)"
    for t in TYPES:
        p = profiles[t.key]
        kind = "hf" if p in HF_PROFILES else "lora" if p in LORA_PROFILES else "fm"
        assert (t.kind, t.name, t.transport, t.profile, t.text) == (kind, p.name, p.transport, p.key, f"radio.type.{p.key}"), t.key
        assert type_of(p.key) is t, f"{p.key}: a profile's key is its type's (a Tnc's rtype)"
        assert t.limits == {"hf": Limits(123, 30, 300, 20), "lora": Limits(250, 30, 300, 20, 252, max_kiss=256), "fm": Limits(None, 20, 0, 0)}[kind], t.key
        sends = {"hf": (False, False, False), "lora": (True, False, True), "fm": (True, True, True)}[kind]
        assert (t.allowed.paths, t.allowed.digipeat, t.allowed.smart_beacon) == (sends if t.can.transmit else (False, False, False)), f"{t.key}: a radio that sends nothing is allowed nothing that sends"
        assert (t.allowed.gateway_heard, t.allowed.shared_channel) == ((t.kind != "hf", t.kind == "fm") if t.can.transmit else (False, False)), "internet gateways hear FM and LoRa; the ALOHA circle is FM's 1200 baud alone; neither for a radio that sends nothing"
        assert t.driver == ("direwolf" if p is DIREWOLF else "mercury" if p.transport == "modem" or p is DUMMY_HF else "tnc") and t.dummy == (p.transport == "dummy")


# Each type's English name, as `neoaprs db radios` and the log say it and the page's catalogue has
# it (ui/src/i18n/en/radio.ts), by the kind's list
NAMES = {
    "fm": ["Sound card", "KISS TNC (Kenwood TH-D74/D75, Mobilinkd…)", "Kenwood TM-D710 / TH-D72", "Kenwood TH-D7 / TM-D700 / TS-2000, TNC-2", "Kantronics KPC-3+", "Your own Direwolf or soundmodem",
           "Yaesu FTM, TNC in monitor mode (RX only)", "Dummy FM radio"],
    "hf": ["Mercury modem (sound card)", "Dummy Mercury radio"],
    "lora": ["LoRa APRS board on the network", "LoRa APRS board on USB or Bluetooth", "LoRa APRS iGate on USB (RX only)", "Dummy LoRa radio"],
}


def test_a_types_name_says_what_the_operator_has_in_hand_and_names_a_program_only_where_he_acts_on_it() -> None:
    """A type is named by what the operator holds: a model, a sound card, a LoRa board. A program is
    in a name only where the operator acts on it (Mercury, Direwolf, soundmodem). No name says a
    band, a mode or how the program reaches it; an RX-only type ends with "(RX only)", a Dummy
    starts with "Dummy"."""
    assert {kind: [t.name for t in types_of(kind)] for kind in KINDS} == NAMES
    names = {t.key: t.name for t in TYPES}
    assert [key for key, name in names.items() if "direwolf" in name.casefold() or "dire wolf" in name.casefold()] == ["kiss-tcp"], "the operator's own alone: the Sound card type's is carried and started by NeoAPRS"
    assert sorted(key for key, name in names.items() if "Mercury" in name) == ["dummy-hf", "mercury"], "the modem's name where the other station must run it too"
    assert [name for name in names.values() if re.search(r"\b(HF|VHF|UHF|SSB|TCP)\b", name)] == [], "no band, no mode, no link"
    assert [t.key for t in TYPES if not t.can.transmit] == [t.key for t in TYPES if t.name.endswith("(RX only)")] == ["tnc-text", "lora-console"]
    assert [t.name for t in TYPES if t.dummy] == [f"Dummy {KIND_WORDS[t.kind]} radio" for t in TYPES if t.dummy], "Dummy, the kind's word (radiospec.KIND_WORDS: the log's name of a radio with none), radio"
    assert KIND_WORDS == {"fm": "FM", "hf": "Mercury", "lora": "LoRa"}, "a kind is called by its signal, who can hear it, never by a band: a Mercury radio may be on 2 m"
    assert max(len(name) for name in names.values()) == 41 and len(set(names.values())) == len(names), "the list is as wide as its widest line"


def test_each_kind_lists_its_types_in_the_order_of_the_pages_list_and_a_new_radio_gets_todays_default() -> None:
    assert [t.key for t in types_of("fm")] == ["direwolf", "kiss", "kenwood-d710", "kenwood-tnc2", "kantronics", "kiss-tcp", "tnc-text", "dummy"], \
        "what most stations have first: the sound card, the KISS TNC (whose name has the TH-D74) above the two Kenwood lines, the operator's own program, the type that only receives, the Dummy"
    assert {t.key for t in types_of("fm")} == {p.key for p in PROFILES} | {"direwolf"}, "the types of before's flat list, and the Sound card type"
    assert [t.key for t in types_of("hf")] == [p.key for p in HF_PROFILES]
    assert [t.key for t in types_of("lora")] == [p.key for p in LORA_PROFILES] == ["lora-tcp", "lora-serial", "lora-console", "dummy-lora"]
    assert (DEFAULT_TYPE["fm"], DEFAULT_TYPE["hf"], DEFAULT_TYPE["lora"]) == (DEFAULT.key, HF_DEFAULT.key, "lora-tcp"), "a new LoRa radio is the iGate at home on the network"
    assert KINDS == ("fm", "hf", "lora") and LOCAL_KINDS == {"fm", "lora"}


def test_what_each_type_can_do() -> None:
    serial, tcp = Can(True, True, False, False, False, False, False), Can(False, True, False, False, False, False, False)
    can = {t.key: t.can for t in TYPES}
    assert can == {"kenwood-tnc2": serial, "kenwood-d710": serial, "kantronics": serial, "kiss": serial, "kiss-tcp": tcp, "tnc-text": Can(False, True, False, False, False, False, False, transmit=False), "dummy": DUMMY_CAN,
                   "mercury": Can(False, True, True, True, True, True, True), "dummy-hf": Can(False, True, False, False, False, False, True), "dummy-lora": DUMMY_CAN,
                   "lora-tcp": tcp, "lora-serial": tcp, "lora-console": replace(tcp, transmit=False),
                   "direwolf": Can(False, True, True, True, False, True, False, rx_level=True)}, "a LoRa board has its terminal, and no Find: an open may restart one; a text TNC and the iGate's log send nothing"
    assert [key for key, c in can.items() if c.rx_level] == ["direwolf"], "the level of the packets heard: Direwolf's alone"


def test_the_types_that_only_receive_share_one_can_and_one_allowed_and_every_line_cuts_text_where_its_type_does() -> None:
    receiving = [t for t in TYPES if not t.can.transmit]
    assert {t.key for t in receiving} == {"tnc-text", "lora-console"} and all(t.can is LISTENS and t.allowed is NOTHING_ALLOWED for t in receiving), "said once, in radiotypes/common.py"
    assert LISTENS == replace(TERMINAL_ONLY, transmit=False) and type_of("kiss-tcp").can is type_of("lora-tcp").can is TERMINAL_ONLY and type_of("mercury").allowed is NOTHING_ALLOWED
    for t in TYPES:
        assert Tnc("", profile={**EVERY_BY_KEY, DIREWOLF.key: DIREWOLF}[t.profile]).rtype.limits.max_text == t.limits.max_text, f"{t.key}: the line refuses what the fit lets through, or the other way round"


def test_a_type_has_its_own_fields_then_the_beacon_and_the_status_and_the_path_and_digipeater_where_allowed() -> None:
    keys = {t.key: [f.key for f in t.fields] for t in TYPES}
    for serial in ("kenwood-tnc2", "kenwood-d710", "kantronics", "kiss"):
        assert keys[serial] == ["port", "baud", "beacon", "status", "ask", "local_info", "path", "digipeat"]
    assert keys["kiss-tcp"] == ["port", "tcp_host", "tcp_port", "beacon", "status", "ask", "local_info", "path", "digipeat"]
    assert keys["tnc-text"] == ["port", "baud"], "a radio that sends nothing has no beacon tick, no path and no digipeater"
    assert keys["dummy"] == ["beacon", "status", "ask", "local_info", "path", "digipeat"] and keys["dummy-lora"] == ["beacon", "status", "ask", "local_info", "path"] and keys["dummy-hf"] == ["beacon", "status", "ask", "local_info"]
    assert keys["mercury"] == ["sound_card", "keying", "tx_gain_db", "tx_card", "rx_card", "beacon", "status", "ask", "local_info"]
    assert (keys["lora-tcp"], keys["lora-serial"], keys["lora-console"]) == (["tcp_host", "tcp_port", "beacon", "status", "ask", "local_info", "path"], ["port", "baud", "beacon", "status", "ask", "local_info", "path"], ["port", "baud"]), \
        "a LoRa board's own fields are where it is reached; no frequency and no modem setting, which no firmware takes from a program"
    assert [f.key for f in COMMON_FIELDS] == ["beacon", "status", "ask", "local_info", "path", "digipeat"]
    assert type_of("kiss-tcp").field("tcp_host") is not None and type_of("kiss").field("tcp_host") is None


def test_a_radio_of_a_kind_may_store_the_fields_of_every_type_of_it_each_the_same_field_in_every_type() -> None:
    assert [f.key for f in kind_fields("fm")] == ["sound_card", "keying", "tx_gain_db", "tx_card", "rx_card", "port", "baud", "tcp_host", "tcp_port", "beacon", "status", "ask", "local_info", "path", "digipeat"], "by the kind's list of types, the Sound card's first"
    assert [f.key for f in kind_fields("hf")] == ["sound_card", "keying", "tx_gain_db", "tx_card", "rx_card", "beacon", "status", "ask", "local_info"]
    assert [f.key for f in kind_fields("lora")] == ["tcp_host", "tcp_port", "port", "baud", "beacon", "status", "ask", "local_info", "path"]
    for kind in KINDS:
        for t in types_of(kind):
            assert all(replace(f, claims=None) == replace(kind_field(kind, f.key), claims=None) for f in t.fields), f"{t.key}: a key is one field across the kind"   # type: ignore[type-var]
    assert kind_field("hf", "port") is None
    assert type_of("kiss").field("port").claims == "serial" and type_of("kiss-tcp").field("port").claims is None, "what a value claims is its type's: a TCP address is no serial device"   # type: ignore[union-attr]


def test_each_field_is_todays_setting_its_default_range_parser_and_claim() -> None:
    # today's flat settings are the FM radio's and the HF radio's: the transmit gain is Mercury's
    fields = {f.key: f for kind in ("lora", "fm", "hf") for f in kind_fields(kind)}
    defaults = DEFAULTS.to_data()
    differ = {(kind, f.key) for kind in KINDS for f in kind_fields(kind) if replace(f, claims=None) != replace(fields[f.key], claims=None)}
    assert differ == {("lora", "tcp_host"), ("fm", "tx_gain_db")}, "a key is one field in every kind but the LoRa board's address, which is never this computer's, and the transmit gain, in each modem's own range"
    for key, old in OLD_KEY.items():
        f = fields[key]
        assert f.default == defaults[old], key
        assert f.range == RANGES.get(old), key
        assert stored_text(f.parse(f.default)) == f.default, key
    assert stored_text(fields["beacon"].parse(fields["beacon"].default)) == "true"
    for key, old, good, bad in (("port", "serial/port", " /dev/ttyUSB0 ", "\x00"), ("baud", "serial/baud", "19200", "12"), ("tcp_host", "tcp/host", " ::1 ", "a b"), ("tcp_port", "tcp/port", "8100", "0"),
                                ("keying", "mercury/keying", "RTS:/dev/ttyUSB1", "pigeon"), ("tx_gain_db", "mercury/tx_gain_db", "-4", "99"), ("path", "beacon/path", "wide1-1, wide2-1", "WIDE2-2,DIRECT"),
                                ("digipeat", "digi/enabled", "yes", "maybe")):
        assert stored_text(fields[key].parse(good)) == Config.check(old, good), key
        with pytest.raises(ValueError):
            fields[key].parse(bad)
        with pytest.raises(ValueError):
            Config.check(old, bad)
    assert {f.key: f.claims for f in fields.values() if f.claims} == {"port": "serial", "sound_card": "sound_card", "keying": "keying"}
    assert {f.key: f.together for f in fields.values() if f.together} == {"tcp_host": "tcp", "tcp_port": "tcp"}
    assert all(f.text == f"radio.field.{f.key}" for f in fields.values())


def test_the_sound_card_type_and_the_dummy_lora_type_stand_side_by_side_in_the_one_registry_each_in_its_kind() -> None:
    sound, lora = type_of("direwolf"), type_of("dummy-lora")
    assert (sound.kind, sound.driver, sound.dummy, lora.kind, lora.driver, lora.dummy) == ("fm", "direwolf", False, "lora", "tnc", True)
    assert [t.key for t in TYPES if t.dummy] == ["dummy", "dummy-hf", "dummy-lora"], "one Dummy of each kind, the types that open no device (Add radio lists them apart)"
    assert [t.key for t in types_of("fm")][0] == "direwolf" and [t.key for t in types_of("fm")][-1] == "dummy" and [t.key for t in types_of("lora")][-1] == "dummy-lora", "the Sound card type first among FM's real ones, each kind's Dummy last in its kind"
    assert sound.systems == {"linux", "win32"} and lora.systems == frozenset(), "the LoRa Dummy carries no program, so every installation offers it"
    assert [unavailable_types(system) for system in ("linux", "win32", "darwin")] == [(), (), ("direwolf",)]
    assert (sound.recommended_path, recommended_path("fm"), recommended_path("lora")) == ("", "", "WIDE1-1"), "the Sound card type's empty path is FM's (the symbol's), LoRa's is its own"
    assert [f.key for f in sound.fields] == ["sound_card", "keying", "tx_gain_db", "tx_card", "rx_card", "beacon", "status", "ask", "local_info", "path", "digipeat"] == [f.key for f in kind_fields("fm") if sound.field(f.key)], "the Sound card type's own fields, in FM's order"
    assert [f.key for f in lora.fields] == [f.key for f in kind_fields("lora") if lora.field(f.key)], "the Dummy LoRa type's own fields, in LoRa's order"


def test_an_unknown_type_is_refused_with_the_types_there_are() -> None:
    with pytest.raises(RadioTypeError, match="'pigeon' is not a type of radio.*kiss.*dummy-hf"):
        type_of("pigeon")
    assert type_of(" mercury ") is BY_KEY["mercury"]
    assert type_of(DEFAULT_TYPE["lora"]).kind == "lora"


def test_todays_slot_word_is_the_id_of_its_radio() -> None:
    assert (radio_id_of("fm"), radio_id_of("hf"), radio_id_of(""), radio_id_of("both")) == (FM_ID, HF_ID, None, None)
    assert (FM_ID, HF_ID) == (1, 2)
    assert [stored_text(v) for v in (None, True, False, 1.5, 2.0, 7, "x")] == ["", "true", "false", "1.5", "2", "7", "x"]
