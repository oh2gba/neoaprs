"""A signal in the Qt sense: handlers connect, the owner emits, every handler is called in order.

Synchronous on purpose: the program is one asyncio loop, and a handler that needs to wait starts a
task of its own. An exception in one handler is logged and does not stop the others, so a bug in the
page's view never silences the alarm.
"""
import logging
from typing import Callable, Generic, ParamSpec

P = ParamSpec("P")
log = logging.getLogger("neoaprs.signal")


class Signal(Generic[P]):
    def __init__(self, name: str = "") -> None:
        self._handlers: list[Callable[P, object]] = []
        self.name = name

    def connect(self, handler: Callable[P, object]) -> None:
        self._handlers.append(handler)

    def disconnect(self, handler: Callable[P, object]) -> None:
        self._handlers = [h for h in self._handlers if h != handler]          # by equality: a bound method is a new object each time it is read, and `is` would never find it

    def clear(self) -> None:
        self._handlers.clear()

    def __len__(self) -> int:
        return len(self._handlers)

    def emit(self, *args: P.args, **kwargs: P.kwargs) -> None:
        for handler in list(self._handlers):
            try:
                handler(*args, **kwargs)
            except Exception:
                log.exception("a handler of signal %s failed", self.name or "?")
