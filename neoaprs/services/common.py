"""What the sending services share: settings access, transmit refusal, and the old radio shapes.

`as_pick` adapts an old radio shape to a `RadioPick` (only tests give one). A frame is built for,
gated by and sent on its own radio.
"""
import logging
from collections.abc import Callable, Sequence
from typing import Any, Protocol, TypeIs, runtime_checkable

from neoaprs import ax25
from neoaprs.beaconrule import send_on_radios
from neoaprs.coded import CodedError
from neoaprs.config import Config, can_transmit
from neoaprs.message import MessagingError
from neoaprs.packet import Packet
from neoaprs.radiospec import RadioSpec, log_name
from neoaprs.radiotype import FM_ID, HF_ID, Allowed, Kind, Limits, RadioId, RadioType
from neoaprs.radiotypes import kind_field
from neoaprs.services.radioset import NO_RADIO, AirRadio, RadioPick, first_sender
# Re-exports.
from neoaprs.services.radioset import FRAME_ERRORS as FRAME_ERRORS, fit_frame as fit_frame, fixed_prefix as fixed_prefix, our_frame as our_frame
from neoaprs.source import Source
from neoaprs.tncwatchdog import TncStats

log = logging.getLogger("neoaprs.services")

ConfigSource = Callable[[], Config]
# (call, attempt, radio id) -> digipeaters; PrefBook.path_for.
Paths = Callable[[str, int | None, RadioId], tuple[str, ...]]


class Radio(Protocol):
    """What the services need of the Tnc: its type and its line."""
    @property
    def state(self) -> Source.State: ...
    @property
    def usable(self) -> bool: ...
    @property
    def max_frame(self) -> int | None: ...
    @property
    def rtype(self) -> RadioType: ...
    def why_unusable(self) -> str: ...
    def send_frame(self, frame: ax25.Frame, raw: bytes | None = None) -> bool: ...


@runtime_checkable
class RadioSet(Radio, Protocol):
    """The old set of radios: itself the default (FM if on, else HF), choosable per station."""
    def for_station(self, call: str) -> Radio: ...
    def for_packet(self, packet: Packet) -> Radio: ...
    def of(self, kind: str) -> Radio | None: ...
    @property
    def on(self) -> list[Radio]: ...


def old_id(kind: str) -> RadioId:
    """The id of an old-shape radio of this kind: hf 2, anything else fm 1."""
    return HF_ID if kind == "hf" else FM_ID


def old_spec(config: Config, id: RadioId, key: str | None = None) -> RadioSpec | None:
    """The settings of radio `id`, or radio 1's if it has none (or none with the field `key`)."""
    spec = config.radio(id)
    return spec if spec is not None and (key is None or kind_field(spec.kind, key) is not None) else config.radio(FM_ID)


class OldAir:
    """An old Radio as an AirRadio: id by kind (fm 1, hf 2), choices from the station's radio."""

    def __init__(self, radio: Radio, config: ConfigSource) -> None:
        self.radio, self._config = radio, config
        found = getattr(radio, "stats", None)
        self._stats = found if isinstance(found, TncStats) else TncStats()

    @property
    def rtype(self) -> RadioType:
        return self.radio.rtype

    @property
    def id(self) -> RadioId:
        return old_id(self.kind)

    @property
    def kind(self) -> Kind:
        return self.radio.rtype.kind

    @property
    def name(self) -> str:
        config = self._config()
        spec = config.radio(self.id)
        return "" if spec is None else log_name(spec, config.radios)

    @property
    def limits(self) -> Limits:
        return self.radio.rtype.limits

    @property
    def allowed(self) -> Allowed:
        return self.radio.rtype.allowed

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
        spec = old_spec(self._config(), self.id, key)
        return None if spec is None else spec.value(key)


