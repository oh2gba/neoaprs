"""The seams of the radio round (work/par/round/breakdown.md, section 1) as views of today's values, so that nothing behaves differently while they are new: the radios of the settings are today's FM radio
(radio 1) and HF radio (radio 2) made of the flat keys (`radios_from_flat`, every shape of today's settings); the id views of a packet, a station, a message and its attempts and an object say what the old fields
say; today's rules written with ids (neoaprs/messagerule.py, neoaprs/emailrule.py) choose what `Radios.for_station` and the email gateway's radio choose, over a table of cases, and the beacon rule
(neoaprs/beaconrule.py, plan rule 3.1, tests/test_beaconrule.py) keeps today's two beacons on today's radios with each radio's own floor; the one fit function makes the frame the sender makes today; the shapes wave 1 writes (tests/support/seamshapes.py, which mypy holds to the Protocols) work as the
services take them; and the constructors that gained keywords keep their old call."""
import itertools
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from neoaprs import ax25
from neoaprs.beaconrule import beacon_interval, beacon_radios
from neoaprs.chain import Attempt
from neoaprs.claims import Claims
from neoaprs.clock import utc
from neoaprs.config import DEFAULTS, Config, radio_key_of, radio_state_key, radios_from_flat
from neoaprs.emailrule import email_radio
from neoaprs.mercurymodem import Mercury
from neoaprs.message import EMAIL_GATEWAY, MessageRecord, MessagingError
from neoaprs.messagerule import message_radio
from neoaprs.ownobject import make_object
from neoaprs.packet import Packet, Undecoded
from neoaprs.policy import MESSAGE_RADIO_RECENT_HOURS, TNC_CHECK_SEC
from neoaprs.radiodriver import RunOverrides
from neoaprs.radiorules import FM, HF
from neoaprs.radios import Radios
from neoaprs.radiospec import FM_ID, HF_ID, RadioError, RadioHeard
from neoaprs.radiotype import Allowed, Limits
from neoaprs.radiotypes import type_of
from neoaprs.services import common, radioset, sender
from neoaprs.services.common import fit_frame, our_frame
from neoaprs.services.radioset import NO_RADIO, fit
from neoaprs.services.sender import SendError, Sender
from neoaprs.source import Source
from neoaprs.station import Station
from neoaprs.stationbook import StationBook
from neoaprs.tnc import Tnc
from neoaprs.tncprofile import DUMMY_HF, KISS_TCP, MERCURY
from tests.support.seamshapes import DriverShape, LineOfTest, LiveShape, ModemDriverShape, ModemOfTest, RegistryShape, as_air, as_driver, as_pick, frozen_air

T0 = utc(2026, 11, 14, 8, 0)
SHAPES: list[dict[str, str]] = [            # the settings of today's stations, as the database keeps them
    {},
    {"hf/enabled": "true"},
    {"fm/enabled": "false", "hf/enabled": "true", "hf/profile": "dummy-hf"},
    {"fm/enabled": "false", "hf/enabled": "false"},
    {"tnc/profile": "kiss-tcp", "tcp/host": "::1", "tcp/port": "8100", "beacon/path": "DIRECT"},
    {"tnc/profile": "kenwood-d710", "serial/port": "/dev/serial/by-id/usb-FTDI-if00", "serial/baud": "19200", "beacon/path": "WIDE1-1,WIDE2-1", "digi/enabled": "true"},
    {"tnc/profile": "dummy", "hf/enabled": "true", "mercury/sound_card": "plughw:1,0", "mercury/keying": "rts:/dev/ttyUSB1", "mercury/tx_gain_db": "-6"},
    {"tnc/enter_kiss": "true"},                                 # the legacy rows (configlegacy.py): the Kenwood TNC-2 entry ...
    {"tnc/profile": "mercury"},                                 # ... and the HF radio alone
    {"serial/baud": "12", "tcp/port": "0", "mercury/tx_gain_db": "99"},     # wrong values: the defaults, as for the flat keys
]
FLAT = {"port": "serial_port", "baud": "serial_baud", "tcp_host": "tcp_host", "tcp_port": "tcp_port", "path": "beacon_path", "digipeat": "digi_enabled",
        "sound_card": "mercury_sound_card", "keying": "mercury_keying", "tx_gain_db": "mercury_tx_gain_db"}


