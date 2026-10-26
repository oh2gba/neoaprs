"""What escapes: an exception that nothing caught goes to the log with its traceback, wherever it came from. Python prints these to stderr, which a service has in its journal but a program without a console (Windows's
`neoaprsw` and `neoaprs-app`) has nowhere; the log is where the person who reads a support bundle looks.

`install` takes over `sys.excepthook` (the main thread, and so an exception that ends the program) and `threading.excepthook` (any thread of ours) and gives back the function that restores them; `loop_handler` is the event
loop's exception handler (a task nobody awaited that failed, a callback that raised, a transport that broke), which asyncio would otherwise write to the logger `asyncio` in its own words."""
import asyncio
import logging
import sys
import threading
from collections.abc import Callable
from types import TracebackType
from typing import Any

SHOWN_CONTEXT = ("task", "future", "handle", "protocol", "transport", "source_traceback")
MAX_CONTEXT_CHARS = 300


def install(log: logging.Logger, chain: bool = False) -> Callable[[], None]:
    """Logs the exceptions that end the program or a thread (not Ctrl+C or a plain exit). `chain`: and still lets Python print them to stderr, for a program that is run in a console and has no handler there."""
    before_sys, before_thread = sys.excepthook, threading.excepthook

    def on_main(kind: type[BaseException], error: BaseException, trace: TracebackType | None) -> None:
        if issubclass(kind, (KeyboardInterrupt, SystemExit)):
            before_sys(kind, error, trace)
            return
        log.critical("uncaught exception, the program ends", exc_info=(kind, error, trace))
        if chain:
            before_sys(kind, error, trace)

    def on_thread(args: "threading.ExceptHookArgs") -> None:
        if args.exc_type is SystemExit or args.exc_value is None:
            return
        name = args.thread.name if args.thread is not None else "?"
        log.error("uncaught exception in the thread %s", name, exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        if chain:
            before_thread(args)

    sys.excepthook, threading.excepthook = on_main, on_thread

    def restore() -> None:
        sys.excepthook, threading.excepthook = before_sys, before_thread
    return restore


def loop_handler(log: logging.Logger) -> Callable[[asyncio.AbstractEventLoop, dict[str, Any]], None]:
    """The exception handler of an event loop: asyncio's message, what it names (the task, the callback), and the traceback."""
    def handle(loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        error = context.get("exception")
        message = str(context.get("message", "unhandled exception in the event loop"))
        named = "; ".join(f"{key}: {str(context[key])[:MAX_CONTEXT_CHARS]}" for key in SHOWN_CONTEXT if context.get(key))
        exc_info = (type(error), error, error.__traceback__) if isinstance(error, BaseException) else None
        log.error("event loop: %s%s", message, f" ({named})" if named else "", exc_info=exc_info)
    return handle
