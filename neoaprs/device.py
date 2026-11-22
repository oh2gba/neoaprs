"""Identify the device or software a station runs from its packets, by the APRS device list.

An exact tocall wins over a wildcard, then the wildcard with most literal characters. A Mic-E
packet carries its latitude in the destination, so its device comes from the comment. Unknown is "".
"""

import re
from collections.abc import Iterable
from functools import cache

from .aprsmice import mice_type
from .devicedata import MICE, MICE_LEGACY, TOCALLS
from .packet import Packet, Position

MICE_IDENTIFIERS = (b"'", b"`", b"\x1c", b"\x1d")  # Mic-E data type identifiers
# type-code prefix of a Mic-E radio that does not do messages (` does)
MICE_DUMB = b"'"
# bytes before the comment: identifier, longitude, speed and course, symbol
MICE_BODY = 9
_WILDCARDS = {"?": ".", "n": "[0-9]", "*": ".*"}  # any character, a digit, the rest of the call
_TWO_BYTE_SUFFIX = ("`", "'")  # type codes of Mic-E devices with a two-byte suffix


class DeviceTable:
    """The device list ready for lookup: exact tocalls in a dict, wildcards as patterns, longest
    first.
    """

    def __init__(
        self,
        tocalls: Iterable[tuple[str, str]],
        mice: Iterable[tuple[str, str]],
        legacy: Iterable[tuple[str, str, str]],
    ) -> None:
        self._exact: dict[str, str] = {}
        patterns: list[tuple[int, int, re.Pattern[str], str]] = []
        for order, (tocall, name) in enumerate(tocalls):
            if not any(c in _WILDCARDS for c in tocall):
                self._exact.setdefault(tocall, name)
                continue
            written = sum(c not in _WILDCARDS for c in tocall)
            patterns.append(
                (-written, order, re.compile("".join(_WILDCARDS.get(c) or re.escape(c) for c in tocall)), name)
            )
        self._patterns = [(pattern, name) for _, _, pattern, name in sorted(patterns, key=lambda p: p[:2])]
        self._mice = dict(mice)
        self._legacy = {(prefix, suffix): name for prefix, suffix, name in legacy}

    def by_tocall(self, destination: str) -> str:
        """Return the device of a destination call (SSID ignored), or "" if unknown."""
        tocall = destination.partition("-")[0].upper()
        if tocall in self._exact:
            return self._exact[tocall]
        return next((name for pattern, name in self._patterns if pattern.fullmatch(tocall)), "")

    def by_mice(self, comment: str) -> str:
        """Return the device of a Mic-E comment by the type code and suffix `mice_type` reads.

        `` ` `` and `'` take a two-character suffix; Kenwood's `>` and `]` a one-character one.
        """
        found = mice_type(comment.encode("latin-1", "replace"))
        lead, suffix = found.lead.decode("latin-1"), found.suffix.decode("latin-1")
        if lead in _TWO_BYTE_SUFFIX:
            return self._mice.get(suffix, "")
        return self._legacy.get((lead, suffix)) or self._legacy.get((lead, ""), "")


@cache
def table() -> DeviceTable:
    """Return the device list shipped with the program."""
    return DeviceTable(TOCALLS, MICE, MICE_LEGACY)


def packet_device(packet: Packet, devices: DeviceTable | None = None) -> str:
    """Return what the sender runs, or "" if unknown; for a third-party packet, the inner packet."""
    devices = devices or table()
    info = packet.inner_info
    if info[:1] in MICE_IDENTIFIERS and isinstance(packet.decoded, Position):
        return devices.by_mice(info[MICE_BODY:].decode("latin-1"))
    return devices.by_tocall(packet.destination if packet.third_party is None else packet.third_party.destination)
