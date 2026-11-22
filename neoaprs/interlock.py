"""The transmit interlock: `Interlock.refused(kind)` is the reason nothing may be sent now, or None.

The reason comes from config.can_transmit. A service asks with its kind ("beacon", "message"), the
Tnc about every frame (kind "frame"). The first refusal of a kind is logged, until the interlock opens.
"""

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
