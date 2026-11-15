"""The radio a message of ours goes out on (plan rule 3.2), for services/messaging.py, with the two helpers of its frames.

The radio of a message to a station is the station's (`station_radio`: the registry's `for_station`, neoaprs/messagerule.py), and for the email gateway the email radio. It is asked at the message's first
attempt, and the message keeps that radio until it ends (`MessageRadios`): a station heard on another radio meanwhile does not move a message that is on its way, so that its attempts and the acks to them
stay on one channel. Two things move it: the operator chooses another radio for the station (Route), or the radio is no longer enabled (switched off, removed). Then the radio is asked again, the next
attempt is fitted to it (a message whose frame that radio cannot carry fails with the reason, services/retries.py `end_too_long`), and the message keeps the new one. The choice compared is the one in
force (a choice that names a radio that is off is none), so that a chosen radio switched on again takes the message. After a restart the radio of a message being sent is the one its last attempt went
on, as the delivery chain kept it (services/delivery.py), while the choice in force is none or that radio; a choice of another radio has moved it, and it is given the station's radio of now.

A radio that only stood in for the station's own is kept only until the station's own is on again: one that has never heard the station and that no Route names, given because the radio that heard the
station was off (messagerule.stood_in; the main radio of a station no radio had heard is the rule's choice, and kept). While a message is on such a radio and the station's radio of now is one that heard the
station, the next attempt goes on that one and the message keeps it; after a restart the attempts and what each radio heard of the station tell whether the last attempt's radio stood in.

The operator's choice is read from the station's radios where they have one (`Chooses`: the registry, neoaprs/stationchoices.py), and what each radio heard of the station likewise (`Knows`: the registry's
station book); radios that have none (a test's) have no choice to change and no radio that stands in."""
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
    """Radios that know the operator's radio for a station (the registry: neoaprs/stationchoices.py `choice`)."""
    def choice(self, call: str) -> RadioId | None: ...


@runtime_checkable
class Knows(Protocol):
    """Radios that know what each of them heard of a station (the registry: its station book)."""
    def station_of(self, call: str) -> Station | None: ...


class Kept(NamedTuple):
    """The radio a message keeps: its id, the operator's choice for the station in force when it was taken, and whether it only stood in for the station's own (messagerule.stood_in)."""
    radio: RadioId
    choice: RadioId | None
    stand_in: bool


def last_run(attempts: Sequence[Attempt]) -> tuple[RadioId, datetime] | None:
    """The radio the last of these attempts went on, and when the first of the attempts that went on it since the last on another was sent (when the message was given it); None for no attempt with a radio."""
    if not attempts or (radio := attempts[-1].radio_id) is None:
        return None
    since = attempts[-1].sent_at
    for attempt in reversed(attempts):
        if attempt.radio_id != radio:
            break
        since = attempt.sent_at
    return radio, since


def info(to: str, text: str, ident: str | None, reply: str | None) -> bytes:
    """The information field of a message: `:` and the body, with the reply-ack number `{ident}reply` ("" for none) when `reply` is given (the format's own refusals are told as MessagingError)."""
    try:
        return b":" + format_message(to, text, ident, reply)
    except MessageError as e:
        raise MessagingError(str(e)) from None


def named(name: str) -> str:
    """A station as the overheard messages name it: a call in its normal form, else (an addressee that is no call) the text as it is."""
    try:
        return normal_name(name)
    except CallsignError:
        return name.strip()


def station_radio(radios: RadioPick | Radio, config: ConfigSource, to: str) -> AirRadio:
    """The radio a message of ours to the station goes out on now: the station's (`for_station`); the email radio for the email gateway, which is a station of the internet reached through the iGates that hear
    the radio and never over HF, so a mail is refused (the code `message.email_fm_off`) while there is none. MessagingError while there is no radio at all."""
    pick = as_pick(radios, config)
    radio = pick.email() if to == EMAIL_GATEWAY else pick.for_station(to)
    if radio is None and to == EMAIL_GATEWAY:
        raise MessagingError("no radio that internet gateways hear is on", "message.email_fm_off")
    if radio is None:
        raise MessagingError(NO_RADIO)
    return radio


def _choice(pick: RadioPick, call: str) -> RadioId | None:
    """The operator's radio for the station in force: the one chosen while it is enabled; None for no choice, or one that names a radio that is off or gone."""
    chosen = pick.choice(call) if isinstance(pick, Chooses) else None
    return chosen if chosen is not None and any(r.id == chosen for r in pick.enabled()) else None


