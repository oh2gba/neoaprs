"""Every setting that the page does not show is on one list, here, with its reason, and a setting that can stop something the page offers is never on it.

0.9 took the Transmit switch off the page while `station/transmit` went on acting, and a station that had been switched off was left in RX only with no way back on the page. The rule since: a setting that can block a feature stays
reachable on the page, or a migration resets it when its control is removed (CONVENTIONS.md, "Removing a control from the page").

A radio's own settings (`radio/<id>/<key>`) are read from the types' field lists (neoaprs/radiotypes): until the page names a radio by its id, a field is on the page through the flat key of radios 1
and 2 that is its view (configradios.FLAT_HOMES), or it is listed in `NOT_YET_ON_THE_PAGE` with why that blocks nothing."""
import re

from neoaprs.config import SETTINGS
from neoaprs.configradios import FLAT_HOMES
from neoaprs.radiotypes import TYPES
from tests.conftest import ROOT

KEY_OF_BEFORE = {FLAT_HOMES[s.attr]: s.key for s in SETTINGS if s.attr in FLAT_HOMES}      # (radio, its column or own key) -> the key of before that is its view in Config (configradios.FLAT_HOMES)

SETTINGS_TS = ROOT / "ui" / "src" / "lib" / "settings.ts"

# What the page leaves to `neoaprs db set`, each with why it blocks nothing. A new entry needs its reason here and its place in NOT_ON_THE_PAGE of ui/src/lib/settings.ts.
NOT_ON_THE_PAGE = {
    "update/url": "where the daily check asks; the check is always on and a wrong address only shows no newer version",
    "serial/pattern": "which ports the search for the radio looks at; a port that is named works whatever it says",
    "serial/skip": "which ports the search leaves alone; a port that is named works whatever it says",
    "web/port": "the page's own port; the daemon moves to a free one and says which in the log",
    "web/allowed_hosts": "the host names the page answers to; the default suits nearly everyone and the log says a refusal",
    "igate/server": "the APRS-IS server of the Internet switch; a wrong one only leaves the switch connecting, which the page says",
    "igate/password": "only adds gating; its absence never blocks anything",
    "map/maxzoom": "the detail of the detailed map; any value works",
    "map/source": "where the detailed map is made from; a wrong one makes the download say so",
}

# What stops something the page offers when it is changed: each has its control on the page.
BLOCKERS = (
    "station/transmit",
    "station/call",
    "beacon/interval_min",
    "status/source",
    "digi/enabled",
    "igate/enabled",
    "messages/alert",
    "tnc/profile",
    "serial/port",
    "tcp/host",
    "tcp/port",
    "web/network",
)

MESSAGE = "a setting that can block a feature must stay reachable on the page, or a migration must reset it when its control is removed"


def page_leaves_out() -> set[str]:
    text = SETTINGS_TS.read_text(encoding="utf-8")
    block = re.search(r"const NOT_ON_THE_PAGE: readonly string\[\] = \[(.*?)\];", text, re.S)
    assert block, "ui/src/lib/settings.ts lost NOT_ON_THE_PAGE"
    return set(re.findall(r'"([a-z_]+/[a-z_]+)"', block.group(1)))


def test_the_settings_the_page_leaves_out_are_the_ones_listed_here_each_with_its_reason() -> None:
    assert page_leaves_out() == set(NOT_ON_THE_PAGE), "ui/src/lib/settings.ts (NOT_ON_THE_PAGE) and tests/test_settings_reachable.py must list the same settings"
    assert all(reason.strip() for reason in NOT_ON_THE_PAGE.values())
    keys = {s.key for s in SETTINGS}
    assert set(NOT_ON_THE_PAGE) <= keys, "a listed setting is gone from neoaprs/config.py"


def test_a_setting_that_can_block_a_feature_is_not_left_off_the_page() -> None:
    keys = {s.key for s in SETTINGS}
    assert set(BLOCKERS) <= keys
    left_out = sorted(set(BLOCKERS) & (set(NOT_ON_THE_PAGE) | page_leaves_out()))
    assert not left_out, f"{MESSAGE}: {left_out}"


# ---- a radio's own settings, from the types' field lists

# The fields of a radio that no flat key shows, each with why its absence from the page blocks nothing.
NOT_YET_ON_THE_PAGE = {
    "beacon": "a radio's own Send on tick: every radio that is on sends the beacon in this version, whatever it says",
}

# The fields that stop something the page offers when they are changed: each is on the page (through its flat key until the page names a radio).
RADIO_BLOCKERS = ("port", "tcp_host", "tcp_port", "digipeat", "sound_card", "keying")


def field_keys() -> set[str]:
    return {f.key for t in TYPES for f in t.fields}


def on_the_page(key: str) -> bool:
    """Whether a radio's field is on the page: the flat key that is its view, for some radio, is a setting the page shows."""
    return any(own == key and flat not in page_leaves_out() and flat not in NOT_ON_THE_PAGE for (_, own), flat in KEY_OF_BEFORE.items())


def test_every_field_of_every_type_is_on_the_page_or_listed_here_with_its_reason() -> None:
    keys = field_keys()
    assert set(NOT_YET_ON_THE_PAGE) <= keys and all(reason.strip() for reason in NOT_YET_ON_THE_PAGE.values()), "a listed field is gone from the types"
    assert sorted(key for key in keys if not on_the_page(key) and key not in NOT_YET_ON_THE_PAGE) == [], "a field of a type that the page cannot reach: give it its control, or its reason here"
    assert not [key for key in NOT_YET_ON_THE_PAGE if on_the_page(key)], "a field that the page shows is not to be listed"


def test_a_field_that_can_block_a_feature_is_on_the_page() -> None:
    assert set(RADIO_BLOCKERS) <= field_keys()
    assert [key for key in RADIO_BLOCKERS if not on_the_page(key)] == [], MESSAGE
