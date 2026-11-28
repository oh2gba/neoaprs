"""What the browser suite holds the page to, and the short lists of what is accepted, each with its reason.

An entry of a list is a CSS selector or a pattern with the reason beside it; docs/development.md, "The browser
suite", says when one may be added."""

import json
import re
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOGUES = ROOT / "ui" / "src" / "i18n"

# Text that is cut with an ellipsis by design: words of a station or of the operator that may be of any length.
ELLIPSIS: dict[str, str] = {
    ".conv-text": "the last message of a conversation, in its row of the list",
    ".mail-text": "the text of a mail, in its row of the list",
    ".sked-note": "the note of a sked, in its row of the board",
    ".ask-line": "the line of the latest question to the stations around, one line by design",
}

# The page writes in the system's font (tokens.css --font), and the widths of its words follow it: the suite
# holds the page to Noto Sans, of that list, so that a run here and on GitHub's runner measure the same words.
FONT = '"Noto Sans", "Noto Sans CJK JP", sans-serif'

# Boxes past their container or the screen by design.
OUTSIDE: dict[str, str] = {}

# Boxes that may lie over a sibling.
OVERLAPS: dict[str, str] = {}

# Text that may touch the side of the box it stands in.
EDGES: dict[str, str] = {}

# Selects that may cut even the entry they show: a known fault that waits for the same decision.
SELECTS_CUT: dict[str, str] = {
    ".size-phone [id^=set-radio-][id$=-type]": "a Dummy radio's type, a few pixels short in en, de, es, fi, ja, pt-BR",
    ".size-phone #set-station-call-ssid": "the SSID none with its meaning (es, fr, it, pt-BR)",
}

# Words that do not fit their box: a known fault that waits for a decision.
CUT: dict[str, str] = {
    ".size-phone #set-help-send": "Feedback / send logs on a phone in de, es, fr: its words are wider than the column",
}

# Selects that may be narrower than an entry they do not show: never narrower than the one they show.
# Each is a known fault that waits for a decision: on a phone the label and the control share the row,
# which is narrower than the longest entries of these lists in some of the languages.
SELECTS: dict[str, str] = {
    ".size-phone #set-radio-add": "Add radio's types",
    ".size-phone [id^=set-radio-][id$=-type]": "a radio's types",
    ".size-phone [id^=set-radio-][id$=-path]": "a radio's paths (two pixels short in English)",
    ".size-phone #set-map-aircraft": "the aircraft sources (de, fr, nl, pt-BR)",
    ".size-phone #set-map-ships": "the ships sources (de, fr, nl, pt-BR)",
    ".size-phone #set-status-source": "the status sources",
    ".size-phone #set-station-call-ssid": "the SSIDs with their meaning",
    ".size-phone #set-gps-source": "the position sources",
    ".size-phone #v-1-category": "the object categories (de, fr, it)",
}

# Controls the suite does not change, by their id.
NOT_TRIED: dict[str, str] = {
    "language": "the language changes every word of the page, so everything moves",
    "set-web-network": "it opens the page to the network; the suite's daemon stays on this computer",
    r"set-radio-\d+-type": "a radio's type gives its box the fields of the type",
}

# Controls that show or hide the rest of their group by design (CONVENTIONS.md, "On/off and state
# controls"): they may lay out their own group anew, and what is under it may move up or down, never
# sideways.
REVEALS: dict[str, str] = {
    r"set-radio-\d+-enabled": "a radio's box shows its fields while it is on",
    r"set-radio-\d+-digipeat": "the digipeater's fields show while it is on",
    r"set-pair-\d+-\d+-enabled": "a pair's fields show while it is on",
    "set-messages-alert": "the command shows while the alert is on",
    "alert-mode": "the sound and its test show while the browser notifies",
    "set-status-source": "each source of the status has fields of its own",
    "set-beacon-interval_min": "a beacon that is off greys what it does not time",
}

# Controls whose choice gives other groups under them fields of another kind by design: nothing above them
# may move.
RESHAPES: dict[str, str] = {
    "set-gps-source": "a station with a GPS has a moving station's beacon: the Beacon group's interval is a tick then",
}

