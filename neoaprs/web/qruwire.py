"""QRU on the wire: the command to ask for local info and the topic `qru`, the servers that answered. Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import Iso, _Command, _Model


class AskQru(_Command):
    """Asks the stations near us for local info (repeaters, events, places): one message to the addressee `QRU` (the services/qruask.py of the daemon), whose `text` is `INFO` (which groups are served near
    us?), `NEXT` (the next objects of the group asked for last) or a group of 1 to 8 upper-case letters and digits (`RP70`), with a distance in kilometres, 1 to 20000, after it (`INFO 250`). A request to QRU is a
    broadcast: it is sent once, with no message id, is not kept as a message and is not sent again; it goes by the path of messages with RFONLY after it, by radio only. The answers come as messages to us (they are
    rows of the topic `messages` like any message) and as the topic `qru`; the objects arrive as objects. Answered with an `error` when the text is none, RX only is ticked or no call is set (`transmit.off`, or the
    interlock's reason), the radio is away, or the same request was sent less than 30 seconds ago (`qru.too_soon`, with the `seconds` that are left)."""
    cmd: Literal["qru_ask"]
    text: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9]{1,8}( \d{1,5})?$")


class QruGroup(_Model):
    """A group of objects a server serves near us."""
    name: str = Field(description="the group, 1 to 8 upper-case letters and digits (`RP70`, `FOOD`)")
    count: int = Field(ge=0, description="how many objects the group has in the server's range")


class QruServer(_Model):
    """A QRU server that answered, as it last said."""
    call: str = Field(description="the server's call")
    groups: list[QruGroup] = Field(description="the groups it serves near us, in the order it listed them; empty when it has only sent the closing line of a group")
    max_objects: int | None = Field(description="the most objects it sends for one request; null when its list did not say")
    range: int | None = Field(description="the range round us it serves, in `unit`; null when its list did not say")
    unit: Literal["km", "mi", ""] = Field(description="the unit of `range` (kilometres or miles, as the server counts); empty when the list did not say")
    at: Iso = Field(description="when it answered last")
    sent: str = Field(description="its last closing line as it was heard (`Sent 5 RP70 Objects Max 5@50km de DF8LS-10`); empty before one")
    sent_at: Iso | None = Field(description="when the closing line was heard; null before one")


class QruAsked(_Model):
    """The request we sent last."""
    text: str = Field(description="what was asked (`INFO`, `RP70 150`)")
    at: Iso = Field(description="when it was sent")


class QruState(_Model):
    """The servers that answered a request for local info, and the last request. What is older than an hour is forgotten, with the daemon's restart. Told whole as it changes."""
    asked: QruAsked | None = Field(description="the last request sent from here; null before one, and an hour after it")
    servers: list[QruServer] = Field(description="the servers that answered in the last hour, by call")
