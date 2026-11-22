"""What the services that send share: `ConfigSource` (how they read the settings), `transmit_refusal` and `our_call` (why nothing may be sent, and the call we may send under), and the two shapes of the
radios. The new one is services/radioset.py's: `RadioPick` (the radios by id, the enabled ones, those that send, the station's, the one a packet came on) and `AirRadio`, and its `fit` makes every frame of the
sender, our objects and bulletins and the digipeater. `as_pick` gives an old shape as the new one (`OldRadios`: an old set of two radios with the choice by station, by packet and by kind, or one plain
`Radio`, each radio an `OldAir`): app.py gives every service the registry, and the old shapes come only from the tests (tests/support/rig.py, the cases of the old set). `our_frame` and `fit_frame` (the frame
shortened to what a radio with a fixed frame carries: the Mercury HF modem's 123 bytes) are services/radioset.py's, given here under their old names. The rule every service follows: a frame is built for,
gated by and sent on *its* radio, the one the station is reached on or the one the request came on, never "the radio" of a station that has two."""
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
from neoaprs.services.radioset import FRAME_ERRORS as FRAME_ERRORS, fit_frame as fit_frame, fixed_prefix as fixed_prefix, our_frame as our_frame     # (the parts of the one fit function, under their old names)
from neoaprs.source import Source
from neoaprs.tncwatchdog import TncStats

log = logging.getLogger("neoaprs.services")

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


# ---- the old shapes as the new one, for the tests that still give one

def old_id(kind: str) -> RadioId:
    """The id of the radio an old-shape radio of this kind is: hf 2, anything else fm 1."""
    return HF_ID if kind == "hf" else FM_ID


def old_spec(config: Config, id: RadioId, key: str | None = None) -> RadioSpec | None:
    """The settings of radio `id`, or radio 1's where it has none (or none with the field `key`)."""
    spec = config.radio(id)
    return spec if spec is not None and (key is None or kind_field(spec.kind, key) is not None) else config.radio(FM_ID)


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
    """The old shapes as a RadioPick: an old set of two (its enabled radios, the one of a kind while it is enabled), or one plain Radio (a test's stub) that is every choice. Each radio is one OldAir for as long as this lives."""

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

    def for_station(self, call: str) -> AirRadio | None:
        return self._air(self._old.for_station(call) if isinstance(self._old, RadioSet) else self._old)

    def for_packet(self, packet: Packet) -> AirRadio | None:
        return self._air(self._old.for_packet(packet) if isinstance(self._old, RadioSet) else self._old)

    def email(self) -> AirRadio | None:
        """The FM radio while it is on (the old shapes have no choice of the email radio), else the radio that is on: a mail goes on a radio of any kind."""
        return self._of("fm") or next(iter(self.enabled()), None)


def is_pick(radios: RadioPick | Radio) -> TypeIs[RadioPick]:
    """Whether this is a RadioPick (the registry, a test's), not an old shape: it has the radios by id and the email radio, which no Radio and no old set has."""
    return callable(getattr(radios, "get", None)) and callable(getattr(radios, "email", None))


def as_pick(radios: RadioPick | Radio, config: ConfigSource) -> RadioPick:
    """The radios as a RadioPick: the registry as it is, an old shape as OldRadios."""
    return radios if is_pick(radios) else OldRadios(radios, config)


def send_on(radios: RadioPick | Radio, config: ConfigSource, key: str) -> list[AirRadio]:
    """The radios a thing with a Send on of its own goes out on now (`key`: "ask" for asking around, "local_info" for asking QRU), by position, whether they take frames at the moment or not: the radios
    of beaconrule.send_on_radios that the registry runs; with an old shape of a test's, its one radio. None while there is no radio that can send, or none is ticked."""
    pick = as_pick(radios, config)
    if not is_pick(radios):
        first = first_sender(pick)
        return [] if first is None else [first]
    return [found for id in send_on_radios(key, config().radios) if (found := pick.get(id)) is not None]


def asked_radios(radios: RadioPick | Radio, config: ConfigSource, key: str, radio: RadioId | None = None) -> list[AirRadio]:
    """The radios a request of the operator's to no station in particular goes on now (asking around, asking QRU: plan rule 3.6): each radio its Send on is in force on (`send_on`) that takes frames now;
    or the one named alone (asking QRU: the radio a server answered on). MessagingError while there is none (`radio.none`), none of them takes frames now (why the first does not), or the one named is
    none, is not on, only receives (`radio.receive_only`) or does not take frames now (why not)."""
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
        raise MessagingError(f"radio {found.name} only receives: nothing can be sent on it", "radio.receive_only", name=found.name, radio=radio)      # (the page offers it for no request)
    if not found.usable:
        raise MessagingError.of(found.why_unusable())
    return [found]


def sent_on(frames: Sequence[tuple[AirRadio, ax25.Frame]], what: str) -> list[tuple[AirRadio, ax25.Frame]]:
    """Gives each radio its frame of a request (asking around, asking QRU) and says which took it; a radio that did not is said in the log. MessagingError (`radio.not_taken`) when none did."""
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
