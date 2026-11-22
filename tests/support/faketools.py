"""Stand-ins for `systemctl`, `loginctl` and `launchctl`: small scripts first on the PATH that
record what they were asked and answer the few questions put to them.
"""

import os
import stat
from pathlib import Path

import pytest

SCRIPT = r"""#!/bin/sh
line="$(basename "$0") $*"
echo "$line" >> "$FAKE_CALLS"
case "$line" in
    "$FAKE_FAIL"*) [ -n "$FAKE_FAIL" ] && exit 1 ;;
esac
case "$line" in
    *"is-active"*) echo active ;;
    *"is-enabled"*) echo enabled ;;
    *"show-user"*) [ "$FAKE_LINGER" = yes ] && echo Linger=yes || echo Linger=no ;;
esac
exit 0
"""


class FakeTools:
    def __init__(
        self, folder: Path, calls_file: Path, names: tuple[str, ...] = ("systemctl", "loginctl", "launchctl")
    ) -> None:
        if os.name == "nt":
            pytest.skip("the stand-ins are shell scripts: POSIX only")
        folder.mkdir(parents=True, exist_ok=True)
        self.folder, self.calls_file = folder, calls_file
        self.failing = ""
        self.linger = False
        calls_file.touch()
        for name in names:
            script = folder / name
            script.write_text(SCRIPT)
            script.chmod(script.stat().st_mode | stat.S_IEXEC)

    def use(self, monkeypatch: pytest.MonkeyPatch) -> "FakeTools":
        """Puts the tools first on the PATH of this test. Call `fail` and `linger` before: the
        environment is set when it is called."""
        monkeypatch.setenv("PATH", f"{self.folder}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.setenv("FAKE_CALLS", str(self.calls_file))
        monkeypatch.setenv("FAKE_FAIL", self.failing)
        monkeypatch.setenv("FAKE_LINGER", "yes" if self.linger else "no")
        return self

    def calls(self, only: str = "") -> list[str]:
        """What was asked since the last time this was called (only the calls that start with
        `only`, if given)."""
        lines = self.calls_file.read_text(encoding="utf-8").splitlines()
        self.calls_file.write_text("")
        return [line for line in lines if line.startswith(only)]
