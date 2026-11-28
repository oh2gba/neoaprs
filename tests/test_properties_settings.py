"""Properties of the settings' values (neoaprs/configvalues.py, neoaprs/configtypes.py, the radios' fields): a parser
refuses only with a CodedError whose code the page has words for (ui/src/i18n/en/errors.ts); what it accepts is stored
as text that parses to itself; a save of one value either is refused with such a code or stores that text, and the
stored rows read back as the same settings.
"""

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from neoaprs import configvalues
from neoaprs.coded import CodedError
from neoaprs.config import DEFAULTS, SETTINGS, Config, SettingError
from neoaprs.radiospec import RadioError
from neoaprs.radiotype import stored_text
from neoaprs.radiotypes import TYPES

ROOT = Path(__file__).parent.parent
CODES = frozenset(
    re.findall(r'^\s*"error\.([A-Za-z0-9_.]+)"', (ROOT / "ui/src/i18n/en/errors.ts").read_text(encoding="utf-8"), re.M)
)
PARSERS: dict[str, Callable[[str], Any]] = {
    name: getattr(configvalues, name)
    for name in (
        "device_globs",
        "port_scheme",
        "port_address",
        "digipeater_path",
        "antenna_direction",
        "symbol_table",
        "symbol_code",
        "host_name",
        "host_list",
        "map_source",
        "tnc_profile",
        "hf_profile",
        "mercury_keying",
        "dial_or_empty",
        "aprsis_server",
        "passcode",
    )
}
FIELDS = sorted({(t.key, f.key): f for t in TYPES for f in t.fields}.items())

_PIECES = st.sampled_from(
    [
        "0", "1", "7", "15", "16", "255", "65535", "65536", "-1", "+1", "1e3", "1.5", "60.1699", "-0", "0x1F", "١٢",
        " ", "\t", ",", ":", "/", "*", ".", "-", "[", "]", "%", "//", "://", "\x00", " ", "​",
        "OH2GBA", "oh2gba-7", "WIDE1-1", "DIRECT", "direct", "omni", "nw", "true", "Off", "yes", "vox", "cm108",
        "rts:", "dtr:", "/dev/ttyUSB0", "tcp://", "socket://", "spy://", "bt://", "localhost", "::1", "fe80::1%eth0",
        "127.0.0.1", "MHz", " USB", "28.1800", "http://", "https://", "file:", "rotate.aprs2.net", "plughw:1,0",
        "kiss", "KISS", "d710", "{", "}", "|", "~", "ä", "😀",
    ]
)  # fmt: skip
TEXTS = st.one_of(
    st.text(max_size=30),
    st.lists(_PIECES, max_size=6).map("".join),
    st.integers().map(str),
    st.floats().map(str),
)


def a_page_refusal(e: CodedError) -> None:
    assert e.code in CODES, f"{e.code!r} ({e}) is no code the page words"


@pytest.mark.parametrize("name", sorted(PARSERS))
@settings(max_examples=150)
@given(text=TEXTS)
def test_a_parser_of_configvalues_refuses_by_code_and_normalises_once(name: str, text: str) -> None:
    """Each parser of configvalues raises only CodedError with a page code, and f(f(x)) == f(x)."""
    parse = PARSERS[name]
    try:
        value = parse(text)
    except CodedError as e:
        a_page_refusal(e)
        return
    assert parse(value) == value


@pytest.mark.parametrize("key", [s.key for s in SETTINGS])
@settings(max_examples=100)
@given(text=TEXTS)
def test_a_setting_refuses_by_code_or_stores_text_that_checks_to_itself(key: str, text: str) -> None:
    """Config.check gives a SettingError with a page code, or the stored text, which checks to itself."""
    try:
        stored = Config.check(key, text)
    except SettingError as e:
        a_page_refusal(e)
        return
    assert Config.check(key, stored) == stored


@pytest.mark.parametrize(("where", "field"), FIELDS, ids=[f"{t}-{k}" for (t, k), _ in FIELDS])
@settings(max_examples=60)
@given(text=TEXTS)
def test_a_radios_field_refuses_by_code_or_stores_text_that_parses_to_itself(
    where: tuple[str, str], field: Any, text: str
) -> None:
    """A radio type's field raises only CodedError with a page code; its stored text parses to the same text."""
    try:
        stored = stored_text(field.parse(text))
    except CodedError as e:
        a_page_refusal(e)
        return
    assert stored_text(field.parse(stored)) == stored


@settings(max_examples=400)
@given(st.sampled_from([s.key for s in SETTINGS]), TEXTS)
def test_a_save_of_one_value_is_refused_by_code_or_reads_back_the_same(key: str, text: str) -> None:
    """Config.checked over the defaults refuses with a page code, or holds the value as checked; its rows read back
    as the same settings."""
    try:
        config = Config.checked(DEFAULTS, {key: text})
    except SettingError as e:
        a_page_refusal(e)
        return
    assert config.to_data()[key] == Config.check(key, text)
    again = Config.from_data(config.to_data(), radios=config.radios)
    assert again.to_data() == config.to_data()


@settings(max_examples=200)
@given(st.sampled_from(sorted({f.key for t in TYPES for f in t.fields})), TEXTS)
def test_a_radios_own_value_is_refused_by_code_or_checks_to_itself(key: str, text: str) -> None:
    """Config.check_radio over each radio of the defaults refuses with RadioError of a page code, or gives text that
    checks to itself."""
    for spec in DEFAULTS.radios:
        try:
            stored = Config.check_radio(spec, key, text)
        except RadioError as e:
            a_page_refusal(e)
            continue
        assert Config.check_radio(spec, key, stored) == stored


@pytest.mark.parametrize("key", ["update/url", "map/source"])
def test_an_address_with_an_unclosed_bracket_is_refused_as_no_web_address(key: str) -> None:
    with pytest.raises(SettingError) as refused:
        Config.check(key, "A://[")
    assert refused.value.code == "setting.not_web_address"
