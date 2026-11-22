"""A stand-in for the desktop app's shells (neoaprs/desktop/qtshell.py, webshell.py): `FakeFrame` is
the toolkit as the app logic sees it, and `run` is a shell that `neoaprs.desktop.cmd.run` can be
given by name.
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
        self.loaded: list[str] = []
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

    def load(self, url: str) -> None:
        self.loaded.append(url)


FRAMES: list[FakeFrame] = []                        # the frame of every run, newest last
# What a test wants done once the app is ready (runs in the shell's thread)
STEPS: list[Callable[[FakeFrame], None]] = []
# What the shell did, in order (a test that wants the time of each replaces `event`)
EVENTS: list[str] = []


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
