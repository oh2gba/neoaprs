"""Windows only: the alert command runs in the real Windows PowerShell with its non-ASCII text whole,
a user folder or a file name with accents as the operator typed it, and its output read back as it was
written (neoaprs/alertcommand.py, POWERSHELL_RUN).
"""

import sys
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs.services.alerts import Alerts
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell's own decoding")

WORD = "Käyttäjä Ünïcödé ŁÓDŹ"


async def test_a_command_with_accented_text_and_paths_runs_with_them_whole(tmp_path: Path) -> None:
    target = tmp_path / "Käyttäjä" / "ääni.txt"
    target.parent.mkdir()
    command = f"Set-Content -LiteralPath '{target}' -Value '{WORD}' -Encoding UTF8; Write-Output '{WORD}'"
    config = replace(ON_AIR, messages_alert_command=command)
    outcome = await Alerts(lambda: config, FixedClock(), timeout_sec=60.0).test()
    assert outcome.ok, outcome.short
    assert outcome.out.strip() == WORD, "the output is read as PowerShell wrote it"
    assert target.read_text(encoding="utf-8-sig").strip() == WORD, "the path and the text arrived whole"


async def test_the_exit_code_of_the_command_is_its_status(tmp_path: Path) -> None:
    config = replace(ON_AIR, messages_alert_command="cmd /c exit 4")
    outcome = await Alerts(lambda: config, FixedClock(), timeout_sec=60.0).test()
    assert outcome.status == 4
