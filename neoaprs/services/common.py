"""What the services that send share: `ConfigSource` (how they read the settings), `transmit_refusal` and `our_call` (why nothing may be sent, and the call we may send under), and the two shapes of the
radios. The new one is services/radioset.py's: `RadioPick` (the radios by id, the enabled ones, the main one, the station's, the one a packet came on) and `AirRadio`, and its `fit` makes every frame of the
sender, our objects and bulletins and the digipeater. `as_pick` gives an old shape as the new one (`OldRadios`: an old set of two radios with the choice by station, by packet and by kind, or one plain
`Radio`, each radio an `OldAir`): app.py gives every service the registry, and the old shapes come only from the tests (tests/support/rig.py, the cases of the old set). The old shapes and their choice of
a message's radio (`Radio`, `RadioSet`, `radio_to`, `message_radio`) stay while the tests give old shapes (no service calls `radio_to` or `message_radio`: the refusal of the latter is one of the texts of
`message.email_fm_off` in the page's list of refusals, which this cut does not change); `our_frame` and `fit_frame` (the frame
shortened to what a radio with a fixed frame carries: the Mercury HF modem's 123 bytes) are services/radioset.py's, given here under their old names. The rule every service follows: a frame is built for,
gated by and sent on *its* radio, the one the station is reached on or the one the request came on, never "the radio" of a station that has two."""
from collections.abc import Callable, Sequence
from typing import Any, Protocol, TypeGuard, cast, runtime_checkable

from neoaprs import ax25
from neoaprs.coded import CodedError
from neoaprs.config import Config, can_transmit
from neoaprs.message import EMAIL_GATEWAY, MessagingError
from neoaprs.packet import Packet
from neoaprs.radiospec import log_name
from neoaprs.radiotype import FM_ID, HF_ID, Allowed, Kind, Limits, RadioId, RadioType
from neoaprs.radiotypes import kind_field
from neoaprs.services.radioset import NO_RADIO, AirRadio, RadioPick
from neoaprs.services.radioset import FRAME_ERRORS as FRAME_ERRORS, fit_frame as fit_frame, fixed_prefix as fixed_prefix, our_frame as our_frame     # (the parts of the one fit function, under their old names)
from neoaprs.source import Source
from neoaprs.tncwatchdog import TncStats

ConfigSource = Callable[[], Config]
Paths = Callable[[str, int | None, RadioId], tuple[str, ...]]       # the digipeaters of what we send to a station on a radio (PrefBook.path_for: the call, the attempt, the radio's id)


class Radio(Protocol):
    """What the services need of the Tnc: its type (its kind, its limits, what it is allowed) and its line."""
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
    """The radios of the station as a service that answers stations saw them before the registry (a test's set of two, tests/support/stubtnc.py): itself the default radio (FM while it is on, else HF), and the choice of the radio a station is reached on, or
    the one a packet came on. A service that never chooses takes a plain Radio."""
    def for_station(self, call: str) -> Radio: ...
    def for_packet(self, packet: Packet) -> Radio: ...
    def of(self, kind: str) -> Radio | None: ...
    @property
    def on(self) -> list[Radio]: ...


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


# ---- the old shapes as the new one, for the tests that still give one

class OldAir:
    """An old Radio (a Tnc, the old set as its default radio, a test's stub) as an AirRadio: its id by its type's kind (fm 1, hf 2), its kind, its limits and what it is allowed its type's, its own choices
    from the station's radio of that id (the FM radio's where its kind has no such field: the one beacon/path and digi/enabled of today were the station's), its counters its line's."""

    def __init__(self, radio: Radio, config: ConfigSource) -> None:
        self.radio, self._config = radio, config
        found = getattr(radio, "stats", None)
        self._stats = found if isinstance(found, TncStats) else TncStats()

    @property
    def rtype(self) -> RadioType:
        return self.radio.rtype

    @property
    def id(self) -> RadioId:
        return HF_ID if self.kind == "hf" else FM_ID

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
        config = self._config()
        spec = config.radio(self.id)
        if spec is None or kind_field(spec.kind, key) is None:
            spec = config.radio(FM_ID)
        return None if spec is None else spec.value(key)


class OldRadios:
    """The old shapes as a RadioPick: an old set of two (its enabled radios, the one of a kind while it is enabled, its default radio as the main one: FM while it is on, else HF, else the FM one
    stopped, as today), or one plain Radio (a test's stub) that is every choice. Each radio is one OldAir for as long as this lives."""

    def __init__(self, radios: Radio, config: ConfigSource) -> None:
        self._old, self._config = radios, config
        self._airs: dict[int, OldAir] = {}

    def _air(self, radio: Radio | None) -> OldAir | None:
        if radio is None:
            return None
        found = self._airs.get(id(radio))                  # (the OldAir keeps the radio it wraps, so the id is never another's)
        if found is None:
            found = self._airs[id(radio)] = OldAir(radio, self._config)
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

    def senders(self) -> Sequence[AirRadio]:
        return self.enabled()                              # (the old shapes know no radio that cannot send)

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


def as_pick(radios: RadioPick | Radio, config: ConfigSource) -> RadioPick:
    """The radios as a RadioPick: the registry as it is, an old shape as OldRadios."""
    return radios if is_pick(radios) else OldRadios(cast(Radio, radios), config)


def asked_radio(radios: RadioPick | Radio, config: ConfigSource, radio: RadioId | None = None) -> AirRadio:
    """The radio a request of the operator's to no station in particular goes on (asking around, asking QRU: plan rule 3.6): the one named, else the main radio. MessagingError while there is none, the one
    named is not on or only receives (`radio.receive_only`), or it does not take frames now (why not)."""
    pick = as_pick(radios, config)
    if radio is None:
        chosen = pick.main
        if chosen is None:
            raise MessagingError.of(NO_RADIO)
    else:
        found = next((r for r in pick.enabled() if r.id == radio), None)
        if found is None:
            named = pick.get(radio)
            if named is None:
                raise MessagingError(f"there is no radio {radio}", "radio.unknown", radio=radio)
            raise MessagingError(f"radio {named.name or radio} is off: turn it on first", "radio.off", name=named.name or str(radio), radio=radio)
        if not any(r.id == radio for r in pick.senders()):
            raise MessagingError(f"radio {found.name} only receives: nothing can be sent on it", "radio.receive_only", name=found.name, radio=radio)      # (the page offers it for no request)
        chosen = found
    if not chosen.usable:
        raise MessagingError.of(chosen.why_unusable())
    return chosen


def on_words(radio: AirRadio, radios: RadioPick | Radio, config: ConfigSource) -> str:
    """" on <name>" for the log while more than one radio is on (which one it went on is then worth saying), else nothing."""
    return f" on {radio.name}" if radio.name and len(as_pick(radios, config).enabled()) > 1 else ""


RX_ONLY = "RX only: nothing is sent"                                # what a refusal to the page says while station/transmit is off (its code is `transmit.off`)


def transmit_refusal(config: Config, error: type[CodedError] = CodedError) -> CodedError | None:
    """Why nothing may be sent now, as an error of the class given (not raised): receive only (the code `transmit.off`), or the interlock's reason (no call); None when we may send."""
    if not config.station_transmit or config.listens_only:
        return error(RX_ONLY, "transmit.off")
    if reason := can_transmit(config):
        return error.of(reason)
    return None


def our_call(config: Config) -> str:
    """The call we send under; raises MessagingError when nothing may be transmitted (transmit_refusal)."""
    if refusal := transmit_refusal(config, MessagingError):
        raise refusal
    return config.station_call
