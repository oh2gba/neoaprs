"""The settings (neoaprs/config.py): the defaults, the text of each key and back, and a wrong value that falls back to its default and is told with its key."""
import logging
from dataclasses import fields, replace

import pytest

from neoaprs.config import BY_KEY, DEFAULT_ALERT_COMMAND, DEFAULTS, KEYS, MAX_COMMENT, MAX_COMMENT_PHG, RANGES, SETTINGS, Config
from neoaprs.smartbeacon import TRAVEL, PRESETS, SmartSettings
from neoaprs.policy import LOG_KEEP_DAYS, TNC_CHECK_SEC
from neoaprs.configstatus import MAX_STATUS, fill_template


def test_the_defaults_are_the_ones_of_the_brief() -> None:
    assert DEFAULTS.to_data() == {
        "tnc/profile": "kiss", "serial/port": "", "serial/baud": "", "tcp/host": "127.0.0.1", "tcp/port": "8001", "serial/last_port": "", "serial/pattern": "/dev/serial/by-id/* /dev/ttyUSB* /dev/ttyACM*", "serial/skip": "", "station/call": "", "station/transmit": "true", "station/lat": "", "station/lon": "",
        "station/symbol_table": "/", "station/symbol_code": "-", "station/comment": "NeoAPRS", "station/status": "", "beacon/power_w": "", "beacon/antenna_height_m": "0", "beacon/antenna_gain_db": "0",
        "beacon/antenna_direction": "omni", "web/network": "false", "web/key": "", "web/https": "false", "web/port": "7303", "web/allowed_hosts": "", "beacon/interval_min": "0",
        "beacon/path": "",
        "messages/alert": "true", "messages/alert_command": DEFAULT_ALERT_COMMAND, "status/source": "", "status/rigctld": "", "status/interval_min": "30", "status/template": "QRV {freq} {mode}",
        "map/radius_km": "150", "map/maxzoom": "12", "map/station_hours": "3", "map/source": "",
        "update/url": "https://oh2gba.eu/neoaprs/version.php", "digi/enabled": "false",
        "gps/source": "off", "gps/host": "127.0.0.1:2947", "gps/device": "", "gps/baud": "4800", "beacon/travel": "car"}
    assert Config() == DEFAULTS


def test_every_field_has_a_key_and_every_key_a_field() -> None:
    assert [s.attr for s in SETTINGS] == [f.name for f in fields(Config)]
    assert len(set(KEYS)) == len(KEYS) == len(BY_KEY)


def test_nothing_in_the_database_is_the_defaults_and_what_is_written_is_read_back() -> None:
    assert Config.from_data({}) == DEFAULTS
    c = Config(serial_port="/dev/brainbox_3", serial_baud=19200, serial_last_port="/dev/brainbox_3", serial_pattern="/dev/brainbox_* /dev/ttyUSB*", serial_skip="/dev/brainbox_2, /dev/ttyUSB1", tnc_profile="kenwood-d710", tcp_host="::1", tcp_port=8100, station_call="OH2GBA-9", station_lat=-33.5, station_lon=151.25,
               station_symbol_table="\\", station_symbol_code=">", station_comment="mobile", station_status="On the road, QRV 145.500", beacon_power_w=5, beacon_antenna_height_m=12, beacon_antenna_gain_db=3, beacon_antenna_direction="NW", web_network=True, web_key="k7m2-x9pq-4hrt", web_https=True, web_port=8080, web_allowed_hosts="aprs.example, pi", beacon_interval_min=30,
               beacon_path="WIDE2-2", messages_alert=False, messages_alert_command="echo $NEOAPRS_FROM", status_source="rig", status_rigctld="localhost:4532", status_interval_min=1440, status_template="{mode} {freq}")
    assert Config.from_data(c.to_data()) == c


def test_the_skip_list_is_a_comma_separated_list_of_paths() -> None:
    c = Config.from_data({"serial/skip": " /dev/brainbox_2 ,/dev/ttyUSB1,, "})
    assert c.serial_skip == "/dev/brainbox_2 ,/dev/ttyUSB1,," and c.serial_skip_paths == ("/dev/brainbox_2", "/dev/ttyUSB1")
    assert DEFAULTS.serial_skip_paths == ()
    assert Config.from_data(c.to_data()) == c
    with pytest.raises(ValueError, match="serial/skip"):
        Config.check("serial/skip", "x" * 501)


