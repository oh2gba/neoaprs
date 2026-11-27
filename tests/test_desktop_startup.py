"""Tests for the desktop app start: the window opens at once with the loading page, the daemon
starts without blocking, and the window moves to the page when it answers or closes with a message.
Run with a scripted shell on a slow daemon in virtual time."""

import re
import subprocess
import sys
import threading
import time
import types
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from neoaprs.cli import opencmd
from neoaprs.desktop import cmd, loading, session, webshell
from neoaprs.desktop.menu import OPEN_LABEL
from neoaprs.desktop.session import Daemon, NoPage, Opening, Session
from neoaprs.desktop.shell import Choice, Launch
from neoaprs.desktop.single import SingleApp
from tests.support import fakeshell
from tests.test_desktop_logic import PAGE
from tests.test_desktop_webshell import FakeMenu, Rig, until

ROOT = Path(__file__).resolve().parent.parent


# ---- the loading page


@pytest.fixture(autouse=True)
def _no_end_of_the_test_process(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[int]]:
    """The app's last-resort end of the process, recorded instead; its waits long and the log's end a no-op, so
    that it does not come by itself under load (a test about it sets its own times); ended with the test."""
    ended: list[int] = []
    monkeypatch.setattr(webshell, "HARD_EXIT", ended.append)
    monkeypatch.setattr(webshell, "QUIT_GRACE_SEC", 60.0)
    monkeypatch.setattr(webshell, "LEAVE_SEC", 60.0)
    monkeypatch.setattr(webshell.logging, "shutdown", lambda: None)
    yield ended
    assert webshell.stop_leaving() == [], "a last-resort thread outlived its test"


def tokens(scheme: str) -> dict[str, str]:
    """--bg and --text of the page's palette, in the light block (the first) or the dark one."""
    css = (ROOT / "ui/src/styles/tokens.css").read_text(encoding="utf-8")
    dark = css.index("prefers-color-scheme: dark")
    block = css[dark:] if scheme == "dark" else css[:dark]
    return {name: re.search(rf"--{name}: (#[0-9a-f]{{6}});", block).group(1) for name in ("bg", "text")}  # type: ignore[union-attr]


def test_the_loading_page_is_the_mark_and_the_name_on_the_pages_own_colours_in_both_schemes() -> None:
    assert loading.MARK == (ROOT / "ui/public/icons/icon.svg").read_text(encoding="utf-8").strip(), "the page's icon"
    assert (loading.BACKGROUND[False], loading.TEXT[False]) == (tokens("light")["bg"], tokens("light")["text"])
    assert (loading.BACKGROUND[True], loading.TEXT[True]) == (tokens("dark")["bg"], tokens("dark")["text"])
    assert loading.background(True) == loading.BACKGROUND[True] and "prefers-color-scheme: dark" in loading.HTML
    assert '<body oncontextmenu="return false">' in loading.HTML, (
        "a right-click shows no menu of the web engine (Back, Reload)"
    )
    body = loading.HTML[loading.HTML.index("<body") :]
    assert re.sub(r"<[^>]+>", "", body) == "NeoAPRS", "nothing to read but the name"
    assert not any(
        word in loading.HTML for word in ("<script", "animation", "transition", "@keyframes", "src=", "href=", "url(")
    ), "nothing moves and nothing is fetched"


# ---- the session on its way


def test_the_opening_runs_in_a_thread_of_its_own_and_calls_back_once_it_is_there() -> None:
    gate = threading.Event()
    opening = Opening(Path("data"), lambda: (gate.wait(30), Session(Path("data"), PAGE, True))[1])
    heard: list[str] = []
    opening.when_done(lambda: heard.append("early"))
    assert opening.start() is opening and not opening.done() and heard == []
    gate.set()
    assert opening.result() == Session(Path("data"), PAGE, True)
    opening.thread.join(30)
    opening.when_done(lambda: heard.append("late"))
    assert heard == ["early", "late"], (
        "the one that asked before is called when it comes, the one that asks after at once"
    )


@pytest.mark.expects_errors
def test_a_daemon_that_cannot_be_started_is_a_no_page_that_says_so() -> None:
    def fails() -> Session:
        raise FileNotFoundError(2, "No such file or directory")

    opening = Opening(Path("data"), fails).start()
    with pytest.raises(NoPage, match="the daemon could not be started on data: No such file or directory"):
        opening.result()
    assert Opening.opened(Session(Path("data"), PAGE, False)).done()