@pytest.mark.parametrize("rows", SHAPES, ids=lambda rows: ",".join(f"{k}={v}" for k, v in rows.items()) or "fresh")
def test_the_radios_of_the_settings_are_todays_fm_and_hf_radio_made_of_the_flat_keys(rows: dict[str, str]) -> None:
    config = Config.from_data(rows)
    fm, hf = config.radios
    assert config.radios == radios_from_flat(config) and config.radios is config.radios
    assert (fm.id, fm.kind, fm.type, fm.enabled, fm.name, fm.removed_at) == (FM_ID, "fm", config.tnc_profile, config.fm_enabled, "", None)
    assert (hf.id, hf.kind, hf.type, hf.enabled, hf.name, hf.removed_at) == (HF_ID, "hf", config.hf_profile, config.hf_enabled, "", None)
    for spec in (fm, hf):
        assert spec.rtype.kind == spec.kind and spec.value("beacon") is True, "the beacon goes out on every radio that is on, as today"
        for key, text in spec.settings.items():
            assert key == "beacon" or spec.value(key) == getattr(config, FLAT[key]), key
            assert Config.check_radio(spec, key, text) == text, "what is stored reads back as it is"
    assert set(fm.settings) == {"port", "baud", "tcp_host", "tcp_port", "beacon", "path", "digipeat"} and set(hf.settings) == {"sound_card", "keying", "tx_gain_db", "beacon"}
    today = "fm" if config.fm_enabled else "hf" if config.hf_enabled else None
    assert config.main_radio == {"fm": FM_ID, "hf": HF_ID, None: None}[today], "the main radio is today's default radio (none for none: today's stopped FM radio)"
    assert [s.id for s in config.enabled_radios] == [i for i, on in ((FM_ID, config.fm_enabled), (HF_ID, config.hf_enabled)) if on]
    assert config.live_radios == [fm, hf] and config.radio(FM_ID) is fm and config.radio(HF_ID) is hf and config.radio(3) is None and config.main_choice is None
    assert Config.from_data(config.to_data()) == config and Config.from_data(config.to_data()).radios == config.radios


def test_the_radios_follow_a_replaced_setting_and_leave_what_config_is_unchanged() -> None:
    assert replace(DEFAULTS, hf_enabled=True).radio(HF_ID).enabled and not DEFAULTS.radio(HF_ID).enabled          # type: ignore[union-attr]
    assert replace(DEFAULTS, tnc_profile="kiss-tcp").radio(FM_ID).type == "kiss-tcp"                               # type: ignore[union-attr]
    assert Config() == DEFAULTS == Config.from_data({}) and hash(Config()) == hash(DEFAULTS)
    assert "radios" not in DEFAULTS.to_data() and DEFAULTS.changed(replace(DEFAULTS, hf_enabled=True)) == ["hf/enabled"]


def test_a_radios_value_is_checked_by_its_field_and_a_refusal_names_its_key() -> None:
    fm, hf = DEFAULTS.radios
    assert Config.check_radio(fm, "baud", " 019200 ") == "19200" and Config.check_radio(fm, "digipeat", "YES") == "true" and Config.check_radio(fm, "path", "wide2-2") == "WIDE2-2"
    with pytest.raises(RadioError, match="radio/1/baud: .*12"):
        Config.check_radio(fm, "baud", "12")
    with pytest.raises(RadioError, match="radio/2/port: a radio of the kind hf has no such setting"):
        Config.check_radio(hf, "port", "/dev/ttyUSB0")
    assert radio_state_key(2, "beacon_last_sent_at") == "radio/2/beacon_last_sent_at" and radio_state_key(1, "last_port") == "radio/1/last_port"
    assert radio_key_of(radio_state_key(12, "last_port")) == (12, "last_port") and radio_key_of("radio/1/port") == (1, "port")
    assert [radio_key_of(k) for k in ("serial/port", "radio/0/port", "radio/01/port", "radio/x/port", "radio/1/", "radio/1/a/b", "radio/1")] == [None] * 7


