"""Nothing is left of the wire that named radios 1 and 2 by the words of before (`fm`, `hf`): no topic `tnc` or `hf`, no `hf_*` command and no `message_radio`, no row field that says a radio by its word
(`radio`, the counts of radios 1 and 2 ...), no HF beacon's times in the status, no flat key of a radio among the settings of `config` nor taken by `set_config`, no name of the controller for radio 1 or 2,
on the page neither of its two views of before nor a read of the topics, the commands or the row fields of before, and in the documents (docs/, the generated PROTOCOL.md) no topic, command or state of before.
The names are written here in parts, so that this file is no find of its own search. The page's built bundle (neoaprs/page) is the build's, made again from the sources."""
import re
from pathlib import Path

from pydantic import BaseModel

from neoaprs.config import BY_KEY, DEFAULTS
from neoaprs.configradios import FLAT_HOMES
from neoaprs.controller import Controller
from neoaprs.web.hostwire import Status
from neoaprs.web.messagewire import AttemptRow, MessageRow
from neoaprs.web.ownwire import ObjectSet, OwnObjectRow
from neoaprs.web.packetwire import PacketRow
from neoaprs.web.protocol import COMMAND_NAMES, TOPIC_NAMES
from neoaprs.web.radiowire import RadioScope
from neoaprs.web.stationwire import StationRow
from neoaprs.web.views import CONFIG_KEYS, config_values

ROOT = Path(__file__).resolve().parent.parent
HF_BEACON, SIDES, RADIOS_ON = "hf_" "beacon", "radio" "sides", "useRadios" "On"
OLD = re.compile(rf"\bctl\.(tnc|hf|mercury|beacon|{HF_BEACON})\b|{HF_BEACON}|{SIDES}|{RADIOS_ON}")
SEARCHED = ("neoaprs", "ui/src", "tests", "scripts")
# the page's reading of the topics of before and of the row fields of before (the daemon's own views of a station, `Station.heard_fm` ..., are the stand-in's and the frozen migrations' still)
PAGE_OLD = re.compile(r"""topic: ["'](tnc|hf)["']|\.(tnc|hf)\.value\b|\bheard_(fm|hf)\b|\blast_(fm|hf)_at\b""")
# the scripts' readers of the wire of before (the topics `tnc` and `hf`, the flat keys, a station's count by the word of its kind); update-e2e's `serial/port` is the old release's key and stays
SCRIPTS_OLD = re.compile(r"""OLD_(TOPICS|KEYS)\b|topics\.get\(["'](tnc|hf)["']|["']tnc["'] if kind|f["']heard_\{""")
# the one reader of the wire of before that stays: update-e2e runs an old release (version A, from before the round of the radios, which tells the FM radio in the topic `tnc` alone) before the new one
OLD_RELEASE_READER = ROOT / "scripts" / "update-e2e.py"
# what the documents may not name: the topics, the state, the commands and the beacon of before
DOC_OLD = re.compile(r"topic `(tnc|hf)`|\bTnc" r"State\b|\bRadioRules" r"State\b|\bhf_(tune|key_test|scope|frequencies)\b|\bmessage_" rf"radio\b|\b{HF_BEACON}\b")
DOCS = (ROOT / "PROTOCOL.md", *sorted((ROOT / "docs").rglob("*.md")))
BUILT = ROOT / "neoaprs" / "page"                     # (the page's bundle, which scripts/build-page writes from ui/src)
FLAT = {key for key, setting in BY_KEY.items() if setting.attr in FLAT_HOMES}


def fields(model: type[BaseModel]) -> set[str]:
    return set(model.model_fields)


