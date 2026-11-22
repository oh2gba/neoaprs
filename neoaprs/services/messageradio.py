"""The radio an outgoing message goes on (plan rule 3.2), and two helpers for its frames.

A message keeps its first radio until it ends, unless the operator chooses another one, the
radio is disabled or a stand-in radio is replaced by one that heard the station."""

import logging
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import NamedTuple, Protocol, runtime_checkable

from neoaprs import messagerule
from neoaprs.aprsmessage import MessageError, format_message
from neoaprs.callsign import CallsignError, normal_name
from neoaprs.chain import Attempt
from neoaprs.message import EMAIL_GATEWAY, MessageRecord, MessagingError
from neoaprs.radiotype import RadioId
from neoaprs.services.answers import as_pick
from neoaprs.services.common import ConfigSource, Radio
from neoaprs.services.radioset import NO_RADIO, AirRadio, RadioPick
from neoaprs.station import Station

log = logging.getLogger("neoaprs.messaging")


@runtime_checkable
class Chooses(Protocol):
    def choice(self, call: str) -> RadioId | None: ...


@runtime_checkable
class Knows(Protocol):
    def station_of(self, call: str) -> Station | None: ...


class Kept(NamedTuple):
    """The kept radio, the choice in force when it was taken, and whether it stood in."""

    radio: RadioId
    choice: RadioId | None
    stand_in: bool


def last_run(attempts: Sequence[Attempt]) -> tuple[RadioId, datetime] | None:
    """Return the last attempt's radio and when its run on it began; None if it has no radio."""
    if not attempts or (radio := attempts[-1].radio_id) is None:
        return None
    since = attempts[-1].sent_at
    for attempt in reversed(attempts):
        if attempt.radio_id != radio:
            break
        since = attempt.sent_at
    return radio, since


def info(to: str, text: str, ident: str | None, reply: str | None) -> bytes:
    """Return the information field of a message; raise MessagingError for text it refuses."""
    try:
        return b":" + format_message(to, text, ident, reply)
    except MessageError as e:
        raise MessagingError.of(e) from None


def named(name: str) -> str:
    """Return the normal form of a callsign, or the stripped text if it is not a call."""
    try:
        return normal_name(name)
    except CallsignError:
        return name.strip()


def station_radio(radios: RadioPick | Radio, config: ConfigSource, to: str) -> AirRadio:
    """Return the radio for a message to the station now (the email radio for the gateway).

    Raise MessagingError while no radio that can send is on."""
    pick = as_pick(radios, config)
    radio = pick.email() if to == EMAIL_GATEWAY else pick.for_station(to)
    if radio is None:
        raise MessagingError.of(NO_RADIO)
    return radio


def _choice(pick: RadioPick, config: ConfigSource, call: str) -> RadioId | None:
    """Return the operator's chosen radio if it is enabled, else None (email has its own choice)."""
    if call == EMAIL_GATEWAY:
        chosen = config().email_choice
    else:
        chosen = pick.choice(call) if isinstance(pick, Chooses) else None
    return chosen if chosen is not None and any(r.id == chosen for r in pick.senders()) else None


def _keep(pick: RadioPick, to: str, radio: RadioId, choice: RadioId | None, at: datetime) -> Kept:
    """Return the radio kept from `at`; a stand-in never applies to the email gateway."""
    station = pick.station_of(to) if isinstance(pick, Knows) and to != EMAIL_GATEWAY else None
    return Kept(
        radio,
        choice,
        station is not None and messagerule.stood_in(radio, choice, station.heard_by, station.first_heard, at),
    )


def _leaves(pick: RadioPick, to: str, kept: Kept, on: bool, choice: RadioId | None) -> str | None:
    """Return the log reason the message leaves its kept radio; None if it stays."""
    if not on:
        return "the radio it went out on is off"
    if choice != kept.choice:
        return (
            "no radio is chosen for the station any more"
            if choice is None
            else "the radio chosen for the station applies now"
        )
    if (
        kept.stand_in
        and isinstance(pick, Knows)
        and (station := pick.station_of(to)) is not None
        and station.heard_on(kept.radio).count == 0
    ):
        now = pick.for_station(to)
        if now is not None and station.heard_on(now.id).count > 0:
            return "a radio that heard the station is on now"
    return None


class MessageRadios:
    def __init__(
        self, radios: RadioPick | Radio, config: ConfigSource, last: Callable[[int], tuple[RadioId, datetime] | None]
    ) -> None:
        self._given, self._config = radios, config
        self._last = last
        # By message id; None means it left its radio.
        self._kept: dict[int, Kept | None] = {}

    def station(self, to: str) -> AirRadio:
        """Return the station's radio now. Raise MessagingError while there is none."""
        return station_radio(self._given, self._config, to)

    def of(self, record: MessageRecord) -> AirRadio:
        """Return the kept radio while valid, else the station's radio now; raise MessagingError."""
        pick = as_pick(self._given, self._config)
        choice = _choice(pick, self._config, record.to_call)
        kept = self._keeps(pick, record, choice)
        if kept is not None:
            self._kept[record.id] = kept
            radio = next((r for r in pick.senders() if r.id == kept.radio), None)
            why = _leaves(pick, record.to_call, kept, radio is not None, choice)
            if radio is not None and why is None:
                return radio
            self._kept[record.id] = None
            log.info(
                "message %d to %s goes on the radio the station is reached on now: %s", record.id, record.to_call, why
            )
        return self.station(record.to_call)

    def peek(self, record: MessageRecord) -> AirRadio:
        """Return what `of` would give, without keeping or logging; raise MessagingError."""
        pick = as_pick(self._given, self._config)
        choice = _choice(pick, self._config, record.to_call)
        kept = self._keeps(pick, record, choice)
        radio = None if kept is None else next((r for r in pick.senders() if r.id == kept.radio), None)
        if kept is not None and radio is not None and _leaves(pick, record.to_call, kept, True, choice) is None:
            return radio
        return self.station(record.to_call)

    def _keeps(self, pick: RadioPick, record: MessageRecord, choice: RadioId | None) -> Kept | None:
        """Return the kept radio, restoring the last attempt's radio after a restart."""
        if (
            record.id not in self._kept
            and record.attempts > 0
            and (last := self._last(record.id)) is not None
            and choice in (None, last[0])
        ):
            return _keep(pick, record.to_call, last[0], choice, last[1])
        return self._kept.get(record.id)

    def sent(self, record: MessageRecord, radio: AirRadio, at: datetime) -> None:
        """Record an attempt on `radio`; it becomes the kept radio if none is kept."""
        if self._kept.get(record.id) is None:
            pick = as_pick(self._given, self._config)
            self._kept[record.id] = _keep(
                pick, record.to_call, radio.id, _choice(pick, self._config, record.to_call), at
            )

    def forget(self, number: int) -> None:
        """Drop the kept radio, as the message ended or restarts."""
        self._kept.pop(number, None)
