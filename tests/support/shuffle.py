"""A pytest plugin that runs the tests in another order, to find a test that depends on the one
before it: `pytest -p tests.support.shuffle --shuffle-seed 7`. Modules are shuffled, tests within a
module are shuffled, each module is kept together; the same seed gives the same order.
"""
import random

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--shuffle-seed", type=int, default=None, help="run the tests in the order this number makes (modules, and the tests of each module)")


def shuffled(items: list[pytest.Item], seed: int) -> list[pytest.Item]:
    """`items` with the modules in an order of the seed and each module's tests in another; the
    order they came in plays no part."""
    chance = random.Random(seed)
    modules: dict[str, list[pytest.Item]] = {}
    for item in sorted(items, key=lambda each: each.nodeid):
        modules.setdefault(item.nodeid.split("::", 1)[0], []).append(item)
    order = sorted(modules)
    chance.shuffle(order)
    result: list[pytest.Item] = []
    for module in order:
        chance.shuffle(modules[module])
        result.extend(modules[module])
    return result


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    seed = config.getoption("--shuffle-seed")
    if seed is not None:
        items[:] = shuffled(items, seed)
