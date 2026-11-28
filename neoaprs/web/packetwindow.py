"""Window of the latest packets held by the topic `packets`, keyed by an id that counts up per run.

A view of the same rows is kept for each way the two ticks can leave packets out (neoaprs/shown.py):
the latest `size` packets that each shows.
"""

from collections import deque
from typing import Any

from neoaprs.packet import Packet
from neoaprs.shown import Shown

from .views import packet_row

PACKETS_KEPT = 200
VIEWS = tuple((internet, gated) for internet in (True, False) for gated in (True, False))


class PacketWindow:
    def __init__(self, size: int = PACKETS_KEPT) -> None:
        self.size = size
        self.internet = True
        self.gated = True
        self.own = ""  # our call: a message to it is shown whatever the ticks
        self.rows: dict[int, dict[str, Any]] = {}
        self._views: dict[tuple[bool, bool], deque[int]] = {view: deque() for view in VIEWS}
        self._next = 1

    def load(self, packets: list[Packet]) -> None:
        """Add database packets, given newest first, as the oldest rows of the window."""
        for packet in reversed(packets):
            self.add(packet)

    def add(self, packet: Packet) -> list[int]:
        """Add the packet; return the ids that changed: its own and those that fell out."""
        number, self._next = self._next, self._next + 1
        self.rows[number] = packet_row(number, packet)
        changed = [number]
        for (internet, gated), ids in self._views.items():
            if Shown(internet, gated, self.own).packet(packet):
                ids.append(number)
            while len(ids) > self.size:
                gone = ids.popleft()
                if gone not in changed:
                    changed.append(gone)
        for gone in changed[1:]:
            if not any(gone in ids for ids in self._views.values()):
                del self.rows[gone]
        return changed

    def drop_heard(self) -> None:
        """Forget received packets; sent ones stay."""
        for number in [n for n, row in self.rows.items() if row["direction"] == "in"]:
            del self.rows[number]
        self._views = {view: deque(n for n in ids if n in self.rows) for view, ids in self._views.items()}

    def _shown(self) -> deque[int]:
        return self._views[self.internet, self.gated]

    def whole(self) -> dict[str, Any]:
        return {str(number): self.rows[number] for number in self._shown()}

    def item(self, key: str) -> dict[str, Any] | None:
        number = int(key) if key.isdigit() else 0
        return self.rows[number] if number in self._shown() else None
