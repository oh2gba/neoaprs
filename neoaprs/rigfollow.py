"""The rig program a Sound card radio is keyed through when its keying is flrig or rigctld (mixin of the modems).

The modem keys nothing itself then; its PTT ON and PTT OFF are followed here (rigkeyer.py).
"""

import logging

from .coded import Reason
from .mercury import Keying
from .rigkeyer import RigKeyer
from .rigptt import ptt_for
from .signal import Signal

log = logging.getLogger("neoaprs.rig")


class RigFollow:
    changed: Signal[[]]
    rig: RigKeyer | None = None
    _rig_keying: Keying | None = None

    async def _rig_begin(self, keying: Keying) -> None:
        """Follow the modem with the rig program of `keying`, or with none; the same keying keeps its keyer."""
        if keying == self._rig_keying and self.rig is not None:
            return
        await self._rig_end()
        if keying.rig:
            host, port = keying.address
            self.rig, self._rig_keying = RigKeyer(ptt_for(keying.kind, host, port), self.changed.emit), keying
            log.info("the radio is keyed through %s", self.rig.describe())
            self.rig.start()

    async def _rig_end(self) -> None:
        """Key up and stop following."""
        rig, self.rig, self._rig_keying = self.rig, None, None
        if rig is not None:
            await rig.stop()

    def _rig_ptt(self, on: bool, limit_sec: float) -> None:
        if self.rig is not None:
            self.rig.key(on, limit_sec)

    def _rig_release(self) -> None:
        """Key up: the modem's keying is over, whatever it said last (it stopped, died or is not heard)."""
        if self.rig is not None:
            self.rig.key(False)

    def _rig_holds(self) -> Reason | str:
        return self.rig.holds() if self.rig is not None else ""

    @property
    def rig_problem(self) -> str:
        """`rig_silent`, `rig_keyed_long` or ""; "" for a radio keyed otherwise."""
        return self.rig.problem if self.rig is not None else ""
