"""APRS messages: the addressee, the text, the message id, acks and rejects, and the reply-ack.

`parse_message` takes the bytes that follow the data type identifier ":" and `format_message` and `format_ack` make the same kind of bytes (the caller puts the ":" in front).

A reply-ack (WB4APR's addendum of December 1999) is a message number of the form `{MM}AA`: `MM` is the number of the message and `AA` the number of a message the sender has received from the addressee and
not yet acknowledged by a frame of its own, so that the acknowledgement rides on the next message; `{MM}` alone says the sender knows the form. `parse_message` gives the message its `MM` and the text before
the brace; `reply_ack_of` reads the rest. The ack of such a message is `ackMM}AA` (a copy of the number), and the id of an ack it takes is the `MM` before the brace."""
import re

from neoaprs.packet import Message, decode_text

_ADDRESSEE_LEN = 9
_ID = re.compile(r"[A-Za-z0-9]{1,5}$")
_NUMBER = re.compile(r"\{([A-Za-z0-9]{1,5})(\}[A-Za-z0-9]{0,5})?$")      # the message number at the end of a text: "{MM", "{MM}" or "{MM}AA"
_ACK = re.compile(r"(ack|rej)([A-Za-z0-9]{1,5})(?:\}[A-Za-z0-9]{0,5})?$")
MAX_TEXT = 67                                        # characters of message text the specification allows
FORBIDDEN = "|~{"


class MessageError(ValueError):
    """A body that is not a message, or a message that cannot be sent."""


def _split_id(text: str) -> tuple[str, str | None]:
    """The text without its trailing "{id" (or "{id}reply-ack") and the id."""
    found = _NUMBER.search(text)
    if found is None:
        return text, None
    return text[:found.start()], found.group(1)


def reply_ack_of(text: str) -> str | None:
    """The reply-ack part of the message number a text ends with: None for a text with no number or an old-style `{MM`, "" for `{MM}` (the sender knows reply-acks, nothing to acknowledge), the `AA` of `{MM}AA`."""
    found = _NUMBER.search(text)
    if found is None or found.group(2) is None:
        return None
    return found.group(2)[1:]


def line_of(info: bytes) -> str | None:
    """The text of the message a packet's information field holds, with its message number (`Hello{12}AB`); None when the field is no message."""
    if len(info) < _ADDRESSEE_LEN + 2 or info[:1] != b":" or info[_ADDRESSEE_LEN + 1:_ADDRESSEE_LEN + 2] != b":":
        return None
    return decode_text(info[_ADDRESSEE_LEN + 2:]).rstrip("\r\n")


def parse_message(body: bytes) -> Message:
    if len(body) < _ADDRESSEE_LEN + 1 or body[_ADDRESSEE_LEN:_ADDRESSEE_LEN + 1] != b":":
        raise MessageError("no colon after the nine-character addressee")
    addressee = decode_text(body[:_ADDRESSEE_LEN]).rstrip(" ")
    if not addressee:
        raise MessageError("empty addressee")
    text = decode_text(body[_ADDRESSEE_LEN + 1:]).rstrip("\r\n")
    ack = _ACK.match(text)
    if ack:
        return Message(addressee, "", ack_id=ack.group(2)) if ack.group(1) == "ack" else Message(addressee, "", rej_id=ack.group(2))
    text, msg_id = _split_id(text)
    return Message(addressee, text, msg_id)


def _check_addressee(addressee: str) -> str:
    if not 1 <= len(addressee) <= _ADDRESSEE_LEN or addressee != addressee.strip() or ":" in addressee or not addressee.isascii() or not addressee.isprintable():
        raise MessageError(f"bad addressee {addressee!r}")
    return addressee.ljust(_ADDRESSEE_LEN)


def _check_id(msg_id: str) -> str:
    if not _ID.match(msg_id):
        raise MessageError(f"bad message id {msg_id!r}")
    return msg_id


def format_message(addressee: str, text: str, msg_id: str | None = None, reply_ack: str | None = None) -> bytes:
    """The body of a message packet: addressee padded to nine characters, ":", the text, "{id". With `reply_ack` (needs an id) the number is `{id}` ("" for nothing to acknowledge) or `{id}AA`. Text that would
    read back as something else (an ack, a "{") or that is not printable ASCII is refused."""
    padded = _check_addressee(addressee)
    if any(c in text for c in FORBIDDEN) or not text.isprintable() or not text.isascii() or len(text) > MAX_TEXT:
        raise MessageError("text with a forbidden character, or too long")
    if _ACK.match(text):
        raise MessageError("text that reads as an ack or a reject")
    ident = "" if msg_id is None else "{" + _check_id(msg_id)
    if reply_ack is not None:
        if msg_id is None:
            raise MessageError("a reply-ack needs a message id")
        ident += "}" + (_check_id(reply_ack) if reply_ack else "")
    return f"{padded}:{text}{ident}".encode("ascii")


def format_ack(addressee: str, msg_id: str, reply_ack: str | None = None) -> bytes:
    """The body of the ack of message `msg_id`; of a message with a reply-ack `AA` it is `ack` and the number as it came, `msg_id}AA`."""
    tail = "" if not reply_ack else "}" + _check_id(reply_ack)
    return f"{_check_addressee(addressee)}:ack{_check_id(msg_id)}{tail}".encode("ascii")
