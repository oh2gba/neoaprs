"""The sked board on the wire: the topic `skeds` (when people will be on the air, as the project's server keeps it) and the commands that ask for the board and post and delete a sked of ours. Models like the rest of the protocol, listed in
`neoaprs/web/protocol.py`. A sked's times are `from` and `to` on the wire; the models name the fields `from_` and `to` and say `from` as their alias, since `from` is a word of Python."""
from typing import Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from neoaprs.skeds import ID, MAX_NOTE, MAX_LENGTH, when
from neoaprs.versions import is_dial

from .wirebase import Iso, _Command, _Model

DIAL_PATTERN = r"^\d{1,2}\.\d{3,4} MHz (USB|LSB)$"
ID_PATTERN = ID.pattern


class SkedFrequency(_Model):
    """A dial the project suggests for the HF radio."""
    band: str = Field(description="the band, `40 m`")
    dial: str = Field(description="the dial with its mode, `7.0541 MHz USB`")


class SkedRow(_Model):
    """A sked on the board: a call on the air at a dial from one instant to another. Every row was checked again by the daemon; the note is one line of at most 80 characters of letters, digits, punctuation and plain spaces."""
    model_config = ConfigDict(serialize_by_alias=True)
    id: str = Field(pattern=ID_PATTERN, description="the sked's id, 12 lowercase hex characters, which `sked_delete` names")
    call: str = Field(description="the call that will be on the air, upper case without an SSID of 0 (`OH2GBA`, `OH2GBA-7`)")
    from_: Iso = Field(alias="from", description="when it begins (the field is called `from` on the wire)")
    to: Iso = Field(description="when it ends, after `from` by 24 hours at most; a sked that has ended by the daemon's clock is not told")
    dial: str = Field(pattern=DIAL_PATTERN, description="the dial with its mode, `7.0541 MHz USB`")
    note: str = Field(max_length=MAX_NOTE, description="a short note, may be empty (`Mercury, 10 W`); the page shows it as text")
    ours: bool = Field(description="this installation posted it, so `sked_delete` takes it off the board; no other row can be deleted from here")


class SkedsState(_Model):
    """The sked board: where it stands, the dials the project suggests, and the skeds to come, the nearest first. The value of the topic `skeds`, told whole as it changes (a read of the board, a post, a delete, a sked that ends)."""
    state: Literal["ok", "offline", "off", "closed"] = Field(
        description="`ok`: the board was read (or has not been tried yet), and a sked may be posted. `offline`: the project's server could not be reached or its answer was not a board; `rows` are the last board known, and posting is off. `off`: the check is off "
                    "(`NEOAPRS_UPDATE_CHECK=0`): nothing is read or posted, `rows` is empty. `closed`: the board is closed to new skeds (by the project, or for this call); `rows` are shown without the form")
    fetched_at: Iso | None = Field(description="when the board was last read from the server (or when the one kept from the last run was); null before the first")
    frequencies: list[SkedFrequency] = Field(max_length=3, description="the dials the project suggests for the HF radio, one to three, the same as `modem.frequencies` of the topic `hf` (the tab does not depend on a radio's state)")
    rows: list[SkedRow] = Field(max_length=100, description="the skeds to come by the daemon's clock, the nearest start first; empty when there are none")


class SkedsWanted(_Command):
    """The page shows the Skeds tab (and while it stays visible): the daemon reads the board now, unless it read it less than 15 minutes ago or the update check is off (`NEOAPRS_UPDATE_CHECK=0`). Nothing is answered; the topic `skeds` tells what came."""
    cmd: Literal["skeds_wanted"]


class SkedPost(_Command):
    """Posts a sked of ours on the board of the project's server: our call (the setting `station/call`), `from` and `to` in UTC (`to` after `from` by 24 hours at most, not past, `from` not more than 30 days ahead), a `dial` in the form of the HF
    box and a `note` of at most 80 characters (control and invisible characters are made spaces). It goes only on this command, and carries the call, the two times, the dial, the note and this installation's secret token. Answered by the topic `skeds`, whose
    rows then have it with `ours` true. An `error` when no call is set (the interlock's reason; RX only does not matter, nothing is sent by radio), the sked has ended (`sked.past`) or begins more than 30 days ahead by the daemon's or the server's clock (`sked.far`), too many were posted from here lately (`sked.rate`), the board has no
    room (`sked.full`), or the project's server could not be reached or would not take it (`sked.unreachable`). A board that is closed to the call is no error: the state of the topic says `closed`."""
    model_config = ConfigDict(serialize_by_alias=True)
    cmd: Literal["sked_post"]
    from_: Iso = Field(alias="from", description="UTC, ISO 8601 with a Z; the field is called `from` on the wire")
    to: Iso
    dial: str = Field(pattern=DIAL_PATTERN)
    note: str = Field(max_length=MAX_NOTE * 4, description="at most 80 characters once cleaned; empty for none")

    @field_validator("from_", "to")
    @classmethod
    def _real(cls, text: str) -> str:
        if when(text) is None:
            raise ValueError("not a time")
        return text

    @field_validator("dial")
    @classmethod
    def _dial(cls, text: str) -> str:
        if not is_dial(text):
            raise ValueError("not a dial")
        return text

    @model_validator(mode="after")
    def _order(self) -> "SkedPost":
        start, end = when(self.from_), when(self.to)
        if start is None or end is None or not start < end <= start + MAX_LENGTH:
            raise ValueError("to must be after from by 24 hours at most")
        return self


class SkedDelete(_Command):
    """Deletes a sked that this installation posted, by its id: the server takes it off the board for everybody. A sked that is not ours (another installation posted it, or the data folder is another one) is only dropped from `ours`: nothing is said, and the
    board is read again. An `error` (`sked.unreachable`) when the project's server could not be reached. The topic `skeds` tells the new board."""
    cmd: Literal["sked_delete"]
    id: str = Field(pattern=ID_PATTERN)