# ---- the id views of today's values

def packet(radio: str, via: str = "rf") -> Packet:
    return Packet(T0, "in", b"", "OH2GAX", "APRS", (), b"x", Undecoded("test", "x"), via=via, radio=radio)  # type: ignore[arg-type]


def test_the_id_of_a_packets_a_messages_and_an_attempts_radio_is_its_slot_word() -> None:
    assert [packet(r).radio_id for r in ("fm", "hf", "")] == [FM_ID, HF_ID, None]
    assert packet("", "is").radio_id is None
    record = MessageRecord(1, T0, "in", "OH2GAX", "OH2GBA", "moi", "1", "received")
    assert [replace(record, radio=r).radio_id for r in ("fm", "hf", "")] == [FM_ID, HF_ID, None]
    assert [Attempt(1, T0, (), radio=r).radio_id for r in ("fm", "hf", "")] == [FM_ID, HF_ID, None]


def test_the_radios_of_an_object_are_its_choice_as_ids() -> None:
    made = {radio: make_object(T0, "TEST", "object", 60.2, 24.9, "/", "-", radio=radio) for radio in ("fm", "hf", "both")}
    assert {radio: obj.radios for radio, obj in made.items()} == {"fm": (FM_ID,), "hf": (HF_ID,), "both": (FM_ID, HF_ID)}


@pytest.mark.parametrize(("fm", "hf", "fm_at", "hf_at", "expected"), [
    (0, 0, None, None, {}),
    (3, 0, T0, None, {FM_ID: RadioHeard(3, T0, ("OH2RCH",))}),
    (0, 2, None, T0, {HF_ID: RadioHeard(2, T0, ("OH2RCH",))}),
    (3, 2, T0, T0 - timedelta(hours=1), {FM_ID: RadioHeard(3, T0, ("OH2RCH",)), HF_ID: RadioHeard(2, T0 - timedelta(hours=1))}),
    (3, 2, T0 - timedelta(hours=1), T0, {FM_ID: RadioHeard(3, T0 - timedelta(hours=1)), HF_ID: RadioHeard(2, T0, ("OH2RCH",))}),
    (3, 2, T0, T0, {FM_ID: RadioHeard(3, T0, ("OH2RCH",)), HF_ID: RadioHeard(2, T0)}),
])
def test_what_each_radio_heard_of_a_station_is_its_count_and_time_by_slot_and_the_path_goes_with_the_latest(fm: int, hf: int, fm_at: Any, hf_at: Any, expected: dict[int, RadioHeard]) -> None:
    s = Station("OH2GAX", first_heard=T0, last_heard=T0, heard_fm=fm, heard_hf=hf, last_fm_at=fm_at, last_hf_at=hf_at, last_path=("OH2RCH",))
    assert s.heard_by == expected
    assert s.heard_on(FM_ID).count == fm and s.heard_on(HF_ID).count == hf and s.heard_on(3) == RadioHeard(0, None)


# ---- today's rules, written with ids

def station(fm: int, hf: int, choice: str) -> Station:
    return Station("OH2GAX", first_heard=T0, last_heard=T0, heard_fm=fm, heard_hf=hf, last_fm_at=T0 if fm else None, last_hf_at=T0 if hf else None, message_radio=choice)


CASES = list(itertools.product((True, False), (True, False), (0, 4), (0, 2), ("", "fm", "hf"), (True, False)))     # FM on, HF on, heard on FM, on HF, the choice, the station in the book


