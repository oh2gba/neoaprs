"""The tests in another order, for the hunt for a test that depends on the one before it (the stage `flaky` of scripts/check runs half of its runs this way). A pytest plugin, loaded by name and off unless it is asked:
`pytest -p tests.support.shuffle --shuffle-seed 7`. The modules are put in a random order and the tests of each module in another, each module kept together so that what a module's fixtures hold is
set up once; the same seed gives the same order whatever the order of collection was, which is what pytest-xdist needs, since every worker collects the list by itself and the workers must agree on it."""
import random

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--shuffle-seed", type=int, default=None, help="run the tests in the order this number makes (modules, and the tests of each module)")


def shuffled(items: list[pytest.Item], seed: int) -> list[pytest.Item]:
    """`items` with the modules in an order of the seed and each module's tests in another; the order they came in plays no part."""
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
