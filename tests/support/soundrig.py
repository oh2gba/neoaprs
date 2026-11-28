"""A PipeWire of a test's own: pipewire, wireplumber without its device monitors and pipewire-pulse under a
fresh runtime folder and session bus, holding only the virtual devices the test makes with pactl.

Started only where NEOAPRS_SOUND_RIG=1 says so (the CI job `soundrig`, a container) and the computer has
no sound device: the session of a person at the computer is never reached, nor a card of it.
"""

import os
import shutil
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

ENV = "NEOAPRS_SOUND_RIG"
PROGRAMS = ("pipewire", "wireplumber", "pipewire-pulse", "pactl", "dbus-daemon", "aplay", "arecord", "pacat")
# The longest the rig's programs take to answer: a limit, not a measure
START_SEC = 30.0
NO_DEVICES = """wireplumber.profiles = {
  main = {
    monitor.alsa = disabled
    monitor.alsa-midi = disabled
    monitor.bluez = disabled
    monitor.bluez.midi = disabled
    monitor.v4l2 = disabled
    monitor.libcamera = disabled
  }
}
"""


def why_not() -> str:
    """Return why the rig cannot start here, "" when it can."""
    if os.environ.get(ENV) != "1":
        return f"{ENV}=1 is not set (the CI job soundrig, or a container)"
    if Path("/dev/snd").exists():
        return "this computer has sound devices: the rig runs where there are none"
    if missing := [p for p in PROGRAMS if shutil.which(p) is None]:
        return f"not installed: {', '.join(missing)}"
    return ""


@dataclass
class Rig:
    folder: Path
    env: dict[str, str]
    processes: list["subprocess.Popen[bytes]"] = field(default_factory=list)

    def pactl(self, *args: str) -> str:
        done = subprocess.run(["pactl", *args], env=self.env, capture_output=True, text=True, timeout=START_SEC)
        assert done.returncode == 0, f"pactl {' '.join(args)}: {done.stderr}"
        return done.stdout.strip()

    def index(self, kind: str, name: str) -> int:
        """The index of a sink or source by name (`pactl list short`)."""
        for line in self.pactl("list", "short", kind).splitlines():
            fields = line.split("\t")
            if len(fields) > 1 and fields[1] == name:
                return int(fields[0])
        raise AssertionError(f"no {kind} {name}")

    def start(self, argv: list[str]) -> "subprocess.Popen[bytes]":
        process = subprocess.Popen(
            argv, env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True
        )
        self.processes.append(process)
        return process

    def answers(self) -> bool:
        return subprocess.run(["pactl", "info"], env=self.env, capture_output=True, timeout=START_SEC).returncode == 0


def _wait(condition: "object", what: str) -> None:
    deadline = time.monotonic() + START_SEC
    while not condition():  # type: ignore[operator]
        assert time.monotonic() < deadline, f"the rig's {what} did not come up"
        time.sleep(0.05)


@pytest.fixture
def sound_rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    """The private PipeWire, its folders in the test's own; this process's environment points at it."""
    if why := why_not():
        pytest.skip(why)
    run = tmp_path / "run"
    run.mkdir(mode=0o700)
    config = tmp_path / "config"
    (config / "wireplumber" / "wireplumber.conf.d").mkdir(parents=True)
    (config / "wireplumber" / "wireplumber.conf.d" / "90-no-devices.conf").write_text(NO_DEVICES)
    bus = f"unix:path={run / 'bus'}"
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_path),
        "LANG": "C.UTF-8",
        "XDG_RUNTIME_DIR": str(run),
        "PIPEWIRE_RUNTIME_DIR": str(run),
        "XDG_CONFIG_HOME": str(config),
        "PULSE_SERVER": f"unix:{run / 'pulse' / 'native'}",
        "DBUS_SESSION_BUS_ADDRESS": bus,
    }
    rig = Rig(tmp_path, env)
    try:
        rig.start(["dbus-daemon", "--session", "--nofork", f"--address={bus}"])
        _wait(lambda: (run / "bus").exists(), "session bus")
        rig.start(["pipewire"])
        _wait(lambda: (run / "pipewire-0").exists(), "pipewire")
        rig.start(["wireplumber"])
        rig.start(["pipewire-pulse"])
        _wait(rig.answers, "pipewire-pulse")
        for name, value in env.items():
            if name not in ("PATH", "HOME", "LANG"):
                monkeypatch.setenv(name, value)
        yield rig
    finally:
        for process in reversed(rig.processes):
            process.terminate()
        for process in rig.processes:
            try:
                process.wait(START_SEC)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