@pytest.mark.parametrize(("fm_on", "hf_on", "fm", "hf", "choice", "known"), CASES)
def test_the_radio_of_a_message_is_the_one_radios_for_station_chooses_today(fm_on: bool, hf_on: bool, fm: int, hf: int, choice: str, known: bool) -> None:
    config = replace(DEFAULTS, fm_enabled=fm_on, hf_enabled=hf_on)
    book = StationBook()
    if known:
        book.seed([station(fm, hf, choice)])
    fm_radio, hf_radio = object(), object()
    today = Radios(fm_radio, hf_radio, lambda: config, book).for_station("OH2GAX")      # type: ignore[arg-type]  # what is chosen is all that is asked of a radio here
    s = book.get("OH2GAX")
    heard = s.heard_by if s is not None else {}
    chosen = {"fm": FM_ID, "hf": HF_ID}.get(s.message_radio if s is not None else "")
    got = message_radio(chosen, heard, config.radios, config.main_radio, T0)
    if not fm_on and not hf_on:
        assert got is None, "no radio enabled: none (today's falls to the stopped FM radio, which sends nothing)"
    else:
        assert got == (FM_ID if today is fm_radio else HF_ID)


@pytest.mark.parametrize(("interval", "fm_on", "hf_on"), list(itertools.product((0, 20, 25, 30, 60), (True, False), (True, False))))
def test_the_beacon_interval_is_each_radios_own_and_its_radios_are_todays(interval: int, fm_on: bool, hf_on: bool) -> None:
    config = replace(DEFAULTS, beacon_interval_min=interval, fm_enabled=fm_on, hf_enabled=hf_on)
    for spec in config.radios:
        own = max(interval, 30) if interval and spec.kind == "hf" else interval
        assert beacon_interval(interval, spec, config.radios) == own, "the station's interval, raised on the HF radio alone to its 30 minutes (plan rule 3.1: FM at 20 is no longer slowed by HF)"
    assert beacon_radios(config.radios, config.main_radio) == tuple(i for i, on in ((FM_ID, fm_on), (HF_ID, hf_on)) if on), "each beacon sends while its radio is on"
    assert MESSAGE_RADIO_RECENT_HOURS == 6


@pytest.mark.parametrize(("fm_on", "hf_on"), list(itertools.product((True, False), (True, False))))
def test_the_email_radio_is_the_one_todays_gateway_rule_chooses(fm_on: bool, hf_on: bool) -> None:
    config = replace(DEFAULTS, fm_enabled=fm_on, hf_enabled=hf_on)
    fm_radio, hf_radio = object(), object()
    radios = Radios(fm_radio, hf_radio, lambda: config, StationBook())                  # type: ignore[arg-type]
    try:
        today = FM_ID if common.message_radio(radios, EMAIL_GATEWAY) is fm_radio else HF_ID      # type: ignore[arg-type]
    except MessagingError:
        today = None
    assert email_radio(config.radios, config.main_radio) == today


# ---- the one fit function, against the sender of today

class Air:
    """An AirRadio of a type, its own settings those of the station's flat keys."""
    def __init__(self, config: Config, key: str, radio: int) -> None:
        t = type_of(key)
        self.spec = config.radio(radio)
        self.id, self.kind, self.name, self.limits, self.allowed = radio, t.kind, t.name, t.limits, t.allowed
        self.state, self.usable, self.max_frame = Source.State.CONNECTED, True, t.limits.max_frame

    def why_unusable(self) -> str:
        return ""

    def send_frame(self, frame: ax25.Frame, raw: bytes | None = None) -> bool:
        return True

    def choice(self, key: str) -> Any:
        return self.spec.value(key)                     # type: ignore[union-attr]


class Today:
    """A Radio of today with the rules of a profile."""
    def __init__(self, rules: Any) -> None:
        self.rules, self.max_frame, self.state, self.usable = rules, rules.max_frame, Source.State.CONNECTED, True


