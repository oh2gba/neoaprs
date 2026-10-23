"""Where the data is kept when nobody says (neoaprs/paths.py)."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from neoaprs import paths
from neoaprs.paths import default_data_dir


def test_the_environment_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NEOAPRS_DATA_DIR", str(tmp_path / "mine"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert default_data_dir() == tmp_path / "mine"


@pytest.mark.skipif(sys.platform != "linux", reason="the XDG folders are Linux's")
def test_then_the_xdg_data_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("NEOAPRS_DATA_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert default_data_dir() == tmp_path / "xdg" / "neoaprs"


@pytest.mark.skipif(sys.platform != "linux", reason="the XDG folders are Linux's")
def test_else_the_local_share_of_the_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEOAPRS_DATA_DIR", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert default_data_dir() == Path.home() / ".local" / "share" / "neoaprs"


# ---- the other systems: the module sees the platform as the test says (nothing global is changed)

def platform(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setattr(paths, "sys", SimpleNamespace(platform=name))
    monkeypatch.delenv("NEOAPRS_DATA_DIR", raising=False)


def test_windows_keeps_the_data_in_the_local_app_data_not_the_roaming_one(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    platform(monkeypatch, "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert default_data_dir() == tmp_path / "local" / "NeoAPRS", "XDG_DATA_HOME is not a Windows thing"


def test_windows_without_the_variable_uses_the_folder_it_stands_for(monkeypatch: pytest.MonkeyPatch) -> None:
    platform(monkeypatch, "win32")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert default_data_dir() == Path.home() / "AppData" / "Local" / "NeoAPRS"


def test_macos_keeps_it_in_application_support(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    platform(monkeypatch, "darwin")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert default_data_dir() == Path.home() / "Library" / "Application Support" / "NeoAPRS"


@pytest.mark.parametrize("name", ["win32", "darwin", "linux"])
def test_the_environment_wins_on_every_system(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str) -> None:
    platform(monkeypatch, name)
    monkeypatch.setenv("NEOAPRS_DATA_DIR", str(tmp_path / "mine"))
    assert default_data_dir() == tmp_path / "mine"
