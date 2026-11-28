"""The tests of tests/realmodems start real modems: they are collected only with NEOAPRS_REAL_MODEMS=1,
and stations.refusal decides whether they may run here (docs/realmodems.md)."""

import os
from pathlib import Path

import pytest

collect_ignore_glob = [] if os.environ.get("NEOAPRS_REAL_MODEMS") == "1" else ["test_*.py"]

HERE = Path(__file__).parent


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """A module here is one story told in order on one set of stations (who has heard whom, the
    gateway's duplicate time): its cases run in the file's order, after the suite's random order."""
    ours = [i for i, item in enumerate(items) if HERE in item.path.parents]
    in_order = sorted((items[i] for i in ours), key=_place)
    for i, item in zip(ours, in_order, strict=True):
        items[i] = item


def _place(item: pytest.Item) -> tuple[str, str, int]:
    """The module, the stations' set (a parametrized world), the line of the case."""
    callspec = getattr(item, "callspec", None)
    return str(item.path), callspec.id if callspec is not None else "", item.location[1] or 0
