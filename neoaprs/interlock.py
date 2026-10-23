"""The transmit interlock as the parts use it: `Interlock.refused(kind)` is the reason nothing may be transmitted now (config.can_transmit, which is the only place that decides it), or None. A service asks it before it
builds a frame, with the kind of frame ("beacon", "status", "message", "query answer"), and the Tnc asks it of every frame it is given to send (kind "frame"), whoever built it; the first refusal of each kind is told in
the log, the following ones are not, and a refusal told once is told again after the interlock has been open in between."""
import logging
from collections.abc import Callable

from neoaprs.config import Config, can_transmit

log = logging.getLogger("neoaprs.interlock")


class Interlock:
    def __init__(self, config: Callable[[], Config]) -> None:
        self._config = config
        self._told: set[str] = set()

    def refused(self, kind: str) -> str | None:
        reason = can_transmit(self._config())
        if reason is None:
            self._told.clear()
        elif kind not in self._told:
            self._told.add(kind)
            log.warning("no %s sent: %s", kind, reason)
        return reason