# ---- virtual time: the clock and the sleep of the wait for the page


class VirtualClock:
    """The wait's time: `sleep` moves it on at once. `hold` (an Event) is waited for before the
    first sleep, which is the daemon being slow: nothing answers before the window is there."""

    def __init__(self, hold: threading.Event | None = None) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []
        self.hold = hold

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        if self.hold is not None:
            assert self.hold.wait(30), "(what the daemon waits for did not happen)"
        self.sleeps.append(seconds)
        self.now = round(self.now + seconds, 9)  # (a sum of twentieths that is the second it should be)

    def said(self) -> str:
        return f"{self.now:.2f}"


def slow_page(monkeypatch: pytest.MonkeyPatch, clock: VirtualClock, answers_at: float | None, looks: list[str]) -> None:
    """A daemon whose page answers at `answers_at` seconds of the clock (None: never), and has held
    its lock since it started; `looks` gets what the wait asked, in order."""

    def page_answers(url: str) -> bool:
        looks.append("page")
        return answers_at is not None and clock.now >= answers_at

    def is_running(data: Path) -> bool:
        looks.append("lock")
        return True

    monkeypatch.setattr(opencmd, "page_url", lambda data: PAGE)
    monkeypatch.setattr(opencmd, "page_answers", page_answers)
    monkeypatch.setattr(opencmd, "is_running", is_running)


def test_the_wait_looks_every_twentieth_of_a_second_and_at_the_lock_only_once_the_page_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock, looks = VirtualClock(), []
    slow_page(monkeypatch, clock, 3.0, looks)
    child = types.SimpleNamespace(poll=lambda: None)
    assert opencmd.wait_for_page(tmp_path, child, 60.0, clock.time, clock.sleep) == PAGE  # type: ignore[arg-type]
    assert (
        set(clock.sleeps) == {opencmd.POLL_SEC}
        and opencmd.POLL_SEC == 0.05
        and 3.0 <= clock.now < 3.0 + 2 * opencmd.POLL_SEC
    )
    assert looks[-2:] == ["page", "lock"] and looks.count("lock") == 1, (
        "the lock of a daemon that is starting is not taken for a look"
    )


