"""The desktop app's start: the window is made at once with the loading page (neoaprs/desktop/loading.py), the daemon is started without waiting for it and the toolkit is looked for while it comes up,
and the window goes to the daemon's page when it answers (polled every 0.05 s), or closes with the words the app has always said when no page comes. `neoaprs app` with the scripted shell of
tests/support/fakeshell.py on a slow daemon in virtual time (the wait's clock and sleep are the test's), and the Windows shell against the stand-ins of tests/test_desktop_winshell.py; the Qt shell's
part is in tests/test_desktop_qt.py."""
import re
import subprocess
import threading
import types
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from neoaprs.cli import opencmd
from neoaprs.desktop import cmd, loading, session, winshell
from neoaprs.desktop.menu import OPEN_LABEL
from neoaprs.desktop.session import Daemon, NoPage, Opening, Session
from neoaprs.desktop.shell import Choice, Launch
from neoaprs.desktop.single import SingleApp
from tests.support import fakeshell
from tests.test_desktop_logic import PAGE
from tests.test_desktop_winshell import FakeMenu, Rig, until

ROOT = Path(__file__).resolve().parent.parent


# ---- the loading page

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
    body = loading.HTML[loading.HTML.index("<body>"):]
    assert re.sub(r"<[^>]+>", "", body) == "NeoAPRS", "nothing to read but the name"
    assert not any(word in loading.HTML for word in ("<script", "animation", "transition", "@keyframes", "src=", "href=", "url(")), "nothing moves and nothing is fetched"


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
    assert heard == ["early", "late"], "the one that asked before is called when it comes, the one that asks after at once"


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
    """The wait's time: `sleep` moves it on at once. `hold` (an Event) is waited for before the first sleep, which is the daemon being slow: nothing answers before the window is there."""

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
        self.now = round(self.now + seconds, 9)                  # (a sum of twentieths that is the second it should be)

    def said(self) -> str:
        return f"{self.now:.2f}"


def slow_page(monkeypatch: pytest.MonkeyPatch, clock: VirtualClock, answers_at: float | None, looks: list[str]) -> None:
    """A daemon whose page answers at `answers_at` seconds of the clock (None: never), and has held its lock since it started; `looks` gets what the wait asked, in order."""
    def page_answers(url: str) -> bool:
        looks.append("page")
        return answers_at is not None and clock.now >= answers_at

    def is_running(data: Path) -> bool:
        looks.append("lock")
        return True

    monkeypatch.setattr(opencmd, "page_url", lambda data: PAGE)
    monkeypatch.setattr(opencmd, "page_answers", page_answers)
    monkeypatch.setattr(opencmd, "is_running", is_running)


def test_the_wait_looks_every_twentieth_of_a_second_and_at_the_lock_only_once_the_page_answers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clock, looks = VirtualClock(), []
    slow_page(monkeypatch, clock, 3.0, looks)
    child = types.SimpleNamespace(poll=lambda: None)
    assert opencmd.wait_for_page(tmp_path, child, 60.0, clock.time, clock.sleep) == PAGE  # type: ignore[arg-type]
    assert set(clock.sleeps) == {opencmd.POLL_SEC} and opencmd.POLL_SEC == 0.05 and 3.0 <= clock.now < 3.0 + 2 * opencmd.POLL_SEC
    assert looks[-2:] == ["page", "lock"] and looks.count("lock") == 1, "the lock of a daemon that is starting is not taken for a look"


class App:
    """`neoaprs app` with the scripted shell, the toolkit's look written down, and its daemon a slow one on the virtual clock (the real open_session and wait_for_page)."""

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
        daemon = Daemon(running=lambda data: False, start=self.start, wait=lambda data, child, seconds: opencmd.wait_for_page(data, child, seconds, self.clock.time, self.clock.sleep))
        monkeypatch.setattr(cmd, "open_session", lambda data, timeout, encryption: session.open_session(data, daemon, timeout, encryption))
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
        return types.SimpleNamespace(poll=lambda: None)          # type: ignore[return-value]

    def choose(self) -> Choice:
        assert self.started.wait(30), "the daemon is started before the toolkit is looked for, not after its page answers"
        self.events.append(("toolkit", self.clock.said()))
        return Choice("tests.support.fakeshell", True)

    def run(self) -> int:
        return cmd.run(cmd.parser().parse_args(["--data", str(self.data)]))


