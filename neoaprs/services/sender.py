"""The one place through which scheduled own frames (objects, bulletins) go out.

Frames go one at a time per radio, `spacing_sec` apart, and only while the radio is usable."""

import logging
from collections.abc import Iterable
from datetime import datetime

from neoaprs import ax25
from neoaprs.clock import Clock, utcnow
from neoaprs.interlock import Interlock
from neoaprs.radiospec import in_force_set
from neoaprs.radiotype import RadioId
from neoaprs.services.common import ConfigSource, Radio, as_pick
from neoaprs.services.pace import SPACING_SEC, within
from neoaprs.services.radioset import NO_RADIO, AirRadio, RadioPick, first_sender, fit
from neoaprs.services.radioset import SendError as SendError  # re-exported for callers
from neoaprs.source import Source

log = logging.getLogger("neoaprs.sender")


class Sender:
    def __init__(
        self, radios: RadioPick | Radio, config: ConfigSource, clock: Clock = utcnow, spacing_sec: float = SPACING_SEC
    ) -> None:
        self._radios = radios
        self._config = config
        self._interlock = Interlock(config)
        self.clock = clock
        self.spacing_sec = spacing_sec
        self.problem = ""
        self._last: dict[RadioId, datetime] = {}
        self._told = False

    @property
    def radios(self) -> RadioPick:
        """The station's radios."""
        return as_pick(self._radios, self._config)

    def too_soon(self, radio: AirRadio) -> bool:
        """Return whether the pause after the latest frame on the radio is still running."""
        last = self._last.get(radio.id)
        return last is not None and within(last, self.clock(), self.spacing_sec)

    def ready(self, kind: str, radio: AirRadio | None = None) -> bool:
        """Return whether a frame of this kind ("object", "bulletin") may go out now."""
        radios = [radio] if radio is not None else list(self.radios.senders())
        if radios and all(self.too_soon(r) for r in radios):
            return False
        if refusal := self._interlock.refused(kind):
            self.problem = refusal
            return False
        if not any(r.usable for r in radios):
            away = radios[0] if radios else None
            self.problem = away.why_unusable() if away is not None else NO_RADIO
            # connected but unusable: settling after KISS ON or modem held; wait silently
            if not self._told and (away is None or away.state is not Source.State.CONNECTED):
                self._told = True
                log.warning("the %s is due and %s: it goes out when the radio is back", kind, self.problem)
            return False
        self._told = False
        self.problem = ""
        return True

    def radios_for(self, ids: Iterable[RadioId]) -> list[AirRadio]:
        """Return the sending radios for these ids; a lone sending radio takes everything."""
        config = self._config()
        on = {radio.id: radio for radio in self.radios.senders()}
        found = [on[i] for i in in_force_set(ids, config.radios) if i in on]
        if not found and len(on) == 1 and not any(spec.id in on for spec in config.radios):
            return list(on.values())
        return found

    def frame(self, info: bytes, path: tuple[str, ...] | None, radio: AirRadio | None = None) -> ax25.Frame:
        """Return our frame for `radio` (default: first sender) by `path` (None: the radio's own).

        The comment is cut to fit the radio. Raise SendError, also when there is no radio."""
        target = radio if radio is not None else first_sender(self.radios)
        if target is None:
            raise SendError(NO_RADIO)
        return fit(target, self._config(), info, path)

    def send(self, info: bytes, path: tuple[str, ...] | None, radio: AirRadio | None = None) -> bool:
        """Send the frame on `radio` (default: the first sending radio); return whether it went out.

        False when the radio is unusable, paused or refuses it. Raise SendError."""
        target = radio if radio is not None else first_sender(self.radios)
        if target is None or not target.usable:
            self.problem = NO_RADIO if target is None else target.why_unusable()
            return False
        if self.too_soon(target):
            return False
        frame = self.frame(info, path, target)
        if not target.send_frame(frame):
            self.problem = "the TNC did not take the frame (it is restarting into KISS mode, or the write failed)"
            return False
        self._last[target.id] = self.clock()
        return True