def test_the_search_pattern_is_globs_separated_by_spaces() -> None:
    assert DEFAULTS.serial_pattern == "/dev/serial/by-id/* /dev/ttyUSB* /dev/ttyACM*"
    assert Config.check("serial/pattern", "  /dev/brainbox_*   /dev/ttyUSB[0-3] ") == "/dev/brainbox_* /dev/ttyUSB[0-3]"
    assert Config.from_data({"serial/pattern": "/dev/brainbox_*"}).serial_pattern == "/dev/brainbox_*"
    for bad in ("", "   ", "ttyUSB*", "/dev/ttyUSB* ttyACM*", "/dev/tty\x01*", "/dev/" + "x" * 500):
        with pytest.raises(ValueError, match="serial/pattern"):
            Config.check("serial/pattern", bad)
    assert Config.from_data({"serial/pattern": ""}).serial_pattern == DEFAULTS.serial_pattern, "a stored value that is no pattern is the default"


def test_a_call_is_checked_and_written_in_capitals() -> None:
    assert Config.from_data({"station/call": "oh2gba-7"}).station_call == "OH2GBA-7"
    assert Config.check("station/call", " oh2xyz ") == "OH2XYZ"


@pytest.mark.parametrize("key, text", [
    ("serial/baud", "fast"), ("serial/baud", "50"), ("tnc/profile", "tnc2"), ("tnc/profile", ""), ("tcp/port", "0"), ("tcp/port", "70000"), ("tcp/host", "two words"), ("station/call", "OH2GBA-16"), ("station/call", "TOOLONGCALL"), ("station/lat", "91"), ("station/lat", "nan"),
    ("station/lon", "-181"), ("station/symbol_table", "//"), ("station/symbol_table", "!"), ("station/symbol_code", ""), ("station/comment", "x" * 44), ("station/comment", "tab\there"),
    ("station/comment", "åäö"), ("station/status", "x" * 63), ("station/status", "å" * 32), ("station/status", "two\nlines"), ("web/key", "two words"), ("web/key", "abcd-efgh-jklm0"), ("web/network", "maybe"), ("web/port", "-1"), ("web/port", "70000"), ("web/allowed_hosts", "x" * 501), ("beacon/interval_min", "-1"),
    ("beacon/interval_min", "1441"), ("beacon/path", "WIDE1-1,TOOLONGCALL"), ("beacon/path", "A,B,C,D,E,F,G,H,I"), ("beacon/path", "WIDE1-16"),
    ("beacon/power_w", "-1"), ("beacon/power_w", "10000"), ("beacon/power_w", "lots"), ("beacon/antenna_height_m", "-1"), ("beacon/antenna_height_m", "10000"), ("beacon/antenna_height_m", "tall"), ("beacon/antenna_gain_db", "10"),
    ("beacon/antenna_gain_db", "-1"), ("beacon/antenna_gain_db", "3.5"), ("beacon/antenna_direction", "up"), ("beacon/antenna_direction", "NNE"), ("beacon/antenna_direction", ""),
    ("update/url", ""), ("update/url", "ftp://example.org/v.php"), ("update/url", "https://"), ("update/url", "two words"), ("update/url", "https://example.org/" + "x" * 500),
    ("messages/alert", "loud"), ("messages/alert_command", "x" * 1001), ("messages/alert_command", "two\nlines"), ("status/rigctld", "localhost"), ("status/rigctld", "localhost:0"), ("status/rigctld", "localhost:70000"),
    ("status/rigctld", ":4532"), ("status/rigctld", "two words:4532"), ("status/interval_min", "0"), ("status/interval_min", "1441"), ("status/interval_min", "often"), ("status/template", "QRV {frequency}"),
    ("status/template", "x" * 63), ("status/template", "{freq} {mode} " + "x" * 50), ("status/template", "two\nlines")])
