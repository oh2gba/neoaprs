"""The markers of the suite (unit, integration, safety), given to every test by what it is.

Every test is exactly one of unit, integration or safety.
"""

import inspect
import subprocess
from collections.abc import Iterable
from types import ModuleType

import pytest

KINDS = ("unit", "integration")
# Plus "expects_errors", which a test sets itself (tests/support/guards.py)
EXTRA = ("safety",)
# Where integration starts: what a test module imports from here, or names in a test function, is
# the daemon or a fake service.
INTEGRATION_ORIGINS = ("tests.support.env", "neoaprs.controller", "neoaprs.web.server")
INTEGRATION_NAMES = frozenset({"Env", "Controller", "WebServer"})
# The test files of the data layer (a file that goes away or is renamed fails tests/test_markers.py,
# so this list cannot rot).
SAFETY_MODULES = frozenset({"test_store", "test_migrations", "test_dbfile"})


def touches_the_daemon(module: ModuleType) -> bool:
    return any(getattr(v, "__module__", None) in INTEGRATION_ORIGINS or v is subprocess for v in vars(module).values())


def names_in(function: object) -> frozenset[str]:
    """The global and attribute names the test function uses (the function under a hypothesis
    @given, or any decorator, included)."""
    inner = getattr(getattr(function, "hypothesis", None), "inner_test", function)
    code = getattr(inspect.unwrap(inner) if callable(inner) else inner, "__code__", None)
    return frozenset(code.co_names) if code is not None else frozenset()


def kind_of(item: pytest.Item) -> str:
    function = getattr(item, "obj", None)
    names = names_in(function)
    module = getattr(item, "module", None)
    if (
        inspect.iscoroutinefunction(function)
        or names & INTEGRATION_NAMES
        or any(n.startswith("Fake") for n in names)
        or (module is not None and touches_the_daemon(module))
    ):
        return "integration"
    return "unit"


def extras_of(item: pytest.Item) -> list[str]:
    return ["safety"] if item.path.stem in SAFETY_MODULES else []


def apply(items: Iterable[pytest.Item]) -> None:
    for item in items:
        for name in (kind_of(item), *extras_of(item)):
            item.add_marker(getattr(pytest.mark, name))