def _keep(pick: RadioPick, to: str, radio: RadioId, choice: RadioId | None, at: datetime) -> Kept:
    """The radio a message keeps from `at`, with the choice in force, and whether it only stands in for the station's own (never for the email gateway, whose radio is the email radio)."""
    station = pick.station_of(to) if isinstance(pick, Knows) and to != EMAIL_GATEWAY else None
    return Kept(radio, choice, station is not None and messagerule.stood_in(radio, choice, station.heard_by, station.first_heard, at))


def _leaves(pick: RadioPick, to: str, kept: Kept, on: bool, choice: RadioId | None) -> str | None:
    """Why a message leaves the radio it keeps (`on`: that radio is enabled), in the log's words; None while it keeps it."""
    if not on:
        return "the radio it went out on is off"
    if choice != kept.choice:
        return "no radio is chosen for the station any more" if choice is None else "the radio chosen for the station applies now"
    if kept.stand_in and isinstance(pick, Knows) and (station := pick.station_of(to)) is not None and station.heard_on(kept.radio).count == 0:
        now = pick.for_station(to)
        if now is not None and station.heard_on(now.id).count > 0:
            return "a radio that heard the station is on now"
    return None


class MessageRadios:
    """The radio each message of ours being sent keeps: the one its first attempt went on, with the operator's choice for the station in force at that time."""

    def __init__(self, radios: RadioPick | Radio, config: ConfigSource, last: Callable[[int], tuple[RadioId, datetime] | None]) -> None:
        self._given, self._config = radios, config              # the station's radios (the registry), read at each call
        self._last = last                                        # the radio the last attempt of a message went on and since when, as the delivery chain kept them (a restart: `last_run`); None for none
        self._kept: dict[int, Kept | None] = {}                  # by message: the radio it keeps; None: it left it, and takes the next it goes on

    def station(self, to: str) -> AirRadio:
        """The station's radio now (a new message, a message sent again from its first attempt). MessagingError while there is none."""
        return station_radio(self._given, self._config, to)

    def of(self, record: MessageRecord) -> AirRadio:
        """The radio the message goes out on: the one it keeps while that is enabled and the operator's choice for the station is the one of then; else the station's radio now (told in the log once, when the
        message leaves its radio). MessagingError while there is none."""
        pick = as_pick(self._given, self._config)
        choice = _choice(pick, record.to_call)
        kept = self._keeps(pick, record, choice)
        if kept is not None:
            self._kept[record.id] = kept
            radio = next((r for r in pick.enabled() if r.id == kept.radio), None)
            why = _leaves(pick, record.to_call, kept, radio is not None, choice)
            if radio is not None and why is None:
                return radio
            self._kept[record.id] = None
            log.info("message %d to %s goes on the radio the station is reached on now: %s", record.id, record.to_call, why)
        return self.station(record.to_call)

    def peek(self, record: MessageRecord) -> AirRadio:
        """The radio `of` gives now, with nothing kept and nothing logged (for the page's row). MessagingError while there is none."""
        pick = as_pick(self._given, self._config)
        choice = _choice(pick, record.to_call)
        kept = self._keeps(pick, record, choice)
        radio = None if kept is None else next((r for r in pick.enabled() if r.id == kept.radio), None)
        if kept is not None and radio is not None and _leaves(pick, record.to_call, kept, True, choice) is None:
            return radio
        return self.station(record.to_call)

    def _keeps(self, pick: RadioPick, record: MessageRecord, choice: RadioId | None) -> Kept | None:
        """The radio the message keeps; after a restart the one its last attempt went on, unless a choice of another radio moved it (made here, stored by `of` alone)."""
        if record.id not in self._kept and record.attempts > 0 and (last := self._last(record.id)) is not None and choice in (None, last[0]):
            return _keep(pick, record.to_call, last[0], choice, last[1])
        return self._kept.get(record.id)

    def sent(self, record: MessageRecord, radio: AirRadio, at: datetime) -> None:
        """An attempt of the message went out on the radio at `at`: the radio it keeps, when it keeps none yet."""
        if self._kept.get(record.id) is None:
            pick = as_pick(self._given, self._config)
            self._kept[record.id] = _keep(pick, record.to_call, radio.id, _choice(pick, record.to_call), at)

    def forget(self, number: int) -> None:
        """The message ended, or is sent again from its first attempt: it keeps no radio."""
        self._kept.pop(number, None)
