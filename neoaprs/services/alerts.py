"""The message alert: a shell command the operator chose, run when a message to us arrives.

`alert(record)` is told by the inbox of every message to us the first time it is heard (a repeat or another digipeater's copy is not told again, and an ack, a reject, a bulletin, a group message and a
message we only overheard never get here). A query (`?APRSP` and the others, queries.py) is answered, not announced. With `messages/alert` on and `messages/alert_command` not empty the command runs through
the shell (`asyncio.create_subprocess_shell`; on Windows PowerShell, started by a thread) with these in its environment, next to the few variables a program needs to find the desktop
(neoaprs/childenv.py):

    NEOAPRS_FROM     the sender's call
    NEOAPRS_TEXT     the text of the message
    NEOAPRS_AT       when it was heard, ISO 8601 in UTC (2026-10-21T12:00:00Z)
    NEOAPRS_MSG_ID   the message id the sender gave it; empty when it had none

The text comes in the environment and not in the command line, so what a stranger wrote is never read as shell. The command gets TIMEOUT_SEC seconds, then it is killed with everything it started; its output is
logged at DEBUG. `test()` runs the command as saved for a made-up message (the test button of the page), whatever `messages/alert` says, and answers (ok, text). A command that fails (it cannot start, exits with a status other than 0, runs out of time) is logged as a warning once an hour, then at DEBUG: an alert that cannot be made must not fill the log or
touch the daemon, and nothing here raises.
"""
import asyncio
import base64
import logging
import os
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

from neoaprs.childenv import child_environment
from neoaprs.clock import Clock, iso, utcnow
from neoaprs.message import MessageRecord, is_query
from neoaprs.services.common import ConfigSource
from neoaprs.tasks import TaskSet

log = logging.getLogger("neoaprs.alerts")

TIMEOUT_SEC = 60.0 if sys.platform == "win32" else 20.0          # a cold PowerShell on a busy Windows machine can take longer than 20 s to show a toast
TOLD_EVERY = timedelta(hours=1)
TEST_FROM = "NEOAPRS"                                            # the message the test button pretends to have heard
TEST_TEXT = "This is a test of the NeoAPRS alert"
MAX_RUNNING = 5                                                 # alerts running at once; more are dropped (a flood of messages is no reason to start a flood of programs)
MAX_LINE = 200                                                  # characters of the first line of stderr the test button shows
MAX_OUTPUT = 400                                                # characters of a command's output kept in the log
POWERSHELL = ("powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-OutputFormat", "Text", "-EncodedCommand")       # (Text: else what it writes to stderr is XML)
POWERSHELL_PRELUDE = "$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';"           # the Windows counterpart of `set -e` for cmdlets; the status of a program that failed is passed on by the postlude
POWERSHELL_POSTLUDE = ";if($LASTEXITCODE){exit $LASTEXITCODE}"


@dataclass(frozen=True)
class Outcome:
    """How a run of the command ended: `problem` when it could not start or ran out of time, else its exit status and what it wrote to stdout and stderr."""
    problem: str = ""
    status: int = 0
    out: str = ""
    err: str = ""

    @property
    def ok(self) -> bool:
        return not self.problem and self.status == 0

    @property
    def output(self) -> str:
        return (self.out + self.err).strip()[:MAX_OUTPUT]

    @property
    def short(self) -> str:
        """What the page is told of a failure: the problem, or the exit code and the first line of stderr."""
        if self.problem:
            return self.problem
        line = next((ln.strip() for ln in self.err.splitlines() if ln.strip()), "")
        return f"exit code {self.status}: {line[:MAX_LINE]}" if line else f"exit code {self.status}"


def alert_environment(record: MessageRecord, base: dict[str, str] | None = None) -> dict[str, str]:
    """The environment of the command: what childenv lets through and the four NEOAPRS_ variables (a NUL byte cannot be in an environment and is dropped)."""
    env = child_environment() if base is None else base
    env.update({"NEOAPRS_FROM": record.from_call, "NEOAPRS_TEXT": record.text.replace("\0", ""), "NEOAPRS_AT": iso(record.at) or "", "NEOAPRS_MSG_ID": record.msg_id or ""})
    return env


