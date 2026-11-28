"""KISS frames for tests that put messages through an `Env` radio.

`on_air` builds a frame the TNC would hand over, `from_internet` a packet as APRS-IS hands it on,
`said` returns the frames the daemon has written.
"""

import asyncio
from datetime import datetime
from typing import Protocol

from neoaprs import ax25, kiss
from neoaprs.aprsisline import parse_is_line
from neoaprs.aprsmessage import format_ack, format_message
from neoaprs.packet import Packet
from tests.support.patience import PATIENCE_SEC


def on_air(source: str, info: bytes, destination: str = "APRS", path: str = "WIDE1-1") -> bytes:
    """A frame from `source`, as the TNC delivers it over KISS."""
    return kiss.encode(
        ax25.encode(
            ax25.Frame(
                ax25.Address.parse(destination),
                ax25.Address.parse(source),
                tuple(ax25.Address.parse(p) for p in path.split(",") if p),
                info=info,
            )
        )
    )


def message_info(addressee: str, text: str, msg_id: str | None = None, reply: str | None = None) -> bytes:
    """A message; with `reply` the number is the reply-ack form `{msg_id}reply`. A refused text is
    not made."""
    return b":" + format_message(addressee, text, msg_id, reply)


def ack_info(addressee: str, msg_id: str, reply: str | None = None) -> bytes:
    return b":" + format_ack(addressee, msg_id, reply)


def reject_info(addressee: str, msg_id: str) -> bytes:
    return f":{addressee:<9}:rej{msg_id}".encode()


def from_internet(
    source: str, info: bytes, at: datetime, destination: str = "APRS", path: str = "TCPIP*,qAC,T2FINLAND"
) -> Packet:
    """A packet as APRS-IS hands it on, parsed as `parse_is_line` does; `via` is `is`."""
    return parse_is_line(f"{source}>{destination},{path}:".encode() + info, at)


class Hears(Protocol):
    """What `said` needs of a world: the `Env` of tests/support/env.py."""

    async def heard(self, count: int = 1, timeout_sec: float = PATIENCE_SEC) -> bytes: ...


async def said(radio: Hears, count: int = 1, timeout_sec: float = PATIENCE_SEC) -> list[ax25.Frame]:
    """The frames the daemon has written to the radio, waiting until `count` arrived or time is up."""
    out: list[ax25.Frame] = []
    decoder = kiss.KissDecoder()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_sec
    while len(out) < count and loop.time() < deadline:
        out += [ax25.decode(f.payload) for f in decoder.feed(await radio.heard(1, max(0.0, deadline - loop.time())))]
    return out
