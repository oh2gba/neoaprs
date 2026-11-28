"""Nothing is left of the wire that named radios 1 and 2 by the words `fm` and `hf`: no topic `tnc`
or `hf`, no `hf_*` command or `message_radio`, no row field saying a radio by its word, no flat
radio key in `config`.
"""

import importlib.util
import re
from pathlib import Path

from pydantic import BaseModel

import pytest

from neoaprs.chain import Attempt
from neoaprs.config import BY_KEY, DEFAULTS
from neoaprs.configradios import FLAT_HOMES
from neoaprs.controller import Controller
from neoaprs.message import MessageRecord
from neoaprs.ownobject import OwnObject
from neoaprs.packet import Packet
from neoaprs.radioregistry import LiveRadio
from neoaprs.station import Station
from neoaprs.tnc import Tnc
from neoaprs.tncprofile import Profile
from neoaprs.web.hostwire import Status
from neoaprs.web.messagewire import AttemptRow, MessageRow
from neoaprs.web.ownwire import ObjectSet, OwnObjectRow
from neoaprs.web.packetwire import PacketRow
from neoaprs.web.protocol import COMMAND_NAMES, TOPIC_NAMES
from neoaprs.web.radiowire import RadioScope
from neoaprs.web.stationwire import StationRow
from neoaprs.web.views import CONFIG_KEYS, config_values

ROOT = Path(__file__).resolve().parent.parent
HF_BEACON, SIDES, RADIOS_ON = "hf_beacon", "radiosides", "useRadiosOn"
# A station's counts and times of radios 1 and 2 by the words of before
HEARD_OLD = r"\bheard_" r"(fm|hf)\b|\blast_" r"(fm|hf)_at\b"
# The rules of a kind beside its type, the set of two of before
RULES_OLD = (
    r"\bRadio"
    r"Rules\b|\bradio"
    r"rules\b|\bneoaprs\.radios\b|\bfrom neoaprs import radios\b|\bhf_is_"
    r"(mercury|dummy)\b"
)
# The values' old words and the constructors that took them
WORDS_OLD = r"\bid_of" r"_word\b|\bold_" r"keywords\b|\bOBJECT_" r"RADIOS\b|\bradios_of" r"_word\b"
SEED_OLD = (
    r"\b_stand"
    r"_in\b|\bseed_"
    r"radios\b|\bseed_"
    r"rows\b|\bSeed"
    r"Row\b|\bkeep_"
    r"unknown\b|\bold_carries"
    r"_path\b|\bFLAT_KEY"
    r"_OF\b|\bflat_"
    r"home\b|\bflat_"
    r"view\b"
    # The stand-in and the seed of before, and the command line's and the drivers' flat view
    r"|\btnc_"
    r"settings\b|\bhf_"
    r"settings\b|\bhf_"
    r"words\b|radioedits\.(seed|stand_in|held|new_id)\b"
)
OLD = re.compile(
    rf"\bctl\.(tnc|hf|mercury|beacon|{HF_BEACON})\b|{HF_BEACON}|{SIDES}|{RADIOS_ON}|{HEARD_OLD}|{RULES_OLD}|{WORDS_OLD}|{SEED_OLD}"
)
SEARCHED = ("neoaprs", "ui/src", "tests", "scripts")
# The frozen migration steps, their tests and the count of the columns of before
FROZEN = (
    "neoaprs/migrationsteps*.py",
    "tests/test_migration*.py",
    "tests/support/migrated*.py",
    "scripts/migration-size",
)
# the page's reading of the topics of before and of the row fields of before
PAGE_OLD = re.compile(r"""topic: ["'](tnc|hf)["']|\.(tnc|hf)\.value\b|\bheard_(fm|hf)\b|\blast_(fm|hf)_at\b""")
# the scripts' readers of the wire of before (the topics `tnc` and `hf`, the flat keys, a station's
# count by the word of its kind); update-e2e's `serial/port` is the old release's key and stays
SCRIPTS_OLD = re.compile(r"""OLD_(TOPICS|KEYS)\b|topics\.get\(["'](tnc|hf)["']|["']tnc["'] if kind|f["']heard_\{""")
# the one reader of the wire of before that stays: update-e2e runs an old release (version A, from
# before the round of the radios, which tells the FM radio in the topic `tnc` alone) before the new
# one
OLD_RELEASE_READER = ROOT / "scripts" / "update-e2e.py"
# what the documents may not name: the topics, the state, the commands and the beacon of before
DOC_OLD = re.compile(
    r"topic `(tnc|hf)`|\bTnc"
    r"State\b|\bRadio"
    r"Rules"
    r"(State)?\b|\bradio"
    r"rules\b|\bradio"
    r"s\.py\b|\bhf_(tune|key_test|scope|frequencies)\b|\bmessage_"
    rf"radio\b|\b{HF_BEACON}\b"
)
DOCS = (ROOT / "PROTOCOL.md", *sorted((ROOT / "docs").rglob("*.md")))
# The page's bundle, which scripts/build-page writes from ui/src
BUILT = ROOT / "neoaprs" / "page"
FLAT = {key for key, setting in BY_KEY.items() if setting.attr in FLAT_HOMES}


