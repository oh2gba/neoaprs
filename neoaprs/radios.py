"""Radios 1 and 2 as the services of before the radio round see them: the FM radio (slot `fm`) and the HF radio (slot `hf`) as one `RadioSet` (neoaprs/services/common.py), the default radio for a service
that sends to no station in particular (the FM one while it is on, else the HF one), `for_station` for a message of ours and `for_packet` for an ack or an answer, each giving the radio's `Tnc`. The radios
themselves, any number of them, their lifecycle and the operator's choice by station are the registry's (neoaprs/radioregistry.py, `Services.radios`); the composition root gives this view (`Services.radio_set`)
to each service until the service takes the registry, and then it goes, with `hf_is_mercury`, `hf_is_dummy` and `KINDS`, which the page's handlers and the tests still read.

The slots are enabled by the settings `fm/enabled` and `hf/enabled`; a radio that is not enabled is never chosen. The rule of `for_station` is the one of neoaprs/messagerule.py (tests/test_seams.py holds
the two equal). The operator's choice by station (`choose`, `restore`) is the registry's own part (`radioregistry.StationChoices`), which a set made by itself, as the tests make one, keeps for itself."""
from collections.abc import Awaitable, Callable, Iterator

from . import ax25
from .config import Config
from .packet import Packet
from .radioregistry import StationChoices
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


class Radios(StationChoices):
    def __init__(self, fm: Tnc, hf: Tnc, config: Callable[[], Config], book: StationBook, remember: Callable[[str], None] = lambda text: None,
                 flush: Callable[[], Awaitable[None]] | None = None) -> None:
        super().__init__(book, remember, flush)                                   # (the operator's radio by station, as the registry keeps it: `choose`, `forget`, `restore`)
        self.fm, self.hf = fm, hf
        self._config = config

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