# Faults of the page that are known and wait for a decision (the round's report lists each with a
# picture): judged as a control that shows the rest of its group, so they may move what is under them up
# or down, never sideways.
KNOWN_MOVES: dict[str, str] = {
    "set-map-aircraft": "the Aircraft box has the receiver's address row only for an own receiver or a "
    "Radarcape, so the boxes under it move when the source changes (the Ships box keeps the row's room)",
}

# Failed requests and console lines of the demo that are not faults.
QUIET: dict[str, str] = {
    r"/basemap(-world)?\.pmtiles\b": "the demo daemon has no base map; the page asks and is told 404",
    r"Not Found: the base map is not in the data folder": "the console's line for the same 404",
    r"request failed: GET \S+/access net::ERR_ABORTED": "the page's check of its access is ended when it leaves",
}

# Text the page shows that looks like a code, an address or a path but is a name the operator knows.
NAMES: dict[str, str] = {
    "adsb.fi": "the aircraft service's own name",
    "adsb.lol": "the aircraft service's own name",
    "neo.oh2gba.eu": "the project's site, where an HF test is posted",
}

# Elements whose words may hold an address or a path: what the operator types for the computer.
MAY_SHOW: dict[str, str] = {
    "#set-messages-alert_command": "the example command in the field where the operator writes one for the computer",
}

# A daemon's code (`radio.silent`, `port_busy`) or a catalogue id (`settings.map.title`) shown as text.
CODE = re.compile(r"(?<![\w./-])[a-z][a-z0-9]*(?:[._][a-z0-9]+)+(?![\w/-])")
# An address of this computer or of a network, a port, a path of the computer.
INTERNAL = re.compile(
    r"(?<![\w.])(?:localhost|\d{1,3}(?:\.\d{1,3}){3})(?::\d+)?(?![\w.])"
    r"|(?<![\w])port \d{2,5}\b"
    r"|(?:^|\s)(?:/home/|/tmp/|/var/|/usr/|~/|[A-Z]:\\)"
    r"|\.(?:sqlite|py|log|pmtiles)\b"
)


def selector(allowed: dict[str, str]) -> str | None:
    return ", ".join(allowed) or None


def quiet_patterns() -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern) for pattern in QUIET)


STRING = re.compile(r'"((?:[^"\\\n]|\\.)*)"')


def _strings(paths: list[Path]) -> frozenset[str]:
    found: set[str] = set()
    for path in paths:
        for literal in STRING.findall(path.read_text(encoding="utf-8")):
            try:
                found.add(json.loads(f'"{literal}"').strip())
            except ValueError:
                continue
    return frozenset(found)


@cache
def catalogue(language: str) -> frozenset[str]:
    """Every text of the language's catalogue (ui/src/i18n), its ids among them."""
    paths = [CATALOGUES / f"{language}.ts", *sorted((CATALOGUES / language).glob("*.ts"))]
    return _strings([p for p in paths if p.is_file() and not p.name.endswith(".test.ts")])


def untranslated(language: str, texts: list[tuple[str, str]]) -> list[str]:
    """The texts shown that are English words of the catalogue the language does not have."""
    english_only = catalogue("en") - catalogue(language)
    return [
        f'{where} says "{text}" in English'
        for where, text in texts
        if text in english_only and re.search("[a-z]{2}", text)
    ]


def internals(texts: list[tuple[str, str]]) -> list[str]:
    found = []
    for where, text in texts:
        for pattern, what in ((CODE, "a code"), (INTERNAL, "an internal")):
            for hit in pattern.finditer(text):
                if hit.group().strip() not in NAMES:
                    found.append(f'{where} shows {what}: "{hit.group().strip()}" in "{text[:80]}"')
    return found


# axe-core's serious and critical findings that are accepted: (rule id, a pattern of the element's selector).
AXE: dict[tuple[str, str], str] = {
    (
        "color-contrast",
        r"\.disabled\.field",
    ): "the words of a field that does not apply now are dimmed with it: an inactive "
    "control, which the contrast rule of WCAG leaves out",
    ("label-content-name-mismatch", r"button\[title="): "Write is named by what it writes (To ANSRVR: CQ HOTG), "
    "not by its word; a known fault that waits for a decision",
    ("label-content-name-mismatch", r"symbol-change"): "the symbol's button is named Change symbol and shows the "
    "symbol's name; a known fault that waits for a decision",
}
