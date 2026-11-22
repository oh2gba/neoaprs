"""The manual quotes the page's marks, headings and hover texts in the words of the English
catalogue."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EN = ROOT / "ui" / "src" / "i18n" / "en"
PAGE = ROOT / "docs" / "manual" / "page.md"

# The ids whose English the manual quotes as a mark or a heading, in bold.
IN_BOLD = ("pill.daemon", "pill.radio_waiting", "pill.radio_searching", "pill.radio_kiss", "stats.section.radio")
# The ids whose English the manual quotes inside a sentence, from a small letter.
IN_A_SENTENCE = ("stats.frames", "pill.radio_waiting_why")


def english() -> dict[str, str]:
    texts: dict[str, str] = {}
    for path in EN.glob("*.ts"):
        texts.update(re.findall(r'^\s*"([a-z0-9_.]+)": "((?:[^"\\]|\\.)*)",?$', path.read_text(encoding="utf-8"), re.MULTILINE))
    return texts


def test_the_manual_quotes_the_marks_and_headings_of_the_page_as_the_page_says_them() -> None:
    texts, manual = english(), PAGE.read_text(encoding="utf-8")
    missing = [f"{id}: **{texts[id]}**" for id in IN_BOLD if f"**{texts[id]}**" not in manual]
    missing += [f"{id}: {texts[id][0].lower()}{texts[id][1:]}" for id in IN_A_SENTENCE if f"{texts[id][0].lower()}{texts[id][1:]}" not in manual]
    assert missing == [], missing


def test_the_ids_the_manual_quotes_are_in_the_catalogue() -> None:
    texts = english()
    assert [id for id in IN_BOLD + IN_A_SENTENCE if id not in texts] == []
