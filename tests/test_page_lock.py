"""The page's lock does what ui/package.json's overrides ask: no copy of an overridden package is left
in the range the override replaces.
"""

import json
import operator
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPARE = {">=": operator.ge, ">": operator.gt, "<=": operator.le, "<": operator.lt, "=": operator.eq}


def version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("-")[0].split("."))


def in_range(found: str, spec: str) -> bool:
    terms = re.findall(r"(>=|<=|>|<|=)?\s*(\d+\.\d+\.\d+)", spec)
    assert terms, f"an override's range this test cannot read: {spec}"
    return all(COMPARE[sign or "="](version(found), version(bound)) for sign, bound in terms)


def test_in_range_reads_the_ranges_of_the_overrides() -> None:
    assert in_range("10.2.6", ">=7.0.0 <11.0.1")
    assert not in_range("11.0.9", ">=7.0.0 <11.0.1")
    assert not in_range("6.2.0", ">=7.0.0 <11.0.1")


def test_no_copy_of_an_overridden_package_is_left_in_the_range_it_replaces() -> None:
    overrides = json.loads((ROOT / "ui" / "package.json").read_text(encoding="utf-8")).get("overrides", {})
    packages = json.loads((ROOT / "ui" / "package-lock.json").read_text(encoding="utf-8"))["packages"]
    for key in overrides:
        name, _, spec = key.rpartition("@") if key.count("@") > key.startswith("@") else (key, "", "")
        if not spec:
            continue
        left = [
            f"{place} {entry['version']}"
            for place, entry in packages.items()
            if place.rsplit("node_modules/", 1)[-1] == name and in_range(entry["version"], spec)
        ]
        assert not left, f"the override {key} did not reach: {left}; take the copies out of the lock and npm install"
