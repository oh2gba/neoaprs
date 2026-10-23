"""The settings (neoaprs/config.py): the defaults, the text of each key and back, and a wrong value that falls back to its default and is told with its key."""
import logging
from dataclasses import fields, replace

import pytest

from neoaprs.config import BY_KEY, DEFAULT_ALERT_COMMAND, DEFAULTS, KEYS, MAX_COMMENT, MAX_COMMENT_COMPRESSED, MAX_COMMENT_PHG, MAX_STATUS, SETTINGS, Config, fill_template


def test_the_defaults_are_the_ones_of_the_brief() -> None:
    assert DEFAULTS.to_data() == {
        "tnc/profile": "kiss", "serial/port": "", "serial/baud": "", "tcp/host": "127.0.0.1", "tcp/port": "8001", "serial/last_port": "", "serial/pattern": "/dev/serial/by-id/* /dev/ttyUSB* /dev/ttyACM*", "serial/skip": "", "tnc/check_sec": "60", "station/call": "", "station/lat": "", "station/lon": "",
        "station/symbol_table": "/", "station/symbol_code": "-", "station/comment": "NeoAPRS", "station/status": "", "beacon/power_w": "", "beacon/antenna_height_m": "0", "beacon/antenna_gain_db": "0",
        "beacon/antenna_direction": "omni", "log/keep_days": "30", "web/network": "false", "web/key": "", "web/port": "7303", "web/allowed_hosts": "", "beacon/interval_min": "0",
        "beacon/path": "WIDE1-1,WIDE2-1", "beacon/destination": "APZNEO", "beacon/compressed": "false", "beacon/dao": "false",
        "messages/alert": "true", "messages/alert_command": DEFAULT_ALERT_COMMAND, "status/rigctld": "", "status/interval_min": "30", "status/template": "QRV {freq} {mode}",
        "map/hide_after_min": "180", "map/radius_km": "150", "map/maxzoom": "12", "map/source": "",
        "update/check": "true", "update/url": "https://oh2gba.eu/neoaprs/version.php"}
    assert Config() == DEFAULTS


def test_every_field_has_a_key_and_every_key_a_field() -> None:
    assert [s.attr for s in SETTINGS] == [f.name for f in fields(Config)]
    assert len(set(KEYS)) == len(KEYS) == len(BY_KEY)


def test_nothing_in_the_database_is_the_defaults_and_what_is_written_is_read_back() -> None:
    assert Config.from_data({}) == DEFAULTS
    c = Config(serial_port="/dev/brainbox_3", serial_baud=19200, serial_last_port="/dev/brainbox_3", serial_pattern="/dev/brainbox_* /dev/ttyUSB*", serial_skip="/dev/brainbox_2, /dev/ttyUSB1", tnc_profile="kenwood-d710", tcp_host="::1", tcp_port=8100, tnc_check_sec=0, station_call="OH2GBA-9", station_lat=-33.5, station_lon=151.25,
               station_symbol_table="\\", station_symbol_code=">", station_comment="mobile", station_status="On the road, QRV 145.500", beacon_power_w=5, beacon_antenna_height_m=12, beacon_antenna_gain_db=3, beacon_antenna_direction="NW", log_keep_days=7, web_network=True, web_key="k7m2-x9pq-4hrt", web_port=8080, web_allowed_hosts="aprs.example, pi", beacon_interval_min=30,
               beacon_path="WIDE2-2", beacon_destination="APRS", beacon_compressed=True, beacon_dao=True, messages_alert=False, messages_alert_command="echo $NEOAPRS_FROM", status_rigctld="localhost:4532", status_interval_min=1440, status_template="{mode} {freq}", map_hide_after_min=10080)
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
    ("station/comment", "åäö"), ("station/status", "x" * 63), ("station/status", "å" * 32), ("station/status", "two\nlines"), ("log/keep_days", "0"), ("web/key", "two words"), ("web/key", "abcd-efgh-jklm0"), ("web/network", "maybe"), ("web/port", "-1"), ("web/port", "70000"), ("web/allowed_hosts", "x" * 501), ("beacon/interval_min", "-1"),
    ("beacon/interval_min", "1441"), ("beacon/path", "WIDE1-1,TOOLONGCALL"), ("beacon/path", "A,B,C,D,E,F,G,H,I"), ("beacon/path", "WIDE1-16"), ("beacon/destination", "APZNEO-1"),
    ("beacon/destination", "TOOLONGCALL"), ("beacon/destination", ""), ("beacon/compressed", "sometimes"),
    ("beacon/power_w", "-1"), ("beacon/power_w", "10000"), ("beacon/power_w", "lots"), ("beacon/antenna_height_m", "-1"), ("beacon/antenna_height_m", "10000"), ("beacon/antenna_height_m", "tall"), ("beacon/antenna_gain_db", "10"),
    ("beacon/antenna_gain_db", "-1"), ("beacon/antenna_gain_db", "3.5"), ("beacon/antenna_direction", "up"), ("beacon/antenna_direction", "NNE"), ("beacon/antenna_direction", ""), ("beacon/dao", "maybe"),
    ("tnc/check_sec", "-1"), ("tnc/check_sec", "5"), ("tnc/check_sec", "9"), ("tnc/check_sec", "3601"), ("tnc/check_sec", "soon"), ("update/check", "sometimes"), ("update/url", ""), ("update/url", "ftp://example.org/v.php"), ("update/url", "https://"), ("update/url", "two words"), ("update/url", "https://example.org/" + "x" * 500), ("map/hide_after_min", "-1"), ("map/hide_after_min", "10081"), ("map/hide_after_min", "never"),
    ("messages/alert", "loud"), ("messages/alert_command", "x" * 1001), ("messages/alert_command", "two\nlines"), ("status/rigctld", "localhost"), ("status/rigctld", "localhost:0"), ("status/rigctld", "localhost:70000"),
    ("status/rigctld", ":4532"), ("status/rigctld", "two words:4532"), ("status/interval_min", "0"), ("status/interval_min", "1441"), ("status/interval_min", "often"), ("status/template", "QRV {frequency}"),
    ("status/template", "x" * 63), ("status/template", "{freq} {mode} " + "x" * 50), ("status/template", "two\nlines")])