def fields(model: type[BaseModel]) -> set[str]:
    return set(model.model_fields)


def test_the_wire_has_no_topic_no_command_and_no_field_of_the_radios_of_before() -> None:
    assert not {"tnc", "hf"} & set(TOPIC_NAMES)
    assert not {"hf_tune", "hf_key_test", "hf_scope", "hf_frequencies", "message_radio"} & COMMAND_NAMES
    assert not {"heard_fm", "heard_hf", "last_fm_at", "last_hf_at", "message_radio"} & fields(StationRow)
    assert "radio" not in fields(PacketRow) | fields(MessageRow) | fields(AttemptRow) | fields(OwnObjectRow) | fields(
        ObjectSet
    )
    assert not {f"{HF_BEACON}_last_sent", f"{HF_BEACON}_next_due"} & fields(Status)
    assert "named" not in fields(RadioScope), "every frame of a scope names its radio"
    assert (
        {"radio_id"} <= fields(PacketRow) & fields(MessageRow) & fields(AttemptRow)
        and "radios" in fields(OwnObjectRow) & fields(ObjectSet)
        and "heard" in fields(StationRow)
    )


def test_the_config_topic_tells_no_flat_key_of_a_radio() -> None:
    told = config_values(DEFAULTS, [])
    assert not FLAT & set(told["values"]) and not FLAT & set(told["defaults"]) and not FLAT & set(CONFIG_KEYS)
    assert all(key.startswith(("radio/", "pair/")) or key == "email/radio" for key in told["radio_values"]), (
        "the radios' own keys, the pairs' of two radios, and the mail's radio"
    )


def test_the_controller_has_no_name_of_its_own_for_radio_1_or_2(tmp_path: Path) -> None:
    ctl = Controller(tmp_path)
    assert not [name for name in ("tnc", "hf", "mercury", "beacon", HF_BEACON) if hasattr(ctl, name)], (
        "a radio is the registry's (ctl.radios), by its id"
    )


def finds(paths: list[Path], pattern: re.Pattern[str]) -> list[str]:
    """The lines of these files that the pattern finds, as `path:line`."""
    found = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        found += [
            f"{path.relative_to(ROOT)}:{n}" for n, line in enumerate(text.splitlines(), 1) if pattern.search(line)
        ]
    return found


def sources(*tops: str) -> list[Path]:
    return [
        path
        for top in tops
        for path in sorted((ROOT / top).rglob("*"))
        if path.is_file() and path.suffix in (".py", ".ts", ".vue", "") and BUILT not in path.parents
    ]


def frozen(path: Path) -> bool:
    return any(path.relative_to(ROOT).match(pattern) for pattern in FROZEN)


@pytest.mark.slow("reads every source file of the repository")
def test_no_source_names_the_wire_or_the_views_of_before() -> None:
    # This file names the old words to search for them, so the scan leaves it out
    assert finds([path for path in sources(*SEARCHED) if not frozen(path) and path != Path(__file__)], OLD) == []
    assert (
        not (ROOT / "ui" / "src" / "lib" / f"{SIDES}.ts").exists()
        and not (ROOT / "ui" / "src" / "composables" / f"{RADIOS_ON}.ts").exists()
    )


