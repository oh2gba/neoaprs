"""The changelog is brief (CONVENTIONS.md, "Documents, scripts, units"): under `## Unreleased` stand one sentence that sums the release up and one line for each thing a user can see or do. Neither is longer than MAX_WORDS
words, and neither names what only a developer knows: a path into the source tree, a file of code, a test, a module, a document for developers, or work that a user cannot see (a refactoring, the checkers).

The summary is written when the section is tidied for a release (docs/MAINTAINING.md), so a section without one is no fault, and an empty section has none. Two kinds of section are read: `## Unreleased`, and the section of every
release after AS_WRITTEN. scripts/release renames `## Unreleased` to the version before it runs the gate, so the notes of a release are read once more under their new heading, and a section that the rule refuses stops the
release before its commit. The section of AS_WRITTEN and the older ones were the notes of their releases before there was a rule and stay as they were written. The second half of this file shows each rule failing on a made-up
section."""
import importlib.machinery
import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

AS_WRITTEN = (0, 18, 2)      # the newest release made before the rule

MAX_WORDS = 25      # the longest change that says one thing in the sections of 0.9.1, 0.10.0 and 0.10.1 (38 changes, every word after the dash counted; the one longer change there says two things, and the three summaries have 15, 24 and 28 words)
SOURCE_FOLDERS = ("neoaprs", "tests", "scripts", "ui", "packaging", ".github")      # (`docs/` is not among them: a line may send the reader to the manual; nor `systemd/`: "systemd/launchd" is how a line names the service of two systems)
CODE_SUFFIXES = ("py", "ts", "vue", "js", "css", "html", "sh", "php", "toml", "yml", "yaml", "json", "c", "patch")
USER_DOCUMENTS = ("RADIOS", "MANUAL")      # the documents in `docs/` that are written for the operator, beside the folder `docs/manual/`
DATA_FILES = ("log", "lock", "exe", "sqlite")      # what follows `neoaprs.` in the name of a file the operator meets; anything else after it is a module
SERVICES = ("ntfy.sh",)      # a name that ends like code and is none: the service the operator types into the alerts
# What a line must not name, by the words the fault is told in. A file a user downloads or starts (`NeoAPRS-Setup.exe`), the log (`neoaprs.log`), a command and an option a user types are none of these. A name that ends like code
# is one even where the manual shows it (`state.json` of the logs file): the line says it in words.
INTERNALS: dict[str, re.Pattern[str]] = {
    "a path into the source tree": re.compile(r"(?<![\w./-])(?:" + "|".join(map(re.escape, SOURCE_FOLDERS)) + r")/[\w.-]"),      # (not the `neoaprs/` in the middle of an address)
    "a file of code": re.compile(r"(?<![\w-])(?!(?:" + "|".join(map(re.escape, SERVICES)) + r")\b)[\w-]+\.(?:" + "|".join(CODE_SUFFIXES) + r")\b"),      # (from the start of the name, so that a service is not found by its tail)
    "a test": re.compile(r"\btest_\w+"),
    "a module": re.compile(r"(?<![\w./-])neoaprs\.(?!(?:" + "|".join(DATA_FILES) + r")\b)[a-z_]\w*"),
    "a document for developers": re.compile(r"\b(?:CONVENTIONS|PROTOCOL|ARCHITECTURE|MAINTAINING)\.md\b|\bdocs/(?!(?:" + "|".join(USER_DOCUMENTS) + r")\.md)[\w-]+\.md\b"),
    "work a user cannot see": re.compile(r"\b(?:refactor\w*|pytest|vitest|mypy|ruff|eslint)\b", re.I),
}


