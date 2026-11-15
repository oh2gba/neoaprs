"""The commands that name a radio, on the wire: add one, remove one, change its name, type, Enable or place, work its modem (Tune, the keying test, the scope), and choose the radio a station's messages go out on;
and the message that answers an add. The radios themselves are the topic `radios` (neoaprs/web/tncwire.py `RadioRow`), and a radio's own settings ride `set_config` and the topic `config` under `radio/<id>/<key>`.
Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`.

A radio is named by its id (`radio`, an integer from 1: the `id` of its row). A refusal is an `error` with a code: `radio.unknown` (no radio of that id, or one that is removed), `radio.last_enabled` (the last radio that is on
cannot be switched off or removed), `radio.name_taken`, `radio.name_label` (a name typed in the form a radio with no name of its own is called by, "FM", "HF 2"), `radio.name_form`, `radio.type_kind` (a type of another kind), `radio.unknown_type`, `radio.off` (the radio a control sends on is switched off, with its `name`),
`radio.receive_only` (the radio a control sends on, or Find my radio's, is of a type that only receives, with its `name`), `radio.not_connected` (it is on and does not take frames now, with its `name`), `radio.no_modem` (a modem's command on a radio that has none running, with its `name`), `radio.no_line` (Find my radio for a radio
with no serial line, with its `name`), `radio.no_scope` (the scope of a radio whose type has none, with its `name`), `radio.none` (there is no radio at all), `setting.not_stored` (the change was not stored: the reason is in the log).
A refusal that names a radio by its `name` (the daemon's English: the name typed, else its kind's word and number, "FM", "HF 2") carries its id too (`radio`), and `radio.resource_held` the holder's id beside its `holder`
(`held_by`: the radio's, 0 for the GPS receiver, as the ports' `held_by`), by which a page puts its own words for that radio. A removed radio is `radio.unknown` with its `name` and `removed` 1 too."""
from typing import Annotated, Literal

from pydantic import Field

from .wirebase import Call, _Command, _Message

RADIO_NAME_ROOM = 64                     # a radio's name as typed: the daemon says what is wrong with one (at most 8 printable characters, coded), with room over it
TYPE_ROOM = 32                           # a type's key as sent

RadioRef = Annotated[int, Field(ge=1, description="the radio's id, the `id` of its row in the topic `radios`")]


class RadioAdd(_Command):
    """Adds a radio of the type (`type`, a `key` of `RADIO_TYPES`): after the others, enabled, with the defaults of its kind, the name typed (empty or left out: none), and started at once. Answered with `radio_added` (its
    id) to the page that asked, at once, and then the `set` of its row in `radios` (the topic is told at most four times a second: the row may come a few messages later, so a page that opens the new radio waits
    for it), or with an `error`: `radio.unknown_type`, `radio.name_form`, `radio.name_taken`, `radio.name_label`, `setting.not_stored`."""
    cmd: Literal["radio_add"]
    type: str = Field(min_length=1, max_length=TYPE_ROOM)
    name: str = Field(default="", max_length=RADIO_NAME_ROOM, description="the name typed; left out or empty: none")


class RadioAddedMsg(_Message):
    """The answer to `radio_add`, to the page that asked: the id the new radio was given."""
    type: Literal["radio_added"]
    id: int = Field(ge=1)


class RadioRemove(_Command):
    """Removes the radio: it is stopped for good, and in the same write its id leaves the objects' sets, the stations' choices of it and their paths on it. Its row stays in `radios`, `removed`, so that what came by it keeps
    its name. Answered by the row, or an `error`: `radio.unknown`, `radio.last_enabled` (the last radio that is on stays), `setting.not_stored`."""
    cmd: Literal["radio_remove"]
    radio: RadioRef


class RadioChange(_Command):
    """Changes what is given of the radio and nothing else: its `name` (empty: none), its `type` (one of its own kind), its Enable (`enabled`) or its place in the list (`position`, from 1; the others keep theirs, a tie goes by
    id). Stored, then in force; the radio is restarted when its type or its Enable changed what runs. Answered by the row, or an `error`: `radio.unknown`, `radio.last_enabled` (the last radio that is on is not switched off),
    `radio.name_form`, `radio.name_taken`, `radio.name_label`, `radio.type_kind`, `radio.unknown_type`, `setting.not_stored`."""
    cmd: Literal["radio_change"]
    radio: RadioRef
    name: str | None = Field(default=None, max_length=RADIO_NAME_ROOM, description="the new name; left out: unchanged")
    type: str | None = Field(default=None, min_length=1, max_length=TYPE_ROOM, description="the new type; left out: unchanged")
    enabled: bool | None = Field(default=None, description="the new Enable; left out: unchanged")
    position: int | None = Field(default=None, ge=1, description="the new place; left out: unchanged")


class RadioTune(_Command):
    """Tune on the radio's modem: with `on`, keys the radio through its keying and sends a steady tone (1000 Hz, Mercury's own TUNE) through its sound card for ten seconds, then stops by itself; with `on` false, stops it early. The radio's row says `modem.test: "tune"`
    meanwhile. Answered with an `error` for a radio that is none (`radio.unknown`), whose type has no modem or whose modem is not running (`radio.no_modem`, with its `name`), while RX only is ticked (`transmit.off`) and
    while a frame is on the air or the channel is busy (`hf.held`)."""
    cmd: Literal["radio_tune"]
    radio: RadioRef
    on: bool = Field(description="true starts the tone, false stops it")


class RadioKeyTest(_Command):
    """The keying test on the radio's modem: keys it for one second, so that the operator sees it go to transmit and come back: with next to no audio (Mercury's TUNE at its quietest level) where the keying is a
    line (RTS, DTR, CM108), with the tune tone where the radio keys on audio (VOX); the radio's row says `modem.test: "key"` meanwhile. The same refusals as `radio_tune`."""
    cmd: Literal["radio_key_test"]
    radio: RadioRef


class RadioScope(_Command):
    """The scope of the radio's modem: with `on`, this page is sent the rows of its waterfall as binary frames that name the radio (*Binary frames*), first the rows kept and then the rows as they come, with `on`
    false, or when the page closes, no more. Several radios can be looked at at once. Nothing comes while the radio's modem is not running or has no interface (its row's `modem.scope`). Refused, with `on`, for a radio that is none
    (`radio.unknown`) and for one whose type has no scope (`radio.no_scope`, with its `name`: `can.scope` of its row is false); `on` false is never refused."""
    cmd: Literal["radio_scope"]
    radio: RadioRef
    on: bool = Field(description="true starts the rows for this page, false stops them")


class StationRadio(_Command):
    """Chooses the radio messages to a station go out on (`radio`, or null to leave it to the daemon again: plan rule 3.2, the radio that heard it lately, a local one before HF). It holds from the next attempt on, also of a
    message on its way, and across a restart; the station's row says it (`radio_choice`, and `radio_now` the radio a message takes now). A radio that is off is no choice: the station's row says null while it is. For a
    station of the book it is answered by the station's row (and the `radio_now` of each message to it on its way); a call the book does not hold is chosen for too (plan rule 3.2: the choice is kept by call), with no
    answer, and its station's row says it once the station is heard. The call is kept in its normal form, as a message names it (upper case, no SSID 0). Refused with an `error`: `radio.unknown` (no radio of that
    id that is not removed), `radio.receive_only` (a radio of a type that only receives, with its `name`), or a `call.*` code for a text that is no call."""
    cmd: Literal["station_radio"]
    call: Call
    radio: RadioRef | None