class App:
    """`neoaprs app` with the scripted shell, the toolkit's look written down, and its daemon a slow
    one on the virtual clock (the real open_session and wait_for_page)."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answers_at: float | None) -> None:
        self.data = tmp_path / "data"
        self.data.mkdir()
        self.said: list[str] = []
        self.window = threading.Event()
        self.started = threading.Event()
        self.clock = VirtualClock(hold=self.window)
        self.looks: list[str] = []
        fakeshell.FRAMES.clear()
        fakeshell.STEPS.clear()
        self.events: list[tuple[str, str]] = []
        monkeypatch.setattr(fakeshell, "event", self.event)
        slow_page(monkeypatch, self.clock, answers_at, self.looks)
        daemon = Daemon(
            running=lambda data: False,
            start=self.start,
            wait=lambda data, child, seconds: opencmd.wait_for_page(
                data, child, seconds, self.clock.time, self.clock.sleep
            ),
        )
        monkeypatch.setattr(
            cmd,
            "open_session",
            lambda data, timeout, encryption, owns: session.open_session(data, daemon, timeout, encryption, owns),
        )
        monkeypatch.setattr(cmd.shell, "choose", self.choose)
        monkeypatch.setattr(cmd, "autostart_for", lambda data, encryption=False: None)
        monkeypatch.setattr(cmd.opencmd, "tell_the_user", self.said.append)
        monkeypatch.setattr(cmd, "say", self.said.append)

    def event(self, name: str) -> None:
        self.events.append((name, self.clock.said()))
        if name == "window":
            self.window.set()

    def start(self, data: Path) -> "subprocess.Popen[bytes]":
        self.events.append(("daemon started", self.clock.said()))
        self.started.set()
        return types.SimpleNamespace(poll=lambda: None)  # type: ignore[return-value]

    def choose(self) -> Choice:
        assert self.started.wait(30), (
            "the daemon is started before the toolkit is looked for, not after its page answers"
        )
        self.events.append(("toolkit", self.clock.said()))
        return Choice("tests.support.fakeshell", True)

    def run(self) -> int:
        return cmd.run(cmd.parser().parse_args(["--data", str(self.data)]))


def test_on_a_slow_daemon_the_window_is_there_at_once_and_goes_to_the_page_when_it_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = App(tmp_path, monkeypatch, answers_at=3.0)
    fakeshell.STEPS.append(lambda frame: frame.quit())
    assert app.run() == 0
    assert app.events == [("daemon started", "0.00"), ("toolkit", "0.00"), ("window", "0.00"), (f"page {PAGE}", "3.00")]
    assert app.said == [] and not SingleApp(app.data).running()


def test_a_daemon_that_never_comes_closes_the_window_after_the_timeout_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = App(tmp_path, monkeypatch, answers_at=None)
    assert app.run() == 1
    assert [name for name, _ in app.events] == ["daemon started", "toolkit", "window", "closed"] and app.events[-1][
        1
    ] == "60.00"
    assert app.said == [
        f"app: NeoAPRS did not come up: no page came up on {app.data} within 60 s; see the log, neoaprs.log in that folder. The log is {app.data / 'neoaprs.log'}"
    ]
    assert not SingleApp(app.data).running(), "the app lets go of the folder"


# ---- the Windows shell: the window before the page, and no page


class Gate:
    """An opener that gives its session (or raises its NoPage) when the test says."""

    def __init__(self, data: Path) -> None:
        self.data = data
        self.open = threading.Event()
        self.error: NoPage | None = None

    def __call__(self) -> Session:
        assert self.open.wait(30)
        if self.error is not None:
            raise self.error
        return Session(self.data, PAGE, owned=False)


@pytest.fixture
def pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Rig, Gate, Launch, list[str], Callable[[], threading.Thread]]]:
    rig = Rig(tmp_path, monkeypatch)
    gate = Gate(rig.data)
    assert rig.single.acquire()
    launch = Launch(rig.data, Opening(rig.data, gate).start(), False, True, rig.auto, rig.single, rig.daemon)
    told: list[str] = []
    monkeypatch.setattr(opencmd, "tell_the_user", told.append)
    codes: list[int] = []

    def go() -> threading.Thread:
        thread = threading.Thread(target=lambda: codes.append(webshell.run(launch)), daemon=True)
        thread.start()
        until(lambda: rig.toolkits.started)
        return thread

    yield rig, gate, launch, told, go
    gate.open.set()
    launch.close()


def texts(rig: Rig) -> list[Any]:
    return [i if i == FakeMenu.SEPARATOR else i.text for i in rig.toolkits.icons[0].menu.items()]  # type: ignore[attr-defined]


def test_the_windows_window_shows_the_loading_page_before_the_daemon_answers_and_its_page_after(
    pending: tuple[Rig, Gate, Launch, list[str], Callable[[], threading.Thread]],
) -> None:
    rig, gate, launch, told, go = pending
    thread = go()
    (window,) = rig.toolkits.windows
    assert window.kwargs["html"] == loading.HTML and window.loaded == [] and not launch.opening.done()
    assert texts(rig) == [OPEN_LABEL, FakeMenu.SEPARATOR, "Quit"] and rig.toolkits.icons[0].calls == ["run_detached"], (
        "the tray is there, with Open and a Quit that does not wait for the window"
    )
    opening = rig.toolkits.icons[0].menu.items()[0]  # type: ignore[attr-defined]
    opening.action(rig.toolkits.icons[0], opening)
    assert window.calls == ["show", "restore"], "Open shows the window that waits"
    gate.open.set()
    until(lambda: window.loaded == [PAGE + "#app"] and launch.ctx is not None and launch.ctx.watch is not None)
    assert (
        texts(rig)[-1] == "Quit (NeoAPRS keeps running as a service)" and "update_menu" in rig.toolkits.icons[0].calls
    )
    assert window.kwargs["js_api"].page_url == PAGE
    item = next(i for i in rig.toolkits.icons[0].menu.items() if i != FakeMenu.SEPARATOR and i.text.startswith("Quit"))  # type: ignore[attr-defined]
    item.action(rig.toolkits.icons[0], item)
    thread.join(30)
    assert not thread.is_alive() and told == []


def test_the_windows_window_closes_when_no_page_comes_and_the_app_says_why(
    pending: tuple[Rig, Gate, Launch, list[str], Callable[[], threading.Thread]],
) -> None:
    rig, gate, launch, told, go = pending
    thread = go()
    gate.error = NoPage(f"no page came up on {rig.data} within 60 s; see the log, neoaprs.log in that folder")
    gate.open.set()
    thread.join(30)
    (window,) = rig.toolkits.windows
    assert not thread.is_alive() and window.calls[-1] == "destroy" and window.loaded == []
    assert told == [
        f"app: NeoAPRS did not come up: no page came up on {rig.data} within 60 s; see the log, neoaprs.log in that folder. The log is {rig.data / 'neoaprs.log'}"
    ]
    assert rig.toolkits.icons[0].calls[-1] == "stop" and not SingleApp(rig.data).running()


def test_the_dark_scheme_of_windows_is_read_where_its_settings_keep_it() -> None:
    class Key:
        def __init__(self, value: int) -> None:
            self.value = value

        def __enter__(self) -> "Key":
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    def registry(value: int | None) -> Any:
        def open_key(root: str, path: str) -> Key:
            assert root == "HKCU" and path.endswith(r"\Themes\Personalize")
            if value is None:
                raise FileNotFoundError(path)
            return Key(value)

        return types.SimpleNamespace(
            HKEY_CURRENT_USER="HKCU", OpenKey=open_key, QueryValueEx=lambda key, name: (key.value, 4)
        )

    assert (
        webshell.dark_scheme(registry(0)) is True
        and webshell.dark_scheme(registry(1)) is False
        and webshell.dark_scheme(registry(None)) is False
    )


# ---- the app can always be ended: the tray and the second app's commands do not wait for the window


class OwnedGate(Gate):
    def __call__(self) -> Session:
        assert self.open.wait(30)
        return Session(self.data, PAGE, owned=True)


def test_quit_in_the_tray_before_the_page_stops_the_daemon_the_app_started_once_it_is_up_and_ends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = Rig(tmp_path, monkeypatch)
    gate = OwnedGate(rig.data)
    assert rig.single.acquire()
    launch = Launch(rig.data, Opening(rig.data, gate).start(), False, True, rig.auto, rig.single, rig.daemon)
    codes: list[int] = []
    thread = threading.Thread(target=lambda: codes.append(webshell.run(launch)), daemon=True)
    thread.start()
    until(lambda: rig.toolkits.started)
    quit_item = rig.toolkits.icons[0].menu.items()[-1]  # type: ignore[attr-defined]
    assert quit_item.text == "Quit"
    quit_item.action(rig.toolkits.icons[0], quit_item)
    gate.open.set()
    thread.join(30)
    assert not thread.is_alive() and codes == [0]
    assert rig.daemon.stopped == [rig.data], "the daemon it started is not left running"
    assert launch.ctx is None or launch.ctx.watch is None, "the session was not attached after the Quit"
    launch.close()


def test_a_second_apps_quit_ends_an_app_whose_window_engine_never_came_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The installer's and the uninstaller's `neoaprs-app --quit`."""
    monkeypatch.setattr(webshell, "LEAVE_SEC", 0.3)
    monkeypatch.setattr(webshell, "QUIT_GRACE_SEC", 0.3)
    rig = Rig(tmp_path, monkeypatch)
    gate = Gate(rig.data)
    assert rig.single.acquire()
    launch = Launch(rig.data, Opening(rig.data, gate).start(), False, True, rig.auto, rig.single, rig.daemon)
    hung = threading.Event()
    ended: list[int] = []

    def never(func: Any = None, **kwargs: Any) -> None:
        rig.toolkits.started.append(kwargs)
        assert hung.wait(30)

    monkeypatch.setattr(sys.modules["webview"], "start", never)
    monkeypatch.setattr(webshell, "HARD_EXIT", lambda code: ended.append(code) or hung.set())
    thread = threading.Thread(target=lambda: webshell.run(launch), daemon=True)
    thread.start()
    until(lambda: rig.toolkits.started)
    assert SingleApp(rig.data).tell_the_other("quit")
    gate.open.set()
    until(lambda: ended == [0])
    thread.join(30)
    assert not thread.is_alive()


