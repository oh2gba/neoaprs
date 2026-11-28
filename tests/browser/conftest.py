"""The browser suite drives Chromium on the built page of scripts/demo-daemon (docs/development.md, "The browser
suite"). It is collected only with NEOAPRS_BROWSER=1, which `scripts/check --stage browser` sets."""

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

collect_ignore_glob = [] if os.environ.get("NEOAPRS_BROWSER") == "1" else ["test_*.py"]


@pytest.fixture(scope="session")
def browser() -> Iterator[Any]:
    sync_api = pytest.importorskip("playwright.sync_api", reason="Playwright is not installed: uv sync --group browser")
    from tests.browser.drive import browsers_folder, launch

    manager = sync_api.sync_playwright()
    with manager as playwright:
        # Playwright's loop lives as long as the session's browser; its threads are named for the guard.
        manager._loop.set_default_executor(ThreadPoolExecutor(thread_name_prefix="neoaprs-browser-loop"))
        found = launch(playwright)
        if found is None:
            pytest.skip(
                f"no Chromium in {browsers_folder()}: the suite never downloads one (playwright install chromium)"
            )
        try:
            yield found
        finally:
            found.close()


def _demo(folder: Path) -> Iterator[Any]:
    from tests.browser.drive import Demo

    demo = Demo(folder)
    demo.prepare()
    try:
        demo.start()
        yield demo
    finally:
        demo.stop()


@pytest.fixture(scope="session")
def demo(tmp_path_factory: pytest.TempPathFactory, browser: Any) -> Iterator[Any]:
    """The daemon of the checks that only look."""
    yield from _demo(tmp_path_factory.mktemp("browser") / "demo")


@pytest.fixture(scope="module")
def own_demo(tmp_path_factory: pytest.TempPathFactory, browser: Any) -> Iterator[Any]:
    """A daemon of the module's own, for the tests that type and change what they like."""
    yield from _demo(tmp_path_factory.mktemp("browser") / "demo")


@pytest.fixture
def fresh_demo(tmp_path: Path, browser: Any) -> Iterator[Any]:
    """A daemon of the test's own, for a test that must start from the demo's first settings."""
    yield from _demo(tmp_path / "demo")


@pytest.fixture
def faults() -> Iterator[Any]:
    """The page's console errors, uncaught errors and failed requests of the test: none may be left."""
    from tests.browser.drive import Faults
    from tests.browser.rules import quiet_patterns

    found = Faults(quiet_patterns())
    yield found
    assert not found.found, "the page said something was wrong:\n  " + "\n  ".join(found.found[:20])


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    here = Path(__file__).parent
    for item in items:
        if here in item.path.parents:
            item.add_marker(pytest.mark.slow("Chromium on the page of a daemon"))