def test_a_wrong_value_names_its_key_in_the_error_and_falls_back_to_the_default_with_a_log_line(key: str, text: str, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(ValueError, match=key):
        Config.check(key, text)
    caplog.set_level(logging.WARNING, "neoaprs.config")
    c = Config.from_data({key: text, "map/radius_km" if key != "map/radius_km" else "web/port": "77"})
    assert c.to_data()[key] == DEFAULTS.to_data()[key]
    assert any(key in r.getMessage() and "default" in r.getMessage() for r in caplog.records)
    assert 77 in (c.map_radius_km, c.web_port), "the other values are kept"


def test_a_key_that_is_not_a_setting_is_refused_by_check_and_ignored_by_from_data() -> None:
    with pytest.raises(ValueError, match="neoaprs/web/colour"):
        Config.check("neoaprs/web/colour", "red")
    assert Config.from_data({"neoaprs/web/colour": "red"}) == DEFAULTS


def test_the_text_of_a_value_is_the_way_the_program_writes_it() -> None:
    assert [Config.check(k, t) for k, t in [("tnc/profile", " kenwood-d710 "), ("station/lat", "60.170000"), ("station/lon", "25"), ("serial/baud", " 4800 "), ("serial/baud", " ")]] == ["kenwood-d710", "60.17", "25", "4800", ""]


def test_changed_names_the_keys_that_differ() -> None:
    from dataclasses import replace
    assert DEFAULTS.changed(DEFAULTS) == []
    assert DEFAULTS.changed(replace(DEFAULTS, serial_baud=1200, station_lat=1.0)) == ["serial/baud", "station/lat"]


def test_the_path_of_the_beacon_is_a_list_of_calls_written_in_capitals_without_blanks() -> None:
    assert Config.check("beacon/path", " wide1-1 , wide2-1 ") == "WIDE1-1,WIDE2-1"
    assert Config.check("beacon/path", "") == "" and Config.from_data({"beacon/path": ""}).beacon_path_calls == ("WIDE2-1",), "empty is the recommended path (of a house), not none"
    assert Config.check("beacon/path", " direct ") == "DIRECT" and Config.from_data({"beacon/path": "DIRECT"}).beacon_path_calls == (), "DIRECT is no digipeaters, said explicitly"
    assert Config.from_data({"beacon/path": "WIDE2-2"}).beacon_path_calls == ("WIDE2-2",)
    with pytest.raises(ValueError, match="DIRECT"):
        Config.check("beacon/path", "DIRECT,WIDE1-1")
    assert Config.from_data({"beacon/path": "wide1-1,,wide2-1,"}).beacon_path_calls == ("WIDE1-1", "WIDE2-1")
    assert DEFAULTS.beacon_path == "" and DEFAULTS.beacon_path_calls == ("WIDE2-1",), "the default is the recommended path, which follows the symbol: a house is fixed"
    assert Config.check("beacon/path", ",".join(["WIDE1-1"] * 8)).count(",") == 7


@pytest.mark.parametrize(("table", "code", "calls"), [
    ("/", "-", ("WIDE2-1",)), ("/", "_", ("WIDE2-1",)), ("/", "#", ("WIDE2-1",)), ("\\", "-", ("WIDE2-1",)), ("D", "#", ("WIDE2-1",)),
    ("/", ">", ("WIDE1-1", "WIDE2-1")), ("/", "b", ("WIDE1-1", "WIDE2-1")), ("/", "[", ("WIDE1-1", "WIDE2-1")), ("/", "O", ("WIDE1-1", "WIDE2-1")), ("\\", "s", ("WIDE1-1", "WIDE2-1")), ("E", ">", ("WIDE1-1", "WIDE2-1")),
])
def test_the_empty_path_is_the_recommended_path_of_the_symbol_and_a_path_that_is_set_is_not(table: str, code: str, calls: tuple[str, ...]) -> None:
    empty = Config(station_symbol_table=table, station_symbol_code=code, beacon_path="")
    assert empty.beacon_path_calls == calls and empty.recommended_path == ",".join(calls)
    assert replace(empty, beacon_path="WIDE2-2").beacon_path_calls == ("WIDE2-2",), "a custom path (the owner's) does not follow the symbol"
    assert replace(empty, beacon_path="WIDE1-1,WIDE2-1").beacon_path_calls == ("WIDE1-1", "WIDE2-1"), "typed in, it is a custom path too"
    assert replace(empty, beacon_path="DIRECT").beacon_path_calls == ()


def test_the_keep_alive_is_fixed_at_10_minutes_and_what_an_earlier_version_stored_is_ignored() -> None:
    assert TNC_CHECK_SEC == 600 and "tnc/check_sec" not in KEYS
    with pytest.raises(ValueError, match="tnc/check_sec: no such setting"):
        Config.parse("tnc/check_sec", "90")
    with pytest.raises(ValueError, match="tnc/check_sec: no such setting"):
        Config.checked(DEFAULTS, {"tnc/check_sec": "0"})
    assert Config.from_data({"tnc/check_sec": "0", "web/port": "9"}) == Config.from_data({"web/port": "9"}), "a stored 0 is ignored: the keep-alive runs"


def test_what_an_earlier_version_stored_as_the_time_on_the_map_is_ignored() -> None:
    assert DEFAULTS.map_station_hours == 3 and "map/hide_after_min" not in KEYS
    with pytest.raises(ValueError, match="map/hide_after_min: no such setting"):
        Config.parse("map/hide_after_min", "30")
    with pytest.raises(ValueError, match="map/hide_after_min: no such setting"):
        Config.checked(DEFAULTS, {"map/hide_after_min": "30"})
    stored = Config.from_data({"map/hide_after_min": "30"})
    assert not hasattr(stored, "map_hide_after_min") and stored == DEFAULTS, "a stored 30 is ignored: the 3 hours of map/station_hours apply"


def test_a_stored_watchdog_row_from_before_is_ignored() -> None:
    assert Config.from_data({"tnc/watchdog_min": "15", "tnc/check_sec": "90"}) == DEFAULTS
    assert Config.from_data({"tnc/watchdog_min": "15"}) == DEFAULTS


def test_the_status_is_printable_ascii_of_at_most_55_characters_and_empty_is_none() -> None:
    assert MAX_STATUS == 55 and DEFAULTS.station_status == "" and Config.check("station/status", "  ") == ""
    assert Config.check("station/status", " QRV 145.500 ") == "QRV 145.500"
    assert Config.check("station/status", "x" * 55) == "x" * 55, "55 with the time; 62 only without one"
    with pytest.raises(ValueError, match=r"station/status: 56 characters is more than the 55"):
        Config.check("station/status", "x" * 56)
    assert Config.from_data({"station/status": "At the cottage"}).station_status == "At the cottage"
    assert Config.from_data({"station/status": "x" * 60}).station_status == "", "a stored text that is too long falls back to the default, in the log"


@pytest.mark.parametrize("key", ["station/comment", "station/status", "status/template"])
@pytest.mark.parametrize("text", ["a|b", "a~b", "häll", "tab\there"])
def test_the_comment_and_the_status_texts_refuse_the_tnc_switch_characters_and_anything_but_printable_ascii(key: str, text: str) -> None:
    with pytest.raises(ValueError, match=key):
        Config.check(key, text)


def test_the_comment_limit_is_what_the_beacon_will_send() -> None:
    assert (MAX_COMMENT, MAX_COMMENT_PHG) == (43, 36)
    assert [Config(**kw).comment_limit for kw in ({}, {"beacon_power_w": 5})] == [43, 36]
    assert Config(station_comment="x" * 43).comment_problem() == ""
    assert "36 allowed with the PHG" in Config(station_comment="x" * 37, beacon_power_w=1).comment_problem()


def test_a_save_checks_the_comment_against_the_settings_it_is_saved_with() -> None:
    base = Config(station_comment="x" * 43)
    with pytest.raises(ValueError, match=r"station/comment: 43 characters is more than the 36"):
        Config.checked(base, {"beacon/power_w": "5"})
    assert Config.checked(base, {"beacon/power_w": "5", "station/comment": "y" * 36}).comment_limit == 36
    with pytest.raises(ValueError, match="station/comment: 37 characters"):
        Config.checked(Config(beacon_power_w=5), {"station/comment": "z" * 37})
    assert Config.checked(replace(base, beacon_power_w=5), {"web/port": "8000"}).web_port == 8000, "a setting that does not touch the comment is not held up by it"
    with pytest.raises(ValueError, match="station/status: 56 characters"):
        Config.checked(base, {"station/status": "x" * 56})


def test_the_beacon_is_off_or_every_20_minutes_or_more_and_the_status_every_15_and_a_stored_lower_one_is_raised(caplog: pytest.LogCaptureFixture) -> None:
    assert Config.check("beacon/interval_min", "0") == "0" and Config.check("beacon/interval_min", "20") == "20" and Config.check("status/interval_min", "15") == "15"
    for text in ("14", "15", "19"):
        with pytest.raises(ValueError, match=rf"beacon/interval_min: {text} is not 0 \(off\) or between 20 and 1440"):
            Config.check("beacon/interval_min", text)
    with pytest.raises(ValueError, match=r"status/interval_min: 14 is not between 15 and 1440"):
        Config.check("status/interval_min", "14")
    with caplog.at_level(logging.WARNING, logger="neoaprs.config"):
        c = Config.from_data({"beacon/interval_min": "1", "status/interval_min": "5", "web/port": "9"})
        assert (c.beacon_interval_min, c.status_interval_min, c.web_port) == (20, 15, 9)
        assert Config.from_data({"beacon/interval_min": "10"}).beacon_interval_min == 20, "a beacon every 10 minutes, which 0.5.0 allowed, is every 20"
        assert Config.from_data({"beacon/interval_min": "15"}).beacon_interval_min == 20, "a beacon every 15 minutes, which 0.6 allowed, is every 20"
        assert Config.from_data({"beacon/interval_min": "19"}).beacon_interval_min == 20
    assert sum("20 is used" in r.getMessage() for r in caplog.records) == 4 and any("beacon/interval_min" in r.getMessage() for r in caplog.records)
    assert sum("15 is used" in r.getMessage() for r in caplog.records) == 1 and any("status/interval_min" in r.getMessage() for r in caplog.records)
    assert Config.from_data({"beacon/interval_min": "0"}).beacon_interval_min == 0, "an installation that turned the beacon off keeps it off"
    assert Config.from_data({"beacon/interval_min": "20"}).beacon_interval_min == 20 and Config.from_data({"beacon/interval_min": "45"}).beacon_interval_min == 45, "a stored value that is none of the page's choices stays"
    assert [Config.from_data({"beacon/interval_min": t}).beacon_interval_min for t in ("30", "60", "180")] == [30, 60, 180], "the choices of the page"
    assert Config.from_data({}).beacon_interval_min == 0, "the beacon is off unless the station says otherwise: an upgrade never starts transmitting (the setup guide sets 30 for a new station)"
    assert Config.from_data({"status/interval_min": "0"}).status_interval_min == 30, "a status interval of nothing is no number: the default"
    assert Config.from_data({"beacon/interval_min": "x"}).beacon_interval_min == 0


def test_the_power_of_the_phg_is_a_number_or_nothing() -> None:
    assert DEFAULTS.beacon_power_w is None and DEFAULTS.to_data()["beacon/power_w"] == ""
    assert Config.check("beacon/power_w", "") == "" and Config.check("beacon/power_w", "  ") == "" and Config.check("beacon/power_w", " 5 ") == "5" and Config.check("beacon/power_w", "0") == "0"
    assert Config.from_data({"beacon/power_w": ""}).beacon_power_w is None and Config.from_data({"beacon/power_w": "0"}).beacon_power_w == 0
    assert Config.from_data(Config(beacon_power_w=None).to_data()) == Config(beacon_power_w=None)


def test_the_direction_of_the_antenna_is_omni_or_a_point_of_the_compass_written_the_same_way_every_time() -> None:
    assert [Config.check("beacon/antenna_direction", t) for t in ("omni", "OMNI", " Omni ", "n", "ne", "E", "se", "s", "sw", "W", "nw")] == ["omni"] * 3 + ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    with pytest.raises(ValueError, match="omni or one of N NE E SE S SW W NW"):
        Config.check("beacon/antenna_direction", "NNW")


def test_the_antenna_settings_come_with_the_beacons_in_the_order_the_page_lists_them() -> None:
    keys = list(KEYS)
    assert keys[keys.index("station/status") + 1:keys.index("station/status") + 5] == ["beacon/power_w", "beacon/antenna_height_m", "beacon/antenna_gain_db", "beacon/antenna_direction"]


def test_the_tocall_the_position_format_are_not_settings_and_what_an_older_database_stored_for_them_is_ignored() -> None:
    assert not {"beacon/destination", "beacon/compressed", "beacon/dao"} & set(KEYS)
    assert Config.from_data({"beacon/destination": "APRS", "beacon/compressed": "true", "beacon/dao": "true"}) == DEFAULTS
    with pytest.raises(ValueError, match="beacon/destination: no such setting"):
        Config.check("beacon/destination", "APRS")


def test_the_alert_and_status_settings_have_their_defaults_and_are_read_back() -> None:
    assert DEFAULTS.messages_alert is True and DEFAULTS.messages_alert_command == DEFAULT_ALERT_COMMAND and "NEOAPRS_FROM" in DEFAULTS.messages_alert_command
    assert (DEFAULTS.status_rigctld, DEFAULTS.status_interval_min, DEFAULTS.status_template) == ("", 30, "QRV {freq} {mode}")
    assert Config.check("messages/alert_command", "  ") == "" and Config.check("messages/alert_command", " echo hi ") == "echo hi"
    assert Config.check("status/interval_min", " 15 ") == "15" and Config.check("status/interval_min", "1440") == "1440"


def test_the_rigctld_is_a_host_and_a_port_or_nothing() -> None:
    assert DEFAULTS.status_rig_address is None and Config.check("status/rigctld", "  ") == ""
    assert Config(status_rigctld=Config.check("status/rigctld", " 127.0.0.1:4532 ")).status_rig_address == ("127.0.0.1", 4532)
    assert Config(status_rigctld=Config.check("status/rigctld", "[::1]:4532")).status_rig_address == ("::1", 4532)
    assert Config(status_rigctld="shack:65535").status_rig_address == ("shack", 65535)


def test_the_template_names_only_freq_and_mode_and_must_fit_with_the_widest_values() -> None:
    assert Config.check("status/template", "{freq} {mode} QRV") == "{freq} {mode} QRV" and Config.check("status/template", "") == ""
    assert Config.check("status/template", "x" * 55) == "x" * 55
    with pytest.raises(ValueError, match=r"\{frequency\} is not a field"):
        Config.check("status/template", "QRV {frequency}")
    with pytest.raises(ValueError, match="more than the 55 allowed"):
        Config.check("status/template", "{freq} {mode} " + "x" * 36)
    assert Config.check("status/template", "{freq} {mode} " + "x" * 35).endswith("x" * 35), "12 + 1 + 6 + 1 + 35 = 55 with the widest frequency and mode"
    assert fill_template("QRV {freq} {mode} {x} {{", "14.074 MHz", "USB") == "QRV 14.074 MHz USB {x} {{"


# ---- the network switch and the access key

def test_network_access_is_off_by_default_and_a_web_bind_row_that_is_not_the_loopback_turns_it_on_until_the_switch_has_a_row() -> None:
    assert DEFAULTS.web_network is False and DEFAULTS.web_key == "" and "web/bind" not in DEFAULTS.to_data()
    for bind in ("*", "0.0.0.0", "::", "192.168.1.5", "pi"):
        assert Config.from_data({"web/bind": bind}).web_network is True, bind
    for bind in ("", "127.0.0.1", "localhost", "::1", " LOCALHOST "):
        assert Config.from_data({"web/bind": bind}).web_network is False, bind
    assert Config.from_data({"web/bind": "*", "web/network": "false"}).web_network is False, "the switch, once it has a row, wins"
    assert "web/bind" not in Config.from_data({"web/bind": "*"}).to_data()


def test_the_access_key_is_three_groups_of_four_that_are_written_the_same_however_they_were_typed() -> None:
    assert Config.check("web/key", "K7M2 x9pq-4HRT") == "k7m2-x9pq-4hrt" and Config.check("web/key", "k7m2x9pq4hrt") == "k7m2-x9pq-4hrt" and Config.check("web/key", "") == ""
    for bad in ("k7m2-x9pq", "k7m2-x9pq-4hrt-2222", "k7m2-x9pq-4hr0", "k7m2-x9pq-4hrl", "k7m2-x9pq-4hr!"):
        with pytest.raises(ValueError, match="web/key"):
            Config.check("web/key", bad)


# ---- the TNC profile

def test_a_fresh_install_is_sent_no_text_and_a_database_from_before_the_profiles_keeps_what_it_did() -> None:
    assert DEFAULTS.profile.key == "kiss" and DEFAULTS.profile.enter == () and not DEFAULTS.profile.can_probe
    assert Config.from_data({"tnc/enter_kiss": "true"}).tnc_profile == "kenwood-tnc2", "entering KISS was on: the TNC-2 profile enters it the same way"
    assert Config.from_data({"tnc/enter_kiss": "false"}).tnc_profile == "kiss"
    assert Config.from_data({"tnc/enter_kiss": "maybe"}).tnc_profile == "kiss"
    assert Config.from_data({"tnc/enter_kiss": "true", "tnc/profile": "kantronics"}).tnc_profile == "kantronics", "a profile that was chosen wins"
    assert Config.from_data({"tnc/enter_kiss": "true", "tnc/profile": "kiss"}).tnc_profile == "kiss"
    assert "tnc/enter_kiss" not in DEFAULTS.to_data()


def test_the_speed_is_the_settings_else_the_profiles() -> None:
    assert DEFAULTS.tnc_baud == 9600 and replace(DEFAULTS, serial_baud=57600).tnc_baud == 57600
    assert replace(DEFAULTS, tnc_profile="kenwood-d710").tnc_baud == 9600
    assert Config.from_data({"serial/baud": "4800"}).serial_baud == 4800 and Config.from_data({"serial/baud": ""}).serial_baud is None


def test_a_tcp_profile_is_refused_with_a_serial_port_and_accepted_with_a_tcp_address_or_none() -> None:
    base = replace(DEFAULTS, serial_port="/dev/ttyUSB0")
    with pytest.raises(ValueError, match="tnc/profile: .*not to the serial port /dev/ttyUSB0"):
        Config.checked(base, {"tnc/profile": "kiss-tcp"})
    assert Config.checked(base, {"tnc/profile": "kiss-tcp", "serial/port": ""}).tnc_profile == "kiss-tcp"
    assert Config.checked(base, {"tnc/profile": "kiss-tcp", "serial/port": "tcp://127.0.0.1:8100"}).serial_port == "tcp://127.0.0.1:8100"
    tcp = replace(DEFAULTS, tnc_profile="kiss-tcp")
    with pytest.raises(ValueError, match="serial/port: "):
        Config.checked(tcp, {"serial/port": "COM3"})
    assert Config.checked(replace(DEFAULTS, tnc_profile="kenwood-tnc2"), {"serial/port": "socket://localhost:7000"}).serial_port == "socket://localhost:7000", "a serial profile on a socket works as it always did"
    assert Config.checked(DEFAULTS, {"serial/port": "/dev/ttyUSB0"}).serial_port == "/dev/ttyUSB0"


def test_the_update_check_asks_the_page_of_the_project_unless_the_settings_say_otherwise() -> None:
    assert DEFAULTS.update_url == "https://oh2gba.eu/neoaprs/version.php"
    c = Config.from_data({"update/url": " http://127.0.0.1:8000/version.php "})
    assert c.update_url == "http://127.0.0.1:8000/version.php"
    assert Config.check("update/url", "https://example.org/v.php?a=1") == "https://example.org/v.php?a=1"


def test_the_log_time_and_the_update_check_are_fixed_and_what_an_earlier_version_stored_is_ignored() -> None:
    assert LOG_KEEP_DAYS == 7
    for key in ("log/keep_days", "update/check"):
        assert key not in KEYS
        with pytest.raises(ValueError, match=f"{key}: no such setting"):
            Config.parse(key, "false")
    assert Config.from_data({"log/keep_days": "400", "update/check": "false"}) == DEFAULTS


def test_the_digipeater_is_off_unless_the_setting_says_it_is_on() -> None:
    assert DEFAULTS.digi_enabled is False and Config.from_data({"station/call": "OH2GBA"}).digi_enabled is False, "a database from before the setting has none"
    assert Config.from_data({"digi/enabled": "yes"}).digi_enabled is True and Config.check("digi/enabled", "On") == "true"
    assert Config.from_data({"digi/enabled": "perhaps"}).digi_enabled is False


def test_the_attempts_setting_of_an_older_version_is_not_a_setting_and_is_left_alone() -> None:
    assert "messages/attempts" not in KEYS
    assert Config.from_data({"messages/attempts": "9"}) == DEFAULTS
    with pytest.raises(ValueError, match="messages/attempts: no such setting"):
        Config.parse("messages/attempts", "3")


# ---- a moving station: the GPS and how it moves

def test_the_gps_is_off_the_station_is_fixed_and_it_moves_as_a_car_with_dire_wolfs_numbers() -> None:
    c = Config()
    assert (c.gps_source, c.gps_host, c.gps_device, c.gps_baud, c.beacon_travel, c.mobile) == ("off", "127.0.0.1:2947", "", 4800, "car", False)
    assert c.smart == SmartSettings(100, 60, 8, 1800, 30, 15, 255) and c.smart == SmartSettings() and c.smart == PRESETS["car"]


def test_the_gps_source_alone_decides_whether_the_station_moves() -> None:
    assert not Config().mobile and not Config.from_data({"gps/source": "off"}).mobile
    assert Config.from_data({"gps/source": "gpsd"}).mobile and Config.from_data({"gps/source": "serial"}).mobile
    assert Config.checked(DEFAULTS, {"gps/source": "serial"}).mobile and not Config.checked(replace(DEFAULTS, gps_source="gpsd"), {"gps/source": "off"}).mobile


def test_the_presets_are_the_four_ways_of_moving_and_the_car_is_dire_wolfs() -> None:
    assert TRAVEL == ("car", "bicycle", "foot", "boat") == tuple(PRESETS)
    assert PRESETS == {"car": SmartSettings(100, 60, 8, 1800, 30, 15, 255), "bicycle": SmartSettings(30, 60, 4, 1800, 35, 20, 255),
                       "foot": SmartSettings(7, 120, 1.5, 1800, 45, 60, 100), "boat": SmartSettings(40, 60, 3, 1800, 20, 30, 255)}
    for name, preset in PRESETS.items():
        assert preset.fast_kmh > preset.slow_kmh and preset.fast_sec < preset.slow_sec, name
        assert Config.from_data({"beacon/travel": name}).smart == preset


def test_what_the_station_moves_as_is_one_of_four_words_written_in_lower_case() -> None:
    assert Config.check("beacon/travel", " Boat ") == "boat" and Config.check("beacon/travel", "foot") == "foot"
    for bad in ("", "plane", "walk", "mobile"):
        with pytest.raises(ValueError, match="beacon/travel") as e:
            Config.check("beacon/travel", bad)
        assert e.value.code == "setting.not_among" and e.value.params == {"value": bad, "choices": "car, bicycle, foot, boat"}     # type: ignore[attr-defined]
    assert Config.from_data({"beacon/travel": "nonsense"}).beacon_travel == "car", "a stored value that is no preset is the default"
    assert Config.checked(DEFAULTS, {"beacon/travel": "bicycle"}).smart == PRESETS["bicycle"]


def test_the_settings_of_the_smartbeaconing_numbers_and_the_mobile_flag_are_gone() -> None:
    gone = ["beacon/mobile", "smart/fast_kmh", "smart/fast_sec", "smart/slow_kmh", "smart/slow_sec", "smart/turn_min_deg", "smart/turn_min_sec", "smart/turn_slope"]
    assert not set(gone) & set(KEYS) and not set(gone) & RANGES.keys()
    assert Config.from_data({key: "1" for key in gone}) == DEFAULTS
    with pytest.raises(ValueError, match="beacon/mobile: no such setting"):
        Config.check("beacon/mobile", "true")


def test_the_gps_source_is_one_of_three_words_written_in_lower_case() -> None:
    assert Config.check("gps/source", " GPSD ") == "gpsd" and Config.check("gps/source", "serial") == "serial" and Config.check("gps/source", "off") == "off"
    for bad in ("", "usb", "gps", "nmea"):
        with pytest.raises(ValueError, match="gps/source") as e:
            Config.check("gps/source", bad)
        assert e.value.code == "setting.not_among"                                 # type: ignore[attr-defined]
    assert Config.from_data({"gps/source": "nonsense"}).gps_source == "off", "a stored value that is no source is the default"


def test_the_gpsd_address_is_host_and_port_and_the_device_is_a_text() -> None:
    assert Config.check("gps/host", " 10.0.0.7:2947 ") == "10.0.0.7:2947" and Config.check("gps/host", "[::1]:2947") == "[::1]:2947"
    for bad in ("gps", "host:0", "host:70000", "a b:2947"):
        with pytest.raises(ValueError, match="gps/host"):
            Config.check("gps/host", bad)
    assert Config.check("gps/device", " /dev/ttyUSB1 ") == "/dev/ttyUSB1" and Config.check("gps/device", "socket://192.168.1.5:7000") == "socket://192.168.1.5:7000"
    with pytest.raises(ValueError, match="gps/device"):
        Config.check("gps/device", "x" * 256)


@pytest.mark.parametrize(("key", "low", "high"), [
    ("gps/baud", 300, 921600)])
def test_each_number_has_its_range_and_it_is_the_one_the_page_is_told(key: str, low: int, high: int) -> None:
    assert RANGES[key] == (low, high)
    assert Config.check(key, str(low)) == str(low) and Config.check(key, str(high)) == str(high)
    for bad in (low - 1, high + 1, "x", "1.5", ""):
        with pytest.raises(ValueError, match=key):
            Config.check(key, str(bad))


def test_a_gps_source_without_what_it_reads_is_a_valid_setting() -> None:
    serial = Config.checked(DEFAULTS, {"gps/source": "serial"})
    assert (serial.gps_source, serial.gps_device) == ("serial", "")
    assert Config.checked(replace(DEFAULTS, gps_source="gpsd"), {"gps/host": ""}).gps_host == ""
    assert Config.checked(DEFAULTS, {"gps/source": "serial", "gps/device": "/dev/ttyUSB1"}).gps_device == "/dev/ttyUSB1"
    assert Config.checked(DEFAULTS, {"gps/source": "gpsd"}).gps_host == "127.0.0.1:2947"
    assert Config.checked(DEFAULTS, {"gps/source": "off"}).gps_source == "off"


def test_the_mobile_settings_come_after_the_others_in_the_order_the_page_lists_them() -> None:
    assert list(KEYS[-5:]) == ["gps/source", "gps/host", "gps/device", "gps/baud", "beacon/travel"]
