"""A stand-in for the desktop app's shells (neoaprs/desktop/qtshell.py, winshell.py): `FakeFrame` is the toolkit as the app's logic sees it (it writes down what it is asked), and the module's `run` is a
shell that `neoaprs.desktop.cmd.run` can be given by name (`Choice("tests.support.fakeshell", True)`): it makes the actions, tells the app it is ready and waits until a quit reaches it, or until `STEPS` (a script of what to do first) is done.

    frame = FakeFrame(); frame.shown, frame.told, frame.quits    what the app asked of the window, the tray and the loop
"""
import threading
from collections.abc import Callable

from neoaprs.desktop.shell import ShellContext


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


def run(ctx: ShellContext) -> int:
    frame = FakeFrame(ctx.window)
    FRAMES.append(frame)
    actions = ctx.actions_for(frame)
    ctx.ready(actions)
    for step in STEPS:
        step(frame)
    frame.ended.wait(30)
    return 0
