"""A program run as an administrator (neoaprs/winelevate.py): the thread that waits for the prompt and hands the answer to the loop, and the refusal off Windows. The call of Windows itself (ShellExecuteExW with `runas`)
is not run in a test: it would raise the UAC prompt."""
import threading

import pytest

from neoaprs import winelevate
from neoaprs.winelevate import Declined, elevated, run_elevated


def test_off_windows_nothing_is_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(winelevate, "on_windows", lambda: False)
    with pytest.raises(OSError, match="Windows only"):
        run_elevated("netsh.exe", "advfirewall", 1.0)


async def test_the_exit_code_comes_back_from_a_thread_that_is_not_the_loops(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, str, float, bool]] = []

    def run(file: str, parameters: str, timeout_sec: float) -> int:
        seen.append((file, parameters, timeout_sec, threading.current_thread() is threading.main_thread()))
        return 5

    monkeypatch.setattr(winelevate, "run_elevated", run)
    assert await elevated("netsh.exe", "advfirewall", 60.0) == 5
    assert seen == [("netsh.exe", "advfirewall", 60.0, False)]


@pytest.mark.parametrize("error", [Declined(), OSError(5, "Access is denied"), TimeoutError("late")])
async def test_a_declined_prompt_a_failure_and_a_timeout_are_raised_to_the_waiter(monkeypatch: pytest.MonkeyPatch, error: BaseException) -> None:
    def run(file: str, parameters: str, timeout_sec: float) -> int:
        raise error

    monkeypatch.setattr(winelevate, "run_elevated", run)
    with pytest.raises(type(error)):
        await elevated("netsh.exe", "advfirewall", 60.0)
