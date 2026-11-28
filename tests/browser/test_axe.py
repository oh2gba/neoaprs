"""axe-core's serious and critical findings on every tab, at both widths, the map and the settings in the dark
too: none but those the list in rules.py accepts, each with its reason."""

import re
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from tests.browser import drive, rules
from tests.browser.drive import TABS, WIDTHS

GRAVE = ("serious", "critical")


@cache
def axe_script() -> str:
    import axe_playwright_python

    return (Path(axe_playwright_python.__file__).parent / "axe.min.js").read_text(encoding="utf-8")


def findings(page: Any) -> list[str]:
    page.evaluate(axe_script())
    result = page.evaluate("() => axe.run(document, { resultTypes: ['violations'] })")
    found = []
    for violation in result["violations"]:
        if violation["impact"] not in GRAVE:
            continue
        for node in violation["nodes"]:
            target = " ".join(str(t) for t in node["target"])
            if any(re.fullmatch(rule, violation["id"]) and re.search(where, target) for (rule, where) in rules.AXE):
                continue
            found.append(f"{violation['id']} ({violation['impact']}): {target}: {node['failureSummary'][:160]}")
    return found


@pytest.mark.parametrize("width", WIDTHS)
def test_no_serious_finding_of_axe_on_any_tab(browser: Any, demo: Any, faults: Any, width: int) -> None:
    found: list[str] = []
    with drive.opened(browser, demo.url, faults, width=width, tab="messages") as page:
        for tab in TABS:
            drive.show_tab(page, tab)
            found += [f"{tab}: {line}" for line in findings(page)]
    for theme, tab, view in (("dark", "settings", "panel"), ("light", "stations", "map"), ("dark", "stations", "map")):
        with drive.opened(browser, demo.url, faults, width=width, tab=tab, theme=theme, view=view) as page:
            found += [f"{tab if view == 'panel' else 'map'}, {theme}: {line}" for line in findings(page)]
    found = list(dict.fromkeys(found))
    assert not found, f"at {width} px:\n  " + "\n  ".join(found[:40])
