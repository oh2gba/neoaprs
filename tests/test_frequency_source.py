"""The suggested HF dials have one source, `site/frequencies.json`: the module the daemon reads, the table of
the project's page, the manual's table and the dial of the version page's fallback all agree with it."""

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

from neoaprs import mercury

ROOT = Path(__file__).resolve().parent.parent


def generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_protocol", ROOT / "scripts" / "gen-protocol.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source() -> list[tuple[str, str]]:
    found = json.loads((ROOT / "site" / "frequencies.json").read_text(encoding="utf-8"))["frequencies"]
    return sorted(((item["band"], item["dial"]) for item in found), key=lambda pair: float(pair[1].split()[0]))


def test_the_daemons_list_is_what_the_source_gives() -> None:
    assert list(mercury.SUGGESTED) == source()
    made = generator().render()
    path = ROOT / "neoaprs" / "frequencylist.py"
    assert made[path] == path.read_text(encoding="utf-8"), "run scripts/gen-protocol.py"


def test_the_table_of_the_projects_page_is_made_from_the_source() -> None:
    page = ROOT / "site" / "index.html"
    assert generator().render()[page] == page.read_text(encoding="utf-8"), "run scripts/gen-protocol.py"
    table = re.search(r'<table class="freqs" id="frequencies">.*?</table>', page.read_text(encoding="utf-8"), re.DOTALL)
    assert table is not None
    shown = re.findall(r"<th scope=\"row\">(?:&nbsp;)*([^<]*)</th><td>(?:&nbsp;)*([^<]*)</td>", table.group(0))
    assert shown == source()


def test_the_manuals_table_has_the_dials_of_the_source_and_no_other() -> None:
    manual = (ROOT / "docs" / "RADIOS.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| (\d+ m) \| ([\d.]+) MHz \|$", manual, re.MULTILINE)
    assert rows == [(band, dial.removesuffix(" MHz USB")) for band, dial in source()]


def test_the_version_pages_fallback_dial_is_the_forty_metre_one_of_the_source() -> None:
    php = (ROOT / "server" / "version.php").read_text(encoding="utf-8")
    found = re.search(r"const HF_DIAL\s*=\s*'([^']*)';", php)
    assert found is not None
    assert found.group(1) == dict(source())[f"{mercury.DIAL_BAND} m"]