@pytest.mark.parametrize("path", ["", "DIRECT", "OH2RCH-2,WIDE2-1"])
def test_our_frame_for_a_radio_is_the_one_the_sender_makes_today(path: str) -> None:
    config = replace(DEFAULTS, station_call="OH2GBA", beacon_path=path, hf_enabled=True)
    info = b"!6010.00N/02455.00E-" + b"a comment that is long enough to be cut on HF" * 3
    for key, radio, rules in (("kiss", FM_ID, FM), ("mercury", HF_ID, HF)):
        air = Air(config, key, radio)
        assert fit(air, config, info, None) == Sender(Today(rules), lambda: config).frame(info, None)          # type: ignore[arg-type]
        assert fit(air, config, info, ("OH2X",)) == Sender(Today(rules), lambda: config).frame(info, ("OH2X",))    # type: ignore[arg-type]
    hf_frame = fit(Air(config, "mercury", HF_ID), config, info, ("OH2X",))
    assert hf_frame.path == () and len(ax25.encode(hf_frame)) == HF.max_frame
    assert fit(Air(config, "kiss", FM_ID), config, b">x", None) == our_frame(config, config.beacon_path_calls, b">x") == fit_frame(our_frame(config, config.beacon_path_calls, b">x"), None)
    with pytest.raises(SendError):
        fit(Air(config, "kiss", FM_ID), config, b"x" * (ax25.MAX_INFO + 1), None)
    with pytest.raises(SendError):
        fit(Air(replace(config, station_call=""), "kiss", FM_ID), replace(config, station_call=""), b">x", None)
    assert NO_RADIO == "there is no radio"


def test_the_shapes_wave_one_writes_are_what_the_services_take_and_the_frame_parts_have_one_home() -> None:
    config = replace(DEFAULTS, station_call="OH2GBA", hf_enabled=True)
    lines = {FM_ID: LineOfTest(), HF_ID: LineOfTest(profile=MERCURY)}
    live = [LiveShape(spec, config.radios, lines[spec.id]) for spec in config.radios]
    pick = as_pick(RegistryShape(live))
    assert [r.id for r in pick.enabled()] == [FM_ID, HF_ID] and pick.main is live[0] and pick.get(HF_ID) is live[1] and pick.get(3) is None
    assert [(r.name, r.kind, r.max_frame, r.stats is lines[r.id].stats) for r in pick.enabled()] == [("FM", "fm", None, True), ("HF", "hf", HF.max_frame, True)]
    info = b"!6010.00N/02455.00E-" + b"long comment " * 12
    for spec in config.radios:
        assert fit(as_air(frozen_air(spec)), config, info, None) == fit(as_air(live[spec.id - 1]), config, info, None), "a frozen value and a radio of the registry are the same radio to fit"
    plain, modem = DriverShape(LineOfTest()), ModemDriverShape(LineOfTest(), ModemOfTest(Path("unused")))
    for driver in (as_driver(plain), as_driver(modem)):
        driver.configure(config.radios[0], config, RunOverrides())
        assert driver.restart_key(config.radios[0], config, RunOverrides()) != driver.restart_key(config.radios[0], replace(config, serial_skip="/dev/ttyS0"), RunOverrides()), "the station's serial/skip restarts a serial radio"
    assert plain.modem is None and modem.modem is not None and plain.configured == [(config.radios[0], config, RunOverrides())]
    assert sender.SendError is radioset.SendError and (common.FRAME_ERRORS, common.our_frame, common.fixed_prefix, common.fit_frame) == (radioset.FRAME_ERRORS, radioset.our_frame, radioset.fixed_prefix, radioset.fit_frame)


# ---- the constructors that gained a keyword keep their old call

def test_a_tnc_is_the_radio_of_its_kind_until_its_driver_says_and_the_modem_keeps_what_it_is_given(tmp_path: Path) -> None:
    assert (Tnc().radio_id, Tnc(profile=KISS_TCP).radio_id, Tnc(profile=MERCURY).radio_id, Tnc(profile=DUMMY_HF).radio_id) == (FM_ID, FM_ID, HF_ID, HF_ID)
    tnc = Tnc()
    assert tnc.radio_name == "" and tnc.label == "tnc" and Tnc(profile=MERCURY).label == "hf radio", "the log's names are today's"
    modem = Mercury(tmp_path)
    assert (modem.claims, modem.holder, modem.folder) == (None, HF_ID, None)
    claims = Claims()
    other = Mercury(tmp_path, claims=claims, holder=5, folder=tmp_path / "radios" / "5")
    assert (other.claims, other.holder, other.folder) == (claims, 5, tmp_path / "radios" / "5")
    assert RunOverrides() == RunOverrides("", "", "", TNC_CHECK_SEC)
    assert Limits(None, 20, 0, 0) == type_of("kiss").limits and Allowed(False, False, False, False, False) == type_of("dummy-hf").allowed
