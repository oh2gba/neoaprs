"""The interface a driver of a radio type offers the radio registry (only the Protocol).

Settings are passed on every call, so a driver's results depend on its arguments only; `line` and
`modem` are read-only so attributes, properties and test doubles all satisfy it.
"""
from dataclasses import dataclass
from typing import Protocol

from .cardlevels import CardLevels
from .claims import Claim
from .config import Config
from .direwolfmodem import DirewolfModem
from .mercurymodem import Mercury
from .policy import TNC_CHECK_SEC
from .radiospec import HF_ID, RadioId, RadioSpec
from .tnc import Tnc


@dataclass(frozen=True)
class RunOverrides:
    """What the process gives for this run only, never stored."""
    # --port: radio 1's port.
    port: str = ""
    # Search globs for tests, instead of serial/pattern.
    pattern: str = ""
    # --hf-port: a Mercury run by something else, given to the radio `attach_to`.
    hf_port: str = ""
    check_sec: float = TNC_CHECK_SEC
    # The radio that takes hf_port: the first Mercury radio, or None if there is none.
    attach_to: RadioId | None = HF_ID


class RadioDriver(Protocol):
    @property
    def line(self) -> Tnc:
        """The Source that packets come from and frames go to; its packets carry its `radio_id`."""
        ...

    @property
    def modem(self) -> Mercury | DirewolfModem | None:
        """The modem of a "mercury" or "direwolf" driver; None for any other."""
        ...

    @property
    def card(self) -> CardLevels | None:
        """The sound card levels of a modem's radio (cardlevels.py); None without a sound card."""
        ...

    def configure(self, spec: RadioSpec, station: Config, run: RunOverrides) -> None:
        """Take the radio's and the station's settings; the radio is stopped."""
        ...

    def restart_key(self, spec: RadioSpec, station: Config, run: RunOverrides) -> tuple[object, ...]:
        """Return the values whose change restarts the radio, station settings included."""
        ...

    def words(self, spec: RadioSpec, station: Config, run: RunOverrides) -> str:
        """Describe the radio's settings in a few words, for the log."""
        ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    def held(self) -> list[Claim]:
        """Return the resources held now: opened port, chosen card and keying, port pair."""
        ...
