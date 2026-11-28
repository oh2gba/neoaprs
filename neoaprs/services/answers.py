"""Sending the answers of the query and QRU services.

Frames go out by the asker's path on the radio the request came on, paced; all answers together
are held to ANSWERS_PER_WINDOW frames in ANSWER_WINDOW_SEC. Nothing is sent under the interlock.
"""

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from typing import cast

from neoaprs import ax25
from neoaprs.aprsmessage import format_message
from neoaprs.clock import Clock, utcnow
from neoaprs.interlock import Interlock
from neoaprs.message import MessagingError
from neoaprs.policy import DIGI_DUPLICATE_SEC
from neoaprs.recent import Recent
from neoaprs.route import rf_only_path
from neoaprs.services.common import ConfigSource, OldAir, Paths, Radio, our_frame
from neoaprs.services.common import as_pick as as_pick  # re-exported for the messaging services
from neoaprs.services.pace import SPACING_SEC
from neoaprs.services.radioset import NO_RADIO, AirRadio, RadioPick, first_sender, path_on
from neoaprs.tasks import TaskSet

log = logging.getLogger("neoaprs.queries")

ANSWER_AGAIN_SEC = DIGI_DUPLICATE_SEC
ANSWER_FRAMES_MAX = 5
# two of the longest answers
ANSWERS_PER_WINDOW = 2 * ANSWER_FRAMES_MAX
ANSWER_WINDOW_SEC = 60.0


class AnswerBudget:
    """Frames of answers sent in the last ANSWER_WINDOW_SEC plus those still to go."""

    def __init__(self, clock: Clock = utcnow) -> None:
        self._clock = clock
        self._sent: list[datetime] = []
        self._held = 0

    def in_use(self) -> int:
        now = self._clock()
        self._sent = [at for at in self._sent if 0.0 <= (now - at).total_seconds() < ANSWER_WINDOW_SEC]
        return len(self._sent) + self._held

    def take(self, frames: int) -> "Share | None":
        """Hold `frames` frames and return their share, or None if they do not all fit."""
        if self.in_use() + frames > ANSWERS_PER_WINDOW:
            return None
        self._held += frames
        return Share(self, frames)

    def count_sent(self) -> None:
        """Count one held frame as sent now."""
        self._held -= 1
        self._sent.append(self._clock())

    def release(self, frames: int) -> None:
        """Give back `frames` held frames that will not be sent."""
        self._held -= frames


