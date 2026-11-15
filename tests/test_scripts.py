"""`neoaprs replay` and `neoaprs db` as processes, and the scripts that wrap them: the replay of the live capture as a TNC on a TCP port fills the database of a daemon that has no radio, and the tool shows what is
in it; the replay on a pseudo-terminal (`--pty`, POSIX only) is the same through a device file."""
import os
import re
import select
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from neoaprs.kiss import KissDecoder
from tests.conftest import ROOT
from tests.support.files import FIXTURES, text_if_readable
from tests.support.proc import NEW_GROUP, stop
from tests.support.hfchannel import NONBLOCK
from tests.support.ptyline import NOCTTY, posix_only

CAPTURE = FIXTURES / "kiss" / "thd7-2026-10-21.bin"


def env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in ("NEOAPRS_DATA_DIR", "NEOAPRS_DEBUG")}


def tool(data: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "neoaprs", "db", "--data", str(data), *args], cwd=ROOT, env=env(), capture_output=True, text=True, timeout=60)


def script(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    """A wrapper of scripts/ as it is run in a clone, with the test's python for NEOAPRS_PYTHON."""
    return subprocess.run([str(ROOT / "scripts" / name), *args], cwd=ROOT, env={**env(), "NEOAPRS_PYTHON": sys.executable}, capture_output=True, text=True, timeout=60)


def test_the_screenshots_show_no_version_and_make_the_update_shots_next_number_from_the_tree() -> None:
    """A release by itself makes no shot old: the version beside Check now is hidden in every page the script opens (before the first shot is taken), and the newer version its update shot announces is one past VERSION,
    not a number kept by hand."""
    import importlib.util

    from neoaprs import VERSION
    path = ROOT / "scripts" / "screenshots.py"
    spec = importlib.util.spec_from_file_location("screenshots", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.next_version("0.8.0") == "0.8.1" and module.next_version("1.0.0-rc1") == "1.0.1" and module.next_version("2.10.99") == "2.10.100"
    assert module.UPDATE_TO == module.next_version(VERSION) and module.UPDATE_TO != VERSION
    assert ".updateversion" in module.HIDE_VERSION and "visibility: hidden" in module.HIDE_VERSION, "hidden, not removed: the row keeps its place"
    source = path.read_text(encoding="utf-8")
    opened = source.split("async def page(", 1)[1].split("async def save(", 1)[0]
    assert opened.index("page.goto(") < opened.index("add_style_tag(content=HIDE_VERSION)") < opened.index("wait_for_timeout(wait_ms)"), "the sheet goes in as soon as the page is open, before any shot"
    assert not re.search(r'UPDATE_TO = "\d', source), "no version number kept by hand"


def wait_until(condition: object, seconds: float = 90.0) -> None:                    # (real processes on a loaded runner: the Windows one took 14 min for the suite and needed more than 30 s here; it returns as soon as the condition holds)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():  # type: ignore[operator]
            return
        time.sleep(0.05)
    raise AssertionError("the condition did not come true")


def test_a_replayed_capture_fills_the_database_of_a_daemon_without_a_radio_over_tcp(tmp_path: Path) -> None:
    data = tmp_path / "data"
    for key, value in (("station/call", "OH2GBA"), ("station/lat", "60.17"), ("station/lon", "24.94")):         # (a station that is set up: with no call and position there is no station of ours in the book)
        assert tool(data, "set", key, value).returncode == 0
    replay = subprocess.Popen([sys.executable, "-m", "neoaprs", "replay", str(CAPTURE), "--interval", "0.2"], cwd=ROOT, env=env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    daemon = None
    try:
        assert replay.stdout is not None
        path = replay.stdout.readline().strip()
        assert path.startswith("socket://127.0.0.1:")
        daemon = subprocess.Popen([sys.executable, "-m", "neoaprs", "--data", str(data), "--port", path, "--web-port", "0"], cwd=ROOT, env=env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=NEW_GROUP)
        log = data / "neoaprs.log"
        wait_until(lambda: (text_if_readable(log) or "").count(" -> position ") >= 4)
        stations = tool(data, "stations")                                          # while the daemon runs (the appends are committed within a second)
        wait_until(lambda: "OH2PU-9" in tool(data, "stations").stdout)
        stations = tool(data, "stations")
        assert stations.returncode == 0, stations.stderr
        for call in ("OH2RDG", "OH2RDK-7", "OH2RDS", "OH2PU-9", "OH2GBA"):
            assert call in stations.stdout
        assert "60.1650 24.9467" in stations.stdout
        packets = tool(data, "packets", "-n", "2")
        lines = packets.stdout.splitlines()
        assert packets.returncode == 0 and len(lines) == 2 and lines[1].endswith("OH2PU-9>APOTC1,OH2RCH-2*:!/0&m]TbwX>z!GQRV D-STAR 144.650MHz -> position 60.1991 24.6501 />" + " QRV D-STAR 144.650MHz")
        assert lines[0] < lines[1] or lines[0][:20] <= lines[1][:20], "the oldest first"
        stop(daemon)
        out, err = daemon.communicate(timeout=10)
        assert daemon.returncode == 0, (out, err)
    finally:
        for proc in (daemon, replay):
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.communicate()


@posix_only
def test_the_replay_on_a_pseudo_terminal_ends_on_ctrl_c_and_says_what_it_does(tmp_path: Path) -> None:
    replay = subprocess.Popen([sys.executable, "-m", "neoaprs", "replay", "--pty", str(CAPTURE), "--interval", "0.05", "--loop"], cwd=ROOT, env=env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert replay.stdout is not None
    path = replay.stdout.readline().strip()
    assert path.startswith("/dev/pts/")
    time.sleep(0.3)                                                            # (nothing may be sent before a port opens it: the time is the point)
    port = os.open(path, os.O_RDWR | NOCTTY | NONBLOCK)              # a port opens it: until then nothing is sent
    heard = bytearray()
    try:
        deadline = time.monotonic() + 15
        while len(KissDecoder().feed(bytes(heard))) < 12 and time.monotonic() < deadline:     # more than the 4 frames of the file: it loops (and three past the ninth, whose line is in the log by the time the tenth is written)
            if select.select([port], [], [], 0.1)[0]:
                heard += os.read(port, 4096)
    finally:
        os.close(port)
    frames = KissDecoder().feed(bytes(heard))
    assert len(frames) >= 12 and [f.payload for f in frames[:4]] == [f.payload for f in KissDecoder().feed(CAPTURE.read_bytes())]
    replay.send_signal(signal.SIGINT)
    out, err = replay.communicate(timeout=10)
    assert replay.returncode == 0 and "waiting for a port to open" in err and "a port opened it" in err and "frame 9 sent" in err and "stopped" in err


def test_the_replay_refuses_a_file_that_is_not_there_or_holds_no_frame(tmp_path: Path) -> None:
    (tmp_path / "empty.bin").write_bytes(b"no frames here")
    for name, message in (("nothing.bin", "No such file"), ("empty.bin", "holds no KISS frame")):
        done = subprocess.run([sys.executable, "-m", "neoaprs", "replay", str(tmp_path / name)], cwd=ROOT, env=env(), capture_output=True, text=True, timeout=30)
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
    assert any(line.startswith("station/call") and line.endswith("stored") for line in listing.splitlines()) and any(line.startswith("web/port") and line.endswith("default") for line in listing.splitlines())
    bad = tool(data, "set", "web/port", "99999")
    assert bad.returncode == 2 and "web/port" in bad.stderr
    unknown = tool(data, "get", "neoaprs/web/colour")
    assert unknown.returncode == 2 and "no such setting" in unknown.stderr
    assert tool(data, "get", "station/call").stdout.strip() == "OH2GBA-9"
    assert tool(data, "stations").returncode == 0 and tool(data, "packets").stdout == ""


@posix_only      # (shell scripts)
def test_the_wrappers_of_the_scripts_call_the_command_with_the_data_folder_of_their_clone(tmp_path: Path) -> None:
    """The wrappers are run from a copy of scripts/ in a made-up clone, so that the data folder they name is the copy's and never the real clone's."""
    clone = tmp_path / "clone"
    (clone / "scripts").mkdir(parents=True)
    for name in ("neoaprs-db", "replay", "capture"):
        shutil.copy2(ROOT / "scripts" / name, clone / "scripts" / name)
    environment = {**env(), "NEOAPRS_PYTHON": sys.executable, "PYTHONPATH": str(ROOT)}

    def run(name: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(clone / "scripts" / name), *args], cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=60)

    helped = run("neoaprs-db", "--help")
    assert helped.returncode == 0 and "neoaprs db" in helped.stdout and "stations" in helped.stdout
    replay = run("replay", "--help")
    assert replay.returncode == 0 and "neoaprs replay" in replay.stdout and "--loop" in replay.stdout
    capture = run("capture", "--help")
    assert capture.returncode == 0 and "neoaprs capture" in capture.stdout and "--seconds" in capture.stdout
    listing = run("neoaprs-db", "list")
    assert listing.returncode == 1 and str(clone / "data") in listing.stderr, "the data folder of the clone the script is in"
    mine = run("neoaprs-db", "--data", str(tmp_path / "mine"), "get", "web/port")
    assert mine.returncode == 1 and str(tmp_path / "mine") in mine.stderr, "a --data of your own wins over the clone's"
    assert run("neoaprs-db", "set", "station/call", "oh2gba").stdout.strip() == "station/call = OH2GBA" and run("neoaprs-db", "get", "station/call").stdout.strip() == "OH2GBA"
    assert (clone / "data" / "neoaprs.sqlite").is_file()


# ---- the scripts that talk to a daemon's page, on the wire before the radios and on the wire of the radios (breakdown 1.11), and what the screenshots leave

def load_script(name: str) -> ModuleType:
    """A script of scripts/ as a module, with scripts/ on the path as when it is run (screenshots.py imports demoscene and smoke from there)."""
    import importlib.util
    folder = str(ROOT / "scripts")
    if folder not in sys.path:
        sys.path.insert(0, folder)
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py").replace("-", "_"), ROOT / "scripts" / name)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


OLD_HELLO = {"type": "hello", "topics": ["stations", "packets", "tnc", "hf", "config"]}
NEW_HELLO = {"type": "hello", "topics": ["stations", "packets", "tnc", "hf", "radios", "config"]}


def radio_row(id: int, kind: str, type: str, position: int, enabled: bool = True, removed: bool = False, state: str = "connected") -> dict[str, object]:
    """A row of the topic `radios` as breakdown 1.11 names its fields (the ones the scripts read)."""
    return {"id": id, "kind": kind, "type": type, "name": "", "number": 1, "enabled": enabled, "position": position, "removed": removed, "dummy": type.startswith("dummy"), "state": state, "problem": None, "modem": None}


def test_the_scripts_read_the_radios_on_the_wire_the_hello_names_and_refuse_a_daemon_that_names_none() -> None:
    smoke = load_script("smoke.py")
    assert smoke.wire_of(OLD_HELLO) == "tnc" and smoke.wire_of(NEW_HELLO) == "radios"
    with pytest.raises(smoke.Failure, match="tells of no radio"):
        smoke.wire_of({"type": "hello", "topics": ["stations"]})
    old = {"tnc": {"state": "connected"}, "hf": {"state": "waiting"}}
    assert smoke.radio_state(old, "fm") == "connected" and smoke.radio_state(old, "hf") == "waiting" and smoke.radio_state({}, "fm") is None
    new = {"radios": {"1": radio_row(1, "fm", "kiss", 2, state="waiting"), "3": radio_row(3, "fm", "kiss-tcp", 1), "2": radio_row(2, "hf", "mercury", 3, enabled=False),
                      "4": radio_row(4, "hf", "dummy-hf", 4, state="silent"), "5": radio_row(5, "hf", "dummy-hf", 0, removed=True)}, "tnc": {"state": "stopped"}}
    assert smoke.radio_of(new, "fm")["id"] == 3, "the first enabled radio of the kind by position, not radio 1, and not the old topic once `radios` is told"
    assert smoke.radio_state(new, "hf") == "silent", "a radio that is off and a removed one are passed by"
    assert [r["id"] for r in smoke.live_radios(new, "hf")] == [2, 4] and smoke.radio_state({"radios": {}}, "lora") is None
    row = {"call": "OH2X", "heard": {"1": {"count": 3, "last_at": None}, "3": {"count": 2, "last_at": None}, "4": {"count": 5, "last_at": None}}, "heard_fm": 0, "heard_hf": 0}
    assert (smoke.heard_on(new, row, "fm"), smoke.heard_on(new, row, "hf")) == (5, 5), "heard by radio id, counted for the radios of the kind (the new field wins where both are told)"
    assert smoke.heard_on({}, {"call": "OH2X", "heard_fm": 7, "heard_hf": 1}, "hf") == 1
    with pytest.raises(smoke.Failure, match="neither heard"):
        smoke.heard_on(new, {"call": "OH2X"}, "hf")
    assert smoke.heard_on({"stations": {}}, {"call": "OH2X", "heard": {"2": {"count": 4, "last_at": None}}}, "hf") == 0, "a row of the round read before the topic radios has come: nothing counted yet"
    assert smoke.heard_on(new, {"call": "OH2X", "heard": {"9": {"count": 4, "last_at": None}}}, "hf") == 0, "a radio the topic radios does not yet tell"
    assert smoke.modem_state(new, "hf") is None and smoke.modem_state({"hf": {"modem": {"state": "running"}}}, "hf") == "running"
    assert smoke.modem_state({"radios": {"2": {**radio_row(2, "hf", "mercury", 1, enabled=False), "modem": {"state": "starting"}}}}, "hf", 2) == "starting", "by its id, enabled or not"


class FakeDaemonPage:
    """What `smoke.give_radio` and `PageSocket.set_config` see of a daemon, answering their commands at once as the daemon of either wire does: the old one stores the flat keys in `config`; the new one
    adds a radio (`radio_added`), changes it in `radios` and tells `radio/<id>/<key>` in `config`'s `radio_keys_in`: `radio_values` as the round's wire keeps them apart from the form's keys, or `values`
    as breakdown 1.11 words it. A Mercury radio's row gets `modem` (null: no modem came up). A command it is told to refuse is answered with an `error` naming it."""

    def __new__(cls, smoke: ModuleType, hello: dict[str, object], topics: dict[str, object], refuse: str = "", radio_keys_in: str = "radio_values", modem: object = None) -> Any:
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
                    self.topics["radios"][str(id)] = radio_row(id, "hf", str(command["type"]), id, enabled=False, state="stopped")
                    self.messages.append({"type": "radio_added", "id": id})
                elif command["cmd"] == "radio_change":
                    self.topics["radios"][str(command["radio"])].update({k: v for k, v in command.items() if k not in ("cmd", "radio")})
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


def test_a_radio_is_given_by_the_flat_keys_before_the_radios_and_by_the_radio_commands_after() -> None:
    import asyncio
    smoke = load_script("smoke.py")
    old = FakeDaemonPage(smoke, OLD_HELLO, {"config": {"values": {}}})
    asyncio.run(smoke.give_radio(old, "hf", "mercury", {"keying": "vox", "sound_card": ""}, 1))
    assert old.sent == [{"cmd": "set_config", "values": {"hf/enabled": "true", "hf/profile": "mercury", "mercury/keying": "vox", "mercury/sound_card": ""}}]
    for told_in in ("radio_values", "values"):                                          # (the round's wire tells a radio's keys apart from the form's, in radio_values; 1.11 words them as config's values)
        new = FakeDaemonPage(smoke, NEW_HELLO, {"config": {"values": {}, "radio_values": {}}, "radios": {"1": radio_row(1, "fm", "kiss-tcp", 1)}}, radio_keys_in=told_in)
        assert asyncio.run(smoke.give_radio(new, "hf", "mercury", {"keying": "vox", "sound_card": ""}, 1)) == 2
        assert new.sent == [{"cmd": "radio_add", "type": "mercury"}, {"cmd": "radio_change", "radio": 2, "enabled": True},
                            {"cmd": "set_config", "values": {"radio/2/keying": "vox", "radio/2/sound_card": ""}}], "a station with no HF radio is given one; its keys by its id"
        assert new.topics["config"][told_in] == {"radio/2/keying": "vox", "radio/2/sound_card": ""} and new.config()["radio/2/keying"] == "vox", told_in
    there = FakeDaemonPage(smoke, NEW_HELLO, {"config": {"values": {}}, "radios": {"1": radio_row(1, "fm", "kiss", 1), "2": radio_row(2, "hf", "mercury", 2, enabled=False)}})
    asyncio.run(smoke.give_radio(there, "hf", "dummy-hf", {}, 1))
    assert there.sent == [{"cmd": "radio_change", "radio": 2, "type": "dummy-hf", "enabled": True}], "the HF radio there is changed, and nothing more is sent"
    for refused in ("radio_add", "set_config"):
        page = FakeDaemonPage(smoke, NEW_HELLO if refused == "radio_add" else OLD_HELLO, {"config": {"values": {}}, "radios": {}}, refuse=refused)
        with pytest.raises(smoke.Failure, match=f"{refused} was refused: {refused}: no"):
            asyncio.run(smoke.give_radio(page, "hf", "dummy-hf", {}, 1))


def test_the_mercury_shot_waits_for_its_modem_on_the_radio_that_hf_port_names() -> None:
    """settings-hf's daemon is started with --hf-port, which is radio 2's: the Mercury radio given through the page must be radio 2 and its modem `running` before the shot; otherwise its shots are left
    out with the reason (a Failure), never a picture of a Mercury radio with no modem."""
    import asyncio
    shots = load_script("screenshots.py")
    smoke = shots.smoke                                                                 # (the smoke the script imported: its Failure is the one raised)
    running = {"state": "running"}
    for hello, topics in ((NEW_HELLO, {"config": {"values": {}}, "radios": {"1": radio_row(1, "fm", "kiss-tcp", 1)}}), (OLD_HELLO, {"config": {"values": {}}, "hf": {"state": "connected", "modem": running}})):
        asyncio.run(shots.hf_radio_given(FakeDaemonPage(smoke, hello, topics, modem=running), "mercury", {"keying": "vox"}, 1))
    asyncio.run(shots.hf_radio_given(FakeDaemonPage(smoke, NEW_HELLO, {"config": {"values": {}}, "radios": {"1": radio_row(1, "fm", "kiss-tcp", 1)}}), "dummy-hf", {}, 1))                # (no modem waited for)
    with pytest.raises(smoke.Failure, match="the Mercury modem of the HF radio running"):
        asyncio.run(shots.hf_radio_given(FakeDaemonPage(smoke, NEW_HELLO, {"config": {"values": {}}, "radios": {"1": radio_row(1, "fm", "kiss-tcp", 1)}}), "mercury", {}, 1))
    with pytest.raises(smoke.Failure, match="radio 3, and --hf-port names radio 2"):
        asyncio.run(shots.hf_radio_given(FakeDaemonPage(smoke, NEW_HELLO, {"config": {"values": {}}, "radios": {"1": radio_row(1, "fm", "kiss-tcp", 1), "2": radio_row(2, "fm", "kiss", 2)}}, modem=running),
                                         "mercury", {}, 1))


def test_a_run_into_the_site_or_of_everything_refuses_to_draw_the_street_maps_on_the_placeholder(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import asyncio
    shots = load_script("screenshots.py")
    nowhere = str(tmp_path / "no.pmtiles")
    for argv in (["--out", str(tmp_path / "out"), "--basemap", nowhere], ["--only", "map", "--basemap", nowhere]):
        with pytest.raises(SystemExit) as stopped:
            asyncio.run(shots.main(argv))
        assert stopped.value.code == 2 and f"there is no street map at {nowhere}: name one with --basemap FILE" in capsys.readouterr().err, argv
    assert not (tmp_path / "out").exists(), "refused before anything is written"


def png(path: Path, width: int, height: int) -> Path:
    """A file that begins as a PNG of that size does (what the size reader reads)."""
    import struct
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00")
    return path


def test_the_site_declares_each_picture_at_the_size_of_its_file_and_every_shot_has_all_its_files() -> None:
    """The check of `scripts/screenshots.py --check` on the tree: no <img> of site/ at another size than its file (thumbs/chain.png was 681 high in the page and 781 in the file), no dark copy of
    another size in the same box, og.png as og:image:width and height say; and each of the shots its PNG, WebP and both thumbnails, og.png and the README's copies."""
    shots = load_script("screenshots.py")
    assert shots.wrong_sizes(ROOT / "site") == []
    assert shots.missing_files(ROOT / "site" / "shots", ROOT / "docs" / "screenshots") == []
    assert all(shots.image_size(path) == shots.image_size(path.with_suffix(".png")) for path in (ROOT / "site" / "shots").glob("*.webp")), "the WebP header is read as the PNG beside it"


def test_a_picture_declared_at_another_size_is_found_and_written_as_its_file(tmp_path: Path) -> None:
    shots = load_script("screenshots.py")
    png(tmp_path / "shots" / "thumbs" / "chain.png", 640, 781)
    png(tmp_path / "shots" / "thumbs" / "chain-dark.png", 640, 790)
    png(tmp_path / "shots" / "og.png", 1200, 630)
    page = ('<meta property="og:image" content="https://neo.oh2gba.eu/shots/og.png">\n<meta property="og:image:width" content="1200">\n<meta property="og:image:height" content="600">\n'
            '<picture><source srcset="shots/thumbs/chain-dark.png" media="(prefers-color-scheme: dark)"><img src="shots/thumbs/chain.png" width="640" height="681" alt=""></picture>\n<img src="favicon.svg" width="28" height="28">\n')
    (tmp_path / "index.html").write_bytes(page.encode())                 # (with LF, as every system checks the site out: .gitattributes)
    assert shots.wrong_sizes(tmp_path) == ["index.html: shots/thumbs/chain.png is declared 640x681, the file is 640x781", "index.html: shots/thumbs/chain-dark.png is 640x790 in the box of shots/thumbs/chain.png, 640x781",
                                           "index.html: og:image:height says 600, shots/og.png is 630"]
    assert shots.fix_sizes(tmp_path) == ["index.html: shots/thumbs/chain.png 640x681 -> 640x781", "index.html: og:image:height -> 630"]
    fixed = (tmp_path / "index.html").read_bytes().decode()
    assert fixed == page.replace('height="681"', 'height="781"').replace('og:image:height" content="600"', 'og:image:height" content="630"'), "the sizes changed, and nothing else: not the line ends either"
    assert 'src="shots/thumbs/chain.png" width="640" height="781"' in fixed and 'og:image:height" content="630"' in fixed and 'width="28" height="28"' in fixed
    assert shots.wrong_sizes(tmp_path) == ["index.html: shots/thumbs/chain-dark.png is 640x790 in the box of shots/thumbs/chain.png, 640x781"], "the dark file's size is its own: said, never written"
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
    run = shots.Run(taken=["map", "chain"], why_not={"settings-hf": "no Mercury in this checkout: scripts/build-mercury --install", "chain": "failed: TimeoutError: ", "og": "drawn only by a run with everything, --only og or --only map", "thumbs": "no shot taken"})
    png(out / "map.png", 10, 10)                                                         # (written by the run)
    left = shots.leftovers(run, out, docs)
    assert left == {"not asked for (--only)": ["screenshots/weather.png", "shots/map-dark.png"], "no Mercury in this checkout: scripts/build-mercury --install": ["shots/settings-hf.png"],
                    "failed: TimeoutError: ": ["shots/chain.png"], "made by no shot of this script: left as it is": ["shots/old-scene.png"],
                    "drawn only by a run with everything, --only og or --only map": ["shots/og.png"], "no shot taken": ["shots/thumbs/map.png"], "not copied": ["screenshots/map.png"]}
    assert shots.say_what_was_left(run, out, docs) == 2 + 8, "the two shots not taken, and the eight files"
    said = capsys.readouterr().out
    png(out / "thumbs" / "settings-hf.png", 1, 1)                                        # (a copy made by this run from the earlier settings-hf.png: no picture of this run)
    assert shots.leftovers(run, out, docs)["no Mercury in this checkout: scripts/build-mercury --install"] == ["shots/settings-hf.png", "shots/thumbs/settings-hf.png"]
    assert [path.stem for path in shots.thumbs_of(out, None, skip={"settings-hf", "chain"})] == ["map-dark", "map", "old-scene"], "a whole run makes no copies of the shots it did not take"
    assert [path.stem for path in shots.thumbs_of(out, {"map", "chain"})] == ["chain", "map"]
    run.sizes = ["index.html: shots/thumbs/chain-dark.png is 640x790 in the box of shots/thumbs/chain.png, 640x781"]
    assert shots.say_what_was_left(run, out, docs) == 2 + 9 + 1, "a size the site still declares wrongly counts as --check counts it"
    assert "site, at another size (--check fails on it): index.html: shots/thumbs/chain-dark.png" in capsys.readouterr().out
    assert "not taken: settings-hf: no Mercury in this checkout" in said and "not retaken (made by no shot of this script: left as it is): 1 files: shots/old-scene.png" in said and "GitHub's link preview" in said
    assert set(shots.EXTRA_DAEMONS["hf-mercury"]) == {"settings-hf", "settings-hf-dark"} and all(name in shots.SHOTS for names in shots.EXTRA_DAEMONS.values() for name in names)


def test_the_link_preview_names_the_systems_the_site_names() -> None:
    """og.png's pitch names Windows, macOS, Linux and the Raspberry Pi, as the line under the site's name does, and is cut at its words into lines that fit beside the map."""
    shots = load_script("screenshots.py")
    sub = re.search(r'<p class="sub">([^<]+)</p>', (ROOT / "site" / "index.html").read_text(encoding="utf-8"))
    assert sub and all(system in sub.group(1) and system in shots.PITCH for system in ("Windows", "macOS", "Linux", "Raspberry Pi"))
    assert shots.lines_of("a bb ccc dddd", lambda text: len(text) <= 6) == ["a bb", "ccc", "dddd"] and shots.lines_of("toolongword x", lambda text: len(text) <= 4) == ["toolongword", "x"]


def test_the_scripts_that_run_a_daemon_in_their_process_reach_its_radios_by_id_and_name_an_objects_radios() -> None:
    """The day of the screenshots (demoscene) and its folder (screenshots) reach the daemon's radio through the registry, not through the names `ctl.tnc`, `ctl.beacon`, `ctl.hf` that the round's last
    wave deletes; an object of the day is made on the radios `object_set` names (R3 V7). The HF shots give their HF radio through the page: no `db set` of an HF key (refused on a copy of the day)."""
    for name in ("demoscene.py", "screenshots.py"):
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert not re.search(r"\bctl\.(tnc|hf|mercury|beacon|hf_beacon)\b", source), name
    assert "radios=(DEMO_RADIO,)" in (ROOT / "scripts" / "demoscene.py").read_text(encoding="utf-8")
    assert not re.search(r'neoaprs_db_set\([^)]*"(hf|mercury)/', (ROOT / "scripts" / "screenshots.py").read_text(encoding="utf-8"))
