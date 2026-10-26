"""The pytest fixtures every test can use. They are wired in by tests/conftest.py (a fixture is found where the conftest imports it)."""
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.support.clock import FixedClock


@pytest.fixture(autouse=True)
def protocol_violations() -> Iterator[None]:
    """A message that left the daemon and did not match the protocol models fails the test that sent it."""
    from neoaprs.web.outbound import VIOLATIONS
    VIOLATIONS.clear()
    yield
    found = list(VIOLATIONS)
    VIOLATIONS.clear()
    assert not found, "messages that do not match neoaprs/web/protocol.py:\n" + "\n".join(found[:10])


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def tmp_data(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    return d


@pytest.fixture
def search_pattern_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """The test is about the pattern of the settings (serial/pattern and the default): NEOAPRS_SERIAL_PATTERN, which tests/conftest.py sets for every test, is cleared. The test must not let a search that this
    pattern reaches open a real device: it names a folder of its own, or never starts one."""
    monkeypatch.delenv("NEOAPRS_SERIAL_PATTERN")


@pytest.fixture
def no_shipped_world(monkeypatch: pytest.MonkeyPatch) -> None:
    """The program has no world map of its own (a clone without the file): for the tests of the job that makes it. Name it in `pytestmark = pytest.mark.usefixtures("no_shipped_world")`."""
    monkeypatch.setattr("neoaprs.worldmap.search_folders", lambda *args, **kwargs: [])
