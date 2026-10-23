"""The message alert (neoaprs/services/alerts.py): the command runs through the shell for the first copy of a message to us, with the sender, the text, the time and the id in its environment, and not for a
bulletin, an ack, a reject, a query, a second copy or a message overheard; a command that fails is told once an hour and harms nothing. The command is a shell line that writes its environment to a file of the test."""
import asyncio
import logging
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs.alertcommand import DEFAULT_ALERT_COMMAND, LINUX_ALERT_COMMAND, WINDOWS_ALERT_COMMAND
from neoaprs.config import MAX_ALERT_COMMAND, Config
from neoaprs.message import MessageRecord
from neoaprs.services.alerts import Alerts, alert_environment
from tests.support.alertcmd import MISSING_STATUS, SHORT_TIMEOUT_SEC, SURVIVOR_AFTER_SEC, TIMEOUT_SEC, WINDOWS, failing, missing_notifier, not_a_program, starting_a_survivor, then_succeeds, writing
from tests.support.air import message_info, on_air, said
from tests.support.clock import FixedClock
from tests.support.env import Env, idle_for, ON_AIR, remember_stop, until


def record(text: str = "Moi, tulossa kahville?", msg_id: str | None = "12") -> MessageRecord:
    return MessageRecord(0, FixedClock()(), "in", "OH2RDG-7", "OH2GBA", text, msg_id, "received")


class Rig:
    def __init__(self, tmp_path: Path, command: str | None = None, timeout_sec: float = TIMEOUT_SEC, **changes: object) -> None:
        self.out = tmp_path / "alert.txt"
        self.config: Config = replace(ON_AIR, **{"messages_alert_command": command if command is not None else writing(self.out), **changes})       # type: ignore[arg-type]
        self.clock = FixedClock()
        self.alerts = Alerts(lambda: self.config, self.clock, timeout_sec)
        self.logged: list[str] = []                                  # what the alerts logged while they ran: the reason when the command left no file
        remember_stop(self.alerts.stop)

    async def finished(self) -> None:
        collect = _Collect(self.logged)
        logging.getLogger("neoaprs.alerts").addHandler(collect)
        try:
            await asyncio.gather(*self.alerts._tasks, return_exceptions=True)
        finally:
            logging.getLogger("neoaprs.alerts").removeHandler(collect)

    def written(self) -> list[str]:
        assert self.out.is_file(), f"the alert command wrote no file; the alerts logged: {self.logged or 'nothing'}"
        return self.out.read_text(encoding="utf-8").splitlines()


class _Collect(logging.Handler):
    def __init__(self, lines: list[str]) -> None:
        super().__init__(logging.DEBUG)
        self.lines = lines

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(f"{record.levelname} {record.getMessage()}")