class Alerts:
    def __init__(self, config: ConfigSource, clock: Clock = utcnow, timeout_sec: float = TIMEOUT_SEC) -> None:
        self._config = config
        self.clock = clock
        self.timeout_sec = timeout_sec
        self._told_at: datetime | None = None                   # when a failure was last logged above DEBUG
        self._tasks = TaskSet(log, "alert")

    def alert(self, record: MessageRecord) -> None:
        """A message to us was heard for the first time: run the command, in a task."""
        c = self._config()
        command = c.messages_alert_command.strip()
        if not c.messages_alert or not command or is_query(record.text):
            return
        if len(self._tasks) >= MAX_RUNNING:
            log.debug("the alert for the message from %s is dropped: %d alerts are running", record.from_call, MAX_RUNNING)
            return
        self._tasks.spawn(self._run(command, alert_environment(record), record.from_call), "alert")

    async def stop(self) -> None:
        """An alert that is running is ended with the daemon (the command and what it started are killed)."""
        await self._tasks.cancel_all()

    async def _run(self, command: str, env: dict[str, str], sender: str) -> None:
        outcome = await self._execute(command, env)
        log.debug("the alert for the message from %s ended with status %s: %s", sender, outcome.status, outcome.output)
        if not outcome.ok:
            self._fail(outcome.problem or f"the alert command ended with status {outcome.status}: {outcome.output}")

    async def test(self) -> tuple[bool, str]:
        """The test button: the command as it is saved, run as for a real message (the same environment, the same 20 s) from a made-up one, whatever `messages/alert` says. (ok, "ran" or why not: the
        exit code and the first line of stderr). A command that is empty is a ValueError; the log is not told, the operator is looking at the answer."""
        command = self._config().messages_alert_command.strip()
        if not command:
            raise ValueError("no alert command")
        record = MessageRecord(0, self.clock(), "in", TEST_FROM, "", TEST_TEXT, None, "received")
        outcome = await self._execute(command, alert_environment(record))
        return outcome.ok, "ran" if outcome.ok else outcome.short

    async def _execute(self, command: str, env: dict[str, str]) -> "Outcome":
        if sys.platform == "win32":
            return await self._execute_in_thread(command, env)
        else:
            return await self._execute_in_shell(command, env)

    async def _execute_in_shell(self, command: str, env: dict[str, str]) -> "Outcome":
        """The shell line runs under `set -e`: a step that fails ends the command with its status, so a missing notifier is not hidden by the sound that follows it."""
        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_shell("set -e\n" + command, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            out, err = await asyncio.wait_for(proc.communicate(), self.timeout_sec)
        except TimeoutError:
            return Outcome(problem=f"the alert command did not end within {self.timeout_sec:g} s: killed")
        except Exception as e:                                   # (nothing a command does may stop the daemon)
            return Outcome(problem=f"the alert command could not run: {e}")
        finally:
            if proc is not None and proc.returncode is None:
                self._kill(proc)
                await proc.wait()
        return Outcome(status=proc.returncode or 0, out=out.decode("utf-8", errors="replace"), err=err.decode("utf-8", errors="replace"))

    async def _execute_in_thread(self, command: str, env: dict[str, str]) -> "Outcome":
        """Windows: a thread starts the process, whatever loop runs (and the Windows loops differ in what they can do), with PowerShell and the line as an encoded script (no quoting of the line, and the text
        never in it). A run that is cancelled (the daemon ends) kills the process and what it started."""
        running = _Running()
        try:
            return await asyncio.to_thread(self._run_powershell, command, env, running)
        finally:
            running.kill()

    def _run_powershell(self, command: str, env: dict[str, str], running: "_Running") -> "Outcome":
        script = base64.b64encode((POWERSHELL_PRELUDE + command + POWERSHELL_POSTLUDE).encode("utf-16-le")).decode("ascii")
        try:
            creation = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            proc = subprocess.Popen([*POWERSHELL, script], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creation)
        except Exception as e:                                   # (nothing a command does may stop the daemon)
            return Outcome(problem=f"the alert command could not run: {e}")
        running.set(proc)
        try:
            out, err = proc.communicate(timeout=self.timeout_sec)
        except subprocess.TimeoutExpired:
            running.kill()
            proc.communicate()
            return Outcome(problem=f"the alert command did not end within {self.timeout_sec:g} s: killed")
        except Exception as e:
            running.kill()
            return Outcome(problem=f"the alert command could not run: {e}")
        return Outcome(status=proc.returncode or 0, out=out.decode("utf-8", errors="replace"), err=err.decode("utf-8", errors="replace"))

    @staticmethod
    def _kill(proc: asyncio.subprocess.Process) -> None:
        if sys.platform == "win32":
            proc.kill()
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)              # (it leads a session of its own: the shell and what it started)
            except (ProcessLookupError, PermissionError):
                proc.kill()

    def _fail(self, text: str) -> None:
        now = self.clock()
        if self._told_at is None or now - self._told_at >= TOLD_EVERY:
            self._told_at = now
            log.warning("%s (told once an hour)", text)
        else:
            log.debug("%s", text)


class _Running:
    """The process a thread started, so that the loop can end it and everything it started."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[bytes] | None = None

    def set(self, proc: "subprocess.Popen[bytes]") -> None:
        with self._lock:
            self._proc = proc

    def kill(self) -> None:
        with self._lock:
            proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        try:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], stdin=subprocess.DEVNULL, capture_output=True, timeout=10, check=False)      # (the whole tree: PowerShell and what it started)
        except Exception:
            pass
        try:
            proc.kill()
        except OSError:
            pass
