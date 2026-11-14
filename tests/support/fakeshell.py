"""A stand-in for the desktop app's shells (neoaprs/desktop/qtshell.py, winshell.py): `FakeFrame` is the toolkit as the app's logic sees it (it writes down what it is asked), and the module's `run` is a
shell that `neoaprs.desktop.cmd.run` can be given by name (`Choice("tests.support.fakeshell", True)`): as a real one it makes its window at once (it writes "window" into `EVENTS`), waits for the session, and
then makes the actions, gives the window the page ("page URL"), tells the app it is ready and waits until a quit reaches it, or until `STEPS` (a script of what to do first) is done; when no page comes it closes
the window ("closed") and ends as the app does then.

    frame = FakeFrame(); frame.shown, frame.told, frame.quits    what the app asked of the window, the tray and the loop
"""
import threading
from collections.abc import Callable

from neoaprs.desktop.session import NoPage
from neoaprs.desktop.shell import Launch


class FakeFrame:
    def __init__(self, has_window: bool = True) -> None:
        self.has_window = has_window
        self.shown = 0
        self.refreshed = 0
        self.told: list[str] = []
        self.quits = 0
        self.ended = threading.Event()

    def show_window(self) -> None:
        self.shown += 1

    def quit(self) -> None:
        self.quits += 1
        self.ended.set()

    def refresh(self) -> None:
        self.refreshed += 1

    def tell(self, text: str) -> None:
        self.told.append(text)


FRAMES: list[FakeFrame] = []                        # the frame of every run, newest last
STEPS: list[Callable[[FakeFrame], None]] = []       # what a test wants done once the app is ready (runs in the shell's thread)
EVENTS: list[str] = []                              # what the shell did, in order (a test that wants the time of each replaces `event`)


def event(name: str) -> None:
    EVENTS.append(name)


def run(launch: Launch) -> int:
    frame = FakeFrame(launch.window)
    FRAMES.append(frame)
    event("window")
    try:
        ctx = launch.context(launch.opening.result())
    except NoPage as e:
        event("closed")
        return launch.no_page(e)
    event(f"page {ctx.session.url}")
    actions = ctx.actions_for(frame)
    ctx.ready(actions)
    for step in STEPS:
        step(frame)
    frame.ended.wait(30)
    return 0