def test_a_wrong_value_names_its_key_in_the_error_and_falls_back_to_the_default_with_a_log_line(key: str, text: str, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(ValueError, match=key):
        Config.check(key, text)
    caplog.set_level(logging.WARNING, "neoaprs.config")
    c = Config.from_data({key: text, "log/keep_days" if key != "log/keep_days" else "web/port": "7"})
    assert c.to_data()[key] == DEFAULTS.to_data()[key]
    assert any(key in r.getMessage() and "default" in r.getMessage() for r in caplog.records)
    assert 7 in (c.log_keep_days, c.web_port), "the other values are kept"


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
    assert Config.check("beacon/path", "") == "" and Config.from_data({"beacon/path": ""}).beacon_path_calls == ()
    assert Config.from_data({"beacon/path": "wide1-1,,wide2-1,"}).beacon_path_calls == ("WIDE1-1", "WIDE2-1")
    assert DEFAULTS.beacon_path_calls == ("WIDE1-1", "WIDE2-1")
    assert Config.check("beacon/path", ",".join(["WIDE1-1"] * 8)).count(",") == 7


def test_the_destination_of_the_beacon_is_a_call_without_an_ssid() -> None:
    assert Config.check("beacon/destination", "apzneo") == "APZNEO" and Config.check("beacon/destination", "APRS") == "APRS"
    with pytest.raises(ValueError, match="beacon/destination.*SSID"):
        Config.check("beacon/destination", "APRS-1")


def test_the_keep_alive_and_the_map_timeout_take_their_whole_range() -> None:
    assert (DEFAULTS.tnc_check_sec, DEFAULTS.map_hide_after_min) == (60, 180)
    c = Config.from_data({"tnc/check_sec": "0", "map/hide_after_min": "0"})
    assert (c.tnc_check_sec, c.map_hide_after_min) == (0, 0), "0 is off, and never"
    c = Config.from_data({"tnc/check_sec": " 3600 ", "map/hide_after_min": "10080"})
    assert (c.tnc_check_sec, c.map_hide_after_min) == (3600, 10080)
    assert Config.check("tnc/check_sec", " 10 ") == "10" and Config.check("map/hide_after_min", "007") == "7"


def test_a_stored_watchdog_row_from_before_is_ignored() -> None:
    assert Config.from_data({"tnc/watchdog_min": "15", "tnc/check_sec": "90"}).tnc_check_sec == 90
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
    assert (MAX_COMMENT, MAX_COMMENT_PHG, MAX_COMMENT_COMPRESSED) == (43, 36, 40)
    assert [Config(**kw).comment_limit for kw in ({}, {"beacon_power_w": 5}, {"beacon_compressed": True}, {"beacon_compressed": True, "beacon_power_w": 5}, {"beacon_dao": True})] == [43, 36, 40, 40, 43]
    assert Config(station_comment="x" * 43).comment_problem() == "" and Config(station_comment="x" * 43, beacon_dao=True).comment_problem() == "", "the DAO is on top"
    assert "36 allowed with the PHG" in Config(station_comment="x" * 37, beacon_power_w=1).comment_problem()
    assert "40 allowed with a compressed position" in Config(station_comment="x" * 41, beacon_compressed=True).comment_problem()
    assert Config(station_comment="x" * 40, beacon_compressed=True, beacon_power_w=1).comment_problem() == "", "no PHG is sent after a compressed position"


def test_a_save_checks_the_comment_against_the_settings_it_is_saved_with() -> None:
    base = Config(station_comment="x" * 43)
    with pytest.raises(ValueError, match=r"station/comment: 43 characters is more than the 36"):
        Config.checked(base, {"beacon/power_w": "5"})
    with pytest.raises(ValueError, match=r"station/comment: 43 characters is more than the 40"):
        Config.checked(base, {"beacon/compressed": "true"})
    assert Config.checked(base, {"beacon/power_w": "5", "station/comment": "y" * 36}).comment_limit == 36
    assert Config.checked(base, {"beacon/compressed": "true", "station/comment": "y" * 40}).beacon_compressed
    with pytest.raises(ValueError, match="station/comment: 37 characters"):
        Config.checked(Config(beacon_power_w=5), {"station/comment": "z" * 37})
    assert Config.checked(replace(base, beacon_power_w=5), {"web/port": "8000"}).web_port == 8000, "a setting that does not touch the comment is not held up by it"
    with pytest.raises(ValueError, match="station/status: 56 characters"):
        Config.checked(base, {"station/status": "x" * 56})


def test_the_intervals_are_off_or_at_least_ten_minutes_and_a_stored_lower_one_is_raised_to_ten(caplog: pytest.LogCaptureFixture) -> None:
    assert Config.check("beacon/interval_min", "0") == "0" and Config.check("beacon/interval_min", "10") == "10" and Config.check("status/interval_min", "10") == "10"
    with pytest.raises(ValueError, match=r"beacon/interval_min: 9 is not 0 \(off\) or between 10 and 1440"):
        Config.check("beacon/interval_min", "9")
    with pytest.raises(ValueError, match=r"status/interval_min: 9 is not between 10 and 1440"):
        Config.check("status/interval_min", "9")
    with caplog.at_level(logging.WARNING, logger="neoaprs.config"):
        c = Config.from_data({"beacon/interval_min": "1", "status/interval_min": "5", "web/port": "9"})
        assert (c.beacon_interval_min, c.status_interval_min, c.web_port) == (10, 10, 9)
    assert sum("10 is used" in r.getMessage() for r in caplog.records) == 2 and any("beacon/interval_min" in r.getMessage() for r in caplog.records)
    assert Config.from_data({"beacon/interval_min": "0"}).beacon_interval_min == 0
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


def test_the_antenna_and_dao_settings_come_with_the_beacons_in_the_order_the_page_lists_them() -> None:
    keys = list(KEYS)
    assert keys[keys.index("station/status") + 1:keys.index("station/status") + 5] == ["beacon/power_w", "beacon/antenna_height_m", "beacon/antenna_gain_db", "beacon/antenna_direction"]
    assert keys[keys.index("beacon/compressed") + 1] == "beacon/dao"


def test_the_alert_and_status_settings_have_their_defaults_and_are_read_back() -> None:
    assert DEFAULTS.messages_alert is True and DEFAULTS.messages_alert_command == DEFAULT_ALERT_COMMAND and "NEOAPRS_FROM" in DEFAULTS.messages_alert_command
    assert (DEFAULTS.status_rigctld, DEFAULTS.status_interval_min, DEFAULTS.status_template) == ("", 30, "QRV {freq} {mode}")
    assert Config.check("messages/alert_command", "  ") == "" and Config.check("messages/alert_command", " echo hi ") == "echo hi"
    assert Config.check("status/interval_min", " 10 ") == "10" and Config.check("status/interval_min", "1440") == "1440"


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


def test_the_update_check_is_on_and_asks_the_page_of_the_project_unless_the_settings_say_otherwise() -> None:
    assert DEFAULTS.update_check is True and DEFAULTS.update_url == "https://oh2gba.eu/neoaprs/version.php"
    c = Config.from_data({"update/check": "off", "update/url": " http://127.0.0.1:8000/version.php "})
    assert (c.update_check, c.update_url) == (False, "http://127.0.0.1:8000/version.php")
    assert Config.check("update/check", "No") == "false" and Config.check("update/url", "https://example.org/v.php?a=1") == "https://example.org/v.php?a=1"


def test_the_attempts_setting_of_an_older_version_is_not_a_setting_and_is_left_alone() -> None:
    assert "messages/attempts" not in KEYS
    assert Config.from_data({"messages/attempts": "9"}) == DEFAULTS
    with pytest.raises(ValueError, match="messages/attempts: no such setting"):
        Config.parse("messages/attempts", "3")
