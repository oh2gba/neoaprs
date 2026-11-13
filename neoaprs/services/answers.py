"""How a service answers a station that asked (the queries, services/queries.py, and the QRU server, services/qru.py): the frames of an answer go out by the asker's path as frames of our own, the first at once and, for an answer of
several frames, the others one at a time SPACING_SEC apart (services/pace.py); a server may hold the first back (`first_after_sec`: the QRU server waits for the digipeaters to finish repeating the request, or its answer
collides with them at the asker); a message of an answer carries no id, is not retried and is not a message of messaging. The same station asking the same within ANSWER_AGAIN_SEC (the
copies of one transmission by different digipeaters, an impatient asker) is answered once. All the answers of the station together are held to ANSWERS_PER_WINDOW frames in ANSWER_WINDOW_SEC (an AnswerBudget):
whoever asks, with whatever call, the frames beyond it are not sent, and an answer that does not fit whole is not given at all; a frame is counted from the moment it goes on the air, the frames of an answer that are
still to go are held for it meanwhile, and the room of a frame that did not go on the air is given back. Nothing is sent under the transmit interlock or while the radio is not usable."""
import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import datetime

from neoaprs import ax25
from neoaprs.aprsmessage import format_message
from neoaprs.clock import Clock, utcnow
from neoaprs.interlock import Interlock
from neoaprs.message import MessagingError
from neoaprs.recent import Recent
from neoaprs.route import rf_only_path
from neoaprs.services.common import ConfigSource, Radio, our_frame, radio_path
from neoaprs.services.pace import SPACING_SEC
from neoaprs.tasks import TaskSet

log = logging.getLogger("neoaprs.queries")

ANSWER_AGAIN_SEC = 30.0
ANSWER_FRAMES_MAX = 5                                                           # the objects or messages an answer carries at most
ANSWERS_PER_WINDOW = 2 * ANSWER_FRAMES_MAX                                      # frames of answers the station sends in ANSWER_WINDOW_SEC: two of the longest honest answers; a station that asks under a new call each time cannot get more
ANSWER_WINDOW_SEC = 60.0


class AnswerBudget:
    """The frames of answers sent in the last ANSWER_WINDOW_SEC, each counted from the moment it went, and the frames of the answers under way that are still to go, for every service that answers (one budget is
    shared by them, so that it is the station's as a whole). A frame stamped later than now (the clock was set back) does not hold the window shut until the clock is there again: it is let go."""

    def __init__(self, clock: Clock = utcnow) -> None:
        self._clock = clock
        self._sent: list[datetime] = []
        self._held = 0                                          # frames of answers under way that have not gone yet

    def in_use(self) -> int:
        now = self._clock()
        self._sent = [at for at in self._sent if 0.0 <= (now - at).total_seconds() < ANSWER_WINDOW_SEC]
        return len(self._sent) + self._held

    def take(self, frames: int) -> "Share | None":
        """The share of an answer of `frames` frames when they all fit in the window, else None and nothing is held."""
        if self.in_use() + frames > ANSWERS_PER_WINDOW:
            return None
        self._held += frames
        return Share(self, frames)

    def count_sent(self) -> None:
        """One held frame went on the air now."""
        self._held -= 1
        self._sent.append(self._clock())

    def release(self, frames: int) -> None:
        """`frames` held frames will not go (the radio not usable, the TNC refusing, an answer stopped) and do not count."""
        self._held -= frames


class Share:
    """The frames of one answer, held in its budget: `went()` as each goes on the air, `close()` when the answer is over, which gives back what did not go (twice is once)."""

    def __init__(self, budget: AnswerBudget, frames: int) -> None:
        self._budget = budget
        self._left = frames

    def went(self) -> None:
        if self._left > 0:
            self._left -= 1
            self._budget.count_sent()

    def close(self) -> None:
        self._budget.release(self._left)
        self._left = 0


