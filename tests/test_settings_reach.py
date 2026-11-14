"""Where the text of a setting ends up. A setting whose text ends in a command line, a file path, a URL or a port is read by a place that knows more than the program means (pyserial opens a file for a `spy://`
address, a tool takes a word that starts with a dash for an option). For each such setting `REACH` holds what that place would misread, and a generated text must not both pass the setting's check and be one of
those. A setting that is not listed anywhere, and accepts a text that is hostile to one of those places, fails `test_every_free_text_setting_is_classified`: a new setting of such a kind is found there."""
import pkgutil
from collections.abc import Callable
from urllib.parse import urlsplit

import pytest
import serial.urlhandler  # type: ignore[import-untyped]
from hypothesis import given, strategies as st

from neoaprs.config import BY_KEY, KEYS, SETTINGS, Config
from neoaprs.configvalues import PORT_SCHEMES

HANDLERS = tuple(name.removeprefix("protocol_") for _, name, _ in pkgutil.iter_modules(serial.urlhandler.__path__))     # every scheme this pyserial reads
SCHEMES = HANDLERS + PORT_SCHEMES + ("file", "http", "https", "ftp", "javascript", "data")


def port_misread(value: str) -> bool:
    """pyserial reads the scheme of `value` in lower case and hands the rest to the handler of that scheme; a scheme the program does not mean is a misreading."""
    lowered = value.lower()
    return "://" in lowered and lowered.split("://", 1)[0] not in PORT_SCHEMES


def source_misread(value: str) -> bool:
    """map/source is where the cut reads the map from: not a word that starts with a dash, no control character, and an address only an http or https one."""
    return value.startswith("-") or not value.isprintable() or ("://" in value and (urlsplit(value).scheme not in ("http", "https") or " " in value))


def update_url_misread(value: str) -> bool:
    parts = urlsplit(value)
    return parts.scheme not in ("http", "https") or not parts.netloc or any(c.isspace() for c in value) or not value.isprintable()


def pattern_misread(value: str) -> bool:
    """serial/pattern is a list of absolute globs: a word that is not one is listened to relative to wherever the daemon runs."""
    parts = value.split()
    return not parts or any(not part.startswith("/") for part in parts)


def hosts_misread(value: str) -> bool:
    """web/allowed_hosts are names, which the certificate and the Host gate take as they are."""
    return any(not name or any(c in name for c in " /\\@?#") or "://" in name for name in (part.strip() for part in value.split(",")) if value.strip())


REACH: dict[str, Callable[[str], bool]] = {         # setting -> whether the stored text would be misread by the place it ends in
    "serial/port": port_misread,
    "serial/last_port": port_misread,
    "gps/device": port_misread,
    "map/source": source_misread,
    "update/url": update_url_misread,
    "messages/alert_command": lambda value: not value.isprintable(),          # a shell line is one line; what is in it is the operator's, and who may set it is decided where the setting is saved
    "serial/pattern": pattern_misread,
    "web/allowed_hosts": hosts_misread,
}
GAPS: dict[str, Callable[[str], bool]] = {}          # settings whose check lets through what the place misreads: each is held to stay a gap until it is closed, and then moves to REACH
OTHER_TEXT = frozenset({                            # free text that ends in none of the four: why, per key
    "tcp/host",                                     # always put behind `socket://` and a port
    "serial/skip",                                  # only compared with the names of ports, never opened
    "mercury/sound_card", "mercury/keying",         # one argument of the modem's program, which takes the next word for the value
    "station/comment", "station/status", "status/template",     # text for the air or for the page
    "beacon/path", "igate/server", "gps/host", "status/rigctld",     # calls, and host:port pairs checked as such
})
PROBES = ("spy:///dev/ttyUSB0?file=/tmp/x", "-x", "$(x)", "file:///x", "x://y", "a b", "a\nb", "../x")


def passes(key: str, text: str) -> str | None:
    """The stored text when the setting accepts `text`, else None."""
    try:
        return Config.check(key, text)
    except ValueError:
        return None


def texts() -> st.SearchStrategy[str]:
    """Free text, and text built to look like what the places read: an address of every scheme pyserial has (in any case), a word that starts with a dash, blanks and controls round or inside."""
    scheme = st.sampled_from(SCHEMES).map(lambda s: "".join(c.upper() if i % 2 else c for i, c in enumerate(s)))
    free = st.text(max_size=60)
    return st.one_of(
        free,
        st.builds(lambda s, rest: f"{s}://{rest}", scheme, free),
        st.builds(lambda pad, s, rest: f"{pad}{s}://{rest}", st.sampled_from([" ", "\t", "\n", "\u00a0"]), scheme, free),
        st.builds(lambda head, rest: head + rest, st.sampled_from(["-", "--", "/", "/dev/", "//", "http://", "https://", "COM", "socket://"]), free),
        st.builds(lambda a, b: f"{a}://{b}", free, free),
    )


def test_the_tables_name_only_settings_that_exist_and_each_once() -> None:
    listed = [*REACH, *GAPS, *OTHER_TEXT]
    assert len(listed) == len(set(listed)) and set(listed) <= set(KEYS)


@pytest.mark.parametrize("key", sorted(REACH))
@given(text=texts())
def test_no_text_passes_the_check_of_a_setting_and_is_misread_where_it_ends(key: str, text: str) -> None:
    stored = passes(key, text)
    assert stored is None or not REACH[key](stored), f"{key} lets {stored!r} through"


def test_every_free_text_setting_is_classified() -> None:
    """A setting that is in no table and takes a text that is hostile to a port, a path or a URL is a new setting of one of those kinds: classify it, and give it a check."""
    unlisted = [s.key for s in SETTINGS if s.key not in REACH and s.key not in GAPS and s.key not in OTHER_TEXT]
    accepting = {key: [p for p in PROBES if passes(key, p) is not None] for key in unlisted}
    assert {key: found for key, found in accepting.items() if found} == {}, "these settings take a text that a port, a path or a URL would misread: add them to REACH with what is misread"


def test_the_setting_list_is_what_the_tables_are_checked_against() -> None:
    assert tuple(BY_KEY) == KEYS and "spy" in HANDLERS and "alt" in HANDLERS
