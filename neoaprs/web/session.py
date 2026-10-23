"""One open page: the socket it talks through, where it is, and the ways to write to it.

A connection sends through the publisher that made it (neoaprs/web/outbound.py), so a command handler says `conn.error("...")` or `conn.send(message)` and never meets the encoding, the size cap or the
outgoing check. A connection is also what the state hub (neoaprs/web/hub.py) calls a `Link`: a way to write a text frame, and how much the socket holds that the page has not read.
"""
from dataclasses import dataclass
from typing import Any, Protocol


class Client(Protocol):
    """What the daemon needs of a page's socket: a way to write a text frame, and how much the socket holds that the page has not read."""
    def send_json(self, text: str) -> None: ...
    def buffered(self) -> int: ...


class Outbound(Protocol):
    """What a connection needs of the publisher that made it."""
    def send(self, conn: "Connection", message: dict[str, Any]) -> None: ...
    def send_frame(self, conn: "Connection", text: str) -> None: ...


@dataclass(eq=False)
class Connection:
    client: Client
    out: Outbound
    ip: str = ""
    closed: bool = False         # the page left: nothing is written to it any more

    def send(self, message: dict[str, Any]) -> None:
        """One message to this page."""
        if not self.closed:
            self.out.send(self, message)

    def error(self, text: str) -> None:
        self.send({"type": "error", "text": text})

    # ---- what the state hub asks of a link
    def send_text(self, text: str) -> None:
        """A frame that is made already."""
        if not self.closed:
            self.out.send_frame(self, text)

    def buffered(self) -> int:
        return self.client.buffered()
