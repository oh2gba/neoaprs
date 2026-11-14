"""What the services that send share: `ConfigSource` (how they read the settings), `transmit_refusal` and `our_call` (why nothing may be sent, and the call we may send under), and the two shapes of the
radios. The new one is services/radioset.py's: `RadioPick` (the radios by id, the enabled ones, the main one, the station's, the one a packet came on) and `AirRadio`, and its `fit` makes every frame of the
sender, our objects and bulletins and the digipeater. `as_pick` gives an old shape as the new one (`OldRadios`: the set of neoaprs/radios.py with the choice by station, by packet and by kind, or one plain
`Radio`, each radio an `OldAir`), so that what app.py gives them today keeps working until the registry is given instead. The old shapes and their choices (`Radio`, `RadioSet`, `radios_on`, `radio_for`,
`radio_to`, `message_radio`, `radio_path`: none on HF) stay for the services that still take them (messaging, the answers, the beacon); `our_frame` and `fit_frame` (the frame shortened to what a radio with a
fixed frame carries: the Mercury HF modem's 123 bytes) are services/radioset.py's, given here under their old names. The rule every service follows: a frame is built for, gated by and sent on *its* radio, the
one the station is reached on or the one the request came on, never "the radio" of a station that has two."""
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any, Protocol, TypeGuard, cast, runtime_checkable

from neoaprs import ax25
from neoaprs.coded import CodedError
from neoaprs.config import Config, can_transmit
from neoaprs.message import EMAIL_GATEWAY, MessagingError
from neoaprs.packet import Packet
from neoaprs.radiorules import RadioRules
from neoaprs.radiospec import log_name
from neoaprs.radiotype import FM_ID, HF_ID, Allowed, Kind, Limits, RadioId, radio_id_of
from neoaprs.radiotypes import kind_field
from neoaprs.radiotypes.common import FM_ALLOWED, HF_ALLOWED
from neoaprs.services.radioset import AirRadio, RadioPick
from neoaprs.services.radioset import FRAME_ERRORS as FRAME_ERRORS, fit_frame as fit_frame, fixed_prefix as fixed_prefix, our_frame as our_frame     # (the parts of the one fit function, under their old names)
from neoaprs.source import Source
from neoaprs.tncwatchdog import TncStats

ConfigSource = Callable[[], Config]


class Radio(Protocol):
    """What the services need of the Tnc."""
    @property
    def state(self) -> Source.State: ...
    @property
    def usable(self) -> bool: ...
    @property
    def max_frame(self) -> int | None: ...
    @property
    def rules(self) -> RadioRules: ...
    def why_unusable(self) -> str: ...
    def send_frame(self, frame: ax25.Frame, raw: bytes | None = None) -> bool: ...


@runtime_checkable
class RadioSet(Radio, Protocol):
    """The radios of the station as a service that answers stations sees them (neoaprs/radios.py): itself the default radio (FM while it is on, else HF), and the choice of the radio a station is reached on, or
    the one a packet came on. A service that never chooses takes a plain Radio."""
    def for_station(self, call: str) -> Radio: ...
    def for_packet(self, packet: Packet) -> Radio: ...
    def of(self, kind: str) -> Radio | None: ...
    @property
    def on(self) -> list[Radio]: ...


def radios_on(radio: Radio) -> list[Radio]:
    """The radios that are on, each to be asked on its own (a gate that asks "the radio" asks the FM one while it is on, and holds what goes over HF when the FM radio is silent at night): the radios of the set that are
    enabled, or the one radio the service was given (a test's stub)."""
    return radio.on if isinstance(radio, RadioSet) else [radio]


def radio_for(radio: Radio, packet: Packet) -> Radio:
    """The radio to answer the packet on: the one it came on when the service was given the radios, else the one radio it was given (a test's stub)."""
    return radio.for_packet(packet) if isinstance(radio, RadioSet) else radio


def radio_to(radio: Radio, call: str) -> Radio:
    """The radio a frame of ours to the station goes out on: by the station when the service was given the radios, else the one radio it was given."""
    return radio.for_station(call) if isinstance(radio, RadioSet) else radio


def message_radio(radio: Radio, to: str) -> Radio:
    """The radio a message of ours to the station goes out on: the station's (`radio_to`); the FM radio for the email gateway, which is a station of the internet reached through the iGates of the VHF network and never
    over HF, so a mail is refused (MessagingError, the code `message.email_fm_off`) while the FM radio is off."""
    if to == EMAIL_GATEWAY and isinstance(radio, RadioSet):
        fm = radio.of("fm")
        if fm is None:
            raise MessagingError("email goes out over the FM radio, which is off", "message.email_fm_off")
        return fm
    return radio_to(radio, to)


def radio_path(radio: Radio, path: tuple[str, ...]) -> tuple[str, ...]:
    """The digipeaters a frame of ours goes by on this radio: the path given where the network has digipeaters (FM), none where every frame is direct (HF: the settings and the stations' own paths are kept for the day the operator is back on VHF, and a path would only cost bytes of the frame).
    The old form of `radioset.path_on`, for the services that still take a Radio."""
    return path if radio.rules.paths else ()


# ---- the old shapes as the new one, until app.py gives the registry