def test_on_a_slow_daemon_the_window_is_there_at_once_and_goes_to_the_page_when_it_answers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = App(tmp_path, monkeypatch, answers_at=3.0)
    fakeshell.STEPS.append(lambda frame: frame.quit())
    assert app.run() == 0
    assert app.events == [("daemon started", "0.00"), ("toolkit", "0.00"), ("window", "0.00"), (f"page {PAGE}", "3.00")]
    assert app.said == [] and not SingleApp(app.data).running()


def test_a_daemon_that_never_comes_closes_the_window_after_the_timeout_and_says_so(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = App(tmp_path, monkeypatch, answers_at=None)
    assert app.run() == 1
    assert [name for name, _ in app.events] == ["daemon started", "toolkit", "window", "closed"] and app.events[-1][1] == "60.00"
    assert app.said == [f"app: NeoAPRS did not come up: no page came up on {app.data} within 60 s; see the log, neoaprs.log in that folder. The log is {app.data / 'neoaprs.log'}"]
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
def pending(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Rig, Gate, Launch, list[str], Callable[[], threading.Thread]]]:
    rig = Rig(tmp_path, monkeypatch)
    gate = Gate(rig.data)
    assert rig.single.acquire()
    launch = Launch(rig.data, Opening(rig.data, gate).start(), False, True, rig.auto, rig.single, rig.daemon)
    told: list[str] = []
    monkeypatch.setattr(opencmd, "tell_the_user", told.append)
    codes: list[int] = []

    def go() -> threading.Thread:
        thread = threading.Thread(target=lambda: codes.append(winshell.run(launch)), daemon=True)
        thread.start()
        until(lambda: rig.toolkits.started)
        return thread

    yield rig, gate, launch, told, go
    gate.open.set()
    launch.close()


def texts(rig: Rig) -> list[Any]:
    return [i if i == FakeMenu.SEPARATOR else i.text for i in rig.toolkits.icons[0].menu.items()]  # type: ignore[attr-defined]


def test_the_windows_window_shows_the_loading_page_before_the_daemon_answers_and_its_page_after(pending: tuple[Rig, Gate, Launch, list[str], Callable[[], threading.Thread]]) -> None:
    rig, gate, launch, told, go = pending
    thread = go()
    (window,) = rig.toolkits.windows
    assert window.kwargs["html"] == loading.HTML and window.loaded == [] and not launch.opening.done()
    assert texts(rig) == [OPEN_LABEL] and rig.toolkits.icons[0].calls == ["run_detached"], "the tray is there, with Open alone"
    (opening,) = rig.toolkits.icons[0].menu.items()                # type: ignore[attr-defined]
    opening.action(rig.toolkits.icons[0], opening)
    assert window.calls == ["show", "restore"], "Open shows the window that waits"
    gate.open.set()
    until(lambda: window.loaded == [PAGE + "#app"] and launch.ctx is not None and launch.ctx.watch is not None)
    assert texts(rig)[-1] == "Quit (NeoAPRS keeps running as a service)" and "update_menu" in rig.toolkits.icons[0].calls
    assert window.kwargs["js_api"].page_url == PAGE
    item = next(i for i in rig.toolkits.icons[0].menu.items() if i != FakeMenu.SEPARATOR and i.text.startswith("Quit"))  # type: ignore[attr-defined]
    item.action(rig.toolkits.icons[0], item)
    thread.join(30)
    assert not thread.is_alive() and told == []


def test_the_windows_window_closes_when_no_page_comes_and_the_app_says_why(pending: tuple[Rig, Gate, Launch, list[str], Callable[[], threading.Thread]]) -> None:
    rig, gate, launch, told, go = pending
    thread = go()
    gate.error = NoPage(f"no page came up on {rig.data} within 60 s; see the log, neoaprs.log in that folder")
    gate.open.set()
    thread.join(30)
    (window,) = rig.toolkits.windows
    assert not thread.is_alive() and window.calls[-1] == "destroy" and window.loaded == []
    assert told == [f"app: NeoAPRS did not come up: no page came up on {rig.data} within 60 s; see the log, neoaprs.log in that folder. The log is {rig.data / 'neoaprs.log'}"]
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
        return types.SimpleNamespace(HKEY_CURRENT_USER="HKCU", OpenKey=open_key, QueryValueEx=lambda key, name: (key.value, 4))

    assert winshell.dark_scheme(registry(0)) is True and winshell.dark_scheme(registry(1)) is False and winshell.dark_scheme(registry(None)) is False