class Answers:
    def __init__(self, tnc: Radio, config: ConfigSource, paths: Callable[[str], tuple[str, ...]], spacing_sec: float = SPACING_SEC, budget: AnswerBudget | None = None) -> None:
        self._tnc = tnc
        self._config = config
        self._paths = paths                                     # the digipeaters of what we send to a station (PrefBook.path_for)
        self._spacing = spacing_sec
        self._budget = budget if budget is not None else AnswerBudget()
        self.interlock = Interlock(config)
        self._answered: Recent[tuple[str, str]] = Recent(ANSWER_AGAIN_SEC)     # the (station, query) answered lately
        self.tasks = TaskSet(log, "queries")

    async def stop(self) -> None:
        """An answer that is waiting is not sent."""
        await self.tasks.cancel_all()

    def refused(self) -> bool:
        """Whether the transmit interlock holds every answer back now."""
        return self.interlock.refused("query answer") is not None

    def lately(self, asker: str, query: str, at: datetime) -> bool:
        """Whether the same station asked the same and was answered less than ANSWER_AGAIN_SEC ago."""
        return self._answered.lately((asker, query), at)

    def note(self, asker: str, query: str, at: datetime) -> None:
        """The station is being answered for this query: the same one again within ANSWER_AGAIN_SEC is not."""
        self._answered.note((asker, query), at)

    def message(self, asker: str, text: str, msg_id: str | None = None) -> ax25.Frame:
        """Our frame carrying a message to the asker: without an id (nothing is waited for), or a message of ours sent again with its number `{MM}`."""
        return our_frame(self._config(), (), b":" + format_message(asker, text, msg_id, None if msg_id is None else ""))

    def deliver(self, asker: str, query: str, frames: Sequence[ax25.Frame], at: datetime, paced: bool, rf_only: bool = False, first_after_sec: float = 0.0, radio: Radio | None = None) -> bool:
        """Sends the frames of the answer to `query`. Paced, the first goes at once and the others follow one at a time, SPACING_SEC apart (the answer counts as given once the first has gone); not paced, they all go
        at once, and the answer counts as given when every one has. With `rf_only` the frames go by the asker's path with RFONLY added, which keeps the iGates from putting them on APRS-IS. With `first_after_sec` (paced
        only) the first frame goes that long after the request, and the answer counts as given at once, so that the copies of the request that come meanwhile are not answered again. On `radio` (the one the request came
        on; the one radio there is by default). Whether it was given."""
        if not frames:
            return False
        share = self._budget.take(len(frames))
        if share is None:
            log.debug("the %s query of %s is not answered: %d frames of answers went out in the last %g s", query, asker, ANSWERS_PER_WINDOW, ANSWER_WINDOW_SEC)
            return False
        if paced and first_after_sec > 0:
            self.note(asker, query, at)
            log.info("the %s query of %s is answered with %d frames, the first in %g s, %g s apart", query, asker, len(frames), first_after_sec, self._spacing)
            self.tasks.spawn(self._rest(asker, list(frames), rf_only, share, first_after_sec, radio), "query-paced")
            return True
        if paced:
            if not self._went(share, asker, frames[0], rf_only, radio):
                share.close()
                return False
            self.note(asker, query, at)
            log.info("the %s query of %s is answered with %d frames, %g s apart", query, asker, len(frames), self._spacing)
            if len(frames) > 1:
                self.tasks.spawn(self._rest(asker, list(frames[1:]), rf_only, share, None, radio), "query-paced")
            else:
                share.close()
            return True
        went = [self._went(share, asker, frame, rf_only, radio) for frame in frames]
        share.close()
        if not all(went):
            return False
        self.note(asker, query, at)
        log.info("the %s query of %s is answered", query, asker)
        return True

    async def _rest(self, asker: str, frames: list[ax25.Frame], rf_only: bool, share: Share, first_after_sec: float | None = None, radio: Radio | None = None) -> None:
        """The frames of an answer that are still to go, each SPACING_SEC after the one before (the first of them `first_after_sec` after the request when that is given, else it went at once)."""
        try:
            for number, frame in enumerate(frames):
                await asyncio.sleep(first_after_sec if number == 0 and first_after_sec is not None else self._spacing)
                if not self._went(share, asker, frame, rf_only, radio):
                    return
        finally:
            share.close()

    def send(self, asker: str, frames: Sequence[ax25.Frame], rf_only: bool = False, radio: Radio | None = None) -> bool:
        """Sends the frames of an answer that `deliver` does not carry (the general query's) at once, if the budget has room for all of them; else none. Whether every one went."""
        if not frames or self.refused():
            return False
        share = self._budget.take(len(frames))
        if share is None:
            log.debug("an answer to %s is not sent: %d frames of answers went out in the last %g s", asker, ANSWERS_PER_WINDOW, ANSWER_WINDOW_SEC)
            return False
        went = [self._went(share, asker, frame, rf_only, radio) for frame in frames]
        share.close()
        return all(went)

    def _went(self, share: Share, asker: str, frame: ax25.Frame, rf_only: bool, radio: Radio | None) -> bool:
        """Sends the frame (_transmit) and counts it in the budget from now when it went."""
        if not self._transmit(asker, frame, rf_only, radio):
            return False
        share.went()
        return True

    def _transmit(self, asker: str, frame: ax25.Frame, rf_only: bool, radio: Radio | None) -> bool:
        """Sends the frame by the asker's path (with RFONLY added when `rf_only`) on `radio` (the one the request came on; the one radio there is by default); whether it went, and a word in the log when it did not."""
        if self.refused():
            return False
        tnc = radio or self._tnc
        if not tnc.usable:
            log.warning("a query of %s is not answered: %s", asker, tnc.why_unusable())
            return False
        try:
            calls = self._paths(asker)
            calls = radio_path(tnc, rf_only_path(calls) if rf_only else calls)
            if len(calls) > ax25.MAX_PATH:
                raise MessagingError(f"path too long for RF only: {len(calls)} digipeaters")
            path = tuple(ax25.Address.parse(call) for call in calls)
        except MessagingError as e:
            log.warning("a query of %s is not answered: %s", asker, e)
            return False
        if not tnc.send_frame(replace(frame, path=path)):
            log.warning("the answer to %s was not sent: the TNC would not take the frame", asker)
            return False
        return True
