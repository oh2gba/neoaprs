"""How a service answers a station that asked (the queries, services/queries.py, and the QRU server, services/qru.py): the frames of an answer go out by the asker's path as frames of our own, the first at once and, for an answer of
several frames, the others one at a time SPACING_SEC apart (services/pace.py); a server may hold the first back (`first_after_sec`: the QRU server waits for the digipeaters to finish repeating the request, or its answer
collides with them at the asker); a message of an answer carries no id, is not retried and is not a message of messaging. The same station asking the same within ANSWER_AGAIN_SEC (the
copies of one transmission by different digipeaters, an impatient asker) is answered once. Nothing is sent under the transmit interlock or while the radio is not usable."""
import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import datetime

from neoaprs import ax25
from neoaprs.aprsmessage import format_message
from neoaprs.interlock import Interlock
from neoaprs.message import MessagingError
from neoaprs.route import rf_only_path
from neoaprs.services.common import ConfigSource, Radio, our_frame
from neoaprs.services.pace import SPACING_SEC
from neoaprs.tasks import TaskSet

log = logging.getLogger("neoaprs.queries")

ANSWER_AGAIN_SEC = 30.0
ANSWER_FRAMES_MAX = 5                                                           # the objects or messages an answer carries at most


class Answers:
    def __init__(self, tnc: Radio, config: ConfigSource, paths: Callable[[str], tuple[str, ...]], spacing_sec: float = SPACING_SEC) -> None:
        self._tnc = tnc
        self._config = config
        self._paths = paths                                     # the digipeaters of what we send to a station (PrefBook.path_for)
        self._spacing = spacing_sec
        self.interlock = Interlock(config)
        self._answered: dict[tuple[str, str], datetime] = {}    # when each (station, query) was last answered
        self.tasks = TaskSet(log, "queries")

    async def stop(self) -> None:
        """An answer that is waiting is not sent."""
        await self.tasks.cancel_all()

    def refused(self) -> bool:
        """Whether the transmit interlock holds every answer back now."""
        return self.interlock.refused("query answer") is not None

    def lately(self, asker: str, query: str, at: datetime) -> bool:
        """Whether the same station asked the same and was answered less than ANSWER_AGAIN_SEC ago."""
        self._answered = {key: when for key, when in self._answered.items() if (at - when).total_seconds() < ANSWER_AGAIN_SEC}
        return (asker, query) in self._answered

    def note(self, asker: str, query: str, at: datetime) -> None:
        """The station is being answered for this query: the same one again within ANSWER_AGAIN_SEC is not."""
        self._answered[(asker, query)] = at

    def message(self, asker: str, text: str, msg_id: str | None = None) -> ax25.Frame:
        """Our frame carrying a message to the asker: without an id (nothing is waited for), or a message of ours sent again with its number `{MM}`."""
        return our_frame(self._config(), (), b":" + format_message(asker, text, msg_id, None if msg_id is None else ""))

    def deliver(self, asker: str, query: str, frames: Sequence[ax25.Frame], at: datetime, paced: bool, rf_only: bool = False, first_after_sec: float = 0.0) -> bool:
        """Sends the frames of the answer to `query`. Paced, the first goes at once and the others follow one at a time, SPACING_SEC apart (the answer counts as given once the first has gone); not paced, they all go
        at once, and the answer counts as given when every one has. With `rf_only` the frames go by the asker's path with RFONLY added, which keeps the iGates from putting them on APRS-IS. With `first_after_sec` (paced
        only) the first frame goes that long after the request, and the answer counts as given at once, so that the copies of the request that come meanwhile are not answered again. Whether it was given."""
        if not frames:
            return False
        if paced and first_after_sec > 0:
            self.note(asker, query, at)
            log.info("the %s query of %s is answered with %d frames, the first in %g s, %g s apart", query, asker, len(frames), first_after_sec, self._spacing)
            self.tasks.spawn(self._rest(asker, list(frames), rf_only, first_after_sec), "query-paced")
            return True
        if paced:
            if not self.send(asker, frames[0], rf_only):
                return False
            self.note(asker, query, at)
            log.info("the %s query of %s is answered with %d frames, %g s apart", query, asker, len(frames), self._spacing)
            if len(frames) > 1:
                self.tasks.spawn(self._rest(asker, list(frames[1:]), rf_only), "query-paced")
            return True
        if not all([self.send(asker, frame, rf_only) for frame in frames]):
            return False
        self.note(asker, query, at)
        log.info("the %s query of %s is answered", query, asker)
        return True

    async def _rest(self, asker: str, frames: list[ax25.Frame], rf_only: bool, first_after_sec: float | None = None) -> None:
        """The frames of an answer that are still to go, each SPACING_SEC after the one before (the first of them `first_after_sec` after the request when that is given, else it went at once)."""
        for number, frame in enumerate(frames):
            await asyncio.sleep(first_after_sec if number == 0 and first_after_sec is not None else self._spacing)
            if not self.send(asker, frame, rf_only):
                return

    def send(self, asker: str, frame: ax25.Frame, rf_only: bool = False) -> bool:
        """Sends the frame by the asker's path (with RFONLY added when `rf_only`); whether it went, and a word in the log when it did not."""
        if self.refused():
            return False
        if not self._tnc.usable:
            log.warning("a query of %s is not answered: %s", asker, self._tnc.why_unusable())
            return False
        try:
            calls = self._paths(asker)
            calls = rf_only_path(calls) if rf_only else calls
            if len(calls) > ax25.MAX_PATH:
                raise MessagingError(f"path too long for RF only: {len(calls)} digipeaters")
            path = tuple(ax25.Address.parse(call) for call in calls)
        except MessagingError as e:
            log.warning("a query of %s is not answered: %s", asker, e)
            return False
        if not self._tnc.send_frame(replace(frame, path=path)):
            log.warning("the answer to %s was not sent: the TNC would not take the frame", asker)
            return False
        return True
