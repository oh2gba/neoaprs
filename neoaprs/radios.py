"""The radios of the station, at most one of each kind: the FM radio (the KISS TNC of today, slot `fm`) and the HF radio (the Mercury modem, slot `hf`), each a `Tnc` of its own with the rules of its kind
(neoaprs/radiorules.py), and the one place that chooses between them. A service that sends to no station in particular (asking around, our objects and bulletins, the status) takes this object as the one `Radio` it
always took: it is the **default radio**, the FM one while it is on, else the HF one. A service that answers a station takes the radio the station is reached on: `for_station` for a message of ours (FM when the
station was heard on FM, or never on HF alone: it is near, and HF airtime is everyone's; HF when it was heard on HF alone, or the FM radio is off), `for_packet` for an ack or an answer (the radio the packet came
on). While the HF radio is not enabled every choice falls to the FM radio and nothing differs from a station with one radio; a third kind (a LoRa board) is one more slot here and nothing in the services.

The slots are enabled by the settings `fm/enabled` and `hf/enabled`; a radio that is not enabled stays stopped (the controller starts and stops each on its own settings) and is never chosen. Both `Tnc` objects
always exist, so that the page's topics and the tests have them whatever the settings."""
import json
from collections.abc import Awaitable, Callable, Iterator

from . import ax25
from .config import Config
from .packet import Packet
from .radiorules import RadioRules
from .source import Source
from .stationbook import StationBook
from .tnc import Tnc
from .tncprofile import hf_profile_of

KINDS = ("fm", "hf")                     # the slots, in the order a choice falls to them


def hf_is_mercury(config: Config) -> bool:
    """Whether the HF radio, if it is on, is the Mercury modem (the program is started for it, the sound cards are listed, Tune is offered); false while it is off or the Dummy HF radio."""
    return config.hf_enabled and hf_profile_of(config.hf_profile).transport == "modem"


def hf_is_dummy(config: Config) -> bool:
    """Whether the HF radio is on as the Dummy HF radio, which makes up distant stations (dummyhfscene.py) and sends nothing on any air."""
    return config.hf_enabled and hf_profile_of(config.hf_profile).transport == "dummy"


class Radios:
    def __init__(self, fm: Tnc, hf: Tnc, config: Callable[[], Config], book: StationBook, remember: Callable[[str], None] = lambda text: None,
                 flush: Callable[[], Awaitable[None]] | None = None) -> None:
        self.fm, self.hf = fm, hf
        self._config = config
        self._book = book
        self._remember, self._wait_written = remember, flush                     # keep the operator's choices of a radio by station (the state row MESSAGE_RADIOS: the composition root writes it), and wait for it

    def __iter__(self) -> Iterator[Tnc]:
        """Every radio, enabled or not (the page's topics, the wiring of the packets: a radio that is off emits nothing)."""
        yield self.fm
        yield self.hf

    def enabled(self, kind: str) -> bool:
        c = self._config()
        return c.fm_enabled if kind == "fm" else c.hf_enabled if kind == "hf" else False

    def of(self, kind: str) -> Tnc | None:
        """The radio of this kind while it is enabled; None otherwise (and for a kind that is no slot)."""
        if not self.enabled(kind):
            return None
        return self.fm if kind == "fm" else self.hf

    @property
    def on(self) -> list[Tnc]:
        """The radios that are enabled, FM first."""
        return [radio for kind in KINDS if (radio := self.of(kind)) is not None]

    @property
    def default(self) -> Tnc:
        """The radio of what addresses no station in particular: the FM radio while it is on, else the HF one; the FM one (stopped) when neither is, so that there is always a radio to ask."""
        return self.of("fm") or self.of("hf") or self.fm

    def for_station(self, call: str) -> Tnc:
        """The radio a message of ours to the station goes out on: the one the operator chose for it (`choose`), else the FM radio unless the station was heard on HF alone (or FM is off); a station never
        heard goes on the default radio. Every attempt of a message asks again, so a choice made between two attempts holds for the next."""
        fm, hf = self.of("fm"), self.of("hf")
        if fm is None or hf is None:
            return self.default
        station = self._book.get(call)
        if station is not None and station.message_radio in KINDS:
            return fm if station.message_radio == "fm" else hf
        return hf if station is not None and station.heard_hf > 0 and station.heard_fm == 0 else fm

    def choose(self, call: str, kind: str) -> bool:
        """The radio messages to the station go out on from now on (`fm`, `hf`; "" gives the choice back to the daemon), told to the page with the station and kept across a restart; False for a station
        that is not in the book."""
        station = self._book.get(call)
        if station is None or (kind and kind not in KINDS):
            return False
        station.message_radio = kind
        self._book.changed.emit(station)
        self._remember(self.choices_text())
        return True

    def choices_text(self) -> str:
        """The choices of the stations in the book, as the state row keeps them."""
        return json.dumps({s.call: s.message_radio for s in self._book.stations() if s.message_radio}, sort_keys=True)

    async def flush(self) -> None:
        """Waits until a choice being written is written (the stop)."""
        if self._wait_written is not None:
            await self._wait_written()

    def restore(self, text: str | None) -> None:
        """The choices kept in the state row, on the stations of the book (at the start, once the book is seeded); a row that is not one is no choice."""
        try:
            kept = json.loads(text or "{}")
        except ValueError:
            return
        for call, kind in (kept.items() if isinstance(kept, dict) else ()):
            station = self._book.get(str(call))
            if station is not None and kind in KINDS:
                station.message_radio = kind

    def for_packet(self, packet: Packet) -> Tnc:
        """The radio to answer a packet on: the one it came on, while it is enabled; else the default. A packet from the internet is answered by nothing (`Packet.on_air` is false), and asking is a fault."""
        if not packet.on_air:
            raise ValueError("a packet from the internet is answered on no radio")
        return self.of(packet.radio) or self.default

    # ---- the default radio as the one Radio of the services that choose none
    @property
    def state(self) -> Source.State:
        return self.default.state

    @property
    def usable(self) -> bool:
        return self.default.usable

    @property
    def max_frame(self) -> int | None:
        return self.default.max_frame

    @property
    def rules(self) -> RadioRules:
        return self.default.rules

    def why_unusable(self) -> str:
        return self.default.why_unusable()

    def send_frame(self, frame: ax25.Frame, raw: bytes | None = None) -> bool:
        return self.default.send_frame(frame, raw)