def test_a_window_engine_that_never_comes_up_leaves_the_tray_with_the_page_in_the_browser_and_quit_ends_the_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(webshell, "ENGINE_WAIT_SEC", 0.3)
    monkeypatch.setattr(webshell, "LEAVE_SEC", 0.3)
    monkeypatch.setattr(webshell, "QUIT_GRACE_SEC", 0.3)
    rig = Rig(tmp_path, monkeypatch)
    hung = threading.Event()
    ended: list[int] = []

    def never(func: Any = None, **kwargs: Any) -> None:
        rig.toolkits.started.append(kwargs)
        assert hung.wait(30), "the engine hangs until the app ends the process"

    def hard_exit(code: int) -> None:
        ended.append(code)
        hung.set()

    monkeypatch.setattr(sys.modules["webview"], "start", never)
    monkeypatch.setattr(webshell, "HARD_EXIT", hard_exit)
    thread = threading.Thread(target=rig.run, daemon=True)
    thread.start()
    until(lambda: rig.browser == [PAGE] and rig.ctx.watch is not None)
    open_item = next(i for i in rig.toolkits.icons[0].menu.items() if i != FakeMenu.SEPARATOR and i.text == OPEN_LABEL)  # type: ignore[attr-defined]
    open_item.action(rig.toolkits.icons[0], open_item)
    assert rig.browser == [PAGE, PAGE], "Open is the browser now"
    items = rig.toolkits.icons[0].menu.items()  # type: ignore[attr-defined]
    quit_item = next(i for i in items if i != FakeMenu.SEPARATOR and i.text.startswith("Quit"))
    quit_item.action(rig.toolkits.icons[0], quit_item)
    until(lambda: ended == [0])
    thread.join(30)
    assert not thread.is_alive() and "destroy" not in rig.toolkits.windows[0].calls
    assert not SingleApp(rig.data).running(), "the app let go of the folder before it ended"


