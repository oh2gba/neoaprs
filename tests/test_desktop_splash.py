"""The splash of Windows (neoaprs/desktop/splash.py) as far as it is not Win32: the quick look at the app's arguments and that it knows every option of the real parser, the look at a data folder that an app
holds already, the place and the colours, the handle that takes it away from anywhere, where the app takes it away, and that the entry's way to it imports nothing heavy. The window itself is what only a
Windows desktop can show."""
import argparse
import os
import subprocess
import sys
from pathlib import Path

import pytest

from neoaprs import paths
from neoaprs.desktop import cmd, loading, single, splash
from neoaprs.desktop.shell import Choice
from tests.test_desktop_cmd import World
from tests.test_desktop_winshell import Rig, handler, launch, quit_through_the_menu

ROOT = Path(__file__).resolve().parent.parent
HEAVY = ("tornado", "pydantic", "cryptography", "webview", "PySide6", "neoaprs.web", "neoaprs.daemon", "neoaprs.cli", "neoaprs.desktop.cmd", "pathlib", "logging", "asyncio")


@pytest.fixture
def data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The default data folder, of the test's own."""
    monkeypatch.setenv("NEOAPRS_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every `splash.done()`, wherever it is called from."""
    calls: list[str] = []
    monkeypatch.setattr(splash, "done", lambda: calls.append("done"))
    return calls


# ---- the quick look at the arguments

@pytest.mark.parametrize("argv", [[], ["--debug"], ["--encryption"], ["--timeout", "30"], ["--timeout=30"], ["--debug", "--encryption", "--timeout", "5"], ["--enc"], ["--deb"], ["--ti", "9"]])
def test_the_app_started_from_the_start_menu_with_any_options_that_show_a_window_shows_the_splash_on_the_default_data_folder(argv: list[str], data: Path) -> None:
    assert splash.window_now(argv) == str(data)


@pytest.mark.parametrize("argv", [["--data", "D"], ["--data=D"], ["--da", "D"], ["--debug", "--data", "D", "--encryption"], ["--data", "X", "--data", "D"]])
def test_the_data_folder_is_the_one_the_arguments_name_last(argv: list[str], data: Path, tmp_path: Path) -> None:
    given = [str(tmp_path / "D") if arg == "D" else arg.replace("=D", f"={tmp_path / 'D'}") for arg in argv]
    assert splash.window_now(given) == str(tmp_path / "D")
    assert splash.window_now(argv) == os.path.abspath("D"), "a relative folder is the working folder's, as the app makes it"


@pytest.mark.parametrize("argv", [["--tray"], ["--quit"], ["-h"], ["--help"], ["--debug", "--tray"], ["--tr"], ["--q"], ["--he"], ["--data", "D", "--quit"], ["--tray", "--encryption"]])
def test_no_splash_where_the_arguments_say_no_window_now(argv: list[str], data: Path) -> None:
    assert splash.window_now(argv) is None


@pytest.mark.parametrize("argv", [["--d"], ["--data"], ["--timeout"], ["--debug=1"], ["--nonsense"], ["run"], ["-x"], ["--"], ["--data", "D", "extra"]])
def test_no_splash_for_what_the_parser_refuses_or_cannot_be_sure_of(argv: list[str], data: Path) -> None:
    assert splash.window_now(argv) is None, "--d is --data or --debug: argparse refuses it, and a refusal shows no window"


def test_the_quick_look_knows_every_option_of_the_apps_parser_and_whether_it_takes_a_value() -> None:
    real = {name: action.nargs != 0 for action in cmd.parser()._actions for name in action.option_strings}
    assert real == splash.OPTIONS, "an option of cmd.parser is in splash.OPTIONS too, and in NO_WINDOW when it means no window now"
    helps = {name for action in cmd.parser()._actions if isinstance(action, argparse._HelpAction) for name in action.option_strings}
    assert set(splash.NO_WINDOW) == helps | {"--tray", "--quit"}


def test_the_default_data_folder_is_the_one_of_neoaprs_paths_on_every_system(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("NEOAPRS_DATA_DIR", raising=False)
    for platform in ("win32", "darwin", "linux"):
        monkeypatch.setattr(sys, "platform", platform)
        for local, xdg in ((None, None), (str(tmp_path / "local"), str(tmp_path / "xdg"))):
            for name, value in (("LOCALAPPDATA", local), ("XDG_DATA_HOME", xdg)):
                if value is None:
                    monkeypatch.delenv(name, raising=False)
                else:
                    monkeypatch.setenv(name, value)
            assert splash.default_data() == str(paths.default_data_dir()), platform
    monkeypatch.setenv("NEOAPRS_DATA_DIR", str(tmp_path / "given"))
    assert splash.default_data() == str(paths.default_data_dir())


# ---- the look at an app that holds the data folder already

def test_an_app_that_holds_the_folder_is_seen_by_its_files_and_nothing_is_locked_to_find_out(tmp_path: Path) -> None:
    first = single.SingleApp(tmp_path)
    assert not splash.running(str(tmp_path))
    assert first.acquire()
    assert splash.running(str(tmp_path)), "its port file, and its pid file naming this process"
    assert first.running(), "the look took no lock"
    first.close()
    assert not splash.running(str(tmp_path)), "the port file goes with the app; the pid file stays"
    assert (single.PORT_NAME, single.PID_NAME) == (splash.PORT_NAME, splash.PID_NAME)


def test_a_port_file_that_a_crash_left_is_no_app(tmp_path: Path) -> None:
    gone = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True, check=True).stdout.strip()
    (tmp_path / splash.PORT_NAME).write_text("7399\n", encoding="ascii")
    (tmp_path / splash.PID_NAME).write_text(f"{gone}\n", encoding="ascii")
    assert not splash.running(str(tmp_path))
    (tmp_path / splash.PID_NAME).write_text("garbage\n", encoding="ascii")
    assert not splash.running(str(tmp_path))
    (tmp_path / splash.PID_NAME).unlink()
    assert not splash.running(str(tmp_path))
    assert splash.alive(os.getpid()) == single.process_alive(os.getpid()) is True and splash.alive(int(gone)) == single.process_alive(int(gone)) is False


def test_show_starts_the_splash_once_only_on_windows_and_only_for_a_window_now(data: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[splash.Splash] = []
    monkeypatch.setattr(splash, "run", started.append)
    monkeypatch.setattr(splash, "_current", None)
    for argv in (["--tray"], ["--quit"], ["--help"]):
        splash.show(argv)
    assert started == []
    splash.show([])
    splash.show([])
    assert len(started) == (1 if sys.platform == "win32" else 0), "once in a process, and on Windows alone"
    splash.done()
    splash.done()


def test_no_splash_when_an_app_holds_the_folder_already(data: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[splash.Splash] = []
    monkeypatch.setattr(splash, "run", started.append)
    monkeypatch.setattr(splash, "_current", None)
    data.mkdir()
    first = single.SingleApp(data)
    assert first.acquire()
    splash.show([])
    first.close()
    assert started == []


# ---- the handle, the place, the colours

def test_the_handle_closes_the_window_once_whenever_it_is_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    posted: list[int] = []
    monkeypatch.setattr(splash, "post_close", posted.append)
    early = splash.Splash()
    early.close()
    assert not early.made(0x1234) and posted == [], "closed before the window was made: the thread destroys it at once"
    shown = splash.Splash()
    assert shown.made(0x1234)
    shown.close()
    shown.close()
    assert posted == [0x1234], "WM_CLOSE once"
    ended = splash.Splash()
    assert ended.made(0x5678)
    ended.gone()
    ended.close()
    assert posted == [0x1234], "after its thread has ended there is nothing to post to"


def test_done_is_safe_anywhere_any_number_of_times(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(splash, "_current", None)
    splash.done()
    splash.done()
    handle = splash.Splash()
    monkeypatch.setattr(splash, "_current", handle)
    splash.done()
    splash.done()
    assert not handle.made(1)


def test_the_splash_is_the_size_at_the_dpi_in_the_middle_of_the_work_area_on_the_pages_dark_colours() -> None:
    assert splash.place((0, 0, 1366, 728), 96) == (503, 304, 360, 120)
    assert splash.place((0, 0, 2560, 1400), 144) == (1010, 610, 540, 180), "150 %"
    assert splash.place((-1920, 40, 0, 1080), 96) == (-1140, 500, 360, 120), "a work area that does not start at 0"
    assert splash.colorref(loading.BACKGROUND[True]) == 0x1A1714 and splash.colorref(loading.TEXT[True]) == 0xE8E6E3


# ---- where the app takes it away

@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    return World(tmp_path, monkeypatch)


def test_the_app_takes_it_away_when_a_second_start_finds_the_first_and_when_it_ends(world: World, counted: list[str]) -> None:
    first = single.SingleApp(world.data)
    assert first.acquire()
    assert world.run() == 0 and counted == ["done"], "at once, before it tells the first one"
    first.close()
    counted.clear()
    assert cmd.main(["--data", str(world.data), "--quit"]) == 0 and counted == ["done"], "every way out of the app's main takes it away"


def test_the_app_takes_it_away_before_a_message_box_which_it_would_cover(world: World, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    order: list[str] = []
    monkeypatch.setattr(splash, "done", lambda: order.append("done"))
    monkeypatch.setattr(cmd.opencmd, "tell_the_user", lambda text: order.append("told"))
    starting = cmd.Launch(world.data, cmd.Opening(world.data, world.open_session), False, True, None, single.SingleApp(world.data))
    assert starting.no_page(cmd.NoPage("no page came up")) == 1
    assert order == ["done", "told"], "no page came: the message box is not under the splash, which is on top of everything"
    order.clear()
    (tmp_path / "file").write_text("", encoding="ascii")
    assert cmd.main(["--data", str(tmp_path / "file" / "data")]) == 1
    assert order[:2] == ["done", "told"], "the data folder cannot be made"


def test_the_app_takes_it_away_at_once_when_no_window_can_come(world: World, counted: list[str]) -> None:
    world.choice = Choice(None, False)
    assert world.run() == 0 and counted == ["done"]


def test_the_app_takes_it_away_when_the_arguments_are_refused(counted: list[str]) -> None:
    with pytest.raises(SystemExit):
        cmd.main(["--nonsense"])
    assert counted == ["done"]


def test_the_windows_shell_takes_it_away_when_the_window_is_shown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, counted: list[str]) -> None:
    rig = Rig(tmp_path, monkeypatch)
    thread = launch(rig)
    assert counted == []
    handler(rig.toolkits.windows[0].events.shown)()
    assert counted == ["done"]
    quit_through_the_menu(rig, thread)


def test_the_windows_shell_takes_it_away_when_there_is_no_window_to_wait_for(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, counted: list[str]) -> None:
    rig = Rig(tmp_path, monkeypatch, window=False)
    thread = launch(rig)
    assert counted == ["done"]
    quit_through_the_menu(rig, thread)


@pytest.mark.expects_errors
def test_the_windows_shell_takes_it_away_when_the_web_engine_cannot_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, counted: list[str]) -> None:
    rig = Rig(tmp_path, monkeypatch, start_fails=True)
    thread = launch(rig)
    assert counted == ["done"]
    quit_through_the_menu(rig, thread)


# ---- the entry's way to it

def test_the_entrys_way_to_the_splash_imports_nothing_heavy(tmp_path: Path) -> None:
    """What packaging/windows/neoaprs_entry.py does for the app's role before it imports the app: the role, the splash's module, and its look at the arguments and at the data folder."""
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import neoaprs_entry; from neoaprs.desktop import splash; assert neoaprs_entry.role('C:/NeoAPRS/neoaprs-app.exe') == 'app'; "
            "data = splash.window_now([]); assert data and not splash.running(data); splash.show([]); splash.done()")
    env = {**os.environ, "NEOAPRS_DATA_DIR": str(tmp_path / "data"), "NEOAPRS_NO_DEVICES": "1", "NEOAPRS_UPDATE_CHECK": "0"}
    run = subprocess.run([sys.executable, "-X", "importtime", "-c", code, str(ROOT / "packaging" / "windows")], capture_output=True, text=True, env=env, cwd=tmp_path, timeout=60)
    assert run.returncode == 0, run.stderr
    imported = {line.split("|")[-1].strip() for line in run.stderr.splitlines() if line.startswith("import time:")}
    assert "neoaprs.desktop.splash" in imported
    assert sorted(name for name in imported if any(name == heavy or name.startswith(heavy + ".") for heavy in HEAVY)) == []


@pytest.mark.parametrize("program, role", [("neoaprs.exe", "cli"), ("neoaprsw.exe", "daemon"), ("neoaprs-app.exe", "app"), ("NeoAPRS-App.EXE", "app"), ("python.exe", "cli")])
def test_the_entry_tells_the_role_by_the_programs_name(program: str, role: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "packaging" / "windows"))
    import neoaprs_entry  # type: ignore[import-not-found]
    assert neoaprs_entry.role(f"C:/Program Files/NeoAPRS/{program}") == role
