"""What the services that send share: `Radio` (what they need of the Tnc), `ConfigSource` (how they read the settings), `transmit_refusal` and `our_call` (why nothing may be sent, and the call we may send under) and `our_frame` (our frame to the tocall)."""
from collections.abc import Callable
from typing import Protocol

from neoaprs import TOCALL, ax25
from neoaprs.callsign import CallsignError
from neoaprs.coded import CodedError
from neoaprs.config import Config, can_transmit
from neoaprs.message import MessagingError
from neoaprs.source import Source

ConfigSource = Callable[[], Config]
FRAME_ERRORS = (ax25.Ax25Error, CallsignError, ValueError)          # what `our_frame` raises for a call or a path that makes no frame


class Radio(Protocol):
    """What the services need of the Tnc."""
    @property
    def state(self) -> Source.State: ...
    @property
    def usable(self) -> bool: ...
    def why_unusable(self) -> str: ...
    def send_frame(self, frame: ax25.Frame, raw: bytes | None = None) -> bool: ...


def our_frame(config: Config, path: tuple[str, ...], info: bytes) -> ax25.Frame:
    """Our frame with this information field: from `station/call` to the tocall by way of `path`. Raises one of FRAME_ERRORS, each caller says it in its own error."""
    return ax25.Frame(ax25.Address.parse(TOCALL), ax25.Address.parse(config.station_call), tuple(ax25.Address.parse(call) for call in path), info=info)


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
