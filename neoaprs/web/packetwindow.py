"""Window of the latest packets held by the topic `packets`, keyed by an id that counts up per run.

Two views of the same rows are kept: the latest `size` packets of any channel, and the latest
`size` that did not come from the internet.
"""
from collections import deque
from typing import Any

from neoaprs.packet import IS, Packet

from .views import packet_row

PACKETS_KEPT = 200


class PacketWindow:
    def __init__(self, size: int = PACKETS_KEPT) -> None:
        self.size = size
        self.internet = True
        self.rows: dict[int, dict[str, Any]] = {}
        self._all: deque[int] = deque()
        self._radio: deque[int] = deque()  # ids of packets not from the internet
        self._next = 1

    def load(self, packets: list[Packet]) -> None:
        """Add database packets, given newest first, as the oldest rows of the window."""
        for packet in reversed(packets):
            self.add(packet)

    def add(self, packet: Packet) -> list[int]:
        """Add the packet; return the ids that changed: its own and those that fell out."""
        number, self._next = self._next, self._next + 1
        self.rows[number] = packet_row(number, packet)
        self._all.append(number)
        if packet.via != IS:
            self._radio.append(number)
        changed = [number]
        for ids in (self._all, self._radio):
            while len(ids) > self.size:
                gone = ids.popleft()
                if gone not in self._all and gone not in self._radio:
                    del self.rows[gone]
                if gone not in changed:
                    changed.append(gone)
        return changed

    def drop_heard(self) -> None:
        """Forget received packets; sent ones stay."""
        for number in [n for n, row in self.rows.items() if row["direction"] == "in"]:
            del self.rows[number]
        self._all, self._radio = (deque(n for n in ids if n in self.rows) for ids in (self._all, self._radio))

    def _shown(self) -> deque[int]:
        return self._all if self.internet else self._radio

    def whole(self) -> dict[str, Any]:
        return {str(number): self.rows[number] for number in self._shown()}

    def item(self, key: str) -> dict[str, Any] | None:
        number = int(key) if key.isdigit() else 0
        return self.rows[number] if number in self._shown() else None
