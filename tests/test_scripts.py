"""`neoaprs replay` and `neoaprs db` as processes and the scripts that wrap them: the live capture
replayed as a TNC on a TCP port fills a radio-less daemon's database; the same on a pseudo-terminal
(`--pty`, POSIX only).
"""

import os
import re
import select
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from neoaprs.kiss import KissDecoder
from neoaprs.radiotypes import BY_KEY as TYPES
from tests.conftest import ROOT
from tests.support.files import FIXTURES, text_if_readable
from tests.support.proc import NEW_GROUP, STOP_PATIENCE_SEC, stop
from tests.support.hfchannel import NONBLOCK
from tests.support.ptyline import NOCTTY, posix_only

CAPTURE = FIXTURES / "kiss" / "thd7-2026-10-21.bin"


def env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in ("NEOAPRS_DATA_DIR", "NEOAPRS_DEBUG")}


def tool(data: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "neoaprs", "db", "--data", str(data), *args],
        cwd=ROOT,
        env=env(),
        capture_output=True,
        text=True,
        timeout=60,
    )


def script(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    """A wrapper of scripts/ as it is run in a clone, with the test's python for NEOAPRS_PYTHON."""
    return subprocess.run(
        [str(ROOT / "scripts" / name), *args],
        cwd=ROOT,
        env={**env(), "NEOAPRS_PYTHON": sys.executable},
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_the_screenshots_show_no_version_and_make_the_update_shots_next_number_from_the_tree() -> None:
    """A release by itself makes no shot old: the version beside Check now is hidden in every page
    the script opens (before the first shot is taken), and the newer version its update shot
    announces is one past VERSION, not a number kept by hand."""
    import importlib.util

    from neoaprs import VERSION

    path = ROOT / "scripts" / "screenshots.py"
    spec = importlib.util.spec_from_file_location("screenshots", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (
        module.next_version("0.8.0") == "0.8.1"
        and module.next_version("1.0.0-rc1") == "1.0.1"
        and module.next_version("2.10.99") == "2.10.100"
    )
    assert module.UPDATE_TO == module.next_version(VERSION) and module.UPDATE_TO != VERSION
    assert ".updateversion" in module.HIDE_VERSION and "visibility: hidden" in module.HIDE_VERSION, (
        "hidden, not removed: the row keeps its place"
    )
    source = path.read_text(encoding="utf-8")
    opened = source.split("async def page(", 1)[1].split("async def save(", 1)[0]
    assert (
        opened.index("page.goto(")
        < opened.index("add_style_tag(content=HIDE_VERSION)")
        < opened.index("wait_for_timeout(wait_ms)")
    ), "the sheet goes in as soon as the page is open, before any shot"
    assert not re.search(r'UPDATE_TO = "\d', source), "no version number kept by hand"


# Real processes on a loaded runner: the Windows one took 14 min for the suite and needed more than
# 30 s here; it returns as soon as the condition holds
def wait_until(condition: object, seconds: float = 90.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():  # type: ignore[operator]
            return
        time.sleep(0.05)
    raise AssertionError("the condition did not come true")


def test_a_replayed_capture_fills_the_database_of_a_daemon_without_a_radio_over_tcp(tmp_path: Path) -> None:
    data = tmp_path / "data"
    # A station that is set up: with no call and position there is no station of ours in the book
    for key, value in (("station/call", "OH2GBA"), ("station/lat", "60.17"), ("station/lon", "24.94")):
        assert tool(data, "set", key, value).returncode == 0
    # The station's radio, which --port names for this run
    assert tool(data, "radios", "add", "kiss").returncode == 0
    replay = subprocess.Popen(
        [sys.executable, "-m", "neoaprs", "replay", str(CAPTURE), "--interval", "0.2"],
        cwd=ROOT,
        env=env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    daemon = None
    try:
        assert replay.stdout is not None
        path = replay.stdout.readline().strip()
        assert path.startswith("socket://127.0.0.1:")
        daemon = subprocess.Popen(
            [sys.executable, "-m", "neoaprs", "--data", str(data), "--port", path, "--web-port", "0"],
            cwd=ROOT,
            env=env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=NEW_GROUP,
        )
        log = data / "neoaprs.log"
        wait_until(lambda: (text_if_readable(log) or "").count(" -> position ") >= 4)
        # While the daemon runs (the appends are committed within a second)
        stations = tool(data, "stations")
        wait_until(lambda: "OH2PU-9" in tool(data, "stations").stdout)
        stations = tool(data, "stations")
        assert stations.returncode == 0, stations.stderr
        for call in ("OH2RDG", "OH2RDK-7", "OH2RDS", "OH2PU-9", "OH2GBA"):
            assert call in stations.stdout
        assert "60.1650 24.9467" in stations.stdout
        packets = tool(data, "packets", "-n", "2")
        lines = packets.stdout.splitlines()
        assert (
            packets.returncode == 0
            and len(lines) == 2
            and lines[1].endswith(
                "OH2PU-9>APOTC1,OH2RCH-2*:!/0&m]TbwX>z!GQRV D-STAR 144.650MHz -> position 60.1991 24.6501 />"
                + " QRV D-STAR 144.650MHz"
            )
        )
        assert lines[0] < lines[1] or lines[0][:20] <= lines[1][:20], "the oldest first"
        stop(daemon)
        out, err = daemon.communicate(timeout=STOP_PATIENCE_SEC)
        assert daemon.returncode == 0, (out, err)
    finally:
        for proc in (daemon, replay):
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.communicate()


@posix_only
def test_the_replay_on_a_pseudo_terminal_ends_on_ctrl_c_and_says_what_it_does(tmp_path: Path) -> None:
    replay = subprocess.Popen(
        [sys.executable, "-m", "neoaprs", "replay", "--pty", str(CAPTURE), "--interval", "0.05", "--loop"],
        cwd=ROOT,
        env=env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert replay.stdout is not None
    path = replay.stdout.readline().strip()
    assert path.startswith("/dev/pts/")
    # Nothing may be sent before a port opens it: the time is the point
    time.sleep(0.3)
    port = os.open(path, os.O_RDWR | NOCTTY | NONBLOCK)  # a port opens it: until then nothing is sent
    heard = bytearray()
    try:
        deadline = time.monotonic() + 15
        # More than the 4 frames of the file: it loops (and three past the ninth, whose line is in
        # the log by the time the tenth is written)
        while len(KissDecoder().feed(bytes(heard))) < 12 and time.monotonic() < deadline:
            if select.select([port], [], [], 0.1)[0]:
                heard += os.read(port, 4096)
    finally:
        os.close(port)
    frames = KissDecoder().feed(bytes(heard))
    assert len(frames) >= 12 and [f.payload for f in frames[:4]] == [
        f.payload for f in KissDecoder().feed(CAPTURE.read_bytes())
    ]
    replay.send_signal(signal.SIGINT)
    out, err = replay.communicate(timeout=STOP_PATIENCE_SEC)
    assert (
        replay.returncode == 0
        and "waiting for a port to open" in err
        and "a port opened it" in err
        and "frame 9 sent" in err
        and "stopped" in err
    )


def test_the_replay_refuses_a_file_that_is_not_there_or_holds_no_frame(tmp_path: Path) -> None:
    (tmp_path / "empty.bin").write_bytes(b"no frames here")
    for name, message in (("nothing.bin", "No such file"), ("empty.bin", "holds no KISS frame")):
        done = subprocess.run(
            [sys.executable, "-m", "neoaprs", "replay", str(tmp_path / name)],
            cwd=ROOT,
            env=env(),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert done.returncode == 1 and message in done.stderr and done.stdout == ""


def test_the_tool_sets_checks_and_reads_the_settings(tmp_path: Path) -> None:
    data = tmp_path / "data"
    assert tool(data, "list").returncode == 1, "reading makes no database"
    assert not data.exists()
    done = tool(data, "set", "station/call", "oh2gba-9")
    assert done.returncode == 0 and done.stdout.strip() == "station/call = OH2GBA-9"
    assert tool(data, "get", "station/call").stdout.strip() == "OH2GBA-9"
    assert tool(data, "get", "web/port").stdout.strip() == "7303"
    listing = tool(data, "list").stdout
    assert any(line.startswith("station/call") and line.endswith("stored") for line in listing.splitlines()) and any(
        line.startswith("web/port") and line.endswith("default") for line in listing.splitlines()
    )
    bad = tool(data, "set", "web/port", "99999")
    assert bad.returncode == 2 and "web/port" in bad.stderr
    unknown = tool(data, "get", "neoaprs/web/colour")
    assert unknown.returncode == 2 and "no such setting" in unknown.stderr
    assert tool(data, "get", "station/call").stdout.strip() == "OH2GBA-9"
    assert tool(data, "stations").returncode == 0 and tool(data, "packets").stdout == ""


@posix_only  # (shell scripts)
def test_the_wrappers_of_the_scripts_call_the_command_with_the_data_folder_of_their_clone(tmp_path: Path) -> None:
    """The wrappers are run from a copy of scripts/ in a made-up clone, so that the data folder they
    name is the copy's and never the real clone's."""
    clone = tmp_path / "clone"
    (clone / "scripts").mkdir(parents=True)
    for name in ("neoaprs-db", "replay", "capture"):
        shutil.copy2(ROOT / "scripts" / name, clone / "scripts" / name)
    environment = {**env(), "NEOAPRS_PYTHON": sys.executable, "PYTHONPATH": str(ROOT)}

    def run(name: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(clone / "scripts" / name), *args],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
        )

    helped = run("neoaprs-db", "--help")
    assert helped.returncode == 0 and "neoaprs db" in helped.stdout and "stations" in helped.stdout
    replay = run("replay", "--help")
    assert replay.returncode == 0 and "neoaprs replay" in replay.stdout and "--loop" in replay.stdout
    capture = run("capture", "--help")
    assert capture.returncode == 0 and "neoaprs capture" in capture.stdout and "--seconds" in capture.stdout
    listing = run("neoaprs-db", "list")
    assert listing.returncode == 1 and str(clone / "data") in listing.stderr, (
        "the data folder of the clone the script is in"
    )
    mine = run("neoaprs-db", "--data", str(tmp_path / "mine"), "get", "web/port")
    assert mine.returncode == 1 and str(tmp_path / "mine") in mine.stderr, "a --data of your own wins over the clone's"
    assert (
        run("neoaprs-db", "set", "station/call", "oh2gba").stdout.strip() == "station/call = OH2GBA"
        and run("neoaprs-db", "get", "station/call").stdout.strip() == "OH2GBA"
    )
    assert (clone / "data" / "neoaprs.sqlite").is_file()


# ---- the scripts that talk to a daemon's page, on the wire before the radios and that of the
# radios, and what the screenshots leave


def load_script(name: str) -> ModuleType:
    """A script of scripts/ as a module, with scripts/ on the path as when it is run (screenshots.py
    imports demoscene and smoke from there); one without `.py` (build-mercury) too."""
    import importlib.machinery
    import importlib.util

    folder = str(ROOT / "scripts")
    if folder not in sys.path:
        sys.path.insert(0, folder)
    module_name = name.removesuffix(".py").replace("-", "_")
    spec = importlib.util.spec_from_file_location(
        module_name,
        ROOT / "scripts" / name,
        loader=importlib.machinery.SourceFileLoader(module_name, str(ROOT / "scripts" / name)),
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HELLO = {"type": "hello", "topics": ["stations", "packets", "radios", "config"]}


def radio_row(
    id: int, kind: str, type: str, position: int, enabled: bool = True, removed: bool = False, state: str = "connected"
) -> dict[str, object]:
    """A row of the topic `radios` with the fields the scripts read."""
    return {
        "id": id,
        "kind": kind,
        "type": type,
        "name": "",
        "number": 1,
        "enabled": enabled,
        "position": position,
        "removed": removed,
        "dummy": type.startswith("dummy"),
        "state": state,
        "problem": None,
        "modem": None,
    }


def test_the_scripts_read_the_radios_in_the_topic_radios_and_refuse_a_daemon_whose_hello_names_it_not() -> None:
    smoke = load_script("smoke.py")
    assert smoke.wire_of(HELLO) == "radios"
    for topics in (["stations"], ["stations", "packets", "tnc", "hf", "config"]):
        with pytest.raises(smoke.Failure, match="tells of no radio"):
            smoke.wire_of({"type": "hello", "topics": topics})
    assert smoke.radio_state({"tnc": {"state": "connected"}}, "fm") is None and smoke.radio_state({}, "fm") is None, (
        "a topic of a radio's kind is no radio"
    )
    new = {
        "radios": {
            "1": radio_row(1, "fm", "kiss", 2, state="waiting"),
            "3": radio_row(3, "fm", "kiss-tcp", 1),
            "2": radio_row(2, "hf", "mercury", 3, enabled=False),
            "4": radio_row(4, "hf", "dummy-hf", 4, state="silent"),
            "5": radio_row(5, "hf", "dummy-hf", 0, removed=True),
        }
    }
    assert smoke.radio_of(new, "fm")["id"] == 3, "the first enabled radio of the kind by position, not radio 1"
    assert smoke.radio_state(new, "hf") == "silent", "a radio that is off and a removed one are passed by"
    assert [r["id"] for r in smoke.live_radios(new, "hf")] == [2, 4] and smoke.radio_state(
        {"radios": {}}, "lora"
    ) is None
    row = {
        "call": "OH2X",
        "heard": {
            "1": {"count": 3, "last_at": None},
            "3": {"count": 2, "last_at": None},
            "4": {"count": 5, "last_at": None},
        },
    }
    assert (smoke.heard_on(new, row, "fm"), smoke.heard_on(new, row, "hf")) == (5, 5), (
        "heard by radio id, counted for the radios of the kind"
    )
    for without in ({"call": "OH2X"}, {"call": "OH2X", "heard_" + "hf": 1}):
        with pytest.raises(smoke.Failure, match="has no heard"):
            smoke.heard_on(new, without, "hf")
    assert (
        smoke.heard_on({"stations": {}}, {"call": "OH2X", "heard": {"2": {"count": 4, "last_at": None}}}, "hf") == 0
    ), "a row read before the topic radios has come: nothing counted yet"
    assert smoke.heard_on(new, {"call": "OH2X", "heard": {"9": {"count": 4, "last_at": None}}}, "hf") == 0, (
        "a radio the topic radios does not yet tell"
    )
    assert (
        smoke.modem_state(new, "hf") is None
        and smoke.modem_state({"hf": {"modem": {"state": "running"}}}, "hf") is None
    )
    assert (
        smoke.modem_state(
            {"radios": {"2": {**radio_row(2, "hf", "mercury", 1, enabled=False), "modem": {"state": "starting"}}}},
            "hf",
            2,
        )
        == "starting"
    ), "by its id, enabled or not"


class FakeDaemonPage:
    """What `smoke.give_radio` and `PageSocket.set_config` see of a daemon, answering their commands
    at once as the daemon does: it adds a radio (`radio_added`), changes it in `radios` and tells
    `radio/<id>/<key>` in `config`'s `radio_keys_in`: `radio_values` as the radios wire keeps them
    apart from the form's keys, or as `values`. A Mercury radio's row gets
    `modem` (null: no modem came up). A command it is told to refuse is answered with an `error`
    naming it."""

    def __new__(
        cls,
        smoke: ModuleType,
        hello: dict[str, object],
        topics: dict[str, object],
        refuse: str = "",
        radio_keys_in: str = "radio_values",
        modem: object = None,
    ) -> Any:
        class Page(smoke.PageSocket):  # type: ignore[name-defined, misc]
            async def send(self, command: dict[str, object]) -> int:
                since = len(self.messages)
                self.sent.append(command)
                config = self.topics["config"]
                if command["cmd"] == refuse:
                    self.messages.append({"type": "error", "cmd": refuse, "text": f"{refuse}: no"})
                elif command["cmd"] == "set_config":
                    for key, value in dict(command["values"]).items():  # type: ignore[call-overload]
                        config.setdefault(radio_keys_in if key.startswith("radio/") else "values", {})[key] = value
                elif command["cmd"] == "radio_add":
                    id = 1 + max((int(k) for k in self.topics["radios"]), default=0)
                    self.topics["radios"][str(id)] = radio_row(
                        id, TYPES[str(command["type"])].kind, str(command["type"]), id, enabled=False, state="stopped"
                    )
                    self.messages.append({"type": "radio_added", "id": id})
                elif command["cmd"] == "radio_change":
                    self.topics["radios"][str(command["radio"])].update(
                        {k: v for k, v in command.items() if k not in ("cmd", "radio")}
                    )
                for row in (self.topics.get("radios") or {}).values():
                    row["modem"] = modem if row["type"] == "mercury" else None
                return since

            async def until(self, what: str, condition: object, seconds: float) -> None:
                if not condition(self):  # type: ignore[operator]
                    raise smoke.Failure(f"{what}: not so")

        page = Page(None, hello)
        page.topics.update(topics)
        page.sent = []
        return page


def test_a_radio_is_given_by_the_radio_commands() -> None:
    import asyncio

    smoke = load_script("smoke.py")
    # The radios wire tells a radio's keys apart from the form's in radio_values; `values` words
    # them as config's values
    for told_in in ("radio_values", "values"):
        new = FakeDaemonPage(
            smoke,
            HELLO,
            {"config": {"values": {}, "radio_values": {}}, "radios": {"1": radio_row(1, "fm", "kiss-tcp", 1)}},
            radio_keys_in=told_in,
        )
        assert asyncio.run(smoke.give_radio(new, "hf", "mercury", {"keying": "vox", "sound_card": ""}, 1)) == 2
        assert new.sent == [
            {"cmd": "radio_add", "type": "mercury"},
            {"cmd": "radio_change", "radio": 2, "enabled": True},
            {"cmd": "set_config", "values": {"radio/2/keying": "vox", "radio/2/sound_card": ""}},
        ], "a station with no HF radio is given one; its keys by its id"
        assert (
            new.topics["config"][told_in] == {"radio/2/keying": "vox", "radio/2/sound_card": ""}
            and new.config()["radio/2/keying"] == "vox"
        ), told_in
    there = FakeDaemonPage(
        smoke,
        HELLO,
        {
            "config": {"values": {}},
            "radios": {"1": radio_row(1, "fm", "kiss", 1), "2": radio_row(2, "hf", "mercury", 2, enabled=False)},
        },
    )
    asyncio.run(smoke.give_radio(there, "hf", "dummy-hf", {}, 1))
    assert there.sent == [{"cmd": "radio_change", "radio": 2, "type": "dummy-hf", "enabled": True}], (
        "the HF radio there is changed, and nothing more is sent"
    )
    for refused in ("radio_add", "set_config"):
        page = FakeDaemonPage(smoke, HELLO, {"config": {"values": {}}, "radios": {}}, refuse=refused)
        with pytest.raises(smoke.Failure, match=f"{refused} was refused: {refused}: no"):
            asyncio.run(smoke.give_radio(page, "hf", "mercury", {"keying": "vox"}, 1))


def test_the_install_probe_reads_and_gives_the_radios_of_a_release_before_the_round_in_its_own_words_and_of_any_other_by_the_topic_radios() -> (
    None
):
    """The seed of the upgrade (scripts/check-installs) is run on the old release, which may
    be one from before radios were rows (its FM radio the topic `tnc`, its HF radio `hf/enabled`
    and `hf/profile` of `config`); a daemon whose hello lists `radios` is read and given its radios
    by them alone."""
    import asyncio
    from types import SimpleNamespace

    probe = load_script("install-probe.py")
    smoke = probe.smoke
    before = {"type": "hello", "topics": ["stations", "packets", "tnc", "hf", "config"]}
    hf_on = {"station/call": "OH2TST", "hf/enabled": "true", "hf/profile": "dummy-hf"}
    old = SimpleNamespace(hello=before, topics={"tnc": {"state": "connected"}, "config": {"values": hf_on}})
    assert probe.OldRelease.is_one(before) and not probe.OldRelease.is_one(HELLO)
    assert probe.fm_state(old) == "connected" and probe.has_settings(old), (
        "the old release's FM radio by its topic, its HF radio by its two settings"
    )
    assert not probe.has_settings(
        SimpleNamespace(hello=before, topics={"config": {"values": {**hf_on, "hf/enabled": "false"}}})
    ), "an HF radio that is off is not the station of the seed"
    rows = {"1": radio_row(1, "fm", "kiss", 1), "2": radio_row(2, "hf", "dummy-hf", 2)}
    new = SimpleNamespace(hello=HELLO, topics={"radios": rows, "config": {"values": {"station/call": "OH2TST"}}})
    assert probe.fm_state(new) == "connected" and probe.has_settings(new)
    assert probe.fm_state(SimpleNamespace(hello=HELLO, topics={"tnc": {"state": "connected"}})) is None, (
        "a daemon of the radios is never read by the old release's words"
    )
    assert not probe.has_settings(
        SimpleNamespace(hello=HELLO, topics={"radios": {"1": rows["1"]}, "config": {"values": hf_on}})
    ), "the settings of before say nothing to a daemon of the radios"
    page = FakeDaemonPage(smoke, before, {"config": {"values": {"station/call": "OH2TST"}}})
    asyncio.run(probe.give_radios(page, 1))
    assert page.sent == [{"cmd": "set_config", "values": {"hf/enabled": "true", "hf/profile": "dummy-hf"}}], (
        "the old release is given its HF radio by the settings of its own time, and no radio command"
    )
    page = FakeDaemonPage(smoke, HELLO, {"config": {"values": {}}, "radios": {}})
    asyncio.run(probe.give_radios(page, 1))
    assert [m["cmd"] for m in page.sent if m["cmd"] == "radio_add"] == ["radio_add", "radio_add"] and [
        m.get("type") for m in page.sent if m["cmd"] == "radio_add"
    ] == ["kiss", "dummy-hf"], (
        "a daemon of the radios: the FM radio first (a new installation has none), then the HF radio"
    )


def test_the_upgrade_seeds_a_release_from_before_the_radios_on_its_own_wire_and_this_tree_on_the_wire_of_the_radios() -> (
    None
):
    """scripts/check-installs runs this tree's install-probe seed against the old release's daemon:
    the probe gives that daemon its HF radio by the flat settings and reads its FM radio in the
    topic `tnc`; a current daemon gets its HF radio by the radio commands."""
    import asyncio

    probe = load_script("install-probe.py")
    # The smoke the probe loaded: its Failure and PageSocket are the ones it uses
    smoke = probe.smoke
    old_hello = {
        "type": "hello",
        "version": "0.18.2",
        "topics": ["stations", "packets", "tnc", "hf", "messages", "config"],
    }
    # An old daemon answers a radio command it does not know with an error
    old = FakeDaemonPage(smoke, old_hello, {"config": {"values": {}}}, refuse="radio_add")
    asyncio.run(probe.seed_commands(old, 1))
    assert old.sent == [
        {"cmd": "set_config", "values": {"station/call": "OH2TST"}},
        {"cmd": "set_config", "values": {"hf/enabled": "true", "hf/profile": "dummy-hf"}},
        {"cmd": "send_message", "to": probe.MESSAGE_TO, "text": probe.MESSAGE_TEXT},
    ], "the old release's HF radio by its flat settings, no radio command"
    assert probe.OldRelease.HF_SETTINGS["hf/profile"] == probe.HF_TYPE, (
        "the old radio the migration makes is the one verify and the database check look for"
    )
    old.topics.update(
        {
            "stations": {"OH2X": {"call": "OH2X"}},
            "messages": {"1": {"text": probe.MESSAGE_TEXT}},
            probe.OldRelease.TOPIC: {"state": "waiting"},
        }
    )
    assert probe.has_settings(probe.Seen(old)) and not probe.seed_ready(probe.Seen(old)), (
        "the FM radio not yet connected"
    )
    old.topics[probe.OldRelease.TOPIC] = {"state": "connected"}
    assert probe.seed_ready(probe.Seen(old)), "the old release's FM radio read in its topic tnc"
    # A daemon of the round on a new installation: no radio
    new = FakeDaemonPage(smoke, HELLO, {"config": {"values": {}, "radio_values": {}}, "radios": {}})
    asyncio.run(probe.seed_commands(new, 1))
    assert [command["cmd"] for command in new.sent] == [
        "set_config",
        "radio_add",
        "radio_change",
        "radio_add",
        "radio_change",
        "send_message",
    ] and new.sent[0]["values"] == probe.SETTINGS, (
        "this tree's daemon: the radio commands, the FM radio first (a new installation has none), then the HF radio"
    )
    assert [command["type"] for command in new.sent if command["cmd"] == "radio_add"] == [probe.FM_TYPE, probe.HF_TYPE]
    new.topics["radios"]["1"]["state"] = "connected"
    new.topics.update(
        {
            "stations": {"OH2X": {"call": "OH2X"}},
            "messages": {"1": {"text": probe.MESSAGE_TEXT}},
            probe.OldRelease.TOPIC: {"state": "connected"},
        }
    )
    assert (
        probe.has_settings(probe.Seen(new))
        and probe.seed_ready(probe.Seen(new))
        and probe.fm_state(probe.Seen(new)) == "connected"
    )
    new.topics["radios"]["1"]["state"] = "waiting"
    assert not probe.seed_ready(probe.Seen(new)), (
        "a daemon of the round is read in its topic radios, never in a topic tnc"
    )


class Running:
    """A daemon process, as wait_for_interrupt asks after it: still running."""

    returncode = None

    def poll(self) -> None:
        return None


@pytest.mark.parametrize("windows", [True, False])
def test_ctrl_c_on_sim_radios_keep_only_says_stop_and_the_daemon_is_then_stopped_not_killed(
    windows: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """scripts/sim-radios --keep waits for Ctrl+C and then stops its daemon as a service manager
    does. On Windows asyncio.run's own Ctrl+C cancels the run (the daemon killed, a traceback)
    unless the script takes SIGINT itself; on POSIX the loop's handler. Either way the wait returns,
    a second Ctrl+C during the stop does not cut the stop short (Python's default or asyncio.run's
    handler would: a kill and a traceback), and asyncio.run's SIGINT is given back once the stop and
    its checks are done."""
    import asyncio
    import importlib.machinery
    import importlib.util

    if not windows and sys.platform == "win32":
        pytest.skip("a loop's signal handler is POSIX's")
    loader = importlib.machinery.SourceFileLoader("sim_radios", str(ROOT / "scripts" / "sim-radios"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    sim = importlib.util.module_from_spec(spec)
    loader.exec_module(sim)
    monkeypatch.setattr(sim.smoke, "WINDOWS", windows)
    before = signal.getsignal(signal.SIGINT)
    stops: list[str] = []

    def stop_daemon() -> None:
        """The stop and the checks of its end, during which the operator presses Ctrl+C again."""
        signal.raise_signal(signal.SIGINT)
        # A Python handler runs between two steps of this code: here, if at all
        time.sleep(0.05)
        stops.append("stopped")

    async def keep() -> object:
        runs = signal.getsignal(signal.SIGINT)  # asyncio.run's own
        asyncio.get_running_loop().call_later(0.3, signal.raise_signal, signal.SIGINT)
        await asyncio.wait_for(sim.keep_then_stop(Running(), stop_daemon), 30)
        assert signal.getsignal(signal.SIGINT) == runs, "asyncio.run's Ctrl+C is back after the stop"
        return "returned"

    try:
        assert asyncio.run(keep()) == "returned"
    except KeyboardInterrupt:
        pytest.fail(
            f"Ctrl+C ended the run ({'during' if stops == [] else 'after'} the stop): the daemon would be killed, not stopped, or a traceback"
        )
    assert stops == ["stopped"], "the stop ran to its end"
    assert signal.getsignal(signal.SIGINT) == before, "the Ctrl+C of before is back"


def test_the_station_of_the_shots_is_an_fm_an_hf_and_a_lora_radio_of_dummy_types_and_never_a_type_that_starts_a_modem() -> (
    None
):
    """The shots show three radios, "2 m" (FM), "40 m" (HF) and a LoRa radio, each of a Dummy type,
    which opens no device. The script names Mercury and Direwolf types only to refuse them before
    anything is run."""
    import ast

    shots = load_script("screenshots.py")
    assert [(kind, name) for kind, _, name in shots.RADIOS] == [("fm", "2 m"), ("hf", "40 m"), ("lora", "")]
    assert all(TYPES[type].dummy and TYPES[type].kind == kind for kind, type, _ in shots.RADIOS), (
        "a Dummy type of each kind"
    )
    assert (
        shots.LABELS == {"fm": "2 m", "hf": "40 m", "lora": "LoRa"}
        and shots.DAY_RADIO == 1
        and shots.RADIO_TYPE == "kiss-tcp"
    )
    assert {TYPES[type].transport for type in shots.FORBIDDEN_TYPES} == {"modem"} and {
        t.key for t in TYPES.values() if t.transport == "modem"
    } <= set(shots.FORBIDDEN_TYPES)
    for type in shots.FORBIDDEN_TYPES:
        with pytest.raises(ValueError, match=f"no shot uses the {type} type"):
            shots.neoaprs_db_add_radio(ROOT / "work" / "no-such-folder", type)
    tree = ast.parse((ROOT / "scripts" / "screenshots.py").read_text(encoding="utf-8"))
    named = [node for node in ast.walk(tree) if isinstance(node, ast.Constant) and node.value in shots.FORBIDDEN_TYPES]
    refused = next(
        node
        for node in tree.body
        if isinstance(node, ast.AnnAssign | ast.Assign) and "FORBIDDEN_TYPES" in ast.unparse(node).split("=")[0]
    )
    assert named and all(node in list(ast.walk(refused)) for node in named), (
        "no forbidden type is named anywhere but in FORBIDDEN_TYPES"
    )
    assert "--hf-port" not in (ROOT / "scripts" / "screenshots.py").read_text(encoding="utf-8"), (
        "no modem that something else runs either"
    )


def test_the_day_is_played_on_radio_1_and_the_station_is_then_given_its_three_radios_and_radio_1_keeps_what_it_carried(
    tmp_path: Path,
) -> None:
    """give_radios on a data folder with the day's radio 1 (a KISS TNC over TCP, named "2 m"), as
    prepare leaves it once the day is played: radio 1 becomes the Dummy FM radio and keeps its name,
    the Dummy HF radio "40 m" is radio 2 and the Dummy LoRa radio with no name radio 3, all on, and
    radio 1 is ticked for the status, Ask around and Local info (what it carried alone)."""
    import asyncio

    shots = load_script("screenshots.py")
    data = tmp_path / "demo"
    data.mkdir()

    async def made() -> tuple[dict[str, int], Any, dict[str, str]]:
        ctl = shots.Controller(data)
        await ctl.open_database()
        await ctl.db.close()
        assert shots.neoaprs_db_add_radio(data, shots.RADIO_TYPE, "2 m") == shots.DAY_RADIO
        ids = await shots.give_radios(data)
        ctl = shots.Controller(data)
        await ctl.open_database()
        try:
            return ids, await ctl.store.read_radios(), await ctl.store.settings()
        finally:
            await ctl.db.close()

    ids, radios, settings = asyncio.run(made())
    assert ids == {"fm": 1, "hf": 2, "lora": 3}
    assert [(r.id, r.kind, r.type, r.name, r.enabled, r.removed_at) for r in radios] == [
        (1, "fm", "dummy", "2 m", True, None),
        (2, "hf", "dummy-hf", "40 m", True, None),
        (3, "lora", "dummy-lora", "", True, None),
    ]
    assert "station/main_radio" not in settings and [
        {key: r.settings.get(key) for key in ("status", "ask", "local_info")} for r in radios
    ] == [dict.fromkeys(("status", "ask", "local_info"), "true"), *[dict.fromkeys(("status", "ask", "local_info"))] * 2]
    assert "email/radio" in settings and settings["email/radio"] == "1", "the mail where it went"


def test_the_hf_tests_shot_is_given_two_tests_to_come_on_40_m_by_two_of_the_days_cast() -> None:
    """The board the hf-tests shot's daemon reads is one neoaprs/skeds.py takes whole: two tests,
    each by a call of the made-up day (scripts/demoscene.py), on the 40 m dial the page suggests,
    both to come (tomorrow evening and the morning after, UTC) whatever the time of the run, and
    each a row of its own on the page (other times)."""
    from datetime import UTC, datetime
    from neoaprs.mercury import SUGGESTED
    from neoaprs.skeds import parse_board

    shots = load_script("screenshots.py")
    day = (ROOT / "scripts" / "demoscene.py").read_text(encoding="utf-8")
    for now in (
        datetime(2026, 11, 15, 0, 0, tzinfo=UTC),
        datetime(2026, 11, 15, 23, 59, tzinfo=UTC),
        datetime.now(UTC),
    ):
        board = parse_board(shots.made_up_board(now), now)
        assert board is not None and not board.closed and len(board.skeds) == 2, now
        assert [s.call for s in board.skeds] == list(shots.SKED_CALLS) and all(
            f'"{s.call}' in day for s in board.skeds
        ), "two of the day's cast"
        assert all(s.dial == dict(SUGGESTED)["40 m"] and now < s.start < s.end for s in board.skeds)
        assert len({(s.start, s.end, s.dial) for s in board.skeds}) == 2, "two rows on the page"


def test_the_made_up_waterfall_is_the_daemons_own_frames_of_a_channel_with_frames_on_it() -> None:
    """The hf-tests shot's rows are frames as the daemon makes them: the rows kept of the last two
    minutes, ten a second, named by the HF radio, with the page's script writing its clock in after
    the kind byte; then rows of their own; the bins of a frame on the air stand well over the noise
    between 1200 and 1800 Hz. The modem the page is told of is one the wire's model takes."""
    import json
    from neoaprs.mercuryscope import HISTORY_HEADER, HISTORY_SEC, ROW_BINS, history_clock, parse_history, parse_row
    from neoaprs.web.scopefeed import parse_radio_frame
    from neoaprs.web.tncwire import ModemState

    shots = load_script("screenshots.py")
    history, live = shots.scope_frames(7)
    radio, inner = parse_radio_frame(history)
    rows = parse_history(inner)
    assert radio == 7 and rows is not None and len(rows) == HISTORY_SEC * 10 and history_clock(inner) == 0.0
    assert (
        [age for _, age in rows] == sorted((age for _, age in rows), reverse=True)
        and rows[0][1] == 119900
        and rows[-1][1] == 0
    )
    assert all(len(row.bins) == ROW_BINS and not row.tx for row, _ in rows)
    assert len(live) == 300 and all(
        parse_radio_frame(frame)[0] == 7 and parse_row(parse_radio_frame(frame)[1]) is not None for frame in live
    )
    signal = [
        i
        for i in range(ROW_BINS)
        if 1250 <= (shots.ROW_FIRST_BIN + i) * shots.MODEM_RATE / 2 / shots.MODEM_BINS <= 1750
    ]
    quiet, framed = rows[0][0].bins, rows[round((shots.SCOPE_FRAMES[0][0] + 1) * 10)][0].bins
    assert min(framed[i] for i in signal) - max(quiet[i] for i in signal) > 10, (
        "a frame on the air stands over the noise"
    )
    assert HISTORY_HEADER.format == "<Bd", "the page's script writes the clock as a float64 after the kind byte"
    given = json.loads(shots.scope_page(7).split("const P = ", 1)[1].split(";\n", 1)[0])
    assert given["radio"] == 7 and given["clockAt"] == 6 and given["everyMs"] == 100 and len(given["live"]) == 300
    ModemState.model_validate(given["modem"])


def test_every_picture_the_site_names_is_a_shot_of_the_script_and_the_shots_are_light_and_dark() -> None:
    """Each shots/NAME (or thumbs/NAME, .png or .webp, NAME-dark the dark one) that a page of site/
    names is taken by a shot of SHOTS (og.png is drawn from the map); every shot of DARK_TOO has its
    dark one, the new hf-tests among them; each extra daemon is for shots there are."""
    shots = load_script("screenshots.py")
    named = {
        name
        for page in (ROOT / "site").glob("*.html")
        for name in re.findall(r"shots/(?:thumbs/)?([a-z0-9-]+)\.(?:png|webp)", page.read_text(encoding="utf-8"))
    }
    assert named and named - {"og"} <= set(shots.SHOTS), sorted(named - {"og"} - set(shots.SHOTS))
    assert {
        "hf-tests",
        "hf-tests-dark",
        "settings-tnc",
        "stations-hf",
        "stations-menu",
        "packets",
        "beacon-gps",
    } <= named
    assert (
        all(f"{name}-dark" in shots.SHOTS for name in shots.DARK_TOO)
        and "hf-tests" in shots.DARK_TOO
        and shots.SHOTS["hf-tests"] is shots.shot_hf_tests
    )
    assert set(shots.EXTRA_DAEMONS["skeds"]) == {"hf-tests", "hf-tests-dark"} and all(
        name in shots.SHOTS for names in shots.EXTRA_DAEMONS.values() for name in names
    )


def test_the_settings_shots_draw_the_phone_code_of_the_made_up_address_and_key_as_the_page_draws_a_code() -> None:
    """made_up_web puts the code of SHOWN_URL with SHOWN_KEY over the daemon's own: the golden
    symbol "shown" of the page's QR test (ui/src/lib/qr.fixture.json, held to uqr there), in its
    quiet zone of four modules, a run of dark modules in a row one rectangle as qrPath writes it.
    Read back, the path is that symbol and nothing else."""
    import json

    shots = load_script("screenshots.py")
    size, path = shots.shown_code()
    shown = json.loads((ROOT / "ui/src/lib/qr.fixture.json").read_text(encoding="utf-8"))["shown"]
    assert shown["text"] == "http://192.168.1.20:7303/#key=k7m2-x9pq-4hrt" == f"{shots.SHOWN_URL}#key={shots.SHOWN_KEY}"
    assert size == len(shown["rows"]) + 8
    assert re.fullmatch(r"(M\d+ \d+h\d+v1h-\d+z)+", path)
    drawn = [["0"] * size for _ in range(size)]
    for x, y, run, back in re.findall(r"M(\d+) (\d+)h(\d+)v1h-(\d+)z", path):
        assert run == back
        for i in range(int(run)):
            drawn[int(y)][int(x) + i] = "1"
    assert ["".join(row[4:-4]) for row in drawn[4:-4]] == shown["rows"]
    assert all(c == "0" for row in drawn[:4] + drawn[-4:] for c in row) and all(
        c == "0" for row in drawn for c in row[:4] + row[-4:]
    )


def test_every_shot_that_opens_the_settings_tab_puts_the_made_up_key_and_code_over_the_daemons_own_at_once() -> None:
    """The Settings tab shows the access key and the phone code, which hold the screenshot machine's
    own key and address: every shot that opens it calls made_up_web on its page in the very next
    statement, before anything is clicked (the update shot's dialog leaves the Web page group in
    view above it)."""
    import ast

    tree = ast.parse((ROOT / "scripts" / "screenshots.py").read_text(encoding="utf-8"))

    def opens_settings(statement: ast.stmt) -> bool:
        return any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "page"
            and isinstance(n.func.value, ast.Name)
            and n.func.value.id == "s"
            and any(
                k.arg == "tab" and isinstance(k.value, ast.Constant) and k.value.value == "settings" for k in n.keywords
            )
            for n in ast.walk(statement)
        )

    def made_up(statement: ast.stmt) -> bool:
        return (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Await)
            and isinstance(call := statement.value.value, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "made_up_web"
            and [ast.unparse(a) for a in call.args] == ["page"]
        )

    shots = [f for f in tree.body if isinstance(f, ast.AsyncFunctionDef) and f.name.startswith("shot_")]
    opening = {f.name: [i for i, st in enumerate(f.body) if opens_settings(st)] for f in shots}
    assert {"shot_update", "shot_settings", "shot_settings_web", "shot_settings_tnc", "shot_settings_hf"} <= {
        name for name, at in opening.items() if at
    }
    for f in shots:
        for i in opening[f.name]:
            assert i + 1 < len(f.body) and made_up(f.body[i + 1]), (
                f"{f.name}: the Settings tab is shown without the made-up key and code"
            )


def test_a_run_into_the_site_or_of_everything_refuses_to_draw_the_street_maps_on_the_placeholder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import asyncio

    shots = load_script("screenshots.py")
    nowhere = str(tmp_path / "no.pmtiles")
    for argv in (["--out", str(tmp_path / "out"), "--basemap", nowhere], ["--only", "map", "--basemap", nowhere]):
        with pytest.raises(SystemExit) as stopped:
            asyncio.run(shots.main(argv))
        assert (
            stopped.value.code == 2
            and f"there is no street map at {nowhere}: name one with --basemap FILE" in capsys.readouterr().err
        ), argv
    assert not (tmp_path / "out").exists(), "refused before anything is written"


def png(path: Path, width: int, height: int) -> Path:
    """A file that begins as a PNG of that size does (what the size reader reads)."""
    import struct

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x02\x00\x00\x00"
    )
    return path


def test_the_site_declares_each_picture_at_the_size_of_its_file_and_every_shot_has_all_its_files() -> None:
    """The check of `scripts/screenshots.py --check` on the tree: no <img> of site/ at another size
    than its file (thumbs/chain.png was 681 high in the page and 781 in the file), no dark copy of
    another size in the same box, og.png as og:image:width and height say; and each of the shots its
    PNG, WebP and both thumbnails, og.png and the README's copies."""
    shots = load_script("screenshots.py")
    assert shots.wrong_sizes(ROOT / "site") == []
    assert shots.missing_files(ROOT / "site" / "shots", ROOT / "docs" / "screenshots") == []
    assert all(
        shots.image_size(path) == shots.image_size(path.with_suffix(".png"))
        for path in (ROOT / "site" / "shots").glob("*.webp")
    ), "the WebP header is read as the PNG beside it"


def test_a_picture_declared_at_another_size_is_found_and_written_as_its_file(tmp_path: Path) -> None:
    shots = load_script("screenshots.py")
    png(tmp_path / "shots" / "thumbs" / "chain.png", 640, 781)
    png(tmp_path / "shots" / "thumbs" / "chain-dark.png", 640, 790)
    png(tmp_path / "shots" / "og.png", 1200, 630)
    page = (
        '<meta property="og:image" content="https://neo.oh2gba.eu/shots/og.png">\n<meta property="og:image:width" content="1200">\n<meta property="og:image:height" content="600">\n'
        '<picture><source srcset="shots/thumbs/chain-dark.png" media="(prefers-color-scheme: dark)"><img src="shots/thumbs/chain.png" width="640" height="681" alt=""></picture>\n<img src="favicon.svg" width="28" height="28">\n'
    )
    # With LF, as every system checks the site out: .gitattributes
    (tmp_path / "index.html").write_bytes(page.encode())
    assert shots.wrong_sizes(tmp_path) == [
        "index.html: shots/thumbs/chain.png is declared 640x681, the file is 640x781",
        "index.html: shots/thumbs/chain-dark.png is 640x790 in the box of shots/thumbs/chain.png, 640x781",
        "index.html: og:image:height says 600, shots/og.png is 630",
    ]
    assert shots.fix_sizes(tmp_path) == [
        "index.html: shots/thumbs/chain.png 640x681 -> 640x781",
        "index.html: og:image:height -> 630",
    ]
    fixed = (tmp_path / "index.html").read_bytes().decode()
    assert fixed == page.replace('height="681"', 'height="781"').replace(
        'og:image:height" content="600"', 'og:image:height" content="630"'
    ), "the sizes changed, and nothing else: not the line ends either"
    assert (
        'src="shots/thumbs/chain.png" width="640" height="781"' in fixed
        and 'og:image:height" content="630"' in fixed
        and 'width="28" height="28"' in fixed
    )
    assert shots.wrong_sizes(tmp_path) == [
        "index.html: shots/thumbs/chain-dark.png is 640x790 in the box of shots/thumbs/chain.png, 640x781"
    ], "the dark file's size is its own: said, never written"
    assert shots.fix_sizes(tmp_path) == [], "a page that agrees is left as it is"


def test_a_run_says_each_file_it_did_not_write_and_why(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    shots = load_script("screenshots.py")
    out, docs = tmp_path / "shots", tmp_path / "screenshots"
    for name in ("map", "map-dark", "settings-hf", "chain", "old-scene", "og"):
        png(out / f"{name}.png", 10, 10)
    png(out / "thumbs" / "map.png", 1, 1)
    png(docs / "map.png", 1, 1)
    png(docs / "weather.png", 1, 1)
    long_ago = time.time() - 3600
    for path in [*out.rglob("*.png"), *docs.glob("*.png")]:
        os.utime(path, (long_ago, long_ago))
    run = shots.Run(
        taken=["map", "chain"],
        why_not={
            "settings-hf": "its daemon did not come up: TimeoutError: ",
            "chain": "failed: TimeoutError: ",
            "og": "drawn only by a run with everything, --only og or --only map",
            "thumbs": "no shot taken",
        },
    )
    png(out / "map.png", 10, 10)  # (written by the run)
    left = shots.leftovers(run, out, docs)
    assert left == {
        "not asked for (--only)": ["screenshots/weather.png", "shots/map-dark.png"],
        "its daemon did not come up: TimeoutError: ": ["shots/settings-hf.png"],
        "failed: TimeoutError: ": ["shots/chain.png"],
        "made by no shot of this script: left as it is": ["shots/old-scene.png"],
        "drawn only by a run with everything, --only og or --only map": ["shots/og.png"],
        "no shot taken": ["shots/thumbs/map.png"],
        "not copied": ["screenshots/map.png"],
    }
    assert shots.say_what_was_left(run, out, docs) == 2 + 8, "the two shots not taken, and the eight files"
    said = capsys.readouterr().out
    # A copy made by this run from the earlier settings-hf.png: no picture of this run
    png(out / "thumbs" / "settings-hf.png", 1, 1)
    assert shots.leftovers(run, out, docs)["its daemon did not come up: TimeoutError: "] == [
        "shots/settings-hf.png",
        "shots/thumbs/settings-hf.png",
    ]
    assert [path.stem for path in shots.thumbs_of(out, None, skip={"settings-hf", "chain"})] == [
        "map-dark",
        "map",
        "old-scene",
    ], "a whole run makes no copies of the shots it did not take"
    assert [path.stem for path in shots.thumbs_of(out, {"map", "chain"})] == ["chain", "map"]
    run.sizes = ["index.html: shots/thumbs/chain-dark.png is 640x790 in the box of shots/thumbs/chain.png, 640x781"]
    assert shots.say_what_was_left(run, out, docs) == 2 + 9 + 1, (
        "a size the site still declares wrongly counts as --check counts it"
    )
    assert (
        "site, at another size (--check fails on it): index.html: shots/thumbs/chain-dark.png"
        in capsys.readouterr().out
    )
    assert (
        "not taken: settings-hf: its daemon did not come up" in said
        and "not retaken (made by no shot of this script: left as it is): 1 files: shots/old-scene.png" in said
        and "GitHub's link preview" in said
    )
    assert set(shots.EXTRA_DAEMONS["skeds"]) == {"hf-tests", "hf-tests-dark"} and all(
        name in shots.SHOTS for names in shots.EXTRA_DAEMONS.values() for name in names
    )


def test_the_link_preview_names_the_systems_the_site_names() -> None:
    """og.png's pitch names Windows, macOS, Linux and the Raspberry Pi, as the line under the site's
    name does, and is cut at its words into lines that fit beside the map."""
    shots = load_script("screenshots.py")
    sub = re.search(r'<p class="sub">([^<]+)</p>', (ROOT / "site" / "index.html").read_text(encoding="utf-8"))
    assert sub and all(
        system in sub.group(1) and system in shots.PITCH for system in ("Windows", "macOS", "Linux", "Raspberry Pi")
    )
    assert shots.lines_of("a bb ccc dddd", lambda text: len(text) <= 6) == ["a bb", "ccc", "dddd"] and shots.lines_of(
        "toolongword x", lambda text: len(text) <= 4
    ) == ["toolongword", "x"]


def test_the_scripts_that_run_a_daemon_in_their_process_reach_its_radios_by_id_and_name_an_objects_radios() -> None:
    """The day of the screenshots (demoscene) and its folder (screenshots) reach the daemon's radio
    through the registry, by id (the controller names no radio of its own); an object of the day is
    made on the radios `object_set` names . The shots' HF radio is added as a radio (`db
    radios add`), never by a `db set` of a flat HF key (refused)."""
    for name in ("demoscene.py", "screenshots.py"):
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert not re.search(r"\bctl\.(tnc|hf|mercury|beacon|hf_" r"beacon)\b", source), name
    assert "radios=(DEMO_RADIO,)" in (ROOT / "scripts" / "demoscene.py").read_text(encoding="utf-8")
    assert not re.search(
        r'neoaprs_db_set\([^)]*"(hf|mercury)/', (ROOT / "scripts" / "screenshots.py").read_text(encoding="utf-8")
    )


def test_the_demo_daemon_runs_the_checkouts_daemon_under_the_switch_and_never_on_the_operators_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The daemon of the browser pane opens no device, starts no modem of the machine and asks
    nothing of the internet, whatever its settings say; and it is never started on the data of the
    operator's own station, the system's data folder or a checkout's `data`."""
    demo = load_script("demo-daemon")
    started: list[tuple[list[str], Path, dict[str, str]]] = []

    def run(command: list[str], cwd: Path, env: dict[str, str]) -> int:
        started.append((command, cwd, env))
        return 0

    monkeypatch.setenv("NEOAPRS_DATA_DIR", str(tmp_path / "elsewhere"))
    monkeypatch.setenv("NEOAPRS_DEBUG", "1")
    assert demo.main(["--data", str(tmp_path / "demo")], run) == 0
    [(command, cwd, env)] = started
    assert (
        command[1:] == ["-m", "neoaprs", "--data", str((tmp_path / "demo").resolve()), "--web-port", "7390"]
        and cwd == ROOT
        and Path(command[0]).is_file()
    )
    assert (env["NEOAPRS_NO_DEVICES"], env["NEOAPRS_UPDATE_CHECK"]) == ("1", "0") and not list(
        Path("/").glob(env["NEOAPRS_SERIAL_PATTERN"].lstrip("/"))
    )
    assert "NEOAPRS_DATA_DIR" not in env and "NEOAPRS_DEBUG" not in env and env["PATH"] == os.environ["PATH"], (
        "none of the variables of whoever runs it but the three"
    )
    assert (
        demo.main(["--data", str(tmp_path / "demo"), "--web-port", "7391"], run) == 0 and started[-1][0][-1] == "7391"
    )
    monkeypatch.setattr(demo, "default_data_dir", lambda: tmp_path / "share" / "neoaprs")
    checkout = tmp_path / "clone"
    (checkout / "neoaprs").mkdir(parents=True)
    (checkout / "pyproject.toml").write_text("")
    for folder in (
        tmp_path / "share" / "neoaprs",
        tmp_path / "share" / "neoaprs" / ".",
        checkout / "data",
        ROOT / "data",
    ):
        assert demo.main(["--data", str(folder)], run) == 2, folder
    assert (
        len(started) == 2
        and demo.main(["--data", str(checkout / "data" / "demo")], run) == 0
        and demo.main(["--data", str(tmp_path / "data")], run) == 0
    ), "a folder named data that is no checkout's"
    assert demo.own_data_folder() == tmp_path / "share" / "neoaprs" and os.environ["NEOAPRS_DATA_DIR"] == str(
        tmp_path / "elsewhere"
    )


def test_the_check_of_the_built_mercury_lists_no_sound_card_and_holds_its_alsa_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`mercury -z` would open the control device of every sound card of the machine, the radios'
    among them: the check runs `-V` alone, and holds the ALSA configuration the folder carries to
    being there."""
    build = load_script("build-mercury")
    ran: list[list[str]] = []

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        ran.append(argv[1:])
        return subprocess.CompletedProcess(argv, 0, f"Mercury {build.VERSION}\n", "")

    monkeypatch.setattr(build, "MACOS", False)
    # The script's name for the module: the program is never started
    monkeypatch.setattr(build, "subprocess", SimpleNamespace(run=run))
    for name in ("runpath", "glibc_needed", "check_links"):
        monkeypatch.setattr(build, name, lambda *args: "")
    monkeypatch.setattr(build, "check_loopback", lambda program, env: "listens on 127.0.0.1 only")
    folder = tmp_path / "mercury"
    (folder / "share" / "alsa").mkdir(parents=True)
    with pytest.raises(build.BuildError, match="ALSA configuration"):
        build.check(folder)
    (folder / "share" / "alsa" / "alsa.conf").write_text("")
    with pytest.raises(build.BuildError, match="empty"):
        build.check(folder)
    (folder / "share" / "alsa" / "alsa.conf").write_text("pcm.null { type null }\n")
    build.check(folder)
    assert ran == [["-V"]]


async def test_the_radio_of_the_day_on_the_air_listens_on_a_port_the_system_gives_not_where_a_real_modem_may(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The daemon of the screenshots runs under the no-devices switch, which connects to no port of
    this computer where a real modem may listen (Direwolf's 8001 among them): the made-up TNC is
    never there."""
    import asyncio

    from tests.support.guards import MODEM_PORTS

    demoscene = load_script("demoscene.py")
    asked: list[int] = []
    real_start_server = asyncio.start_server

    async def start_server(serve: Any, host: str, port: int) -> asyncio.Server:
        asked.append(port)
        # The port asked for is looked at, never taken
        return await real_start_server(serve, host, 0)

    monkeypatch.setattr(demoscene.asyncio, "start_server", start_server)
    radio = demoscene.DemoRadio()
    await radio.start()
    try:
        assert asked == [0] and radio.port not in MODEM_PORTS
    finally:
        await radio.stop()


def test_sim_radios_refuses_the_data_folder_of_a_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.machinery
    import importlib.util

    loader = importlib.machinery.SourceFileLoader("sim_radios", str(ROOT / "scripts" / "sim-radios"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    sim = importlib.util.module_from_spec(spec)
    loader.exec_module(sim)
    (tmp_path / "neoaprs").mkdir()
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    assert "checkout" in sim.operators_folder(tmp_path / "data")
    assert sim.operators_folder(tmp_path / "work" / "mine") == ""
    monkeypatch.setattr(sys, "argv", ["sim-radios", "--data", str(tmp_path / "data")])
    assert sim.main() == 2


def test_a_run_of_the_screenshots_into_a_folder_of_its_own_does_not_write_the_readmes_shots(tmp_path: Path) -> None:
    shots = load_script("screenshots.py")
    default = ROOT / "docs" / "screenshots"
    assert shots.docs_folder(tmp_path, default).name == "none"
    assert shots.docs_folder(ROOT / "site" / "shots", default) == default
    assert shots.docs_folder(tmp_path, tmp_path / "docs") == tmp_path / "docs", "a folder named is written"


def test_a_position_never_has_60_minutes() -> None:
    scene = load_script("demoscene.py")
    assert (
        scene._dm(24.99999, 3, "E", "W") == "02500.00E"
        and scene._dm(-60.0, 2, "N", "S") == "6000.00S"
        and scene._dm(60.5, 2, "N", "S") == "6030.00N"
    )
