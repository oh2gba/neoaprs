"""The modems of the Sound card and Mercury radios on a sound server's devices: looked up before every
start, opened by our ALSA names, and ended when a stream strays (neoaprs/soundwatch.py). pactl is a
stand-in that answers with pactl's own JSON (tests/fixtures/pactl), the modems the made-up ones."""

import copy
import json
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs import direwolfmodem, soundserver, soundwatch
from neoaprs.claims import Claims
from neoaprs.direwolf import CONF_FILE
from neoaprs.mercuryclaims import card_claims
from neoaprs.soundserver import Node
from tests.support.env import until, until_started
from tests.support.files import fixture_text
from tests.support.modemports import base_of_this_test, own_ports
from tests.test_direwolf_modem import modem as direwolf_modem
from tests.test_mercury_modem import HF, modem as mercury_modem

SOURCE, SINK = "pulse:DEVICE=quad_in", "pulse:DEVICE=Radio_remap"
SETTING = f"{SOURCE}|{SINK}"
RADIO_NULL, QUAD_IN = 52, 82
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
        if part in ("sinks", "sources"):
            return json.dumps([e for e in self._entries(part) if e["name"] not in self.gone])
        field, at = ("sink", 0) if part == "sink-inputs" else ("source", 1)
        return json.dumps([self._stream(part, field, pid, on[at]) for pid, on in self.streams.items()])


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
    await m.start(f"{SOURCE},CHANNEL=rear-right|{SINK}", "vox", 0)
    await until_started(lambda: m.state == "running")
    conf = (m.home / CONF_FILE).read_text(encoding="utf-8")
    assert "ADEVICE neoaprs_pulse_ch3:DEVICE=quad_in,CHANNELS=4 neoaprs_pulse:DEVICE=Radio_remap\n" in conf
    await m.stop()


async def test_direwolf_whose_stream_plays_on_another_device_is_ended(tmp_path: Path, server: Server) -> None:
    m = direwolf_modem(tmp_path)
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
    started: list[list[str]] = []
    start = m._program.start
    m._program.start = lambda argv, cwd, pid_file=None: (started.append(argv), start(argv, cwd, pid_file))[1]  # type: ignore[method-assign]
    await m.start(replace(HF, mercury_sound_card=SETTING))
    await until_started(lambda: m.state == "running")
    argv = started[-1]
    assert argv[argv.index("-i") + 1] == "neoaprs_pulse:DEVICE=quad_in"
    assert argv[argv.index("-o") + 1] == "neoaprs_pulse:DEVICE=Radio_remap"
    pid = m.pid
    server.gone.add("Radio_remap")
    await until(lambda: m.reason == "sound_card")
    assert m.pid != pid
    await m.stop()


async def test_an_alsa_card_starts_as_before_and_asks_the_server_nothing(tmp_path: Path, server: Server) -> None:
    m = direwolf_modem(tmp_path)
    await m.start("plughw:1,0", "vox", 0)
    await until_started(lambda: m.state == "running")
    assert server.asked == 0
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
