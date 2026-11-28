"""The browsers the page is built for: ui/vite.config.ts's build.target is the one docs/development.md
names, and the desktop app's own web engine is newer than its floor.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def configured() -> list[str]:
    found = re.search(r"^\s*target:\s*\[([^\]]*)\]", (ROOT / "ui" / "vite.config.ts").read_text(encoding="utf-8"), re.M)
    assert found, "ui/vite.config.ts names no build.target, so vite's own default decides the browsers"
    return re.findall(r'"([^"]+)"', found.group(1))


def test_the_build_target_is_the_one_the_docs_name() -> None:
    docs = (ROOT / "docs" / "development.md").read_text(encoding="utf-8")
    found = re.search(r"\*\*The browsers\.\*\*.*?`build\.target` in `ui/vite\.config\.ts`\s+is `([^`]+)`", docs, re.S)
    assert found, "docs/development.md says which browsers the page is built for"
    assert configured() == [part.strip() for part in found.group(1).split(",")]


def test_the_desktop_apps_web_engine_is_inside_the_floor() -> None:
    engine = pytest.importorskip("PySide6.QtWebEngineCore")
    chrome = next(int(t.removeprefix("chrome")) for t in configured() if t.startswith("chrome"))
    assert int(engine.qWebEngineChromiumVersion().split(".")[0]) >= chrome