def test_no_value_of_the_daemon_says_a_radio_by_its_word_and_no_rules_stand_beside_the_type() -> None:
    assert not [
        name for name in ("heard_fm", "heard_hf", "last_fm_at", "last_hf_at", "message_radio") if hasattr(Station, name)
    ], "what each radio heard is `heard_by`, by the radio's id"
    assert not [
        value.__name__ for value in (Packet, MessageRecord, Attempt) if hasattr(value, "radio")
    ] and not hasattr(OwnObject, "radio"), "a radio is its id (`radio_id`, an object's `radios`)"
    assert not [value.__name__ for value in (Tnc, LiveRadio, Profile) if hasattr(value, "rules")] and not hasattr(
        Profile, "max_frame"
    ), "the kind, the limits and what is allowed are the type's (`rtype`)"
    assert importlib.util.find_spec("neoaprs.radiorules") is None and importlib.util.find_spec("neoaprs.radios") is None


def test_the_page_reads_no_topic_and_no_row_field_of_before() -> None:
    assert finds(sources("ui/src"), PAGE_OLD) == []


def test_the_scripts_read_no_topic_and_no_key_of_before() -> None:
    assert (
        finds([path for path in sources("scripts", "tests/support") if path != OLD_RELEASE_READER], SCRIPTS_OLD) == []
    )
    assert len(finds([OLD_RELEASE_READER], SCRIPTS_OLD)) == 1, (
        "update-e2e reads the old release's topic `tnc` in one line, its `connected`, and nowhere else"
    )


def test_no_document_names_a_topic_a_command_or_a_state_of_before() -> None:
    assert finds(list(DOCS), DOC_OLD) == []


def test_the_searches_find_what_they_are_for() -> None:
    assert OLD.search("x = e.ctl.beacon") and OLD.search("ctl.mercury.tune()") and not OLD.search("ctl.radios")
    assert (
        OLD.search("station.heard_hf > 0")
        and OLD.search("last_fm_at=T0")
        and OLD.search("from neoaprs.radiorules import FM")
        and OLD.search("-> RadioRules:")
        and OLD.search("import old_keywords")
    )
    assert (
        OLD.search("ctl._stand_in(rows)")
        and OLD.search("store.seed_radios(decide)")
        and OLD.search("radioedits.seed(store, run)")
        and OLD.search("restore(text, keep_unknown=True)")
        and OLD.search("tncdriver.tnc_settings(config)")
    )
    assert (
        OLD.search("flat_view(rows, specs)")
        and OLD.search("FLAT_KEY_OF[key]")
        and not OLD.search("radioedits.start_notes(")
        and not OLD.search("Store.read_radios()")
        and not OLD.search("line_settings(spec)")
    )
    assert (
        OLD.search("from neoaprs.radios import Radios")
        and not OLD.search("from neoaprs.radiospec import FM_ID")
        and not OLD.search("heard_by")
        and not OLD.search("heard_rf")
        and not OLD.search("radio_id")
    )
    assert (
        frozen(ROOT / "neoaprs" / "migrationsteps31.py")
        and frozen(ROOT / "tests" / "test_migration_33.py")
        and frozen(ROOT / "scripts" / "migration-size")
        and not frozen(ROOT / "tests" / "test_packetlog.py")
    )
    assert (
        PAGE_OLD.search('{ type: "state", topic: "tnc" }')
        and PAGE_OLD.search("daemon.hf.value")
        and PAGE_OLD.search("row.heard_fm")
        and PAGE_OLD.search("last_hf_at")
    )
    assert not PAGE_OLD.search('topic: "radios"') and not PAGE_OLD.search("radio.modem.value")
    assert (
        SCRIPTS_OLD.search("OLD_KEYS[kind]")
        and SCRIPTS_OLD.search('self.topics.get("tnc")')
        and SCRIPTS_OLD.search('f"heard_{kind}"')
        and not SCRIPTS_OLD.search('topics.get("radios")')
    )
    assert (
        DOC_OLD.search("the topic `tnc` says")
        and DOC_OLD.search("`TncState`")
        and DOC_OLD.search("asks `hf_tune`")
        and DOC_OLD.search(f"(`beacon`, `{HF_BEACON}`)")
        and not DOC_OLD.search("the topic `radios`")
    )
    assert (
        DOC_OLD.search("`RadioRules` (`neoaprs/radiorules.py`)")
        and DOC_OLD.search("(neoaprs/radios.py)")
        and DOC_OLD.search("(`radios.py`, the two radios as one,")
    )
    assert (
        not DOC_OLD.search("`tests/support/tworadios.py`")
        and not DOC_OLD.search("`configradios.py`")
        and not DOC_OLD.search("`neoaprs/radiospec.py`")
        and not DOC_OLD.search("`neoaprs/radiotype.py`")
    )
