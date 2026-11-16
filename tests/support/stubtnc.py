"""A Tnc that is a stub, for the tests of the parts that send frames by a schedule (services/sender.py and what uses it): a state the test sets, whether it takes a frame, and every frame it was given.

    tnc = StubTnc()
    tnc.state = Source.State.SILENT         # the radio is switched off: `usable` is False
    tnc.held = "the channel is busy"        # connected, but the modem holds its frames (the HF radio while a frame is on the air or the channel is busy): `usable` is False and `why_unusable` says so
    tnc.takes = False                       # it is settling after KISS ON: the write is refused
    tnc.infos()                             # the information fields of the frames it took
    tnc.lines()                             # the same frames as TNC-2 lines ("OH2GBA>APNEO1:text")
    tnc.asked                               # how many times it was asked to send, taken or not
    tnc.raw                                 # the bytes it took with a frame (send_frame's `raw`: the digipeater's), as they were given

    radios = StubRadios(hf_stations=("OH2C",))      # two stubs as one set (the old set of two, as the services still take one): `fm` and `hf`, the FM one the default while it is in `enabled`; a message to a
                                                    # station named in `hf_stations` goes on HF, to any other on FM; a packet is answered on the radio it came on (`Packet.radio_id`)

A StubTnc is a radio of a type (`rtype`: the Mercury modem's when it has a frame cap, else the KISS TNC's, or the one given) and also a radio as the services see one from the radio round on
(neoaprs/services/radioset.AirRadio): its id (1 of the FM kind, 2 of the HF kind, or the one given), its kind, name, limits (its type's, with its own frame cap) and what it is allowed (its type's), its counters,
and the operator's choices on it (`choices`). `HF_WITH_PATHS` is a type of the HF kind that may carry a path, for the tests of a radio with a frame cap and digipeaters. `StubRegistry` is two of them as the choice of a radio the services take then (`RadioPick`), the same
choices as StubRadios:

    pick = StubRegistry(hf_stations=("OH2C",))      # pick.fm (radio 1) and pick.hf (radio 2), both on while their ids are in `on`; `main` the FM one while it is on, else the HF one, else None
"""
from dataclasses import replace
from typing import Any

from neoaprs import ax25
from neoaprs.packet import Packet
from neoaprs.radiospec import FM_ID, HF_ID, KIND_WORDS, RadioId
from neoaprs.radiotype import Allowed, Kind, Limits, RadioType
from neoaprs.radiotypes import type_of
from neoaprs.services.radioset import AirRadio, RadioPick
from neoaprs.source import Source, unusable_because
from neoaprs.tncwatchdog import TncStats


HF_WITH_PATHS = replace(type_of("mercury"), allowed=replace(type_of("mercury").allowed, paths=True))


class StubTnc:
    def __init__(self, state: Source.State = Source.State.CONNECTED, max_frame: int | None = None, rtype: RadioType | None = None, *, id: RadioId | None = None) -> None:
        self.state = state
        self.sent: list[ax25.Frame] = []
        self.raw: list[bytes] = []                  # the bytes given with a frame (the digipeater's), as they were given
        self.takes = True
        self.held = ""                              # why the radio, though connected, takes no frame now ("" when it does): the HF modem transmitting or hearing a busy channel
        self.asked = 0
        self.max_frame = max_frame                  # the longest frame the radio carries (the Mercury HF modem's 123), None for the AX.25 limit alone
        self.rtype = rtype if rtype is not None else type_of("mercury") if max_frame is not None else type_of("kiss")      # its type: the HF radio's when it has a frame cap, else the FM radio's; a test may give another (a frame cap with paths)
        self.id: RadioId = id if id is not None else HF_ID if self.rtype.kind == "hf" else FM_ID      # the radio it stands for: 1 of the FM kind, 2 of the HF kind, unless one is given
        self.stats = TncStats()
        self.choices: dict[str, Any] = {"beacon": True, "path": "", "digipeat": False}              # the operator's choices on the radio (`choice`)

    @property
    def kind(self) -> Kind:
        return self.rtype.kind

    @property
    def name(self) -> str:
        return KIND_WORDS[self.kind]

    @property
    def limits(self) -> Limits:
        return replace(self.rtype.limits, max_frame=self.max_frame)

    @property
    def allowed(self) -> Allowed:
        return self.rtype.allowed

    def choice(self, key: str) -> Any:
        return self.choices[key]

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
        came = {FM_ID: "fm", HF_ID: "hf"}.get(packet.radio_id or 0)
        return (self.of(came) if came is not None else None) or self.default

    state = property(lambda self: self.default.state)
    usable = property(lambda self: self.default.usable)
    max_frame = property(lambda self: self.default.max_frame)
    rtype = property(lambda self: self.default.rtype)

    def why_unusable(self) -> str:
        return self.default.why_unusable()

    def send_frame(self, frame: ax25.Frame, raw: bytes | None = None) -> bool:
        return self.default.send_frame(frame, raw)


class StubRegistry:
    """Two stubs as the one `RadioPick` of the services (neoaprs/services/radioset.py): radio 1, the FM radio, and radio 2, the HF radio (its frame cap `hf_max_frame`), each on while its id is in `on`; the radio of a
    call no radio heard the FM one while it is on, else the HF one, else none; the choice by station (`hf_stations` go on HF while both are on) and by packet (the radio it came on while it is on, else none, a packet made without a radio too); an email goes on the FM radio
    while it is on, else on the one radio that is."""

    def __init__(self, hf_stations: tuple[str, ...] = (), hf_max_frame: int = 123) -> None:
        self.fm, self.hf = StubTnc(), StubTnc(max_frame=hf_max_frame)
        self.on: set[RadioId] = {FM_ID, HF_ID}
        self.hf_stations = hf_stations

    def get(self, id: RadioId) -> StubTnc | None:
        return {FM_ID: self.fm, HF_ID: self.hf}.get(id)

    def enabled(self) -> list[StubTnc]:
        return [radio for radio in (self.fm, self.hf) if radio.id in self.on]

    def senders(self) -> list[StubTnc]:
        return self.enabled()                    # (both stubs can send)

    @property
    def main(self) -> StubTnc | None:
        return next(iter(self.enabled()), None)

    def for_station(self, call: str) -> StubTnc | None:
        return self.hf if len(self.on) == 2 and call in self.hf_stations else self.main

    def for_packet(self, packet: Packet) -> StubTnc | None:
        came = self.get(packet.radio_id) if packet.radio_id is not None else None
        return came if came is not None and came.id in self.on else None

    def email(self) -> StubTnc | None:
        return self.fm if FM_ID in self.on else self.main


def as_air(radio: StubTnc) -> AirRadio:
    return radio


def as_pick(registry: StubRegistry) -> RadioPick:
    return registry
