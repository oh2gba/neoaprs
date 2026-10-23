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
