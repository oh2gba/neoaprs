"""How a service answers a station that asked (the queries, services/queries.py, and the QRU server, services/qru.py): the frames of an answer go out by the asker's path as frames of our own, the first at once and, for an answer of
several frames, the others one at a time SPACING_SEC apart (services/pace.py); a server may hold the first back (`first_after_sec`: the QRU server waits for the digipeaters to finish repeating the request, or its answer
collides with them at the asker); a message of an answer carries no id, is not retried and is not a message of messaging. The same station asking the same within ANSWER_AGAIN_SEC (the
copies of one transmission by different digipeaters, an impatient asker) is answered once. All the answers of the station together are held to ANSWERS_PER_WINDOW frames in ANSWER_WINDOW_SEC (an AnswerBudget):
whoever asks, with whatever call, the frames beyond it are not sent, and an answer that does not fit whole is not given at all; a frame is counted from the moment it goes on the air, the frames of an answer that are
still to go are held for it meanwhile, and the room of a frame that did not go on the air is given back. Nothing is sent under the transmit interlock or while the radio is not usable.

An answer goes on the radio the request came on (`radio`, the RadioPick's `for_packet`; the main radio when none is named), by the path that radio may carry (services/radioset.py `path_on`). The services that
answer and the messaging take the radios as a `RadioPick` (services/radioset.py); `as_pick` reads what they are given today (the old set of neoaprs/radios.py, a plain Radio of a test) as one, at each call."""
import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any, TypeGuard, cast

from neoaprs import ax25
from neoaprs.aprsmessage import format_message
from neoaprs.clock import Clock, utcnow
from neoaprs.interlock import Interlock
from neoaprs.message import MessagingError
from neoaprs.packet import Packet
from neoaprs.radiorules import RadioRules
from neoaprs.radiospec import KIND_WORDS, log_name
from neoaprs.radiotype import FM_ID, HF_ID, Allowed, Kind, Limits, RadioId, radio_id_of
from neoaprs.radiotypes import kind_field
from neoaprs.radiotypes.common import FM_ALLOWED, HF_ALLOWED
from neoaprs.recent import Recent
from neoaprs.route import rf_only_path
from neoaprs.services.common import ConfigSource, Radio, RadioSet, our_frame, radio_for, radio_to, radios_on
from neoaprs.services.pace import SPACING_SEC
from neoaprs.services.radioset import NO_RADIO, AirRadio, RadioPick, path_on
from neoaprs.source import Source
from neoaprs.tasks import TaskSet
from neoaprs.tncwatchdog import TncStats

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
    def __init__(self, radios: RadioPick | Radio, config: ConfigSource, paths: Callable[[str], tuple[str, ...]], spacing_sec: float = SPACING_SEC, budget: AnswerBudget | None = None) -> None:
        self._given = radios                                    # the station's radios (the registry; an old shape until app.py gives it: `as_pick`)
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

    def deliver(self, asker: str, query: str, frames: Sequence[ax25.Frame], at: datetime, paced: bool, rf_only: bool = False, first_after_sec: float = 0.0, radio: AirRadio | None = None) -> bool:
        """Sends the frames of the answer to `query`. Paced, the first goes at once and the others follow one at a time, SPACING_SEC apart (the answer counts as given once the first has gone); not paced, they all go
        at once, and the answer counts as given when every one has. With `rf_only` the frames go by the asker's path with RFONLY added, which keeps the iGates from putting them on APRS-IS. With `first_after_sec` (paced
        only) the first frame goes that long after the request, and the answer counts as given at once, so that the copies of the request that come meanwhile are not answered again. On `radio` (the one the request came
        on; the main radio by default). Whether it was given."""
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

    async def _rest(self, asker: str, frames: list[ax25.Frame], rf_only: bool, share: Share, first_after_sec: float | None = None, radio: AirRadio | None = None) -> None:
        """The frames of an answer that are still to go, each SPACING_SEC after the one before (the first of them `first_after_sec` after the request when that is given, else it went at once)."""
        try:
            for number, frame in enumerate(frames):
                await asyncio.sleep(first_after_sec if number == 0 and first_after_sec is not None else self._spacing)
                if not self._went(share, asker, frame, rf_only, radio):
                    return
        finally:
            share.close()

    def send(self, asker: str, frames: Sequence[ax25.Frame], rf_only: bool = False, radio: AirRadio | None = None) -> bool:
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

    def _went(self, share: Share, asker: str, frame: ax25.Frame, rf_only: bool, radio: AirRadio | None) -> bool:
        """Sends the frame (_transmit) and counts it in the budget from now when it went."""
        if not self._transmit(asker, frame, rf_only, radio):
            return False
        share.went()
        return True

    def _transmit(self, asker: str, frame: ax25.Frame, rf_only: bool, radio: AirRadio | None) -> bool:
        """Sends the frame by the asker's path (with RFONLY added when `rf_only`) on `radio` (the one the request came on; the main radio by default) by what that radio may carry; whether it went, and a word in the
        log when it did not."""
        if self.refused():
            return False
        tnc = radio or as_pick(self._given, self._config).main
        if tnc is None or not tnc.usable:
            log.warning("a query of %s is not answered: %s", asker, NO_RADIO if tnc is None else tnc.why_unusable())
            return False
        try:
            calls = self._paths(asker)
            calls = path_on(tnc, self._config(), rf_only_path(calls) if rf_only else calls)
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


