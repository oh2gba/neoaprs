"""web/allowed_hosts: host names and IP addresses separated by commas, nothing else. The certificate and the Host gate take each as it stands, so what is not a name is refused when the setting is saved, and a stored value that is not one leaves the daemon starting with the default."""
import pytest

from neoaprs.config import DEFAULTS, Config, SettingError

KEY = "web/allowed_hosts"
GOOD = ("", "   ", "pi", "pi.local", "Radio-1.example.org", "192.168.1.20", "::1", "[::1]", "fe80::1", "[2001:db8::1]", "a" * 63 + "." + "b" * 63, "10.0.0.1, pi ,[::1]", "my_box")
BAD = ("a b", "x/y", "a@b", "http://x", "a,,b", "a,", ",a", "a?b", "-a", "a-", "a..b", ".a", "café", "a\nb", "fe80::1%eth0", "[1.2.3.4", "1.2.3.4]", "a" * 64, ".".join(["a" * 50] * 6), "a:80", "a.b,c d")


@pytest.mark.parametrize("text", GOOD)
def test_names_and_addresses_are_kept_as_they_were_written(text: str) -> None:
    stored = Config.check(KEY, text)
    assert stored == text.strip()
    assert Config.checked(DEFAULTS, {KEY: text}).web_allowed_hosts == stored


@pytest.mark.parametrize("text", BAD)
def test_anything_else_is_refused_with_the_host_code(text: str) -> None:
    with pytest.raises(SettingError) as e:
        Config.check(KEY, text)
    assert (e.value.key, e.value.code) == (KEY, "setting.not_host") and e.value.params == {"value": text}
    with pytest.raises(SettingError):
        Config.checked(DEFAULTS, {KEY: text})


def test_a_name_of_253_characters_is_the_longest() -> None:
    longest = ".".join(["a" * 61] * 4) + "." + "b" * 5
    assert len(longest) == 253 and Config.check(KEY, longest) == longest
    with pytest.raises(SettingError):
        Config.check(KEY, longest + "c")


@pytest.mark.parametrize("text", ("a b", "http://x", "x/y"))
def test_a_stored_value_that_is_refused_now_leaves_the_daemon_starting_with_the_default(text: str, caplog: pytest.LogCaptureFixture) -> None:
    config = Config.from_data({KEY: text, "station/call": "OH2GBA"})
    assert config.web_allowed_hosts == "" and config.station_call == "OH2GBA" and KEY in caplog.text
