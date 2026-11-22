"""The alert: a shell command run when a message to us arrives or a station alert fires.

The text travels in the environment (`NEOAPRS_*`), never in the command line. The command is
killed after TIMEOUT_SEC; a failure is logged once an hour; nothing here raises.
"""
import asyncio
import logging
import os
import signal
import subprocess
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from neoaprs import nodevices
from neoaprs.alertcommand import DEFAULT_ALERT_COMMAND
from neoaprs.childenv import child_environment, windows_program
from neoaprs.clock import Clock, iso, utcnow
from neoaprs.coded import CodedError
from neoaprs.message import MessageRecord, is_query
from neoaprs.pref import Fired
from neoaprs.services.common import ConfigSource
from neoaprs.tasks import TaskSet

log = logging.getLogger("neoaprs.alerts")

TIMEOUT_SEC = 60.0 if sys.platform == "win32" else 20.0
TOLD_EVERY = timedelta(hours=1)
TEST_FROM = "NEOAPRS"
TEST_TEXT = "This is a test of the NeoAPRS alert"
# more alerts than this are dropped
MAX_RUNNING = 5
MAX_LINE = 200
MAX_OUTPUT = 400
# the script goes in on standard input: an encoded command looks like malware to Defender
POWERSHELL_ARGS = ("-NoProfile", "-NonInteractive", "-OutputFormat", "Text", "-Command", "-")
# the Windows counterpart of `set -e`
POWERSHELL_PRELUDE = "$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';"
POWERSHELL_POSTLUDE = ";if($LASTEXITCODE){exit $LASTEXITCODE}"


@dataclass(frozen=True)
class Outcome:
    """How a run ended: `problem` if it could not start or timed out, else its status and output."""
    problem: str = ""
    why: Literal["", "timeout", "no_start"] = ""
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
    def kind(self) -> Literal["ran", "exit", "timeout", "no_start"]:
        """How it ended, as a code."""
        return self.why or ("ran" if self.status == 0 else "exit")

    @property
    def first_line(self) -> str:
        """The first non-empty line of stderr, or ""."""
        return next((ln.strip() for ln in self.err.splitlines() if ln.strip()), "")[:MAX_LINE]

    @property
    def short(self) -> str:
        """The failure as shown to the operator: the problem, or exit code and first stderr line."""
        if self.problem:
            return self.problem
        line = next((ln.strip() for ln in self.err.splitlines() if ln.strip()), "")
        return f"exit code {self.status}: {line[:MAX_LINE]}" if line else f"exit code {self.status}"


def alert_environment(record: MessageRecord, base: dict[str, str] | None = None) -> dict[str, str]:
    """Return the command environment for a message; NUL bytes are dropped from the text."""
    return _environment("message", f"APRS message from {record.from_call}", record.from_call, record.text, record.at, record.msg_id or "", base)


def station_environment(fired: Fired, base: dict[str, str] | None = None) -> dict[str, str]:
    """Return the command environment for a station alert: kind `station`, no message id."""
    return _environment("station", f"APRS alert: {fired.call}", fired.call, fired.text, fired.at, "", base)


def _environment(kind: str, title: str, sender: str, text: str, at: datetime, msg_id: str, base: dict[str, str] | None) -> dict[str, str]:
    env = child_environment() if base is None else base
    env.update({"NEOAPRS_KIND": kind, "NEOAPRS_TITLE": title, "NEOAPRS_FROM": sender, "NEOAPRS_TEXT": text.replace("\0", ""), "NEOAPRS_AT": iso(at) or "", "NEOAPRS_MSG_ID": msg_id})
    return env