def held(text: str) -> dict[str, str]:
    """The sections of a changelog that the rule is held for, by their heading (the words after `## `): `Unreleased`, and every release after AS_WRITTEN. A heading is a release's wherever its version stands in it, as
    scripts/release-notes.py finds the notes of a version, so that no heading it reads is passed over here. tests/test_hygiene.py holds that there is an `Unreleased`."""
    parts = re.split(r"^## (.*)$", text, flags=re.M)             # [before, heading, body, heading, body, ...]
    out: dict[str, str] = {}
    for heading, body in zip((part.strip() for part in parts[1::2]), parts[2::2]):
        versions = [tuple(map(int, found.groups())) for found in re.finditer(r"(?<![\w.])(\d+)\.(\d+)\.(\d+)", heading)]
        if heading == "Unreleased" or any(version > AS_WRITTEN for version in versions):
            out[heading] = out.get(heading, "") + body
    return out


def words(line: str) -> int:
    """The words of a line, the label of a change (`**Fixed:**`) among them, the dash of the list not."""
    return len(line.removeprefix("- ").split())


def named(line: str) -> list[str]:
    """The kinds of INTERNALS that a line names."""
    return [kind for kind, pattern in INTERNALS.items() if pattern.search(line)]


def one_sentence(line: str) -> bool:
    """A line that ends with a full stop and has no end of a sentence before that; a sentence also ends where its full stop is inside quotes, a bracket, bold or backticks."""
    return line.endswith(".") and re.search(r"[.!?][\"'”’)\]*_`]*\s+\S", line) is None


def faults(section: str) -> list[str]:
    """What is wrong with a section of the changelog, as `what: the start of the line`; [] when it is brief. The first line is the summary unless it is a change, a change that lost its dash or the space after it (a line that
    opens with a label such as `**Fixed:**`, or with a dash), a heading or a list item; every other line has to be a change."""
    out: list[str] = []
    for at, line in enumerate(line.rstrip() for line in section.splitlines() if line.strip()):
        start = line if len(line) <= 70 else line[:70] + "…"
        summary = at == 0 and re.match(r"\s|#|-|[*+] |\*\*[^*]+(?::\*\*|\*\*:)", line) is None
        if summary and not one_sentence(line):
            out.append(f"the summary is not one sentence: {start}")
        elif not summary and not line.startswith("- "):
            out.append(f"is neither the summary nor the one line of a change: {start}")
        if words(line) > MAX_WORDS:
            out.append(f"has {words(line)} words where {MAX_WORDS} are the most: {start}")
        if named(line):
            out.append(f"names {', '.join(named(line))}: {start}")
    return out


def test_what_is_not_released_yet_and_every_release_since_the_rule_is_written_briefly() -> None:
    found = [f"`## {heading}`: {fault}" for heading, section in held((ROOT / "CHANGELOG.md").read_text(encoding="utf-8")).items() for fault in faults(section)]
    assert not found, ("CHANGELOG.md (CONVENTIONS.md, 'Documents, scripts, units', says how a line is written; under a version that scripts/release has just written, correct the line there and run the same command again):\n"
                       + "\n".join(found))


# ---- each rule, failing on a made-up section ----

BRIEF = """
The page in Finnish, and a map download that is kept when it is done.

- **New:** the page speaks Suomi, chosen like the other languages.
- **Fixed:** a detailed map that had downloaded whole was thrown away.
"""
CHANGE = "- **New:** the page speaks Suomi.\n"
NEXT = f"{AS_WRITTEN[0]}.{AS_WRITTEN[1]}.{AS_WRITTEN[2] + 1}"      # the first version whose section is held
CHANGELOG = f"""# Changelog

## Unreleased

{CHANGE}
## 0.9.0

- **Fixed:** the retries of `neoaprs/services/sender.py` were refactored (tests/test_sender.py): two stations that collided on HF retried 32 and 64 seconds later to the second and collided again, so a retry now waits a pause of its own.
"""


def what(found: list[str]) -> list[str]:
    """The faults without the lines they are about."""
    return [fault.split(": ", 1)[0] for fault in found]


def change(count: int) -> str:
    """The line of a change that has `count` words, its label among them."""
    return "- **Fixed:** " + " ".join(["word"] * (count - 1)) + "\n"


