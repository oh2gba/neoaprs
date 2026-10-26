"""The window of the latest packets that the topic `packets` holds: the rows a page opens with, by id (the daemon's database is the log). The ids count up in this run of the daemon, in the order the packets came.

The window has two views of the same rows, the latest `size` packets of any channel and the latest `size` that did not come from the internet, and the page is shown one of them: with the internet hidden (`internet` is
false) the Packets tab is as full as it would have been had no packet from the internet ever come, and showing them again needs no read of the database."""
from collections import deque
from typing import Any

from neoaprs.packet import IS, Packet

from .views import packet_row

PACKETS_KEPT = 200                      # the packets a page opens with


class PacketWindow:
    def __init__(self, size: int = PACKETS_KEPT) -> None:
        self.size = size
        self.internet = True                                # whether the packets from the internet are shown
        self.rows: dict[int, dict[str, Any]] = {}          # every row kept, in the order of their ids
        self._all: deque[int] = deque()                    # the ids of the latest `size` packets
        self._radio: deque[int] = deque()                  # the ids of the latest `size` packets that were not from the internet
        self._next = 1

    def load(self, packets: list[Packet]) -> None:
        """The packets the database holds, the newest first: they are the oldest rows of the window."""
        for packet in reversed(packets):
            self.add(packet)

    def add(self, packet: Packet) -> list[int]:
        """Adds the packet; the ids that changed: its own, and the ones that fell out of the window."""
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
        """The packets heard are forgotten (the ones we sent stay)."""
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
