"""The radio a message of ours goes out on (plan rule 3.2), for services/messaging.py, with the two helpers of its frames.

The radio of a message to a station is the station's (`station_radio`: the registry's `for_station`, neoaprs/messagerule.py), and for the email gateway the email radio. It is asked at the message's first
attempt, and the message keeps that radio until it ends (`MessageRadios`): a station heard on another radio meanwhile does not move a message that is on its way, so that its attempts and the acks to them
stay on one channel. Two things move it: the operator chooses another radio for the station (Route), or the radio is no longer enabled (switched off, removed). Then the radio is asked again, the next
attempt is fitted to it (a message whose frame that radio cannot carry fails with the reason, services/retries.py `end_too_long`), and the message keeps the new one. The choice compared is the one in
force (a choice that names a radio that is off is none), so that a chosen radio switched on again takes the message. After a restart the radio of a message being sent is the one its last attempt went
on, as the delivery chain kept it (services/delivery.py), while the choice in force is none or that radio; a choice of another radio has moved it, and it is given the station's radio of now.

The operator's choice is read from the station's radios where they have one (`Chooses`: the registry, neoaprs/stationchoices.py); radios that have none (a test's) have no choice to change."""
import logging
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from neoaprs.aprsmessage import MessageError, format_message
from neoaprs.callsign import CallsignError, normal_name
from neoaprs.message import EMAIL_GATEWAY, MessageRecord, MessagingError
from neoaprs.radiotype import RadioId
from neoaprs.services.answers import as_pick
from neoaprs.services.common import ConfigSource, Radio
from neoaprs.services.radioset import NO_RADIO, AirRadio, RadioPick

log = logging.getLogger("neoaprs.messaging")


@runtime_checkable
class Chooses(Protocol):
    """Radios that know the operator's radio for a station (the registry: neoaprs/stationchoices.py `choice`)."""
    def choice(self, call: str) -> RadioId | None: ...


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
        raise MessagingError("email goes out over the FM radio, which is off", "message.email_fm_off")
    if radio is None:
        raise MessagingError(NO_RADIO)
    return radio


def _choice(pick: RadioPick, call: str) -> RadioId | None:
    """The operator's radio for the station in force: the one chosen while it is enabled; None for no choice, or one that names a radio that is off or gone."""
    chosen = pick.choice(call) if isinstance(pick, Chooses) else None
    return chosen if chosen is not None and any(r.id == chosen for r in pick.enabled()) else None


class MessageRadios:
    """The radio each message of ours being sent keeps: the one its first attempt went on, with the operator's choice for the station in force at that time."""

    def __init__(self, radios: RadioPick | Radio, config: ConfigSource, last: Callable[[int], RadioId | None]) -> None:
        self._given, self._config = radios, config              # the station's radios (the registry), read at each call
        self._last = last                                        # the radio the last attempt of a message went on, as the delivery chain kept it (a restart); None for none
        self._kept: dict[int, tuple[RadioId, RadioId | None] | None] = {}    # by message: the id of its radio and the operator's choice in force for the station when it was taken; None: it left it, and takes the next it goes on

    def station(self, to: str) -> AirRadio:
        """The station's radio now (a new message, a message sent again from its first attempt). MessagingError while there is none."""
        return station_radio(self._given, self._config, to)

    def of(self, record: MessageRecord) -> AirRadio:
        """The radio the message goes out on: the one it keeps while that is enabled and the operator's choice for the station is the one of then; else the station's radio now (told in the log once, when the
        message leaves its radio). MessagingError while there is none."""
        pick = as_pick(self._given, self._config)
        choice = _choice(pick, record.to_call)
        if record.id not in self._kept and record.attempts > 0 and (last := self._last(record.id)) is not None and choice in (None, last):
            self._kept[record.id] = (last, choice)                  # (a restart: the radio its last attempt went on, unless a choice of another radio moved it)
        kept = self._kept.get(record.id)
        if kept is not None:
            radio = next((r for r in pick.enabled() if r.id == kept[0]), None)
            if radio is not None and choice == kept[1]:
                return radio
            self._kept[record.id] = None
            why = "the radio it went out on is off" if radio is None else "no radio is chosen for the station any more" if choice is None else "the radio chosen for the station applies now"
            log.info("message %d to %s goes on the radio the station is reached on now: %s", record.id, record.to_call, why)
        return self.station(record.to_call)

    def sent(self, record: MessageRecord, radio: AirRadio) -> None:
        """An attempt of the message went out on the radio: the radio it keeps, when it keeps none yet."""
        if self._kept.get(record.id) is None:
            self._kept[record.id] = (radio.id, _choice(as_pick(self._given, self._config), record.to_call))

    def forget(self, number: int) -> None:
        """The message ended, or is sent again from its first attempt: it keeps no radio."""
        self._kept.pop(number, None)