def test_the_limit_and_the_last_release_left_as_written_are_the_ones_the_conventions_name() -> None:
    rule = " ".join((ROOT / "CONVENTIONS.md").read_text(encoding="utf-8").split())
    assert f"neither is longer than {MAX_WORDS} words" in rule, "CONVENTIONS.md ('Documents, scripts, units') and MAX_WORDS say the same number"
    assert f"the section of every release after {'.'.join(map(str, AS_WRITTEN))}," in rule, "CONVENTIONS.md and AS_WRITTEN name the same release"
    assert f"\n## {'.'.join(map(str, AS_WRITTEN))}\n" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), "AS_WRITTEN is a release that the changelog has"


def test_a_brief_section_has_no_fault_with_its_summary_without_one_and_when_it_is_empty() -> None:
    assert faults(BRIEF) == []
    assert faults(BRIEF.split("\n\n", 1)[1]) == [], "the lines alone: the summary is written when the release is made"
    assert faults("\nNothing changes for the operator.\n") == [], "a release that nobody can see: its summary alone"
    assert faults("") == [] and faults("\n\n") == []


def test_a_line_of_more_words_than_the_limit_is_a_fault_and_so_is_such_a_summary() -> None:
    assert words(change(MAX_WORDS)) == MAX_WORDS and faults(change(MAX_WORDS)) == []
    assert what(faults(change(MAX_WORDS + 1))) == [f"has {MAX_WORDS + 1} words where {MAX_WORDS} are the most"]
    assert faults("word " * (MAX_WORDS - 1) + "word.\n") == []
    assert what(faults("word " * MAX_WORDS + "word.\n")) == [f"has {MAX_WORDS + 1} words where {MAX_WORDS} are the most"]


@pytest.mark.parametrize("section", [
    "- **Fixed:** the tray icon's menu opens on Windows\n  again, as it did.\n",        # a second line
    "- **Fixed:** the tray icon's menu opens on Windows.\n  - Open and Quit too.\n",    # a list inside
    "### Fixed\n\n- the tray icon's menu opens on Windows.\n",                          # a heading over it
    "- **Fixed:** the tray icon's menu opens on Windows.\n\nIt failed at every start.\n",       # a paragraph after it
    "* **Fixed:** the tray icon's menu opens on Windows.\n",                            # a star for the dash
    "**Fixed:** the tray icon's menu opens on Windows.\n",                              # no dash: not the summary either
    "-**Fixed:** the tray icon's menu opens on Windows.\n",                             # no space after the dash
    "**Fixed**: the tray icon's menu opens on Windows.\n",                             # the colon after the bold
    "+ **Fixed:** the tray icon's menu opens on Windows.\n",                           # a plus for the dash
    "-the tray icon's menu opens on Windows.\n",
])
def test_a_change_is_one_line_with_no_second_line_no_list_inside_no_heading_and_no_paragraph(section: str) -> None:
    assert what(faults(section)) == ["is neither the summary nor the one line of a change"]


def test_the_summary_is_one_sentence_on_one_line_that_ends_with_a_full_stop() -> None:
    assert faults("The page in Finnish.\n\n" + CHANGE) == []
    assert what(faults("The page in Finnish. A map download is kept when it is done.\n\n" + CHANGE)) == ["the summary is not one sentence"]
    assert what(faults("The page in Finnish\n\n" + CHANGE)) == ["the summary is not one sentence"]
    assert what(faults("The page in Finnish,\nand a map download that is kept.\n\n" + CHANGE)) == ["the summary is not one sentence", "is neither the summary nor the one line of a change"]
    assert faults("**Update now** says what it installs.\n\n" + CHANGE) == [], "a summary may open with the name of a control"