class OldAir:
    """An old Radio (a Tnc, the old set as its default radio, a test's stub) as an AirRadio: its id and kind by its rules' kind (fm 1, hf 2), its limits and what it is allowed from its rules, its own choices
    from the station's radio of that id (the FM radio's where its kind has no such field: the one beacon/path and digi/enabled of today were the station's), its counters its line's (or the ones given)."""

    def __init__(self, radio: Radio, config: ConfigSource, stats: TncStats | None = None) -> None:
        self.radio, self._config = radio, config
        found = stats if stats is not None else getattr(radio, "stats", None)
        self._stats = found if isinstance(found, TncStats) else TncStats()

    @property
    def id(self) -> RadioId:
        return radio_id_of(self.radio.rules.kind) or FM_ID

    @property
    def kind(self) -> Kind:
        return cast(Kind, self.radio.rules.kind)

    @property
    def name(self) -> str:
        config = self._config()
        spec = config.radio(self.id)
        return "" if spec is None else log_name(spec, config.radios)

    @property
    def limits(self) -> Limits:
        r = self.radio.rules
        return Limits(r.max_frame, r.beacon_min_min, r.beacon_jitter_sec, r.retry_jitter_sec)

    @property
    def allowed(self) -> Allowed:
        r = self.radio.rules
        return replace(FM_ALLOWED if r.kind == "fm" else HF_ALLOWED, paths=r.paths, digipeat=r.digipeat, smart_beacon=r.smart_beacon)

    @property
    def stats(self) -> TncStats:
        return self._stats

    @property
    def state(self) -> Source.State:
        return self.radio.state

    @property
    def usable(self) -> bool:
        return self.radio.usable

    @property
    def max_frame(self) -> int | None:
        return self.radio.max_frame

    def why_unusable(self) -> str:
        return self.radio.why_unusable()

    def send_frame(self, frame: ax25.Frame, raw: bytes | None = None) -> bool:
        return self.radio.send_frame(frame, raw)

    def choice(self, key: str) -> Any:
        config = self._config()
        spec = config.radio(self.id)
        if spec is None or kind_field(spec.kind, key) is None:
            spec = config.radio(FM_ID)
        return None if spec is None else spec.value(key)


class OldRadios:
    """The old shapes as a RadioPick: the set of neoaprs/radios.py (its enabled radios, the one of a kind while it is enabled, its default radio as the main one: FM while it is on, else HF, else the FM one
    stopped, as today), or one plain Radio (the digipeater's FM Tnc, a test's stub) that is every choice. Each radio is one OldAir for as long as this lives (the counters of the stats it was given stay its)."""

    def __init__(self, radios: Radio, config: ConfigSource, stats: TncStats | None = None) -> None:
        self._old, self._config, self._stats = radios, config, stats
        self._airs: dict[int, OldAir] = {}

    def _air(self, radio: Radio | None) -> OldAir | None:
        if radio is None:
            return None
        found = self._airs.get(id(radio))                  # (the OldAir keeps the radio it wraps, so the id is never another's)
        if found is None:
            found = self._airs[id(radio)] = OldAir(radio, self._config, self._stats if radio is self._old else None)
        return found

    def _of(self, kind: str) -> OldAir | None:
        if isinstance(self._old, RadioSet):
            return self._air(self._old.of(kind))
        one = self._air(self._old)
        return one if one is not None and one.kind == kind else None

    def get(self, id: RadioId) -> AirRadio | None:
        """The radio of the id (fm 1, hf 2) while it is enabled: the old set knows no other."""
        kind = "fm" if id == FM_ID else "hf" if id == HF_ID else None
        return None if kind is None else self._of(kind)

    def enabled(self) -> Sequence[AirRadio]:
        return [air for radio in (self._old.on if isinstance(self._old, RadioSet) else [self._old]) if (air := self._air(radio)) is not None]

    @property
    def main(self) -> AirRadio | None:
        return self._air(self._old)

    def for_station(self, call: str) -> AirRadio | None:
        return self._air(self._old.for_station(call) if isinstance(self._old, RadioSet) else self._old)

    def for_packet(self, packet: Packet) -> AirRadio | None:
        return self._air(self._old.for_packet(packet) if isinstance(self._old, RadioSet) else self._old)

    def email(self) -> AirRadio | None:
        return self._of("fm")


def is_pick(radios: object) -> TypeGuard[RadioPick]:
    """Whether this is a RadioPick (the registry, a test's), not an old shape: it has the radios by id and the email radio, which no Radio and no old set has."""
    return callable(getattr(radios, "get", None)) and callable(getattr(radios, "email", None))


def as_pick(radios: RadioPick | Radio, config: ConfigSource, stats: TncStats | None = None) -> RadioPick:
    """The radios as a RadioPick: the registry as it is, an old shape as OldRadios (`stats` the counters of one plain Radio, as app.py gives the digipeater the FM Tnc's)."""
    return radios if is_pick(radios) else OldRadios(cast(Radio, radios), config, stats)


RX_ONLY = "RX only: nothing is sent"                                # what a refusal to the page says while station/transmit is off (its code is `transmit.off`)


def transmit_refusal(config: Config, error: type[CodedError] = CodedError) -> CodedError | None:
    """Why nothing may be sent now, as an error of the class given (not raised): receive only (the code `transmit.off`), or the interlock's reason (no call); None when we may send."""
    if not config.station_transmit:
        return error(RX_ONLY, "transmit.off")
    if reason := can_transmit(config):
        return error(reason)
    return None


def our_call(config: Config) -> str:
    """The call we send under; raises MessagingError when nothing may be transmitted (transmit_refusal)."""
    if refusal := transmit_refusal(config, MessagingError):
        raise refusal
    return config.station_call