class Share:
    """The frames of one answer held in the budget: `went()` per frame sent, then `close()`."""

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
    def __init__(
        self,
        radios: RadioPick | Radio,
        config: ConfigSource,
        paths: Paths,
        spacing_sec: float = SPACING_SEC,
        budget: AnswerBudget | None = None,
    ) -> None:
        self._given = radios
        self._config = config
        self._paths = paths
        self._spacing = spacing_sec
        self._budget = budget if budget is not None else AnswerBudget()
        self.interlock = Interlock(config)
        self._answered: Recent[tuple[str, str]] = Recent(ANSWER_AGAIN_SEC)
        self.tasks = TaskSet(log, "queries")

    async def stop(self) -> None:
        """Cancel answers that are still waiting."""
        await self.tasks.cancel_all()

    def refused(self) -> bool:
        """Whether the transmit interlock is holding answers back."""
        return self.interlock.refused("query answer") is not None

    def lately(self, asker: str, query: str, at: datetime) -> bool:
        """Whether this asker was answered for this query less than ANSWER_AGAIN_SEC ago."""
        return self._answered.lately((asker, query), at)

    def note(self, asker: str, query: str, at: datetime) -> None:
        """Record that the asker is being answered; a repeat within ANSWER_AGAIN_SEC is ignored."""
        self._answered.note((asker, query), at)

    def message(self, asker: str, text: str, msg_id: str | None = None) -> ax25.Frame:
        """Build our frame carrying a message to the asker, with no id unless `msg_id` is given."""
        return our_frame(self._config(), (), b":" + format_message(asker, text, msg_id, None if msg_id is None else ""))

    def deliver(
        self,
        asker: str,
        query: str,
        frames: Sequence[ax25.Frame],
        at: datetime,
        paced: bool,
        rf_only: bool = False,
        first_after_sec: float = 0.0,
        radio: AirRadio | None = None,
    ) -> bool:
        """Send the frames of the answer to `query` on `radio` (default: first sender); True if so.

        Paced: the first at once (or after `first_after_sec`), the rest SPACING_SEC apart.
        """
        if not frames:
            return False
        share = self._budget.take(len(frames))
        if share is None:
            log.debug(
                "the %s query of %s is not answered: %d frames of answers went out in the last %g s",
                query,
                asker,
                ANSWERS_PER_WINDOW,
                ANSWER_WINDOW_SEC,
            )
            return False
        if paced and first_after_sec > 0:
            self.note(asker, query, at)
            log.info(
                "the %s query of %s is answered with %d frames, the first in %g s, %g s apart",
                query,
                asker,
                len(frames),
                first_after_sec,
                self._spacing,
            )
            self.tasks.spawn(self._rest(asker, list(frames), rf_only, share, first_after_sec, radio), "query-paced")
            return True
        if paced:
            if not self._went(share, asker, frames[0], rf_only, radio):
                share.close()
                return False
            self.note(asker, query, at)
            log.info(
                "the %s query of %s is answered with %d frames, %g s apart", query, asker, len(frames), self._spacing
            )
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

    async def _rest(
        self,
        asker: str,
        frames: list[ax25.Frame],
        rf_only: bool,
        share: Share,
        first_after_sec: float | None = None,
        radio: AirRadio | None = None,
    ) -> None:
        """Send the remaining frames SPACING_SEC apart, the first after `first_after_sec`."""
        try:
            for number, frame in enumerate(frames):
                await asyncio.sleep(first_after_sec if number == 0 and first_after_sec is not None else self._spacing)
                if not self._went(share, asker, frame, rf_only, radio):
                    return
        finally:
            share.close()

    def send(
        self, asker: str, frames: Sequence[ax25.Frame], rf_only: bool = False, radio: AirRadio | None = None
    ) -> bool:
        """Send all frames at once if the budget has room, else none; return whether all went."""
        if not frames or self.refused():
            return False
        share = self._budget.take(len(frames))
        if share is None:
            log.debug(
                "an answer to %s is not sent: %d frames of answers went out in the last %g s",
                asker,
                ANSWERS_PER_WINDOW,
                ANSWER_WINDOW_SEC,
            )
            return False
        went = [self._went(share, asker, frame, rf_only, radio) for frame in frames]
        share.close()
        return all(went)

    def _went(self, share: Share, asker: str, frame: ax25.Frame, rf_only: bool, radio: AirRadio | None) -> bool:
        """Send the frame and count it in the budget if it went."""
        if not self._transmit(asker, frame, rf_only, radio):
            return False
        share.went()
        return True

    def _transmit(self, asker: str, frame: ax25.Frame, rf_only: bool, radio: AirRadio | None) -> bool:
        """Send the frame by the asker's path, as the radio allows; return whether it went."""
        if self.refused():
            return False
        tnc = radio or first_sender(as_pick(self._given, self._config))
        if tnc is None or not tnc.usable:
            log.warning("a query of %s is not answered: %s", asker, NO_RADIO if tnc is None else tnc.why_unusable())
            return False
        try:
            calls = self._paths(asker, None, tnc.id)
            calls = path_on(tnc, self._config(), rf_only_path(calls) if rf_only else calls, rf_only=rf_only)
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


def air_of(radio: AirRadio | Radio, config: ConfigSource) -> AirRadio:
    """Return `radio` as an AirRadio, wrapping a plain Radio in OldAir."""
    return cast(AirRadio, radio) if hasattr(radio, "allowed") else OldAir(radio, config)


def radio_word(radio: AirRadio) -> str:
    """The radio's name for log text."""
    return radio.name
