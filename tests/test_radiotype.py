"""The types of radio (neoaprs/radiotype.py, the registry neoaprs/radiotypes/): each type is a TNC profile and the rules of its kind field by field (radiorules.rules_of gives the RadioRules back), the
fields are today's flat settings with their defaults, ranges and parsers, the page's order of each kind is today's, a radio of a kind may store the fields of all its types, and an unknown type is refused."""
from dataclasses import replace

import pytest

from neoaprs.config import DEFAULTS, RANGES, Config
from neoaprs.radiorules import FM, HF, LORA, rules_of
from neoaprs.radiotype import FM_ID, HF_ID, KINDS, LOCAL_KINDS, Can, RadioTypeError, radio_id_of, stored_text
from neoaprs.radiotypes import BY_KEY, COMMON_FIELDS, DEFAULT_TYPE, TYPES, kind_field, kind_fields, type_of, types_of
from neoaprs.tncprofile import DEFAULT, DUMMY_HF, EVERY_BY_KEY, HF_DEFAULT, HF_PROFILES, LORA_PROFILES, PROFILES

OLD_KEY = {"port": "serial/port", "baud": "serial/baud", "tcp_host": "tcp/host", "tcp_port": "tcp/port", "sound_card": "mercury/sound_card", "keying": "mercury/keying", "tx_gain_db": "mercury/tx_gain_db",
           "path": "beacon/path", "digipeat": "digi/enabled"}       # the flat setting of today that each field of a radio is (the beacon is new: on, as both beacons are today)
NONE_CAN = Can(False, False, False, False, False, False, False)


def test_every_type_is_todays_profile_and_the_rules_of_its_kind_field_by_field() -> None:
    profiles = EVERY_BY_KEY
    assert set(BY_KEY) == set(profiles) and len(TYPES) == len(profiles), "one type for each entry of the lists of profiles"
    for t in TYPES:
        p = profiles[t.key]
        assert (t.kind, t.name, t.transport, t.profile, t.text) == (p.rules.kind, p.name, p.transport, p.key, f"radio.type.{p.key}"), t.key
        kind = {"fm": FM, "hf": HF, "lora": LORA}[t.kind]
        assert rules_of(t) == p.rules == (kind if t.can.transmit else replace(kind, paths=False, digipeat=False, smart_beacon=False)), f"{t.key}: a radio that sends nothing is allowed nothing that sends"
        assert (t.limits.max_frame, t.limits.beacon_min_min, t.limits.beacon_jitter_sec, t.limits.retry_jitter_sec) == (p.rules.max_frame, p.rules.beacon_min_min, p.rules.beacon_jitter_sec, p.rules.retry_jitter_sec)
        assert (t.allowed.paths, t.allowed.digipeat, t.allowed.smart_beacon) == (p.rules.paths, p.rules.digipeat, p.rules.smart_beacon)
        assert (t.allowed.gateway_heard, t.allowed.shared_channel) == ((t.kind != "hf", t.kind == "fm") if t.can.transmit else (False, False)), "internet gateways hear FM and LoRa; the ALOHA circle is FM's 1200 baud alone; neither for a radio that sends nothing"
        assert t.driver == ("mercury" if p.transport == "modem" or p is DUMMY_HF else "tnc") and t.dummy == (p.transport == "dummy")


def test_each_kind_lists_its_types_in_todays_order_and_a_new_radio_gets_todays_default() -> None:
    assert [t.key for t in types_of("fm")] == [p.key for p in PROFILES]
    assert [t.key for t in types_of("hf")] == [p.key for p in HF_PROFILES]
    assert [t.key for t in types_of("lora")] == [p.key for p in LORA_PROFILES] == ["lora-tcp", "lora-serial", "lora-console", "dummy-lora"]
    assert (DEFAULT_TYPE["fm"], DEFAULT_TYPE["hf"], DEFAULT_TYPE["lora"]) == (DEFAULT.key, HF_DEFAULT.key, "lora-tcp"), "a new LoRa radio is the iGate at home on the network"
    assert KINDS == ("fm", "hf", "lora") and LOCAL_KINDS == {"fm", "lora"}


