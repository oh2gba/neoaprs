"""What is new between two versions, read from the changelog (neoaprs/releasenotes.py): the sections by version, Unreleased and the preamble left out, the ones newer than ours up to the latest, the newest first."""
from neoaprs.releasenotes import MAX_BYTES, Section, changelog_url, sections, sections_after

CHANGELOG = """# Changelog

Some words before the first heading.

## Unreleased

- Not out yet.

## 0.10.2

Bug fixes.

- **Fixed:** one thing.
- **Fixed:** another.

## 0.10.1

Local info and a clearer top bar.

- Local info is in the Objects tab.

##  0.10.0

The first of the tens.

## 1.0.0-rc1

A candidate.
"""


def test_the_sections_are_the_versions_of_the_headings_with_their_text_and_nothing_else() -> None:
    found = sections(CHANGELOG)
    assert [s.version for s in found] == ["0.10.2", "0.10.1", "0.10.0", "1.0.0-rc1"]
    assert found[0] == Section("0.10.2", "Bug fixes.\n\n- **Fixed:** one thing.\n- **Fixed:** another.")
    assert found[2].text == "The first of the tens."
    assert sections("no headings at all") == [] and sections("## Unreleased\n\ntext\n") == []


def test_what_is_new_is_the_sections_after_ours_up_to_the_latest_the_newest_first() -> None:
    assert [s.version for s in sections_after(CHANGELOG, "0.10.0", "0.10.2")] == ["0.10.2", "0.10.1"]
    assert [s.version for s in sections_after(CHANGELOG, "0.10.1", "0.10.2")] == ["0.10.2"]
    assert [s.version for s in sections_after(CHANGELOG, "0.9.0", "0.10.1")] == ["0.10.1", "0.10.0"]
    assert sections_after(CHANGELOG, "0.10.2", "0.10.2") == []
    assert [s.version for s in sections_after(CHANGELOG, "0.10.2", "1.0.0-rc1")] == ["1.0.0-rc1"]


def test_the_changelog_is_read_at_the_tag_of_the_release() -> None:
    assert changelog_url("0.10.2") == "https://raw.githubusercontent.com/oh2gba/neoaprs/v0.10.2/CHANGELOG.md"
    assert MAX_BYTES >= 100_000