def late_engine(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> tuple[threading.Event, list[int]]:
    """pywebview whose engine comes up only when the test says (then its start callback runs), and an
    end of the process that is recorded, not made."""
    up = threading.Event()
    ended: list[int] = []

    def start(func: Any = None, **kwargs: Any) -> None:
        rig.toolkits.started.append(kwargs)
        assert up.wait(30)
        func()
        assert rig.toolkits.windows[0].destroyed.wait(30), "the window loop runs until the window is destroyed"

    monkeypatch.setattr(sys.modules["webview"], "start", start)
    monkeypatch.setattr(webshell, "HARD_EXIT", ended.append)
    return up, ended


def tray_item(rig: Rig, text: str) -> Any:
    items = rig.toolkits.icons[0].menu.items()  # type: ignore[attr-defined]
    return next(i for i in items if i != FakeMenu.SEPARATOR and i.text.startswith(text))


def test_an_engine_that_comes_after_the_fallback_gets_the_page_and_quit_ends_the_app_the_normal_way(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(webshell, "ENGINE_WAIT_SEC", 0.3)
    rig = Rig(tmp_path, monkeypatch)
    up, ended = late_engine(rig, monkeypatch)
    thread = threading.Thread(target=rig.run, daemon=True)
    thread.start()
    until(lambda: rig.browser == [PAGE] and rig.ctx.watch is not None)  # the fallback, at "60 s"
    (window,) = rig.toolkits.windows
    up.set()  # at "61 s"
    until(lambda: window.loaded == [PAGE + "#app"])
    item = tray_item(rig, OPEN_LABEL)
    item.action(rig.toolkits.icons[0], item)
    assert "show" in window.calls and rig.browser == [PAGE], "Open shows the window now, not a second tab"
    item = tray_item(rig, "Quit")
    item.action(rig.toolkits.icons[0], item)
    thread.join(30)
    assert not thread.is_alive() and "destroy" in window.calls and ended == [], "no end of the process needed"


# ---- the daemon ends (its watch quits the app) at every moment of the window's start


def daemon_ends(rig: Rig) -> None:
    """What the app's watch does when its daemon has ended (session.DaemonWatch -> AppActions)."""
    until(lambda: rig.ctx.actions is not None)
    assert rig.ctx.actions is not None
    rig.ctx.actions.daemon_gone()


def test_the_daemon_ends_while_webview2_starts_and_the_app_ends_in_seconds_without_destroying_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _no_end_of_the_test_process: list[int]
) -> None:
    """The order of an install proof's log: quit (the window hidden), then the window's `shown`, then
    WebView2's E_ABORT, and pywebview's loop never returns."""
    monkeypatch.setattr(webshell, "QUIT_GRACE_SEC", 1.0)
    monkeypatch.setattr(webshell, "LEAVE_SEC", 5.0)
    rig = Rig(tmp_path, monkeypatch)
    up = threading.Event()

    def start(func: Any = None, **kwargs: Any) -> None:
        rig.toolkits.started.append(kwargs)
        assert up.wait(30)
        (window,) = rig.toolkits.windows
        for handler in list(window.events.shown.handlers):
            handler()  # the window's `shown`, after the quit
        func()
        threading.Event().wait(30)  # E_ABORT: the loop does not return

    monkeypatch.setattr(sys.modules["webview"], "start", start)
    thread = threading.Thread(target=rig.run, daemon=True)
    thread.start()
    daemon_ends(rig)
    up.set()
    started = time.monotonic()
    until(lambda: _no_end_of_the_test_process == [0], 10.0)
    assert time.monotonic() - started < webshell.LEAVE_SEC, "within seconds, not after the long wait"
    assert "destroy" not in rig.toolkits.windows[0].calls, "a WebView2 in its start is not destroyed"
    assert not SingleApp(rig.data).running(), "the app let go of the folder before it ended"


def test_the_daemon_ends_before_the_window_is_made_and_no_window_loop_is_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _no_end_of_the_test_process: list[int]
) -> None:
    rig = Rig(tmp_path, monkeypatch)
    iconed = webshell.new_icon

    def quit_first(frame: webshell.WebFrame, launch: Launch) -> Any:
        icon = iconed(frame, launch)
        frame.quit()  # (the tray icon is made first: the quit comes before the window)
        return icon

    monkeypatch.setattr(webshell, "new_icon", quit_first)
    assert rig.run() == 0
    assert rig.toolkits.windows == [] and rig.toolkits.started == [] and _no_end_of_the_test_process == []


