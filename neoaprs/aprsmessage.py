"""APRS messages: addressee, text, message id, acks and rejects, and the reply-ack `{MM}AA`."""

import re

from neoaprs.coded import CodedError
from neoaprs.packet import Message, decode_text

_ADDRESSEE_LEN = 9
MAX_ID = 5
_ID_CHARS = "[A-Za-z0-9]"
_ID = re.compile(f"{_ID_CHARS}{{1,{MAX_ID}}}")
_NUMBER = re.compile(rf"\{{({_ID_CHARS}{{1,{MAX_ID}}})(\}}{_ID_CHARS}{{0,{MAX_ID}}})?$")
_ACK = re.compile(rf"(ack|rej)({_ID_CHARS}{{1,{MAX_ID}}})(?:\}}{_ID_CHARS}{{0,{MAX_ID}}})?$")
MAX_TEXT = 67
FORBIDDEN = "|~{"
_TRAILING = " \r\n"  # some senders append these; not part of an id or ack


class MessageError(CodedError):
    """Not a message, or a message that cannot be sent."""


def _split_id(text: str) -> tuple[str, str | None]:
    """Return the text without its trailing "{id" or "{id}AA", and the id."""
    found = _NUMBER.search(text)
    if found is None:
        return text, None
    return text[:found.start()], found.group(1)


def reply_ack_of(text: str) -> str | None:
    """Return the `AA` of a trailing `{MM}AA`; "" for `{MM}`, None for no reply-ack."""
    found = _NUMBER.search(text.rstrip(_TRAILING))
    if found is None or found.group(2) is None:
        return None
    return found.group(2)[1:]


def _split(body: bytes) -> tuple[str, str] | None:
    """Return the addressee and text of a message body; None if there is no addressee field.

    An unpadded addressee (`KH2Z:hi`, ended by the first colon) is accepted.
    """
    end = _ADDRESSEE_LEN if body[_ADDRESSEE_LEN:_ADDRESSEE_LEN + 1] == b":" else body.find(b":", 0, _ADDRESSEE_LEN)
    if end < 0:
        return None
    return decode_text(body[:end]).rstrip(" "), decode_text(body[end + 1:]).rstrip("\r\n")


def line_of(info: bytes) -> str | None:
    """Return the text with its number (`Hello{12}AB`) of an information field, or None."""
    found = _split(info[1:]) if info[:1] == b":" else None
    return None if found is None or not found[0] else found[1]


def parse_message(body: bytes) -> Message:
    """Return the `Message` of a body; raise MessageError if it is none."""
    found = _split(body)
    if found is None:
        raise MessageError("no colon after the nine-character addressee")
    addressee, text = found
    if not addressee:
        raise MessageError("empty addressee")
    bare = text.rstrip(_TRAILING)
    ack = _ACK.match(bare)
    if ack:
        return Message(addressee, "", ack_id=ack.group(2)) if ack.group(1) == "ack" else Message(addressee, "", rej_id=ack.group(2))
    head, msg_id = _split_id(bare)
    return Message(addressee, text) if msg_id is None else Message(addressee, head, msg_id)


def _check_addressee(addressee: str) -> str:
    if not 1 <= len(addressee) <= _ADDRESSEE_LEN or addressee != addressee.strip() or ":" in addressee or not addressee.isascii() or not addressee.isprintable():
        raise MessageError(f"{addressee!r} cannot be the addressee of a message", "message.addressee", addressee=addressee)
    return addressee.ljust(_ADDRESSEE_LEN)


def _check_id(msg_id: str) -> str:
    if not _ID.fullmatch(msg_id):
        raise MessageError(f"bad message id {msg_id!r}", "failed")
    return msg_id


def format_message(addressee: str, text: str, msg_id: str | None = None, reply_ack: str | None = None) -> bytes:
    """Return the body of a message packet; `reply_ack` (needs an id) adds `}` or `}AA`.

    Raise MessageError for text that reads as an ack or is not printable ASCII.
    """
    padded = _check_addressee(addressee)
    if any(c in text for c in FORBIDDEN) or not text.isprintable() or not text.isascii() or len(text) > MAX_TEXT:
        raise MessageError("the text has a character a message cannot carry, or is too long", "message.bad_text")
    if _ACK.match(text.rstrip(_TRAILING)):
        raise MessageError("the text reads as an ack or a reject", "message.reads_as_ack")
    ident = "" if msg_id is None else "{" + _check_id(msg_id)
    if reply_ack is not None:
        if msg_id is None:
            raise MessageError("a reply-ack needs a message id", "failed")
        ident += "}" + (_check_id(reply_ack) if reply_ack else "")
    return f"{padded}:{text}{ident}".encode("ascii")


def format_ack(addressee: str, msg_id: str, reply_ack: str | None = None) -> bytes:
    """Return the body of the ack of message `msg_id`, with the reply-ack if given."""
    tail = "" if reply_ack is None else "}" + (_check_id(reply_ack) if reply_ack else "")
    return f"{_check_addressee(addressee)}:ack{_check_id(msg_id)}{tail}".encode("ascii")
