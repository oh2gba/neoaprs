"""A signal in the Qt sense: handlers connect, the owner emits, every handler is called in order.

Synchronous; a handler that must wait starts a task. A failing handler is logged, not fatal.
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
        # Compare by equality: a bound method is a new object on every read, so `is` never matches.
        self._handlers = [h for h in self._handlers if h != handler]

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
