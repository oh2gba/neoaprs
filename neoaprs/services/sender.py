"""Our frames that go out by a schedule of their own (the objects and the bulletins: services/ownobjects.py, services/ownbulletins.py) through one place: `ready` says whether one may go now, `send` makes the
frame and hands it to the Tnc.

Nothing goes while the call is not set (the interlock, `ready("object")`: the first refusal is told in the log, as the interlock does) and nothing while the Tnc is not usable: not connected, silent, not yet
confirmed or settling after KISS ON. What is due then is not skipped and not made up: it waits, the log says once per outage `... due and the radio is silent`, and it goes out when the radio is back. Our own
frames go out one at a time: after one, `spacing_sec` pass before the next, so that a restart with many objects due at once, or a radio that comes back, never sends a burst. The frame is from `station/call` to
`beacon/destination` by the path given, else `beacon/path`; one that cannot be made (a path of more than 8 digipeaters, an information field that is too long) is a SendError."""
import logging
from datetime import datetime

from neoaprs import ax25
from neoaprs.clock import Clock, utcnow
from neoaprs.interlock import Interlock
from neoaprs.services.common import FRAME_ERRORS, ConfigSource, Radio, our_frame
from neoaprs.source import Source

log = logging.getLogger("neoaprs.sender")

SPACING_SEC = 10.0


class SendError(ValueError):
    """The settings and the values make no frame."""


class Sender:
    def __init__(self, tnc: Radio, config: ConfigSource, clock: Clock = utcnow, spacing_sec: float = SPACING_SEC) -> None:
        self._tnc = tnc
        self._config = config
        self._interlock = Interlock(config)
        self.clock = clock
        self.spacing_sec = spacing_sec
        self.problem = ""                                       # why the latest try did not send (the interlock's or the radio's reason); empty when it could
        self._last: datetime | None = None                      # when the latest frame went out
        self._told = False

    def ready(self, kind: str) -> bool:
        """May a frame of this kind (a word for the log: "object", "bulletin") go out now?"""
        if self._last is not None and (self.clock() - self._last).total_seconds() < self.spacing_sec:
            return False
        if refusal := self._interlock.refused(kind):
            self.problem = refusal
            return False
        if not self._tnc.usable:
            self.problem = self._tnc.why_unusable()
            if not self._told and self._tnc.state is not Source.State.CONNECTED:        # (a connected Tnc that is not usable is settling after KISS ON: the frame waits for it, saying nothing)
                self._told = True
                log.warning("the %s is due and %s: it goes out when the radio is back", kind, self.problem)
            return False
        self._told = False
        self.problem = ""
        return True

    def frame(self, info: bytes, path: tuple[str, ...] | None) -> ax25.Frame:
        """Our frame with this information field by this path (None: `beacon/path`). Raises SendError."""
        c = self._config()
        calls = c.beacon_path_calls if path is None else path
        if len(info) > ax25.MAX_INFO:
            raise SendError(f"the information field is {len(info)} bytes, more than the {ax25.MAX_INFO} AX.25 allows")
        try:
            return our_frame(c, calls, info)
        except FRAME_ERRORS as e:
            raise SendError(str(e)) from None

    def send(self, info: bytes, path: tuple[str, ...] | None) -> bool:
        """Sends the frame through the Tnc; False when the Tnc would not take it (it is settling, or the write failed): it is tried again at the next tick. Raises SendError."""
        frame = self.frame(info, path)
        if not self._tnc.send_frame(frame):
            self.problem = "the TNC did not take the frame (it is restarting into KISS mode, or the write failed)"
            return False
        self._last = self.clock()
        return True
