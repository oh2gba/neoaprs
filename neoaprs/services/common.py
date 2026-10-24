"""What the services that send share: `Radio` (what they need of the Tnc), `ConfigSource` (how they read the settings) and `our_frame` (our frame to the tocall)."""
from collections.abc import Callable
from typing import Protocol

from neoaprs import TOCALL, ax25
from neoaprs.callsign import CallsignError
from neoaprs.config import Config
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
