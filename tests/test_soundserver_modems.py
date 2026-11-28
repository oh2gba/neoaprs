"""The modems of the Sound card and Mercury radios on a sound server's devices: looked up before every
start, opened by our ALSA names, and ended when a stream strays (neoaprs/soundwatch.py). pactl is a
stand-in that answers with pactl's own JSON (tests/fixtures/pactl), the modems the made-up ones."""

import copy
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from neoaprs import direwolfmodem, mercuryclaims, soundserver, soundwatch
from neoaprs.claims import Claims
from neoaprs.direwolf import CONF_FILE
from neoaprs.direwolfmodem import levels_card
from neoaprs.mercuryclaims import card_claims
from neoaprs.soundserver import Node
from tests.support.env import until, until_started
from tests.support.files import fixture_text
from tests.support.modemports import base_of_this_test, own_ports
from tests.test_direwolf_modem import modem as direwolf_modem
from tests.test_mercury_modem import HF, modem as mercury_modem

SOURCE, SINK = "pulse:DEVICE=quad_in", "pulse:DEVICE=Radio_remap"
SETTING = f"{SOURCE}|{SINK}"
RADIO_NULL, RADIO_REMAP, QUAD_IN = 52, 60, 82
# a sound server is looked up on Linux only
pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="Linux only"
)  # the indexes of the fixture's Radio_null sink and quad_in source


class Server:
    """pactl of a server with the fixture's devices; `streams[pid]` puts the process's two streams on a sink and a source."""

    def __init__(self) -> None:
        self.streams: dict[int, tuple[int, int]] = {}
        self.gone: set[str] = set()
        self.asked = 0
        self.down = False
        self.placed: list[Callable[[], int | None]] = []  # modems whose streams sit on SETTING's devices

    def place(self, modem: Any) -> None:
        self.placed.append(lambda: modem.pid)

    def _entries(self, part: str) -> list[dict[str, object]]:
        return list(json.loads(fixture_text(f"pactl/virtual-{part}.json")))

    def _stream(self, part: str, field: str, pid: int, index: int) -> dict[str, object]:
        real = copy.deepcopy(next(e for e in self._entries(part) if "application.process.id" in e["properties"]))
        real[field] = index
        real["properties"]["application.process.id"] = str(pid)
        return real

    def __call__(self, args: Sequence[str]) -> str | None:
        self.asked += 1
        part = args[1]
        if self.down:
            return None
        if part == "clients":
            return "[]"  # (the streams of the fixture carry their process's id themselves)
        if part in ("sinks", "sources"):
            return json.dumps([e for e in self._entries(part) if e["name"] not in self.gone])
        field, at = ("sink", 0) if part == "sink-inputs" else ("source", 1)
        streams = {pid: (RADIO_REMAP, QUAD_IN) for pid in (p() for p in self.placed) if pid is not None}
        streams.update(self.streams)
        return json.dumps([self._stream(part, field, pid, on[at]) for pid, on in streams.items()])


@pytest.fixture(autouse=True)
def _ports_of_this_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """The modems' ports from this test's own base (tests/support/modemports.py)."""
    monkeypatch.setattr(direwolfmodem, "FIRST_PORT", base_of_this_test())
    own_ports(monkeypatch)


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> Server:
    fake = Server()
    monkeypatch.setattr(soundserver, "pactl", fake)
    monkeypatch.setattr(soundwatch, "WATCH_SEC", 0.05)
    monkeypatch.setattr(soundwatch, "FIRST_WATCH_SEC", 0.05)
    return fake


async def test_direwolf_on_a_device_the_server_does_not_list_is_not_started_and_shows_the_sound_card_state(
    tmp_path: Path, server: Server
) -> None:
    server.gone.add("Radio_remap")
    m = direwolf_modem(tmp_path)
    await m.start(SETTING, "vox", 0)
    await until(lambda: m.reason == "sound_card")
    assert m.state == "waiting" and m.pid is None and m.starts == 0
    await m.stop()


async def test_direwolf_opens_the_named_devices_by_our_alsa_names(tmp_path: Path, server: Server) -> None:
    m = direwolf_modem(tmp_path)
    server.place(m)
    await m.start(f"{SOURCE},CHANNEL=rear-right|{SINK}", "vox", 0)
    await until_started(lambda: m.state == "running")
    conf = (m.home / CONF_FILE).read_text(encoding="utf-8")
    assert m._program.system_sound, "on the system's ALSA library, for whose version its plug-ins are built"
    assert "ADEVICE neoaprs_pa_ch3:82,4 neoaprs_pa:60\n" in conf
    await m.stop()


async def test_direwolf_whose_stream_plays_on_another_device_is_ended(tmp_path: Path, server: Server) -> None:
    m = direwolf_modem(tmp_path)
    server.place(m)
    await m.start(SETTING, "vox", 0)
    await until_started(lambda: m.state == "running")
    pid = m.pid
    assert pid is not None
    server.streams[pid] = (RADIO_NULL, QUAD_IN)  # the sink is not the one named: the default, say
    await until(lambda: m.reason == "sound_card")
    assert m.pid != pid
    await m.stop()


async def test_mercury_on_a_device_the_server_does_not_list_is_not_started(tmp_path: Path, server: Server) -> None:
    server.gone.add("quad_in")
    m = mercury_modem(tmp_path)
    await m.start(replace(HF, mercury_sound_card=SETTING))
    await until(lambda: m.reason == "sound_card")
    assert m.state == "waiting" and m.pid is None and m.starts == 0
    await m.stop()