def test_the_wire_has_no_topic_no_command_and_no_field_of_the_radios_of_before() -> None:
    assert not {"tnc", "hf"} & set(TOPIC_NAMES)
    assert not {"hf_tune", "hf_key_test", "hf_scope", "hf_frequencies", "message_radio"} & COMMAND_NAMES
    assert not {"heard_" "fm", "heard_" "hf", "last_fm_at", "last_hf_at", "message_radio"} & fields(StationRow)
    assert "radio" not in fields(PacketRow) | fields(MessageRow) | fields(AttemptRow) | fields(OwnObjectRow) | fields(ObjectSet)
    assert not {f"{HF_BEACON}_last_sent", f"{HF_BEACON}_next_due"} & fields(Status)
    assert "named" not in fields(RadioScope), "every frame of a scope names its radio"
    assert {"radio_id"} <= fields(PacketRow) & fields(MessageRow) & fields(AttemptRow) and "radios" in fields(OwnObjectRow) & fields(ObjectSet) and "heard" in fields(StationRow)


def test_the_config_topic_tells_no_flat_key_of_a_radio() -> None:
    told = config_values(DEFAULTS, [])
    assert not FLAT & set(told["values"]) and not FLAT & set(told["defaults"]) and not FLAT & set(CONFIG_KEYS)
    assert all(key.startswith("radio/") or key == "station/main_radio" for key in told["radio_values"])


def test_the_controller_has_no_name_of_its_own_for_radio_1_or_2(tmp_path: Path) -> None:
    ctl = Controller(tmp_path)
    assert not [name for name in ("tnc", "hf", "mercury", "beacon", HF_BEACON) if hasattr(ctl, name)], "a radio is the registry's (ctl.radios), by its id"


def finds(paths: list[Path], pattern: re.Pattern[str]) -> list[str]:
    """The lines of these files that the pattern finds, as `path:line`."""
    found = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        found += [f"{path.relative_to(ROOT)}:{n}" for n, line in enumerate(text.splitlines(), 1) if pattern.search(line)]
    return found


def sources(*tops: str) -> list[Path]:
    return [path for top in tops for path in sorted((ROOT / top).rglob("*")) if path.is_file() and path.suffix in (".py", ".ts", ".vue", "") and BUILT not in path.parents]


def test_no_source_names_the_wire_or_the_views_of_before() -> None:
    assert finds(sources(*SEARCHED), OLD) == []
    assert not (ROOT / "ui" / "src" / "lib" / f"{SIDES}.ts").exists() and not (ROOT / "ui" / "src" / "composables" / f"{RADIOS_ON}.ts").exists()


def test_the_page_reads_no_topic_and_no_row_field_of_before() -> None:
    assert finds(sources("ui/src"), PAGE_OLD) == []


def test_the_scripts_read_no_topic_and_no_key_of_before() -> None:
    assert finds([path for path in sources("scripts", "tests/support") if path != OLD_RELEASE_READER], SCRIPTS_OLD) == []
    assert len(finds([OLD_RELEASE_READER], SCRIPTS_OLD)) == 1, "update-e2e reads the old release's topic `tnc` in one line, its `connected`, and nowhere else"


def test_no_document_names_a_topic_a_command_or_a_state_of_before() -> None:
    assert finds(list(DOCS), DOC_OLD) == []


def test_the_searches_find_what_they_are_for() -> None:
    assert OLD.search("x = e.ctl." "beacon") and OLD.search("ctl." "mercury.tune()") and not OLD.search("ctl.radios")
    assert PAGE_OLD.search('{ type: "state", topic: "' 'tnc" }') and PAGE_OLD.search("daemon." "hf.value") and PAGE_OLD.search("row." "heard_" "fm") and PAGE_OLD.search("last_" "hf_at")
    assert not PAGE_OLD.search('topic: "radios"') and not PAGE_OLD.search("radio.modem.value")
    assert SCRIPTS_OLD.search("OLD_" "KEYS[kind]") and SCRIPTS_OLD.search('self.topics.get("' 'tnc")') and SCRIPTS_OLD.search('f"heard_' '{kind}"') and not SCRIPTS_OLD.search('topics.get("radios")')
    assert DOC_OLD.search("the topic `" "tnc` says") and DOC_OLD.search("`Tnc" "State`") and DOC_OLD.search("asks `hf_" "tune`") and DOC_OLD.search(f"(`beacon`, `{HF_BEACON}`)") and not DOC_OLD.search("the topic `radios`")
