"""A Tnc that is a stub, for the tests of the parts that send frames by a schedule (services/sender.py and what uses it): a state the test sets, whether it takes a frame, and every frame it was given.

    tnc = StubTnc()
    tnc.state = Source.State.SILENT         # the radio is switched off: `usable` is False
    tnc.held = "the channel is busy"        # connected, but the modem holds its frames (the HF radio while a frame is on the air or the channel is busy): `usable` is False and `why_unusable` says so
    tnc.takes = False                       # it is settling after KISS ON: the write is refused
    tnc.infos()                             # the information fields of the frames it took
    tnc.lines()                             # the same frames as TNC-2 lines ("OH2GBA>APNEO1:text")
    tnc.asked                               # how many times it was asked to send, taken or not
    tnc.raw                                 # the bytes it took with a frame (send_frame's `raw`: the digipeater's), as they were given

    radios = StubRadios(hf_stations=("OH2C",))      # two stubs as one set (neoaprs/radios.py as the services see it): `fm` and `hf`, the FM one the default while it is in `enabled`; a message to a station
                                                    # named in `hf_stations` goes on HF, to any other on FM; a packet is answered on the radio it came on (`Packet.radio`)
"""
from neoaprs import ax25
from neoaprs.packet import Packet
from neoaprs.radiorules import FM, HF, RadioRules
from neoaprs.source import Source, unusable_because


class StubTnc:
    def __init__(self, state: Source.State = Source.State.CONNECTED, max_frame: int | None = None, rules: RadioRules | None = None) -> None:
        self.state = state
        self.sent: list[ax25.Frame] = []
        self.raw: list[bytes] = []                  # the bytes given with a frame (the digipeater's), as they were given
        self.takes = True
        self.held = ""                              # why the radio, though connected, takes no frame now ("" when it does): the HF modem transmitting or hearing a busy channel
        self.asked = 0
        self.max_frame = max_frame                  # the longest frame the radio carries (the Mercury HF modem's 123), None for the AX.25 limit alone
        self.rules = rules if rules is not None else HF if max_frame is not None else FM         # the rules of the kind of radio: the HF radio's when it has a frame cap, else the FM radio's; a test may give others (a frame cap with paths)

    @property
    def usable(self) -> bool:
        return self.state is Source.State.CONNECTED and not self.held

    def why_unusable(self) -> str:
        return self.held if self.state is Source.State.CONNECTED else unusable_because(self.state)

    def send_frame(self, frame: ax25.Frame, raw: bytes | None = None) -> bool:
        self.asked += 1
        if self.takes:
            self.sent.append(frame)
            if raw is not None:
                assert ax25.decode(raw) == frame, "the bytes are the frame's"
                self.raw.append(raw)
        return self.takes

    def infos(self) -> list[bytes]:
        return [f.info for f in self.sent]

    def lines(self) -> list[str]:
        return [f.tnc2() for f in self.sent]


class StubRadios:
    """Two stubs as the one `RadioSet` of the services: the FM radio and the HF radio (its frame cap `hf_max_frame`), the default the FM one while it is enabled, the choice by station (`hf_stations` go on HF) and by
    packet (the radio it came on)."""

    def __init__(self, hf_stations: tuple[str, ...] = (), hf_max_frame: int = 123) -> None:
        self.fm, self.hf = StubTnc(), StubTnc(max_frame=hf_max_frame)
        self.enabled = {"fm", "hf"}
        self.hf_stations = hf_stations

    def of(self, kind: str) -> StubTnc | None:
        return {"fm": self.fm, "hf": self.hf}.get(kind) if kind in self.enabled else None

    @property
    def on(self) -> list[StubTnc]:
        return [radio for kind in ("fm", "hf") if (radio := self.of(kind)) is not None]

    @property
    def default(self) -> StubTnc:
        return self.of("fm") or self.of("hf") or self.fm

    def for_station(self, call: str) -> StubTnc:
        hf = self.of("hf")
        return hf if hf is not None and self.of("fm") is not None and call in self.hf_stations else self.default

    def for_packet(self, packet: Packet) -> StubTnc:
        return self.of(packet.radio) or self.default

    state = property(lambda self: self.default.state)
    usable = property(lambda self: self.default.usable)
    max_frame = property(lambda self: self.default.max_frame)
    rules = property(lambda self: self.default.rules)

    def why_unusable(self) -> str:
        return self.default.why_unusable()

    def send_frame(self, frame: ax25.Frame, raw: bytes | None = None) -> bool:
        return self.default.send_frame(frame, raw)