def test_what_each_type_can_do() -> None:
    serial, tcp = Can(True, True, False, False, False, False, False), Can(False, True, False, False, False, False, False)
    can = {t.key: t.can for t in TYPES}
    assert can == {"kenwood-tnc2": serial, "kenwood-d710": serial, "kantronics": serial, "kiss": serial, "kiss-tcp": tcp, "tnc-text": Can(False, True, False, False, False, False, False, transmit=False), "dummy": NONE_CAN,
                   "mercury": Can(False, True, True, True, True, True, True), "dummy-hf": Can(False, False, False, False, False, False, True), "dummy-lora": NONE_CAN,
                   "lora-tcp": tcp, "lora-serial": tcp, "lora-console": replace(tcp, transmit=False)}, "a LoRa board has its terminal, and no Find: an open may restart one; a text TNC and the iGate's log send nothing"


def test_a_type_has_its_own_fields_then_the_beacon_and_the_path_and_digipeater_where_allowed() -> None:
    keys = {t.key: [f.key for f in t.fields] for t in TYPES}
    for serial in ("kenwood-tnc2", "kenwood-d710", "kantronics", "kiss"):
        assert keys[serial] == ["port", "baud", "beacon", "path", "digipeat"]
    assert keys["kiss-tcp"] == ["port", "tcp_host", "tcp_port", "beacon", "path", "digipeat"]
    assert keys["tnc-text"] == ["port", "baud"], "a radio that sends nothing has no beacon tick, no path and no digipeater"
    assert keys["dummy"] == ["beacon", "path", "digipeat"] and keys["dummy-lora"] == ["beacon", "path"] and keys["dummy-hf"] == ["beacon"]
    assert keys["mercury"] == ["sound_card", "keying", "tx_gain_db", "beacon"]
    assert (keys["lora-tcp"], keys["lora-serial"], keys["lora-console"]) == (["tcp_host", "tcp_port", "beacon", "path"], ["port", "baud", "beacon", "path"], ["port", "baud"]), \
        "a LoRa board's own fields are where it is reached; no frequency and no modem setting, which no firmware takes from a program"
    assert [f.key for f in COMMON_FIELDS] == ["beacon", "path", "digipeat"]
    assert type_of("kiss-tcp").field("tcp_host") is not None and type_of("kiss").field("tcp_host") is None


def test_a_radio_of_a_kind_may_store_the_fields_of_every_type_of_it_each_the_same_field_in_every_type() -> None:
    assert [f.key for f in kind_fields("fm")] == ["port", "baud", "tcp_host", "tcp_port", "beacon", "path", "digipeat"]
    assert [f.key for f in kind_fields("hf")] == ["sound_card", "keying", "tx_gain_db", "beacon"]
    assert [f.key for f in kind_fields("lora")] == ["tcp_host", "tcp_port", "port", "baud", "beacon", "path"]
    for kind in KINDS:
        for t in types_of(kind):
            assert all(replace(f, claims=None) == replace(kind_field(kind, f.key), claims=None) for f in t.fields), f"{t.key}: a key is one field across the kind"   # type: ignore[type-var]
    assert kind_field("hf", "port") is None
    assert type_of("kiss").field("port").claims == "serial" and type_of("kiss-tcp").field("port").claims is None, "what a value claims is its type's: a TCP address is no serial device"   # type: ignore[union-attr]


def test_each_field_is_todays_setting_its_default_range_parser_and_claim() -> None:
    fields = {f.key: f for kind in reversed(KINDS) for f in kind_fields(kind)}       # (today's flat settings are the FM radio's and the HF radio's)
    defaults = DEFAULTS.to_data()
    differ = {(kind, f.key) for kind in KINDS for f in kind_fields(kind) if replace(f, claims=None) != replace(fields[f.key], claims=None)}
    assert differ == {("lora", "tcp_host")}, "a key is one field in every kind but the LoRa board's address, which is never this computer's"
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


def test_an_unknown_type_is_refused_with_the_types_there_are() -> None:
    with pytest.raises(RadioTypeError, match="'pigeon' is not a type of radio.*kiss.*dummy-hf"):
        type_of("pigeon")
    assert type_of(" mercury ") is BY_KEY["mercury"]
    assert type_of(DEFAULT_TYPE["lora"]).kind == "lora"


def test_todays_slot_word_is_the_id_of_its_radio() -> None:
    assert (radio_id_of("fm"), radio_id_of("hf"), radio_id_of(""), radio_id_of("both")) == (FM_ID, HF_ID, None, None)
    assert (FM_ID, HF_ID) == (1, 2)
    assert [stored_text(v) for v in (None, True, False, 1.5, 2.0, 7, "x")] == ["", "true", "false", "1.5", "2", "7", "x"]
