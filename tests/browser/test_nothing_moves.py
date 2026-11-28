"""Nothing moves when a control changes: every tick and every choice of the tabs of settings and forms, in
English and the two languages with the longest words, at both widths. A control that shows or hides the
rest of its group by design may lay out its group anew and move what is under the group up or down, never
sideways."""

import re
from functools import partial
from typing import Any

import pytest

from tests.browser import drive, rules
from tests.browser.drive import LONGEST, WIDTHS

PANES = ("beacon", "settings", "objects", "nearby", "bulletins")
MOST_CHOICES = 6  # a longer list is tried at its first, middle and last entries
# A click on a tick, in one step: nothing when it has gone meanwhile
TICK = "id => document.getElementById(id)?.click()"
# A choice as the person makes it, in one step: nothing when the field has become another kind meanwhile
# (a choice can make another field of its group a tick: the group's design).
CHOOSE = """([id, value]) => {
  const e = document.getElementById(id);
  if (!e || e.tagName !== "SELECT") return;
  e.value = value;
  e.dispatchEvent(new Event("change", { bubbles: true }));
}"""


def controls(page: Any, tab: str) -> list[str]:
    ids = page.evaluate(
        """tab => [...document.querySelectorAll(`#pane-${tab} input[type=checkbox], #pane-${tab} select`)]
            .filter(e => e.id && e.checkVisibility() && !e.disabled).map(e => e.id)""",
        tab,
    )
    return [i for i in ids if not any(re.fullmatch(pattern, i) for pattern in rules.NOT_TRIED)]


def reveals(control: str) -> bool:
    return any(re.fullmatch(pattern, control) for pattern in (*rules.REVEALS, *rules.KNOWN_MOVES, *rules.RESHAPES))


def faults_of(control: str, found: list[drive.Change]) -> list[str]:

    def sideways(c: drive.Change) -> bool:  # (its own group it may lay out anew: a choice that brings fields)
        return c.now is not None and not c.beside and (abs(c.was[0] - c.now[0]) > 0.5 or abs(c.was[2] - c.now[2]) > 0.5)

    def grows(c: drive.Change) -> bool:  # a group round the control, taller or shorter as rows come or go
        return c.holds and c.now is not None and all(abs(a - b) <= 0.5 for a, b in zip(c.was[:3], c.now[:3]))

    def above(c: drive.Change) -> bool:
        return not c.after and not grows(c)

    # (a box that went, or one that came, moved nothing by itself: what it pushed is in the list)
    judge = above if control in rules.RESHAPES else sideways if reveals(control) else lambda c: not grows(c)
    return [str(c) for c in found if c.now is not None and judge(c)]


def choices(control: Any) -> list[str]:
    values: list[str] = control.evaluate("e => [...e.options].filter(o => !o.disabled).map(o => o.value)")
    if len(values) > MOST_CHOICES:
        values = [values[0], values[len(values) // 2], values[-1]]
    return values


def tried(page: Any, tab: str, control_id: str) -> list[str]:
    """Change the control each way it goes, and back; what moved that should not."""
    root, selector = f"#pane-{tab}", f"#{control_id}"
    control = page.locator(selector)
    if control.count() != 1 or not control.is_visible() or control.is_disabled():
        return []
    found = []
    if control.evaluate("e => e.tagName") == "SELECT":
        first = control.input_value()
        for value in [v for v in choices(control) if v != first]:
            for to in (value, first):
                moved, _ = drive.changes(page, root, selector, partial(page.evaluate, CHOOSE, [control_id, to]))
                found += [f"{control_id} = {to}: {line}" for line in faults_of(control_id, moved)]
    else:
        for way in ("on", "off"):
            moved, _ = drive.changes(page, root, selector, partial(page.evaluate, TICK, control_id))
            found += [f"{control_id} ticked {way}: {line}" for line in faults_of(control_id, moved)]
    return found


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("language", ("en", *LONGEST))
def test_no_tick_or_choice_moves_what_is_round_it(
    browser: Any, fresh_demo: Any, faults: Any, language: str, width: int
) -> None:
    found: list[str] = []
    with drive.opened(browser, fresh_demo.url, faults, language=language, width=width, tab="settings") as page:
        for tab in PANES:
            drive.show_tab(page, tab)
            done: set[str] = set()
            # (those that show the rest of their group last: what they start, a radio that starts again, may
            # go on after they are back, and must not be taken for the next control's doing)
            while left := sorted((c for c in controls(page, tab) if c not in done), key=reveals):
                done.add(left[0])
                found += [f"{tab}: {line}" for line in tried(page, tab, left[0])]
    assert not found, f"{language} at {width} px:\n  " + "\n  ".join(found[:30])