# ---- the radios as a RadioPick, whatever the services are given until app.py gives the registry

class OldAir:
    """An old Radio (a Tnc, the old set of neoaprs/radios.py as its default radio, a test's stub) as an AirRadio: its id and kind by its rules' kind (fm 1, hf 2), its limits and what it is allowed by its rules,
    its own choices the station's radio of that id (the FM radio's where its kind has no such field), its counters its line's. It keeps `rules`, which today's beacon reads of the radio an answer goes on (the
    registry's radios keep them too until the old shapes go)."""

    def __init__(self, radio: Radio, config: ConfigSource) -> None:
        self.radio, self._config = radio, config

    @property
    def rules(self) -> RadioRules:
        return self.radio.rules

    @property
    def id(self) -> RadioId:
        return radio_id_of(self.radio.rules.kind) or FM_ID

    @property
    def kind(self) -> Kind:
        return "hf" if self.radio.rules.kind == "hf" else "fm"

    @property
    def name(self) -> str:
        config = self._config()
        spec = config.radio(self.id)
        return KIND_WORDS[self.kind] if spec is None else log_name(spec, config.radios)

    @property
    def limits(self) -> Limits:
        r = self.radio.rules
        return Limits(r.max_frame, r.beacon_min_min, r.beacon_jitter_sec, r.retry_jitter_sec)

    @property
    def allowed(self) -> Allowed:
        r = self.radio.rules
        return replace(FM_ALLOWED if r.kind == "fm" else HF_ALLOWED, paths=r.paths, digipeat=r.digipeat, smart_beacon=r.smart_beacon)

    @property
    def stats(self) -> TncStats:
        found = getattr(self.radio, "stats", None)
        return found if isinstance(found, TncStats) else TncStats()

    @property
    def state(self) -> Source.State:
        return self.radio.state

    @property
    def usable(self) -> bool:
        return self.radio.usable

    @property
    def max_frame(self) -> int | None:
        return self.radio.max_frame

    def why_unusable(self) -> str:
        return self.radio.why_unusable()

    def send_frame(self, frame: ax25.Frame, raw: bytes | None = None) -> bool:
        return self.radio.send_frame(frame, raw)

    def choice(self, key: str) -> Any:
        config = self._config()
        spec = config.radio(self.id)
        if spec is None or kind_field(spec.kind, key) is None:
            spec = config.radio(FM_ID)
        return None if spec is None else spec.value(key)


class OldRadios:
    """The old shapes as a RadioPick, each radio an OldAir: the set of neoaprs/radios.py (its enabled radios, the radio of a kind while it is enabled, its default radio as the main one, its choice by station
    and by packet, the FM radio for email), or one plain Radio, which is every choice (a test's stub)."""

    def __init__(self, radios: Radio, config: ConfigSource) -> None:
        self._old, self._config = radios, config

    def _air(self, radio: Radio | None) -> AirRadio | None:
        return None if radio is None else OldAir(radio, self._config)

    def get(self, id: RadioId) -> AirRadio | None:
        if isinstance(self._old, RadioSet):
            return self._air(self._old.of("fm" if id == FM_ID else "hf" if id == HF_ID else ""))
        return self.main if OldAir(self._old, self._config).id == id else None

    def enabled(self) -> Sequence[AirRadio]:
        return [OldAir(radio, self._config) for radio in radios_on(self._old)]

    @property
    def main(self) -> AirRadio | None:
        return self._air(self._old)

    def for_station(self, call: str) -> AirRadio | None:
        return self._air(radio_to(self._old, call))

    def for_packet(self, packet: Packet) -> AirRadio | None:
        return self._air(radio_for(self._old, packet))

    def email(self) -> AirRadio | None:
        return self._air(self._old.of("fm") if isinstance(self._old, RadioSet) else self._old)


def is_pick(radios: object) -> TypeGuard[RadioPick]:
    """Whether this is a RadioPick (the registry, a test's), not an old shape: it has the radios by id and the email radio, which no Radio and no old set has."""
    return callable(getattr(radios, "get", None)) and callable(getattr(radios, "email", None))


def as_pick(radios: RadioPick | Radio, config: ConfigSource) -> RadioPick:
    """The radios as a RadioPick: the registry as it is, an old shape as OldRadios. A service that holds an old shape reads it again at each call, so that it holds no part of its own that takes a packet."""
    return radios if is_pick(radios) else OldRadios(cast(Radio, radios), config)


def air_of(radio: AirRadio | Radio, config: ConfigSource) -> AirRadio:
    """A radio as an AirRadio: an old one as an OldAir (a test of today names a radio by its Tnc)."""
    return cast(AirRadio, radio) if hasattr(radio, "allowed") else OldAir(radio, config)


def request_radio(radios: RadioPick | Radio, config: ConfigSource) -> AirRadio:
    """The radio a request of the operator's to no station in particular goes on (asking around, asking QRU): the main radio. MessagingError while there is none, or it does not take frames now (why not)."""
    radio = as_pick(radios, config).main
    if radio is None or not radio.usable:
        raise MessagingError(NO_RADIO if radio is None else radio.why_unusable())
    return radio


def radio_word(radio: AirRadio) -> str:
    """The radio as the log has named it: radios 1 and 2 by their kind ("the fm radio", "on the hf radio"), any other by its name ("the FM 2 radio")."""
    return radio.kind if radio.id in (FM_ID, HF_ID) else radio.name
