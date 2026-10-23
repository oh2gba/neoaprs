"""Versions (neoaprs/versions.py): which is newer, what the answer of the version page means, and what the platform is called."""
import json

import pytest

from neoaprs.versions import MAX_MESSAGE, Update, compare_versions, parse_update, platform_name


@pytest.mark.parametrize("a, b, order", [
    ("0.2.0", "0.1.0", 1), ("0.1.0", "0.2.0", -1), ("0.1.0", "0.1.0", 0), ("0.10.0", "0.9.0", 1), ("1.0", "1.0.0", 0), ("1.0.1", "1.0", 1), ("1.0.0-rc1", "1.0.0", -1), ("1.0.0", "1.0.0-rc1", 1),
    ("1.0.0-rc2", "1.0.0-rc1", 1), ("1.0.0-RC1", "1.0.0-rc1", 0), (" 2.0 ", "1.9.9", 1), ("1.2.3.4", "1.2.3", 1)])
def test_versions_compare_by_their_numbers(a: str, b: str, order: int) -> None:
    assert compare_versions(a, b) == order


def test_the_answer_is_json_with_a_version_an_https_address_and_a_short_note() -> None:
    body = json.dumps({"version": "0.2.0", "url": "https://oh2gba.github.io/neoaprs/", "message": " Fixes the map "})
    assert parse_update(body) == Update("0.2.0", "https://oh2gba.github.io/neoaprs/", "Fixes the map")
    assert parse_update(body.encode()) == parse_update(body)


def test_an_address_that_is_not_https_is_dropped_and_a_long_note_is_cut() -> None:
    assert parse_update(json.dumps({"version": "0.2.0", "url": "http://example.org/", "message": "x" * 500})) == Update("0.2.0", "", "x" * MAX_MESSAGE)
    assert parse_update(json.dumps({"version": "0.2.0"})) == Update("0.2.0", "", "")
    assert parse_update(json.dumps({"version": "0.2.0", "url": "javascript:alert(1)"})) == Update("0.2.0", "", "")


@pytest.mark.parametrize("body", ["", "not json", "[]", "null", '{"url": "https://x/"}', '{"version": ""}', '{"version": "latest"}', '{"version": "1.0 beta"}', '{"version": "<b>1.0</b>"}', '{"version": 1}', b"\xff\xfe"])
def test_an_answer_that_is_not_one_is_none(body: str | bytes) -> None:
    assert parse_update(body) is None


@pytest.mark.parametrize("system, machine, appimage, name", [
    ("win32", "AMD64", False, "windows"), ("darwin", "arm64", False, "macos"), ("linux", "x86_64", False, "linux"), ("linux", "x86_64", True, "linux-appimage"), ("linux", "aarch64", False, "linux-arm"),
    ("linux", "armv7l", False, "linux-arm"), ("linux", "armv6l", False, "linux-arm"), ("linux", "i686", False, "linux")])
def test_the_platform_is_one_of_the_names_the_version_page_counts(system: str, machine: str, appimage: bool, name: str) -> None:
    assert platform_name(system, machine, appimage) == name