@pytest.mark.parametrize("summary", [
    'The page says "Saved." A map download is kept.',
    "The page says 'Saved.' A map download is kept.",
    "The page says “Saved.” A map download is kept.",
    "The page in **Finnish.** A map download is kept.",
    "The page in Finnish (and Swedish.) A map download is kept.",
    "The page in Finnish [and Swedish.] A map download is kept.",
    "The setup guide asks for `Enter.` A map download is kept.",
    "The page in _Finnish._ A map download is kept.",
    "Is the page in Finnish? A map download is kept.",
])
def test_a_first_sentence_that_ends_inside_quotes_bold_a_bracket_or_backticks_is_seen(summary: str) -> None:
    assert what(faults(summary + "\n\n" + CHANGE)) == ["the summary is not one sentence"]


@pytest.mark.parametrize("text, kinds", [
    ("the clock is read in `neoaprs/clock.py` only", "a path into the source tree, a file of code"),
    ("the retries are held by more tests (tests/test_sender.py)", "a path into the source tree, a file of code, a test"),
    ("`scripts/release` runs the checks before the push", "a path into the source tree"),
    ("the update check asks `version.php` once a day", "a file of code"),
    ("test_migrations seeds the new table", "a test"),
    ("the logs file has `state.json` again", "a file of code"),
    ("the service is installed by `install.sh` again", "a file of code"),
    ("alerts are sent by `my-ntfy.sh`", "a file of code"),
    ("`neoaprs.services.beacon` keeps its timer", "a module"),
    ("the new topic is described in `PROTOCOL.md`", "a document for developers"),
    ("when the beacon is due is in `docs/daemon.md`", "a document for developers"),
    ("the beacon's timer was refactored", "work a user cannot see"),
    ("the page's code passes ESLint and mypy", "work a user cannot see"),
])
def test_a_line_that_names_the_source_a_test_or_work_nobody_sees_is_a_fault(text: str, kinds: str) -> None:
    assert what(faults(f"- **Changed:** {text}.\n")) == [f"names {kinds}"]
    assert what(faults(f"A release in which {text}.\n")) == [f"names {kinds}"], "the summary is held to the same"


@pytest.mark.parametrize("text", [
    "the app takes `--encryption` and passes it on",
    "the release also has `NeoAPRS-Setup.exe` and `neoaprs_arm64.deb`",
    "without a working page, `neoaprs support` saves the file",
    "the log, `neoaprs.log`, says whether encrypted messages are allowed",
    "a second NeoAPRS says who holds `neoaprs.lock`, and `neoaprs.exe` and `neoaprs.sqlite` keep their names",
    "the manual has a page on alerts ([docs/manual/notifications.md](docs/manual/notifications.md))",
    "the radio guide has the HF radio ([docs/RADIOS.md](docs/RADIOS.md))",
    "the project page is <https://github.com/oh2gba/neoaprs/>",
    "a keying **Test** in the HF radio's box",
    "the service (systemd/launchd) starts NeoAPRS again after a crash",
    "alerts reach a phone through ntfy.sh, or through a server of your own (`https://ntfy.sh/mytopic`)",
])
def test_what_a_user_types_downloads_or_reads_is_not_an_internal_name(text: str) -> None:
    assert faults(f"- **New:** {text}.\n") == []


def test_what_is_not_released_and_the_releases_after_the_rule_are_read_and_the_older_ones_are_not() -> None:
    assert held(CHANGELOG) == {"Unreleased": f"\n\n{CHANGE}\n"} and faults(held(CHANGELOG)["Unreleased"]) == []
    assert len(faults(CHANGELOG.split("## 0.9.0\n", 1)[1])) == 2, "the old section is long and names the source, and nothing reads it"
    for heading in (NEXT, f"{NEXT} (2026-11-20)", f"[{NEXT}]", f"Release {NEXT}", f"{AS_WRITTEN[0]}.{AS_WRITTEN[1] + 1}.0", f"{AS_WRITTEN[0] + 1}.0.0-rc1"):
        later = held(CHANGELOG.replace("## 0.9.0", f"## {heading}"))
        assert list(later) == ["Unreleased", heading] and len(faults(later[heading])) == 2, heading
    for heading in (".".join(map(str, AS_WRITTEN)), f"{AS_WRITTEN[0]}.{AS_WRITTEN[1]}.{AS_WRITTEN[2] - 1}", f"{AS_WRITTEN[0]}.{AS_WRITTEN[1] - 1}.99", "Older releases"):
        assert list(held(CHANGELOG.replace("## 0.9.0", f"## {heading}"))) == ["Unreleased"], heading
    assert held("# Changelog\n\n## Unreleased\n\n## 0.9.0\n\n- x\n") == {"Unreleased": "\n\n"}, "the empty section of a tree just released"
    assert held("# Changelog\n\n## Unreleased\n") == {"Unreleased": "\n"} and held("# Changelog\n\n## 0.9.0\n\n- x\n") == {}
    assert held("# Changelog\n\n## Unreleased \n\n### Fixed\n\n- x\n") == {"Unreleased": "\n\n### Fixed\n\n- x\n"}, "a smaller heading is inside its section"


