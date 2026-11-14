"""What the services that send share: `Radio` (what they need of the Tnc), `RadioSet` (the two radios as one, with the choice by station, by packet and by kind: `radio_to`, `radio_for`, `radios_on`), `ConfigSource` (how they read
the settings), `transmit_refusal` and `our_call` (why nothing may be sent, and the call we may send under), `our_frame` (our frame to the tocall), `radio_path` (the path a frame goes by on the radio: none on HF) and `fit_frame` (the frame
shortened to what a radio with a fixed frame carries: the Mercury HF modem's 123 bytes; it and our_frame are services/radioset.py's, given here under their old names). The rule every service follows: a frame is built for, gated by and sent on *its* radio, the one the station is reached on or the one the request
came on, never "the radio" of a station that has two."""
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from neoaprs import ax25
from neoaprs.coded import CodedError
from neoaprs.config import Config, can_transmit
from neoaprs.message import EMAIL_GATEWAY, MessagingError
from neoaprs.packet import Packet
from neoaprs.radiorules import RadioRules
from neoaprs.services.radioset import FRAME_ERRORS as FRAME_ERRORS, fit_frame as fit_frame, fixed_prefix as fixed_prefix, our_frame as our_frame     # (the parts of the one fit function, under their old names)
from neoaprs.source import Source

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
    """The digipeaters a frame of ours goes by on this radio: the path given where the network has digipeaters (FM), none where every frame is direct (HF: the settings and the stations' own paths are kept for the day the operator is back on VHF, and a path would only cost bytes of the frame)."""
    return path if radio.rules.paths else ()


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
