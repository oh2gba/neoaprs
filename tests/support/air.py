"""What the radio says and what is said to it, for the tests that put messages through the radio of an `Env`: `on_air` is a KISS frame the TNC would hand over, `said` the frames the daemon has written.

    e.feed(on_air("OH2RDG-7", message_info("OH2GBA", "Moi!", "12")))       # a station sends us a message
    from_internet("OH2RDG-7", message_info("OH2GBA", "Moi!", "12"), at)    # the same, as APRS-IS hands it on
    frames = await said(e)                                                  # what the daemon put on the line in answer: the ack
"""
import asyncio
from datetime import datetime
from typing import Protocol

from neoaprs import ax25, kiss
from neoaprs.aprsisline import parse_is_line
from neoaprs.aprsmessage import format_ack, format_message
from neoaprs.packet import Packet


def on_air(source: str, info: bytes, destination: str = "APRS", path: str = "WIDE1-1") -> bytes:
    """A frame from `source`, as the TNC delivers it over KISS."""
    return kiss.encode(ax25.encode(ax25.Frame(ax25.Address.parse(destination), ax25.Address.parse(source), tuple(ax25.Address.parse(p) for p in path.split(",") if p), info=info)))


def message_info(addressee: str, text: str, msg_id: str | None = None, reply: str | None = None) -> bytes:
    """A message; with `reply` its number is the reply-ack form `{msg_id}reply` (`{msg_id}` for ""). A text the format refuses (an ack word) is not made."""
    return b":" + format_message(addressee, text, msg_id, reply)


def ack_info(addressee: str, msg_id: str, reply: str | None = None) -> bytes:
    return b":" + format_ack(addressee, msg_id, reply)


def reject_info(addressee: str, msg_id: str) -> bytes:
    return f":{addressee:<9}:rej{msg_id}".encode()


def from_internet(source: str, info: bytes, at: datetime, destination: str = "APRS", path: str = "TCPIP*,qAC,T2FINLAND") -> Packet:
    """A packet as APRS-IS hands it on, parsed the way the connection to it does (`parse_is_line`): `via` is `is`."""
    return parse_is_line(f"{source}>{destination},{path}:".encode() + info, at)


class Hears(Protocol):
    """What `said` needs of a world: the `Env` of tests/support/env.py."""
    async def heard(self, count: int = 1, timeout_sec: float = 2.0) -> bytes: ...


async def said(radio: Hears, count: int = 1, timeout_sec: float = 2.0) -> list[ax25.Frame]:
    """The frames the daemon has written to the radio, waiting until `count` of them came (or the time is up)."""
    out: list[ax25.Frame] = []
    decoder = kiss.KissDecoder()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_sec
    while len(out) < count and loop.time() < deadline:
        out += [ax25.decode(f.payload) for f in decoder.feed(await radio.heard(1, max(0.0, deadline - loop.time())))]
    return out