@pytest.mark.parametrize("heading", [NEXT, f"{NEXT} (2026-11-20)", f"[{NEXT}]", f"Release {NEXT}", f"{NEXT}-rc1", f"{'.'.join(map(str, AS_WRITTEN))}, {NEXT}"])
def test_the_notes_that_the_release_workflow_reads_for_a_version_are_a_section_that_is_held(heading: str) -> None:
    """The workflow makes the notes of the GitHub release with scripts/release-notes.py: the section that finds for a version after AS_WRITTEN, however the heading names the version, is one the rule reads."""
    spec = importlib.util.spec_from_file_location("release_notes_for_the_brief_changelog", ROOT / "scripts" / "release-notes.py")
    assert spec is not None and spec.loader is not None
    notes = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(notes)
    text = CHANGELOG.replace(CHANGE, "").replace("## 0.9.0", f"## {heading}")        # nothing under Unreleased: the tree as the release tags it
    found = notes.section(text, NEXT)
    assert found is not None and found == notes.section(text, None), "the notes of the version, which are the newest notes too"
    assert held(text)[heading].strip() == found and len(faults(held(text)[heading])) == 2, "scripts/release-notes.py reads no section that the rule does not"


def test_the_release_cannot_pass_notes_that_are_not_brief_by_renaming_their_section(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """scripts/release writes the version over `## Unreleased` and then runs the gate: its own step is run here on a made-up changelog, and what was a fault under `Unreleased` is the same fault under the version."""
    changelog = tmp_path / "CHANGELOG.md"
    notes = "The page in Finnish. A map download is kept.\n\n" + change(MAX_WORDS + 1) + "- **Fixed:** the retries of `neoaprs/services/sender.py`.\n"
    changelog.write_text(f"# Changelog\n\n## Unreleased\n\n{notes}\n## {'.'.join(map(str, AS_WRITTEN))}\n\n{change(MAX_WORDS + 1)}", encoding="utf-8")
    before = held(changelog.read_text(encoding="utf-8"))
    assert list(before) == ["Unreleased"] and len(faults(before["Unreleased"])) == 3
    loader = importlib.machinery.SourceFileLoader("release_for_the_brief_changelog", str(ROOT / "scripts" / "release"))        # (a script without .py gets no loader by itself)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    release = importlib.util.module_from_spec(spec)
    monkeypatch.setattr(sys, "path", list(sys.path))            # (the script puts the tree first in the path: not for the tests after this one)
    loader.exec_module(release)
    monkeypatch.setattr(release, "CHANGELOG", changelog)        # the step writes the file this names, and runs no command
    assert release.Release(NEXT, dry_run=False, rerun=False, deploy=False, interval=0.0).step_changelog().startswith("done")
    after = held(changelog.read_text(encoding="utf-8"))
    assert list(after) == ["Unreleased", NEXT] and faults(after["Unreleased"]) == []
    assert faults(after[NEXT]) == faults(before["Unreleased"]), "the gate of the release reads the notes under the heading the release gave them"
