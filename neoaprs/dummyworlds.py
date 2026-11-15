"""The line of each Dummy type, by its profile (`dummy_line`): the made-up world it plays and how it reaches the Tnc. The Dummy radio's and the Dummy HF radio's are the KISS lines of dummyline.py (the HF
one with the modem as the speaker of what we send); the Dummy LoRa radio's is `DummyLoraPort`, a LoRa APRS board of made-up stations (dummylorascene.py) that speaks TNC2 text.

The Dummy LoRa radio's line is what a board does between the air and the computer: each packet of the made-up air is a LoRa packet of text (the header, then `SRC>DST,PATH:information`), the board writes its
text on the line as a line of TNC2, and the line reads that text into a frame (`tnc2line.LineReader`), whose AX.25 encoding, made by us, the Tnc reads as KISS. The frames the Tnc writes are put on the made-up
air as the board would put them, in text with the header (`transmitted`, the latest of them; one longer than a LoRa packet is not sent, as a board cannot), and the scene hears them from there. So TNC2 text is
read and written as on a real board, and the Tnc reads KISS as it does from a board in KISS mode, until it reads text lines of a board itself (lora-plan.md, step L3: then the reading moves into the Tnc's
reader). Each frame is handed over with the reading the scene makes up for it, as a board says the signal of a packet it heard."""
import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from . import ax25, kiss
from .clock import Clock
from .dummyhfscene import STATIONS as CITIES, HfScene
from .dummyline import DummyPort, SceneLike, Speaker
from .dummylorascene import LoraScene, board_air, board_line, calls as lora_calls
from .dummyscene import Scene
from .reading import NO_READING
from .serialport import SerialError
from .tnc2line import LineReader, Tnc2Error, from_air
from .tncport import TncPort
from .tncprofile import DUMMY, DUMMY_HF, DUMMY_LORA, Profile

KEPT_SENT = 50                          # how many of the packets we put on the made-up air are kept to be looked at


class DummyLoraPort(DummyPort):
    def __init__(self, on_data: Callable[[TncPort, bytes], None], on_lost: Callable[[TncPort, str], None], where: Callable[[], tuple[float, float] | None], clock: Clock, tick_sec: float | None = None,
                 seed: int = 1) -> None:
        super().__init__(on_data, on_lost, where, clock, tick_sec, seed, LoraScene)
        self._lines = LineReader()                                    # what reads the board's text lines into frames
        self.transmitted: deque[bytes] = deque(maxlen=KEPT_SENT)      # the LoRa packets of ours on the made-up air, header and text, the latest last

    async def _play(self, scene: SceneLike) -> None:
        while True:
            await asyncio.sleep(self._tick_sec)
            for frame in scene.due(self._clock()):
                reading = scene.reading_of(frame)
                for line in self._lines.feed(board_line(board_air(frame) or b"")):
                    if line.frame is not None:
                        self._reading = reading
                        self._deliver(kiss.encode(ax25.encode(line.frame)))
                        self._reading = NO_READING

    def write(self, data: bytes) -> int:
        """What the Tnc sends, as the board sends it: each KISS data frame put on the made-up air in text with the header, heard there by the scene, and kept in `transmitted`."""
        if self._task is None or self.scene is None:
            raise SerialError("the dummy LoRa radio: not open")
        for kiss_frame in kiss.KissDecoder().feed(data):
            try:
                packet = board_air(ax25.decode(kiss_frame.payload)) if kiss_frame.command == 0 else None
                if packet is not None:
                    self.transmitted.append(packet)
                    self.scene.react(from_air(packet), self._clock())
            except (ax25.Ax25Error, Tnc2Error):
                continue
        return len(data)


class LineOwner(Protocol):
    """What a Dummy line needs of the Tnc it is the line of (tnc.py)."""
    profile: Profile
    radio_id: int
    clock: Clock
    where: Callable[[], tuple[float, float] | None]
    def _on_data(self, port: TncPort, chunk: bytes) -> None: ...
    def _on_lost(self, port: TncPort, reason: str) -> None: ...
    @property
    def modem(self) -> Speaker | None: ...


@dataclass(frozen=True)
class World:
    """A Dummy type's world: its line (a world of its own for each radio, by its id as the seed), what the radio's status line calls it, and the calls it makes its stations up under for a seed (none for the
    Dummy radio's, whose stations are made round the station and go with the daily prune)."""
    line: Callable[[LineOwner], DummyPort]
    words: str
    calls: Callable[[int], frozenset[str]]


_CITY_CALLS = frozenset(station.call for station in CITIES)      # (the Dummy HF radio's stations are the same cities in every world)
WORLDS: dict[str, World] = {        # the world of each Dummy type, by the key of its profile
    DUMMY.key: World(lambda tnc: DummyPort(tnc._on_data, tnc._on_lost, tnc.where, tnc.clock, seed=tnc.radio_id, scene_of=Scene), "dummy radio", lambda _seed: frozenset()),
    DUMMY_HF.key: World(lambda tnc: DummyPort(tnc._on_data, tnc._on_lost, tnc.where, tnc.clock, seed=tnc.radio_id, scene_of=HfScene, speaker=tnc.modem), "dummy HF radio", lambda _seed: _CITY_CALLS),
    DUMMY_LORA.key: World(lambda tnc: DummyLoraPort(tnc._on_data, tnc._on_lost, tnc.where, tnc.clock, seed=tnc.radio_id), "dummy LoRa radio", lora_calls),
}


def dummy_line(tnc: LineOwner) -> DummyPort:
    """The line of the Tnc's Dummy type, not yet open."""
    return WORLDS[tnc.profile.key].line(tnc)


def dummy_words(profile: str) -> str:
    """What the status line of a radio of this Dummy profile calls it: "dummy LoRa radio"."""
    return WORLDS[profile].words


def made_up_calls(profile: str, seed: int) -> frozenset[str]:
    """The calls the world of this profile makes up for the radio of the id `seed`; none for a profile that is no Dummy's."""
    world = WORLDS.get(profile)
    return frozenset() if world is None else world.calls(seed)