async def test_the_command_runs_with_the_sender_the_text_the_time_and_the_id_in_its_environment(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.alerts.alert(record())
    await rig.finished()
    assert rig.written() == ["OH2RDG-7", "Moi, tulossa kahville?", "2026-10-21T12:00:00Z", "12", "end"]


async def test_a_message_without_an_id_has_an_empty_id_and_odd_text_stays_text(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.alerts.alert(record('$(touch pwned); `id` "quoted" \'x\' ; rm -rf ~ åäö', None))
    await rig.finished()
    assert rig.written() == ["OH2RDG-7", '$(touch pwned); `id` "quoted" \'x\' ; rm -rf ~ åäö', "2026-10-21T12:00:00Z", "", "end"]
    assert not (tmp_path / "pwned").exists() and not Path("pwned").exists(), "the text is data in the environment, never shell"


def test_the_environment_is_the_few_names_a_desktop_program_needs_and_the_four_variables_and_nothing_of_the_daemons(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_OF_THE_DAEMON", "x")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", "/run/credentials")
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/user/1000/bus")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    env = alert_environment(record("a\0b"))
    assert env["NEOAPRS_TEXT"] == "ab" and env["DBUS_SESSION_BUS_ADDRESS"] == "unix:path=/run/user/1000/bus" and env["XDG_RUNTIME_DIR"] == "/run/user/1000"
    assert "SECRET_OF_THE_DAEMON" not in env and "CREDENTIALS_DIRECTORY" not in env
    assert sorted(k for k in env if k.startswith("NEOAPRS_")) == ["NEOAPRS_AT", "NEOAPRS_FROM", "NEOAPRS_MSG_ID", "NEOAPRS_TEXT"]


async def test_alert_off_or_an_empty_command_runs_nothing(tmp_path: Path) -> None:
    for changes in ({"messages_alert": False}, {"messages_alert_command": "   "}):
        rig = Rig(tmp_path, **changes)
        rig.alerts.alert(record())
        await rig.finished()
        assert not rig.out.exists()


async def test_the_setting_is_read_at_each_message(tmp_path: Path) -> None:
    rig = Rig(tmp_path, messages_alert=False)
    rig.alerts.alert(record())
    rig.config = replace(rig.config, messages_alert=True)
    rig.alerts.alert(record("second"))
    await rig.finished()
    assert rig.written()[1] == "second"


async def test_a_query_is_answered_and_not_announced(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    for text in ("?APRSP", " ?aprss ", "?APRS?", "?PING?"):
        rig.alerts.alert(record(text))
    await rig.finished()
    assert not rig.out.exists()


async def test_a_failing_command_is_told_once_an_hour_and_harms_nothing(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, "neoaprs.alerts")
    rig = Rig(tmp_path, command=failing(3, "no display"))
    for _ in range(3):
        rig.alerts.alert(record())
        await rig.finished()
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "status 3" in warnings[0].getMessage() and "no display" in warnings[0].getMessage()
    rig.clock.advance(3599)
    rig.alerts.alert(record())
    await rig.finished()
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1
    rig.clock.advance(1)
    rig.alerts.alert(record())
    await rig.finished()
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 2
    assert any("no display" in r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG), "the output is in the log at DEBUG"
    rig.config = replace(rig.config, messages_alert_command=writing(rig.out))        # the next message works again
    rig.alerts.alert(record("fine"))
    await rig.finished()
    assert rig.written()[1] == "fine"


async def test_a_command_that_cannot_start_is_a_failure_not_a_crash(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, "neoaprs.alerts")
    rig = Rig(tmp_path, command=not_a_program())
    rig.alerts.alert(record())
    await rig.finished()
    assert any(f"status {MISSING_STATUS}" in r.getMessage() for r in caplog.records)


async def test_a_command_that_runs_out_of_time_is_killed_with_what_it_started(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, "neoaprs.alerts")
    marker = tmp_path / "survivor"
    rig = Rig(tmp_path, command=starting_a_survivor(marker, SURVIVOR_AFTER_SEC), timeout_sec=SHORT_TIMEOUT_SEC)
    rig.alerts.alert(record())
    await rig.finished()
    assert any(f"did not end within {SHORT_TIMEOUT_SEC:g} s" in r.getMessage() for r in caplog.records)
    await asyncio.sleep(SURVIVOR_AFTER_SEC + 1.0)                          # (the time the survivor would have taken to write its marker is the point)
    assert not marker.exists(), "the sleep the shell started was killed with it"


async def test_only_a_few_alerts_run_at_once(tmp_path: Path) -> None:
    rig = Rig(tmp_path, command="sleep 0.3")
    for _ in range(12):
        rig.alerts.alert(record())
    assert len(rig.alerts._tasks) == 5
    await rig.alerts.stop()


def test_the_default_command_of_each_system_notifies_with_the_variables_and_is_data_never_interpolated() -> None:
    assert DEFAULT_ALERT_COMMAND == (WINDOWS_ALERT_COMMAND if WINDOWS else LINUX_ALERT_COMMAND)
    assert "$NEOAPRS_FROM" in LINUX_ALERT_COMMAND and "$NEOAPRS_TEXT" in LINUX_ALERT_COMMAND and LINUX_ALERT_COMMAND.endswith("message-new-instant.oga")
    assert "$env:NEOAPRS_FROM" in WINDOWS_ALERT_COMMAND and "$env:NEOAPRS_TEXT" in WINDOWS_ALERT_COMMAND and "%" not in WINDOWS_ALERT_COMMAND
    assert "\n" not in WINDOWS_ALERT_COMMAND and len(WINDOWS_ALERT_COMMAND) <= MAX_ALERT_COMMAND



# ---- inside the daemon: which messages get here --------------------------------------------------------------------------------------------------

async def started(tmp_path: Path) -> tuple[Env, Path]:
    e = Env(tmp_path)
    out = tmp_path / "alert.txt"
    await e.start()
    await e.until_usable()
    assert await e.ctl.save_config(replace(e.ctl.config, messages_alert_command=writing(out)))
    return e, out


async def test_a_message_to_us_runs_the_alert_once_for_the_first_copy_only(tmp_path: Path) -> None:
    e, out = await started(tmp_path)
    e.feed(on_air("OH2RDG-7", message_info("OH2GBA", "Moi!", "12"), path="OH2RCH-2*"))
    await until(out.exists)
    assert out.read_text(encoding="utf-8").splitlines() == ["OH2RDG-7", "Moi!", "2026-10-21T12:00:00Z", "12", "end"]
    assert (await said(e))[0].tnc2().endswith("::OH2RDG-7 :ack12"), "and it is acked as before"
    out.unlink()
    e.now.advance(15)                                                       # type: ignore[attr-defined]  (the same message by another digipeater: acked again, kept and announced once)
    e.feed(on_air("OH2RDG-7", message_info("OH2GBA", "Moi!", "12"), path="OH2RCH-3*"))
    await until(lambda: e.tnc.stats.packets == 2)
    await idle_for(0.4)
    assert not out.exists(), "the second copy runs nothing"
    await e.stop()


async def test_what_is_not_a_message_to_us_runs_nothing(tmp_path: Path) -> None:
    e, out = await started(tmp_path)
    e.feed(on_air("OH2XYZ", message_info("BLN1", "Road closed", "5")))               # a bulletin
    e.feed(on_air("OH2XYZ", message_info("QST", "Club news")))                       # a group message
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "?APRSP")))                       # a query
    e.feed(on_air("OH2RDG", message_info("OH2ABC", "Hello Pekka", "3")))             # a message to somebody else, overheard
    await until(lambda: e.tnc.stats.packets == 4)
    await idle_for(0.4)
    assert not out.exists()
    e.feed(on_air("OH2RDG", message_info("OH2GBA-9", "not ours", "4")))              # another SSID is another station
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "Now it is for us")))
    await until(out.exists)
    assert out.read_text(encoding="utf-8").splitlines()[1] == "Now it is for us"
    await e.stop()


