"""Start at sign-in of the desktop app: on Windows the Run key (through the stand-in for winreg of tests/test_service.py, never the real registry) and on Linux an XDG autostart file in a configuration folder of
the test's own; what is run is `neoaprs-app --tray`, and the entry is the one `neoaprs service install` and the installer write too."""
import sys
from pathlib import Path

import pytest

from neoaprs.cli import servicewindows
from neoaprs.desktop import autostart
from neoaprs.desktop.autostart import AutoStartError, DesktopFileAutoStart, RunKeyAutoStart, app_command, autostart_for, desktop_exec
from neoaprs.paths import default_data_dir
from tests.test_service import fake_winreg

SCRIPTS = r"C:\Users\Jo Doe\AppData\Local\uv\tools\neoaprs\Scripts"


def test_the_command_is_the_installed_script_with_tray_and_the_data_folder_only_when_it_is_not_the_default(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "neoaprs-app").write_text("#!/bin/sh\n", encoding="utf-8")
    python = str(bin_dir / "python")
    assert app_command(default_data_dir(), "linux", False, python) == [str(bin_dir / "neoaprs-app"), "--tray"]
    assert app_command(tmp_path / "my data", "linux", False, python) == [str(bin_dir / "neoaprs-app"), "--tray", "--data", str(tmp_path / "my data")]


def test_without_the_script_it_is_this_python_with_the_module(tmp_path: Path) -> None:
    python = str(tmp_path / "bin" / "python")
    assert app_command(default_data_dir(), "linux", False, python, which=lambda name: None) == [python, "-m", "neoaprs", "app", "--tray"]
    assert app_command(default_data_dir(), "linux", False, python, which=lambda name: "/usr/bin/neoaprs-app") == ["/usr/bin/neoaprs-app", "--tray"]


def test_in_the_frozen_app_it_is_its_own_windowless_program_whichever_one_of_the_folder_runs() -> None:
    for running in ("neoaprs.exe", "neoaprsw.exe", "neoaprs-app.exe"):
        assert app_command(default_data_dir(), "win32", True, rf"C:\Program Files\NeoAPRS\{running}")[1:] == ["--tray"]
    first = app_command(default_data_dir(), "win32", True, r"C:\Program Files\NeoAPRS\neoaprs.exe")[0]
    assert first.replace("\\", "/").endswith("NeoAPRS/neoaprs-app.exe")


def test_an_exec_line_quotes_what_the_specification_says() -> None:
    assert desktop_exec(["/usr/bin/neoaprs-app", "--tray"]) == "/usr/bin/neoaprs-app --tray"
    assert desktop_exec(["/home/jo doe/bin/neoaprs-app", "--tray", "--data", "/data/100%"]) == '"/home/jo doe/bin/neoaprs-app" --tray --data /data/100%%'
    assert desktop_exec(["a", 'say "hi"', "$HOME", "back\\slash"]) == 'a "say \\"hi\\"" "\\$HOME" "back\\\\slash"'


def test_linux_writes_and_removes_an_autostart_file_in_the_config_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    entry = DesktopFileAutoStart(["/opt/py aprs/neoaprs-app", "--tray"])
    assert entry.path == tmp_path / "config" / "autostart" / "neoaprs.desktop" and not entry.enabled()
    entry.enable()
    text = entry.path.read_text(encoding="utf-8")
    assert entry.enabled() and text.startswith("[Desktop Entry]\n") and 'Exec="/opt/py aprs/neoaprs-app" --tray\n' in text and "Terminal=false" in text and "Type=Application" in text
    entry.enable()
    assert entry.enabled(), "twice is the same"
    entry.disable()
    entry.disable()
    assert not entry.enabled() and not entry.path.exists()


def test_linux_without_a_config_folder_variable_uses_dot_config_in_the_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert DesktopFileAutoStart(["x"]).path == tmp_path / ".config" / "autostart" / "neoaprs.desktop"


def test_a_config_folder_that_cannot_be_written_is_an_error_with_words(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    blocked = tmp_path / "config"
    blocked.write_text("a file where the folder should be", encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(blocked))
    with pytest.raises(AutoStartError, match="could not be written"):
        DesktopFileAutoStart(["x"]).enable()


def test_windows_sets_the_run_key_to_the_app_in_the_tray_and_takes_it_away(monkeypatch: pytest.MonkeyPatch) -> None:
    values: dict[str, str] = {}
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg(values))
    entry = RunKeyAutoStart([SCRIPTS + r"\neoaprs-app.exe", "--tray"])
    assert not entry.enabled()
    entry.enable()
    assert values == {"NeoAPRS": f'"{SCRIPTS}\\neoaprs-app.exe" --tray'} and entry.enabled()
    entry.disable()
    entry.disable()
    assert values == {} and not entry.enabled()


def test_windows_replaces_the_entry_that_starts_the_daemon_with_the_one_that_starts_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {"NeoAPRS": f'"{SCRIPTS}\\neoaprsw.exe" run --data "C:\\data"'}
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg(values))
    entry = RunKeyAutoStart([SCRIPTS + r"\neoaprs-app.exe", "--tray"])
    assert not entry.enabled(), "the service's entry starts the daemon: it is not the app's"
    entry.enable()
    assert "neoaprs-app.exe" in values["NeoAPRS"] and "run --data" not in values["NeoAPRS"]


def test_windows_does_not_touch_an_entry_that_is_not_neoaprs(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {"NeoAPRS": r"C:\Tools\other.exe"}
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg(values))
    entry = RunKeyAutoStart(["neoaprs-app.exe", "--tray"])
    with pytest.raises(AutoStartError, match="not NeoAPRS's"):
        entry.enable()
    entry.disable()
    assert values == {"NeoAPRS": r"C:\Tools\other.exe"} and servicewindows.current() == r"C:\Tools\other.exe"


def test_each_system_has_its_own_and_macos_has_none(tmp_path: Path) -> None:
    assert isinstance(autostart_for(tmp_path, "linux"), DesktopFileAutoStart)
    assert isinstance(autostart_for(tmp_path, "win32"), RunKeyAutoStart)
    assert autostart_for(tmp_path, "darwin") is None
    assert autostart.APP_NAME == "neoaprs-app"
