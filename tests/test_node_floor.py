"""The oldest Node the page's tools run on: the number the packages of ui/package-lock.json ask for
is the number the docs, the scripts, ui/package.json and the container say, and no CI job runs an older one."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOOR_FILES = (
    "scripts/check",
    "scripts/build-page",
    "scripts/coverage",
    "scripts/worktree-setup",
    "scripts/dup-check",
    "docs/development.md",
)


def lowest_22(alternative: str) -> tuple[int, int] | None:
    """The oldest 22.x.y one alternative of an `engines.node` range takes (None: no 22 in it)."""
    found = re.fullmatch(r"(?:\^|>=\s*|~)?(\d+)(?:\.(\d+))?(?:\.(\d+))?", alternative.strip())
    if not found:
        return None
    major, minor, patch = (int(part or 0) for part in found.groups())
    if alternative.strip().startswith(">="):
        return None if major > 22 else (minor, patch) if major == 22 else (0, 0)
    return (minor, patch) if major == 22 else None


def needed_by(lock: dict[str, dict[str, object]]) -> tuple[int, int, int]:
    floor = (0, 0)
    for entry in lock.values():
        engines = entry.get("engines")
        spec = engines.get("node") if isinstance(engines, dict) else None
        if not isinstance(spec, str):
            continue
        takes = [low for low in map(lowest_22, spec.split("||")) if low is not None]
        if takes:
            floor = max(floor, min(takes))
    return (22, *floor)


def test_the_ranges_are_read() -> None:
    assert lowest_22("^22.13.0") == (13, 0) and lowest_22(">=22.12.0") == (12, 0)
    assert lowest_22(">= 12.0.0") == (0, 0) and lowest_22("^20.19.0") is None and lowest_22("20") is None
    assert lowest_22(">=24") is None
    lock = {"": {}, "a": {"engines": {"node": "^20.19.0 || ^22.13.0 || >=24"}}, "b": {"engines": {"node": ">=18"}}}
    assert needed_by(lock) == (22, 13, 0)


def test_every_place_says_the_number_the_locked_packages_need() -> None:
    lock = json.loads((ROOT / "ui" / "package-lock.json").read_text(encoding="utf-8"))["packages"]
    major, minor, patch = needed = needed_by(lock)
    text = f"{major}.{minor}.{patch}"
    expression = f"(a * 1000 + b) * 1000 + c >= {(major * 1000 + minor) * 1000 + patch} ? 0 : 1"
    for name in FLOOR_FILES:
        content = (ROOT / name).read_text(encoding="utf-8")
        assert f"{text} or newer" in content.replace("Node", "node"), name
        assert not re.search(r"22\.\d+(\.\d+)? or newer", content.replace(f"{text} or newer", "")), name
        if not name.startswith("docs"):
            assert name == "scripts/dup-check" or expression in content, name
    package = json.loads((ROOT / "ui" / "package.json").read_text(encoding="utf-8"))
    assert package["engines"] == {"node": f">={text}"} and lock[""]["engines"] == package["engines"]
    tests = (ROOT / "tests" / "test_page_build.py").read_text(encoding="utf-8")
    assert f"NODE_NEEDED = {needed}" in tests


def test_the_container_and_the_workflows_run_a_node_that_is_new_enough() -> None:
    lock = json.loads((ROOT / "ui" / "package-lock.json").read_text(encoding="utf-8"))["packages"]
    needed = needed_by(lock)
    docker = (ROOT / "packaging" / "ci" / "Dockerfile").read_text(encoding="utf-8")
    version = re.search(r"^ARG NODE_VERSION=(\d+)\.(\d+)\.(\d+)$", docker, re.M)
    assert version and tuple(int(part) for part in version.groups()) >= needed
    for workflow in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for major in re.findall(r"node-version: (\d+)\b", workflow.read_text(encoding="utf-8")):
            assert int(major) > needed[0], f"{workflow.name} runs node {major}, a line that has no 22.x floor"
