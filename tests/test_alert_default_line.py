"""The default alert line of Linux and macOS (neoaprs/alertcommand.py) run by a real shell with notifiers that are scripts of the test: the title and the text reach `notify-send` (and `kdialog` when there is no
notify-send) with & < > as entities, so that a message from the air is shown as typed and cannot be markup of the notification; the variables themselves are not changed (a line of the operator's own gets them as
they came)."""
import subprocess
import sys
from pathlib import Path

import pytest

from neoaprs.alertcommand import LINUX_ALERT_COMMAND

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="a shell line of Linux and macOS")

LINK = '<a href="http://example.org/x?a=1&b=2">OH2RDG-7 asks: click</a> <b>R&D</b> a<b'
LINK_ESCAPED = '&lt;a href="http://example.org/x?a=1&amp;b=2"&gt;OH2RDG-7 asks: click&lt;/a&gt; &lt;b&gt;R&amp;D&lt;/b&gt; a&lt;b'


def notifier(folder: Path, name: str, status: int = 0) -> Path:
    """A program of that name that writes the arguments it got, one to a line, to `<name>.args` and ends with `status`."""
    program = folder / name
    program.write_text(f'#!/bin/sh\nfor a in "$@"; do printf \'%s\\n\' "$a"; done > "{folder}/{name}.args"\nexit {status}\n')
    program.chmod(0o755)
    return program


def run(folder: Path, title: str, text: str) -> subprocess.CompletedProcess[str]:
    env = {"PATH": f"{folder}:/usr/bin:/bin", "NEOAPRS_TITLE": title, "NEOAPRS_TEXT": text, "NEOAPRS_FROM": "OH2RDG-7"}
    return subprocess.run(["/bin/sh", "-c", "set -e\n" + LINUX_ALERT_COMMAND], env=env, capture_output=True, text=True, timeout=20, check=False, cwd=folder)


def test_the_notifier_gets_the_title_and_the_text_with_the_three_characters_escaped(tmp_path: Path) -> None:
    for name in ("notify-send", "kdialog", "paplay"):
        notifier(tmp_path, name)
    done = run(tmp_path, "APRS message from <i>OH2RDG-7</i>", LINK)
    assert done.returncode == 0, done.stderr
    assert (tmp_path / "notify-send.args").read_text().splitlines() == ["--", "APRS message from &lt;i&gt;OH2RDG-7&lt;/i&gt;", LINK_ESCAPED]
    assert not (tmp_path / "kdialog.args").exists() and (tmp_path / "paplay.args").exists()


def test_kdialog_that_takes_over_without_notify_send_gets_the_same_escaped_text(tmp_path: Path) -> None:
    notifier(tmp_path, "notify-send", status=1)
    notifier(tmp_path, "kdialog")
    notifier(tmp_path, "paplay")
    assert run(tmp_path, "APRS alert: A&B", LINK).returncode == 0
    assert (tmp_path / "kdialog.args").read_text().splitlines() == ["--title", "APRS alert: A&amp;B", "--passivepopup", LINK_ESCAPED, "10"]


@pytest.mark.parametrize("text", ["Moi, tulossa kahville?", "plain 73 de OH2RDG", "a  b", "50% $HOME `id` \\n \"quoted\" 'single'"])
def test_a_text_without_the_three_characters_and_with_shell_syntax_arrives_as_typed(tmp_path: Path, text: str) -> None:
    for name in ("notify-send", "kdialog", "paplay"):
        notifier(tmp_path, name)
    assert run(tmp_path, "APRS message from OH2RDG-7", text).returncode == 0
    assert (tmp_path / "notify-send.args").read_text().splitlines()[1:] == ["APRS message from OH2RDG-7", text]


def test_an_ampersand_that_is_already_an_entity_is_escaped_too_it_was_typed(tmp_path: Path) -> None:
    for name in ("notify-send", "kdialog", "paplay"):
        notifier(tmp_path, name)
    run(tmp_path, "t", "&lt;")
    assert (tmp_path / "notify-send.args").read_text().splitlines()[2] == "&amp;lt;"


def test_the_line_changes_the_text_for_the_notifier_only_the_variables_stay_as_they_are() -> None:
    assert "$NEOAPRS_TITLE" in LINUX_ALERT_COMMAND and "$NEOAPRS_TEXT" in LINUX_ALERT_COMMAND and '"$NEOAPRS_TEXT"' not in LINUX_ALERT_COMMAND.split("notify-send")[1]
