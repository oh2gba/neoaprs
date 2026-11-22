"""One open page: its socket, its address and whether it is local, and the ways to write to it.

A connection sends through the publisher that made it (outbound.py), so handlers never deal with
encoding, size caps or the outgoing check. It also serves as the `Link` of the state hub (hub.py).
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from neoaprs.coded import Param


def error_message(
    text: str, cmd: str = "", code: str = "other", key: str | None = None, params: Mapping[str, Param] | None = None
) -> dict[str, Any]:
    """Return the `error` message; `cmd` is empty for a frame that was no command.

    A non-finite float, which JSON cannot carry, is sent as its text.
    """
    shown = {
        name: (f"{value:g}" if isinstance(value, float) and not math.isfinite(value) else value)
        for name, value in (params or {}).items()
    }
    return {"type": "error", "cmd": cmd, "key": key, "code": code, "params": shown, "text": text}


class Client(Protocol):
    def send_json(self, text: str) -> None: ...
    def send_binary(self, data: bytes) -> None: ...
    def buffered(self) -> int: ...


class Outbound(Protocol):
    def send(self, conn: "Connection", message: dict[str, Any]) -> None: ...
    def send_frame(self, conn: "Connection", text: str) -> None: ...
    def send_binary(self, conn: "Connection", data: bytes) -> None: ...


@dataclass(eq=False)
class Connection:
    client: Client
    out: Outbound
    ip: str = ""
    # The page is on this computer; only such a page may change LOCAL_ONLY settings or run the alert
    # test.
    local: bool = False
    closed: bool = False

    def send(self, message: dict[str, Any]) -> None:
        if not self.closed:
            self.out.send(self, message)

    def send_binary(self, data: bytes) -> None:
        """Send a binary frame (waterfall rows)."""
        if not self.closed:
            self.out.send_binary(self, data)

    def error(
        self,
        text: str,
        cmd: str = "",
        code: str = "other",
        key: str | None = None,
        params: Mapping[str, Param] | None = None,
    ) -> None:
        self.send(error_message(text, cmd, code, key, params))

    # Link interface used by the state hub.
    def send_text(self, text: str) -> None:
        """Send an already encoded text frame."""
        if not self.closed:
            self.out.send_frame(self, text)

    def buffered(self) -> int:
        return self.client.buffered()