def test_the_daemon_ends_between_the_window_and_its_loop_and_the_loop_is_not_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _no_end_of_the_test_process: list[int]
) -> None:
    rig = Rig(tmp_path, monkeypatch)
    made = webshell.make_window

    def quit_after(frame: webshell.WebFrame, launch: Launch) -> Any:
        window = made(frame, launch)
        frame.quit()
        return window

    monkeypatch.setattr(webshell, "make_window", quit_after)
    assert rig.run() == 0
    assert rig.toolkits.started == [] and "destroy" not in rig.toolkits.windows[0].calls
    assert _no_end_of_the_test_process == [], "the run returns by itself"


def test_the_daemon_ends_after_the_window_is_up_and_the_app_ends_the_normal_way(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _no_end_of_the_test_process: list[int]
) -> None:
    rig = Rig(tmp_path, monkeypatch)
    thread = threading.Thread(target=rig.run, daemon=True)
    thread.start()
    until(lambda: rig.toolkits.started and rig.ctx.watch is not None)
    daemon_ends(rig)
    thread.join(30)
    assert not thread.is_alive() and "destroy" in rig.toolkits.windows[0].calls
    assert _no_end_of_the_test_process == [], "the window loop returned: no end of the process needed"


def test_a_tray_icon_that_does_not_stop_cannot_keep_the_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _no_end_of_the_test_process: list[int]
) -> None:
    monkeypatch.setattr(webshell, "QUIT_GRACE_SEC", 1.0)
    rig = Rig(tmp_path, monkeypatch)
    up = threading.Event()

    def start(func: Any = None, **kwargs: Any) -> None:
        rig.toolkits.started.append(kwargs)
        threading.Event().wait(30)  # an engine that never comes up

    monkeypatch.setattr(sys.modules["webview"], "start", start)
    thread = threading.Thread(target=rig.run, daemon=True)
    thread.start()
    until(lambda: rig.toolkits.icons and rig.toolkits.started)
    monkeypatch.setattr(rig.toolkits.icons[0], "stop", lambda: up.wait(30))  # pystray's stop that blocks
    daemon_ends(rig)
    until(lambda: _no_end_of_the_test_process == [0], 10.0)
    up.set()


def test_quit_pressed_twice_before_the_page_stops_the_daemon_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = Rig(tmp_path, monkeypatch)
    gate = OwnedGate(rig.data)
    assert rig.single.acquire()
    launch = Launch(rig.data, Opening(rig.data, gate).start(), False, True, rig.auto, rig.single, rig.daemon)
    thread = threading.Thread(target=lambda: webshell.run(launch), daemon=True)
    thread.start()
    until(lambda: rig.toolkits.started)
    for _ in range(2):
        item = tray_item(rig, "Quit")
        item.action(rig.toolkits.icons[0], item)
    gate.open.set()
    thread.join(30)
    assert not thread.is_alive() and rig.daemon.stopped == [rig.data], "one stop, not two"
    launch.close()