async def test_mercury_is_given_our_alsa_names_and_ended_when_its_device_goes(tmp_path: Path, server: Server) -> None:
    m = mercury_modem(tmp_path)
    server.place(m)
    started: list[list[str]] = []
    start = m._program.start
    m._program.start = lambda argv, cwd, pid_file=None: (started.append(argv), start(argv, cwd, pid_file))[1]  # type: ignore[method-assign]
    await m.start(replace(HF, mercury_sound_card=SETTING))
    await until_started(lambda: m.state == "running")
    argv = started[-1]
    assert argv[argv.index("-i") + 1] == "neoaprs_pa:82"
    assert argv[argv.index("-o") + 1] == "neoaprs_pa:60"
    pid = m.pid
    server.gone.add("Radio_remap")
    await until(lambda: m.reason == "sound_card")
    assert m.pid != pid
    await m.stop()


@pytest.mark.parametrize("fault", ["no stream", "no answer"])
async def test_a_run_whose_streams_are_not_seen_for_ten_rounds_is_the_radios_sound_card_problem(
    tmp_path: Path, server: Server, fault: str
) -> None:
    m = direwolf_modem(tmp_path)
    server.place(m)
    await m.start(SETTING, "vox", 0)
    await until_started(lambda: m.state == "running")
    pid, asked = m.pid, server.asked
    await until(lambda: server.asked >= asked + 3 * 5)
    assert m.pid == pid and m.state == "running", "in place, the run goes on"
    if fault == "no stream":
        server.placed.clear()
    else:
        server.down = True
    await until(lambda: m.reason == "sound_card")
    assert m.pid != pid
    await m.stop()


def test_the_watch_looks_often_in_the_first_ten_seconds_of_a_run_and_then_every_two() -> None:
    assert [soundwatch.watch_pause(t) for t in (0.0, 9.9, 10.0, 600.0)] == [0.5, 0.5, 2.0, 2.0]
    assert soundwatch.UNSEEN_ROUNDS == 10


async def test_a_device_gone_after_the_look_up_is_the_sound_card_problem_and_no_start(
    tmp_path: Path, server: Server, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The look-up passed (the setting read then named a device that was there) and the listing the
    start uses lacks the device: never its raw name to the modem, which would play on the default."""
    monkeypatch.setattr(soundwatch, "missing", lambda setting, nodes: "")
    server.gone.add("Radio_remap")
    dw, hf = direwolf_modem(tmp_path / "dw"), mercury_modem(tmp_path / "hf")
    await dw.start(SETTING, "vox", 0)
    await hf.start(replace(HF, mercury_sound_card=SETTING))
    await until(lambda: dw.reason == "sound_card" and hf.reason == "sound_card")
    assert dw.starts == hf.starts == 0 and dw.pid is None and hf.pid is None
    await dw.stop()
    await hf.stop()


async def test_an_alsa_card_starts_as_before_and_asks_the_server_nothing(tmp_path: Path, server: Server) -> None:
    m = direwolf_modem(tmp_path)
    await m.start("plughw:1,0", "vox", 0)
    await until_started(lambda: m.state == "running")
    assert server.asked == 0 and not m._program.system_sound
    await m.stop()


def test_a_device_on_a_card_is_claimed_as_the_card_and_one_a_user_made_by_its_name() -> None:
    nodes = soundserver.list_nodes(lambda args: fixture_text(f"pactl/station-{args[1]}.json"))
    assert nodes is not None
    sink = "pulse:DEVICE=alsa_output.usb-BurrBrown_from_Texas_Instruments_USB_AUDIO_CODEC-00.analog-stereo"
    claims = Claims()
    for claim in card_claims(f"plughw:CARD=X,DEV=0|{sink}", 3, nodes, {0: "CODEC"}):
        assert claims.hold(claim) is None
    assert claims.holder_of("sound_card", "plughw:CARD=CODEC,DEV=0") == 3, "the FM radio's card is this one"
    virtual: list[Node] = soundserver.list_nodes(lambda args: fixture_text(f"pactl/virtual-{args[1]}.json")) or []
    assert [c.value for c in card_claims(SETTING, 3, virtual, {})] == [SOURCE, SINK]


def test_the_levels_and_the_usb_tie_of_a_device_on_a_card_are_that_cards_and_a_made_ones_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    station = soundserver.list_nodes(lambda args: fixture_text(f"pactl/station-{args[1]}.json")) or []
    virtual = soundserver.list_nodes(lambda args: fixture_text(f"pactl/virtual-{args[1]}.json")) or []
    for module in (soundwatch, mercuryclaims):
        monkeypatch.setattr(module, "alsa_card_names", lambda: {0: "CODEC"})
    codec = "BurrBrown_from_Texas_Instruments_USB_AUDIO_CODEC-00.analog-stereo"
    pair = f"pulse:DEVICE=alsa_input.usb-{codec}|pulse:DEVICE=alsa_output.usb-{codec}"
    dw, hf = direwolf_modem(tmp_path), mercury_modem(tmp_path)
    for m in (dw, hf):
        m.sound_card, m.nodes = pair, tuple(station)
        assert m.claims is not None
        for claim in card_claims(pair, m.holder, station, {0: "CODEC"}):
            m.claims.hold(claim)
        assert m._behind() == "plughw:CARD=CODEC,DEV=0", "the card's mixer and its place on the USB"
    assert levels_card(dw) == hf.held_card() == "plughw:CARD=CODEC,DEV=0"
    dw.sound_card, dw.nodes = SETTING, tuple(virtual)
    assert dw._behind() == "" and levels_card(dw) == "", "a device a user made: no levels row, no tie"
