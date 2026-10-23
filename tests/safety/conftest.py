"""Everything under tests/safety is the safety suite: `pytest -m safety` runs it, `pytest -m "not safety"` leaves it out."""
from pathlib import Path

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    here = Path(__file__).resolve().parent
    for item in items:
        if here in Path(str(item.fspath)).resolve().parents:
            item.add_marker(pytest.mark.safety)