class OldRadios:
    """An old set of two radios, or one plain Radio, as a RadioPick; each radio is one OldAir."""

    def __init__(self, radios: Radio, config: ConfigSource) -> None:
        self._old, self._config = radios, config
        self._airs: dict[int, OldAir] = {}

    def _air(self, radio: Radio | None) -> OldAir | None:
        if radio is None:
            return None
        found = self._airs.get(id(radio))                  # the OldAir keeps its radio alive, so the id is stable
        if found is None:
            found = self._airs[id(radio)] = OldAir(radio, self._config)
        return found

    def _of(self, kind: str) -> OldAir | None:
        if isinstance(self._old, RadioSet):
            return self._air(self._old.of(kind))
        one = self._air(self._old)
        return one if one is not None and one.kind == kind else None

    def get(self, id: RadioId) -> AirRadio | None:
        """The radio of the id (fm 1, hf 2) while enabled; the old set knows no other."""
        kind = "fm" if id == FM_ID else "hf" if id == HF_ID else None
        return None if kind is None else self._of(kind)

    def enabled(self) -> Sequence[AirRadio]:
        return [air for radio in (self._old.on if isinstance(self._old, RadioSet) else [self._old]) if (air := self._air(radio)) is not None]

    def senders(self) -> Sequence[AirRadio]:
        return self.enabled()                              # old shapes have no receive-only radio

    def for_station(self, call: str) -> AirRadio | None:
        return self._air(self._old.for_station(call) if isinstance(self._old, RadioSet) else self._old)

    def for_packet(self, packet: Packet) -> AirRadio | None:
        return self._air(self._old.for_packet(packet) if isinstance(self._old, RadioSet) else self._old)

    def email(self) -> AirRadio | None:
        """The FM radio while on, else any radio that is on."""
        return self._of("fm") or next(iter(self.enabled()), None)


def is_pick(radios: RadioPick | Radio) -> TypeIs[RadioPick]:
    """Whether this is a RadioPick rather than an old shape (only a pick has `get` and `email`)."""
    return callable(getattr(radios, "get", None)) and callable(getattr(radios, "email", None))


def as_pick(radios: RadioPick | Radio, config: ConfigSource) -> RadioPick:
    """Return `radios` as a RadioPick, wrapping an old shape in OldRadios."""
    return radios if is_pick(radios) else OldRadios(radios, config)


def send_on(radios: RadioPick | Radio, config: ConfigSource, key: str) -> list[AirRadio]:
    """Return the radios whose Send on tick for `key` ("ask" or "local_info") is set, usable or not.

    With an old shape, its one radio. Empty if no radio can send or none is ticked.
    """
    pick = as_pick(radios, config)
    if not is_pick(radios):
        first = first_sender(pick)
        return [] if first is None else [first]
    return [found for id in send_on_radios(key, config().radios) if (found := pick.get(id)) is not None]


def asked_radios(radios: RadioPick | Radio, config: ConfigSource, key: str, radio: RadioId | None = None) -> list[AirRadio]:
    """Return the usable radios with Send on ticked (or `radio`); MessagingError if none."""
    pick = as_pick(radios, config)
    if radio is None:
        ticked = send_on(radios, config, key)
        if not ticked:
            raise MessagingError.of(NO_RADIO)
        usable = [one for one in ticked if one.usable]
        if not usable:
            raise MessagingError.of(ticked[0].why_unusable())
        return usable
    found = next((r for r in pick.enabled() if r.id == radio), None)
    if found is None:
        named = pick.get(radio)
        if named is None:
            raise MessagingError(f"there is no radio {radio}", "radio.unknown", radio=radio)
        raise MessagingError(f"radio {named.name or radio} is off: turn it on first", "radio.off", name=named.name or str(radio), radio=radio)
    if not any(r.id == radio for r in pick.senders()):
        raise MessagingError(f"radio {found.name} only receives: nothing can be sent on it", "radio.receive_only", name=found.name, radio=radio)
    if not found.usable:
        raise MessagingError.of(found.why_unusable())
    return [found]


def sent_on(frames: Sequence[tuple[AirRadio, ax25.Frame]], what: str) -> list[tuple[AirRadio, ax25.Frame]]:
    """Send each radio its frame; return those that took it, else raise MessagingError."""
    went = []
    for radio, frame in frames:
        if radio.send_frame(frame):
            went.append((radio, frame))
        else:
            log.warning("%s: the %s radio did not take the frame", what, radio.name or radio.id)
    if not went:
        raise MessagingError("the TNC did not take the frame", "radio.not_taken")
    return went


def on_words(radio: AirRadio, radios: RadioPick | Radio, config: ConfigSource) -> str:
    """Return " on <name>" for log text while more than one radio is on, else ""."""
    return f" on {radio.name}" if radio.name and len(as_pick(radios, config).enabled()) > 1 else ""


RX_ONLY = "RX only: nothing is sent"                                # refusal text while station/transmit is off


def transmit_refusal(config: Config, error: type[CodedError] = CodedError) -> CodedError | None:
    """Return an `error` (not raised) saying why nothing may be sent now, or None if it may."""
    if not config.station_transmit or config.listens_only:
        return error(RX_ONLY, "transmit.off")
    if reason := can_transmit(config):
        return error.of(reason)
    return None


def our_call(config: Config) -> str:
    """Return the call we send under; raise MessagingError if nothing may be transmitted."""
    if refusal := transmit_refusal(config, MessagingError):
        raise refusal
    return config.station_call