class Alerts:
    def __init__(self, config: ConfigSource, clock: Clock = utcnow, timeout_sec: float = TIMEOUT_SEC) -> None:
        self._config = config
        self.clock = clock
        self.timeout_sec = timeout_sec
        self._told_at: datetime | None = None
        self._tasks = TaskSet(log, "alert")

    def alert(self, record: MessageRecord) -> None:
        """Run the command for a message to us heard first time; queries are not announced."""
        if not is_query(record.text):
            self._start(lambda: alert_environment(record), f"the message from {record.from_call}")

    def station(self, fired: Fired) -> None:
        """Run the command for a station alert, under the same switch and limits as a message."""
        self._start(lambda: station_environment(fired), f"the alert of {fired.call}")

    def _start(self, environment: Callable[[], dict[str, str]], what: str) -> None:
        if not self._config().messages_alert or not (command := self._command()):
            return
        if len(self._tasks) >= MAX_RUNNING:
            log.debug("the alert for %s is dropped: %d alerts are running", what, MAX_RUNNING)
            return
        self._tasks.spawn(self._run(command, environment(), what), "alert")

    def _command(self) -> str:
        """The configured command; empty for the default one under the no-devices switch."""
        command = self._config().messages_alert_command.strip()
        return "" if command == DEFAULT_ALERT_COMMAND and nodevices.refused("the default alert command is not run (no notification on the desktop, no sound)", logging.INFO) else command

    async def stop(self) -> None:
        """Kill running commands and what they started."""
        await self._tasks.cancel_all()

    async def _run(self, command: str, env: dict[str, str], what: str) -> None:
        outcome = await self._execute(command, env)
        log.debug("the alert for %s ended with status %s: %s", what, outcome.status, outcome.output)
        if not outcome.ok:
            self._fail(outcome.problem or f"the alert command ended with status {outcome.status}: {outcome.output}")

    async def test(self) -> "Outcome":
        """Run the saved command for a made-up message; CodedError `alert.no_command` if none."""
        command = self._command()
        if not command:
            raise CodedError("no alert command", "alert.no_command")
        record = MessageRecord(0, self.clock(), "in", TEST_FROM, "", TEST_TEXT, None, "received")
        outcome = await self._execute(command, alert_environment(record))
        if not outcome.ok:
            log.info("the test of the alert command: %s", outcome.short)
        return outcome

    async def _execute(self, command: str, env: dict[str, str]) -> "Outcome":
        if sys.platform == "win32":
            return await self._execute_in_thread(command, env)
        else:
            return await self._execute_in_shell(command, env)

    async def _execute_in_shell(self, command: str, env: dict[str, str]) -> "Outcome":
        """Run under `set -e` so a failing step is not hidden by the steps after it."""
        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_shell("set -e\n" + command, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            out, err = await asyncio.wait_for(proc.communicate(), self.timeout_sec)
        except TimeoutError:
            return Outcome(problem=f"the alert command did not end within {self.timeout_sec:g} s: killed", why="timeout")
        except Exception as e:  # nothing a command does may stop the daemon
            return Outcome(problem=f"the alert command could not run: {e}", why="no_start")
        finally:
            if proc is not None and proc.returncode is None:
                self._kill(proc)
                await proc.wait()
        return Outcome(status=proc.returncode or 0, out=out.decode("utf-8", errors="replace"), err=err.decode("utf-8", errors="replace"))

    async def _execute_in_thread(self, command: str, env: dict[str, str]) -> "Outcome":
        """Windows: start PowerShell from a thread; cancellation kills it and its children."""
        running = _Running()
        try:
            return await asyncio.to_thread(self._run_powershell, command, env, running)
        finally:
            running.kill()

    def _run_powershell(self, command: str, env: dict[str, str], running: "_Running") -> "Outcome":
        # one line, since PowerShell runs what it reads line by line
        script = (POWERSHELL_PRELUDE + command.replace("\r", " ").replace("\n", " ") + POWERSHELL_POSTLUDE + "\n").encode("utf-8")
        try:
            creation = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            proc = subprocess.Popen([windows_program("WindowsPowerShell", "v1.0", "powershell.exe"), *POWERSHELL_ARGS], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creation)
        except Exception as e:
            return Outcome(problem=f"the alert command could not run: {e}", why="no_start")
        running.set(proc)
        try:
            out, err = proc.communicate(script, timeout=self.timeout_sec)
        except subprocess.TimeoutExpired:
            running.kill()
            proc.communicate()
            return Outcome(problem=f"the alert command did not end within {self.timeout_sec:g} s: killed", why="timeout")
        except Exception as e:
            running.kill()
            return Outcome(problem=f"the alert command could not run: {e}", why="no_start")
        return Outcome(status=proc.returncode or 0, out=out.decode("utf-8", errors="replace"), err=err.decode("utf-8", errors="replace"))

    @staticmethod
    def _kill(proc: asyncio.subprocess.Process) -> None:
        if sys.platform == "win32":
            proc.kill()
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)  # the shell leads its own session
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
    """The process a thread started, so the loop can kill it and its children."""

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
            # /T kills the whole tree
            subprocess.run([windows_program("taskkill.exe"), "/T", "/F", "/PID", str(proc.pid)], stdin=subprocess.DEVNULL, capture_output=True, timeout=10, check=False)
        except Exception:  # noqa: S110  (nothing a command does may stop the daemon; proc.kill below still runs)
            pass
        try:
            proc.kill()
        except OSError:
            pass