async def test_a_broken_command_does_not_harm_the_daemon_and_the_message_is_kept_and_acked(tmp_path: Path) -> None:
    e = Env(tmp_path)
    await e.start()
    await e.until_usable()
    assert await e.ctl.save_config(replace(e.ctl.config, messages_alert_command="exit 9"))
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "Moi!", "12")))
    await until(lambda: e.tnc.stats.packets == 1)                           # (said() blocks the loop: it comes after the packet was heard)
    [ack] = await said(e)
    assert ack.tnc2().endswith(":ack12")
    await until(lambda: [m.text for m in e.ctl.messaging.records()] == ["Moi!"])
    await e.stop()


async def test_the_clock_of_a_message_is_the_time_it_was_heard(tmp_path: Path) -> None:
    e, out = await started(tmp_path)
    e.now.advance(timedelta(hours=3, minutes=7, seconds=5).total_seconds())            # type: ignore[attr-defined]
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "Late")))
    await until(out.exists)
    assert out.read_text(encoding="utf-8").splitlines()[2] == "2026-10-21T15:07:05Z"
    await e.stop()


async def test_a_step_that_fails_fails_the_command_even_when_a_later_step_succeeds(tmp_path: Path) -> None:
    """The line runs under set -e: `notify-send ...; paplay ...` with no notify-send must not count as ran because the sound played."""
    alerts = Alerts(lambda: replace(ON_AIR, messages_alert_command=then_succeeds(missing_notifier())), clock=FixedClock(), timeout_sec=TIMEOUT_SEC)
    ok, text = await alerts.test()
    assert not ok
    assert text.startswith(f"exit code {MISSING_STATUS}")
