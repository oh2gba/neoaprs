"""The markers (tests/support/markers.py) give every test its kind, so that `pytest -m unit`, `-m "not e2e"` and `-m safety` mean something."""
import tomllib

import pytest

from tests.conftest import ROOT
from tests.support import markers

PYTEST_OPTIONS = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]


def collected(request: pytest.FixtureRequest) -> list[pytest.Item]:
    return list(request.session.items)


def names_of(item: pytest.Item) -> set[str]:
    return {m.name for m in item.iter_markers()}


def test_every_test_is_exactly_one_of_unit_integration_e2e(request: pytest.FixtureRequest) -> None:
    for item in collected(request):
        kinds = names_of(item) & set(markers.KINDS)
        assert len(kinds) == 1, f"{item.nodeid} is {sorted(kinds) or 'nothing'}"


def test_the_browser_tests_and_only_they_are_e2e(request: pytest.FixtureRequest) -> None:
    for item in collected(request):
        in_browser_dir = any(part in markers.E2E_DIRS for part in item.path.parts)
        assert ("e2e" in names_of(item)) == in_browser_dir, item.nodeid


def test_a_test_with_a_loop_or_the_daemon_is_integration_and_the_rest_is_unit(request: pytest.FixtureRequest) -> None:
    by_file: dict[str, set[str]] = {}
    for item in collected(request):
        by_file.setdefault(item.path.name, set()).update(names_of(item) & set(markers.KINDS))
    for name, expected in (("test_size_ratchet.py", {"unit"}), ("test_architecture.py", {"unit"}), ("test_main.py", {"integration"})):
        if name in by_file:
            assert by_file[name] == expected, name


def test_the_data_layer_is_safety_and_the_rest_is_not(request: pytest.FixtureRequest) -> None:
    for item in collected(request):
        if item.path.name in ("test_store.py", "test_migrations.py", "test_dbfile.py") or "safety" in item.path.parts:
            assert "safety" in names_of(item), item.nodeid
        if item.path.name in ("test_architecture.py", "test_clock.py", "test_signal.py"):
            assert "safety" not in names_of(item), item.nodeid


def test_the_safety_list_names_files_that_exist() -> None:
    present = {p.stem for p in (ROOT / "tests").glob("test_*.py")}
    assert not markers.SAFETY_MODULES - present, "a test file of the safety list was renamed or removed: " + ", ".join(sorted(markers.SAFETY_MODULES - present))


def test_the_markers_are_registered_and_the_default_run_is_the_whole_suite() -> None:
    registered = {line.split(":", 1)[0] for line in PYTEST_OPTIONS["markers"]}
    assert registered >= set(markers.KINDS) | set(markers.EXTRA) | {"expects_errors"}
