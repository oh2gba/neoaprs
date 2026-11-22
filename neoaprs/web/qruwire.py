"""Wire models of the QRU local-info command and the topic `qru`."""

from typing import Literal

from pydantic import Field

from .wirebase import Iso, PathText, _Command, _Model


class AskQru(_Command):
    """Asks the stations near us for local info (repeaters, events, places): one message to the addressee `QRU` (the services/qruask.py of the daemon), whose `text` is `INFO` (which groups are served near
    us?), `NEXT` (the next objects of the group asked for last) or a group of 1 to 8 upper-case letters and digits (`RP70`), with a distance in kilometres, 1 to 20000, after it (`INFO 250`). A request to QRU is a
    broadcast: it is sent once, with no message id, is not kept as a message and is not sent again; it goes by `path` when one is given (digipeater calls or aliases separated by commas, checked as a radio's
    path is, or `DIRECT` for none), else by the path of messages to the station QRU (its own path, else the radio's), with RFONLY after it unless `rf_only` is false: by radio only. With no `radio` it goes
    once on each radio of Local info's Send on (the radios whose `radio/<id>/local_info` is ticked; with one radio that can send, that one) that takes
    frames now; with `radio`, on that radio alone. The answers come as messages to us (they are rows of the topic `messages` like any message) and as the topic `qru`; the objects arrive as objects. All or
    nothing: answered with an `error`, and nothing is sent on any radio, when the text is none, RX only is ticked or no call is set (`transmit.off`, or the interlock's reason), there is no radio
    (`radio.none`) or none takes frames now, a request to QRU went on one of its radios less than 60 seconds ago with the same text or any less than 10 seconds ago (`qru.too_soon`, with the `seconds` that
    are left, the longest), or the path is no path or too long with RFONLY (`path.*`, `call.*`)."""

    cmd: Literal["qru_ask"]
    text: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9]{1,8}( \d{1,5})?$")
    path: PathText | None = Field(
        default=None,
        description="the path the request goes by; left out (or null, or empty) the path of messages to QRU",
    )
    rf_only: bool = Field(default=True, description="RFONLY after the path; left out it is true")
    radio: int | None = Field(
        default=None,
        ge=1,
        description="the one radio the request goes on, its id: the radio a server answered on (`QruServer.radio`), for a request of a group it listed or one asked again; left out: the radios of Local info's Send on. Refused with `radio.unknown` for a radio that is none, `radio.off` for one that is off, `radio.receive_only` for one that only receives and `radio.not_connected` for one that is not connected",
    )


class QruGroup(_Model):
    """A group of objects a server serves near us."""

    name: str = Field(description="the group, 1 to 8 upper-case letters and digits (`RP70`, `FOOD`)")
    count: int = Field(ge=0, description="how many objects the group has in the server's range")


class QruServer(_Model):
    """A QRU server that answered, as it last said."""

    call: str = Field(description="the server's call")
    groups: list[QruGroup] = Field(
        description="the groups it serves near us, in the order it listed them; empty when it has only sent the closing line of a group"
    )
    max_objects: int | None = Field(
        description="the most objects it sends for one request; null when its list did not say"
    )
    range: int | None = Field(description="the range round us it serves, in `unit`; null when its list did not say")
    unit: Literal["km", "mi", ""] = Field(
        description="the unit of `range` (kilometres or miles, as the server counts); empty when the list did not say"
    )
    at: Iso = Field(description="when it answered last")
    sent: str = Field(
        description="its last closing line as it was heard (`Sent 5 RP70 Objects Max 5@50km de DF8LS-10`); empty before one"
    )
    sent_at: Iso | None = Field(description="when the closing line was heard; null before one")
    sent_objects: int | None = Field(description="how many objects its last closing line says it sent; null before one")
    request: str = Field(
        description="the request its closing line answers, which Ask again sends once more (`TEST 150`); empty before a closing line, and when the request is not known"
    )
    received: list[str] = Field(
        description="the names of the objects heard from the server, on a radio that request went on, since it, until `settles_at` (or the last answer, before a closing line); each is an ordinary object of the stations and the map"
    )
    settles_at: Iso | None = Field(
        description="when the counting of `received` ends, 30 seconds after the closing line (a late object may still come); null before a closing line. Fewer `received` than `sent_objects` after it means objects were lost"
    )
    radio: int | None = Field(
        description="the radio its latest answer came on, its id: a request of one of its groups, and one asked again, goes on it; null when the packet named none"
    )


class QruAsked(_Model):
    """The request we sent last."""

    text: str = Field(description="what was asked (`INFO`, `RP70 150`)")
    at: Iso = Field(description="when it was sent")
    radios: list[int] = Field(description="the radios it went on, their ids, in the order of their boxes")


class QruState(_Model):
    """The servers that answered a request for local info, and the last request. What is older than an hour is forgotten, with the daemon's restart. Told whole as it changes."""

    asked: QruAsked | None = Field(description="the last request sent from here; null before one, and an hour after it")
    servers: list[QruServer] = Field(description="the servers that answered in the last hour, by call")
