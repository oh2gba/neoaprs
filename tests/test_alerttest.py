"""The test button of the message alert (`alert_test`, answered with `alert_result`): over the socket, against the daemon. The command is the saved one, run as for a real message with a made-up one,
whatever `messages/alert` says; a fake command writes its environment to a file of the test."""
import json
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs.clock import iso
from tests.support.alertcmd import MISSING_STATUS, SHORT_TIMEOUT_SEC, TIMEOUT_SEC, failing, not_a_program, sleeping, writing
from tests.support.env import Env
from tests.support.wsclient import WsClient
from neoaprs.web.protocol import TOPIC_NAMES


async def started(tmp_path: Path, command: str, **changes: object) -> tuple[Env, WsClient]:
    e = Env(tmp_path, web=True)
    await e.start()
    e.ctl.alerts.timeout_sec = TIMEOUT_SEC
    assert await e.ctl.save_config(replace(e.ctl.config, messages_alert_command=command, **changes))       # type: ignore[arg-type]
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    return e, page


async def test_the_command_runs_with_the_made_up_message_in_its_environment_and_the_answer_is_ran(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_OF_THE_DAEMON", "x")
    out = tmp_path / "alert.txt"
    e, page = await started(tmp_path, writing(out, secret=True))
    other = await e.ws()
    await page.send({"cmd": "alert_test"})
    assert await page.expect("alert_result") == {"type": "alert_result", "ok": True, "text": "ran"}
    assert out.read_text(encoding="utf-8").splitlines() == ["NEOAPRS", "This is a test of the NeoAPRS alert", iso(e.now()), "", "gone"], "the same environment as a real alert, with no id and nothing of the daemon's"
    await other.quiet(0.2)
    assert other.of("alert_result") == [] and page.of("error") == []
    assert page.topics["messages"] == {} and page.topics["packets"] == {}, "a test is no message and sends nothing"
    await e.stop()


async def test_the_alert_being_off_is_ignored_and_the_command_is_the_saved_one(tmp_path: Path) -> None:
    out = tmp_path / "alert.txt"
    e, page = await started(tmp_path, writing(out), messages_alert=False)
    await page.send({"cmd": "alert_test"})
    assert (await page.expect("alert_result"))["ok"] is True and out.exists()
    out.unlink()
    assert await e.ctl.save_config(replace(e.ctl.config, messages_alert_command="exit 0"))
    await page.send({"cmd": "alert_test"})
    assert (await page.expect("alert_result"))["ok"] is True and not out.exists(), "the command as it is now saved"
    await e.stop()


async def test_a_failing_command_is_ok_false_with_the_exit_code_and_the_first_line_of_stderr(tmp_path: Path) -> None:
    e, page = await started(tmp_path, failing(3, "no display", "second line"))
    await page.send({"cmd": "alert_test"})
    assert await page.expect("alert_result") == {"type": "alert_result", "ok": False, "text": "exit code 3: no display"}
    assert page.of("error") == []
    await e.ctl.save_config(replace(e.ctl.config, messages_alert_command="exit 9"))
    await page.send({"cmd": "alert_test"})
    assert (await page.expect("alert_result"))["text"] == "exit code 9"
    await e.ctl.save_config(replace(e.ctl.config, messages_alert_command=not_a_program()))
    await page.send({"cmd": "alert_test"})
    result = await page.expect("alert_result")
    assert result["ok"] is False and result["text"].startswith(f"exit code {MISSING_STATUS}: ")
    await e.stop()


async def test_a_command_that_runs_out_of_time_is_killed_and_the_answer_says_so(tmp_path: Path) -> None:
    e, page = await started(tmp_path, sleeping())
    e.ctl.alerts.timeout_sec = SHORT_TIMEOUT_SEC
    await page.send({"cmd": "alert_test"})
    assert await page.expect("alert_result") == {"type": "alert_result", "ok": False, "text": f"the alert command did not end within {SHORT_TIMEOUT_SEC:g} s: killed"}
    await e.stop()


@pytest.mark.parametrize("command", ["", "   "])
async def test_an_empty_command_is_an_error_and_not_a_result(tmp_path: Path, command: str) -> None:
    e, page = await started(tmp_path, command)
    await page.send({"cmd": "alert_test"})
    assert (await page.expect("error"))["text"] == "alert_test: no alert command"
    await page.quiet(0.2)
    assert page.of("alert_result") == []
    await e.stop()


async def test_the_command_takes_no_fields(tmp_path: Path) -> None:
    e, page = await started(tmp_path, "exit 0")
    await page.send({"cmd": "alert_test", "command": "rm -rf ~"})
    assert "command" in json.dumps((await page.expect("error"))["text"])
    assert page.of("alert_result") == []
    await e.stop()
