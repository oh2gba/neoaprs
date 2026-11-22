"""Tests for the station's units setting (`units/non_metric`): metric by default, a boolean, and
read by nothing of the daemon but the settings, so nothing sent on the air follows it."""

from pathlib import Path

import pytest

from neoaprs.config import DEFAULTS, Config, SettingError

PACKAGE = Path(__file__).resolve().parent.parent / "neoaprs"


def test_units_are_metric_unless_set() -> None:
    assert DEFAULTS.units_non_metric is False and Config.from_data({}).units_non_metric is False
    assert DEFAULTS.to_data()["units/non_metric"] == "false"


def test_units_take_true_and_false() -> None:
    assert Config.check("units/non_metric", " true ") == "true"
    assert Config.check("units/non_metric", "false") == "false"
    assert Config.checked(DEFAULTS, {"units/non_metric": "true"}).units_non_metric is True
    assert Config.from_data({"units/non_metric": "true"}).to_data()["units/non_metric"] == "true"


def test_a_wrong_units_value_is_refused_and_a_stored_one_falls_back() -> None:
    with pytest.raises(SettingError) as refused:
        Config.check("units/non_metric", "miles")
    assert refused.value.key == "units/non_metric" and refused.value.code == "setting.not_boolean"
    assert Config.from_data({"units/non_metric": "miles"}).units_non_metric is False


def test_nothing_but_config_reads_the_units() -> None:
    readers = sorted(
        str(path.relative_to(PACKAGE))
        for path in PACKAGE.rglob("*.py")
        if "units_non_metric" in (text := path.read_text(encoding="utf-8")) or "units/non_metric" in text
    )
    assert readers == ["config.py"]
