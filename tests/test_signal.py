"""Signal (neoaprs/signal.py): synchronous, in the order of connecting, and a handler that fails does not stop the others."""
import logging

import pytest

from neoaprs.signal import Signal


def test_handlers_are_called_in_the_order_they_connected_with_the_arguments() -> None:
    seen: list[tuple[str, int, str]] = []
    s: Signal[[int, str]] = Signal("heard")
    s.connect(lambda n, text: seen.append(("a", n, text)))
    s.connect(lambda n, text: seen.append(("b", n, text)))
    s.emit(3, "x")
    assert seen == [("a", 3, "x"), ("b", 3, "x")] and len(s) == 2


def test_disconnect_and_clear() -> None:
    seen: list[int] = []
    s: Signal[[int]] = Signal()
    first, second = seen.append, lambda n: seen.append(n * 10)
    s.connect(first)
    s.connect(second)
    s.disconnect(first)
    s.emit(1)
    assert seen == [10]
    s.clear()
    s.emit(2)
    assert seen == [10] and len(s) == 0


@pytest.mark.expects_errors
def test_a_handler_that_fails_is_logged_and_the_others_still_run(caplog: pytest.LogCaptureFixture) -> None:
    seen: list[int] = []

    def broken(n: int) -> None:
        raise RuntimeError("boom")

    s: Signal[[int]] = Signal("frames")
    s.connect(broken)
    s.connect(seen.append)
    with caplog.at_level(logging.ERROR, "neoaprs.signal"):
        s.emit(7)
    assert seen == [7]
    assert any("a handler of signal frames failed" in r.getMessage() for r in caplog.records)


def test_a_handler_may_disconnect_itself_while_the_signal_is_emitting() -> None:
    seen: list[str] = []
    s: Signal[[]] = Signal()

    def once() -> None:
        seen.append("once")
        s.disconnect(once)

    s.connect(once)
    s.connect(lambda: seen.append("always"))
    s.emit()
    s.emit()
    assert seen == ["once", "always", "always"]


def test_disconnect_removes_a_bound_method() -> None:
    """A bound method is a new object each time it is read, so `is` never finds it: disconnect compares by equality, which bound methods of one object and one function have."""
    class Listener:
        def __init__(self) -> None:
            self.calls = 0

        def on_it(self) -> None:
            self.calls += 1

    s: Signal[[]] = Signal("bound")
    listener = Listener()
    s.connect(listener.on_it)
    s.emit()
    s.disconnect(listener.on_it)
    s.emit()
    assert listener.calls == 1
    assert len(s) == 0
