"""What a driver of a type of radio is to the radio registry (plan §2, "Type"): the line it gives the packets on, how it takes a radio's settings, what a change of them restarts, its words for the log, its start
and stop, what it holds of the station's resources, and its modem where the type has one. A Protocol only: the drivers are neoaprs/tncdriver.py (the serial, TCP and dummy lines) and neoaprs/mercurydriver.py
(the Mercury modem) and neoaprs/direwolfdriver.py (Direwolf on a sound card), found by `RadioType.driver`. A driver reads the radio's own settings from its spec and what stays the station's (serial/pattern, serial/skip, today's remembered port) from the station's
settings, both given on every call, so that what it computes is a function of its arguments. `RunOverrides` is what the process gives for one run and never stores. The line and the modem are read-only
members, so that a plain attribute, a property, or a subclass of Tnc or Mercury (a test's double) all satisfy the Protocol."""
from dataclasses import dataclass
from typing import Protocol

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
    port: str = ""                   # --port: radio 1's (FM_ID)
    pattern: str = ""                # the tests' search globs, instead of serial/pattern
    hf_port: str = ""                # --hf-port: a Mercury that something else runs, given to the radio `attach_to`
    check_sec: float = TNC_CHECK_SEC
    attach_to: RadioId | None = HF_ID  # the radio that takes hf_port: the station's first Mercury radio (radiospec.modem_radio, as App.run reads it), None while it has none


class RadioDriver(Protocol):
    @property
    def line(self) -> Tnc:
        """The Source the packets come from and frames go to; its packets carry its `radio_id`, which the driver sets."""
        ...

    @property
    def modem(self) -> Mercury | DirewolfModem | None:
        """The modem of a "mercury" or a "direwolf" driver (Tune, the keying test, the transmit level; Mercury's scope); None for any other."""
        ...

    def configure(self, spec: RadioSpec, station: Config, run: RunOverrides) -> None:
        """Takes the radio's settings and the station's; the radio is stopped."""
        ...

    def restart_key(self, spec: RadioSpec, station: Config, run: RunOverrides) -> tuple[object, ...]:
        """What a change of restarts the radio (of the station's settings too: serial/skip and serial/pattern restart a serial radio)."""
        ...

    def words(self, spec: RadioSpec, station: Config, run: RunOverrides) -> str:
        """The radio's settings in a few words, for the log."""
        ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    def held(self) -> list[Claim]:
        """What it holds now: the port it opened, the card and keying the modem chose, the pair of ports."""
        ...
