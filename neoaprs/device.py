"""What a station runs, from its packets: the device or software that the APRS device identification list (devicedata.py, credited there) names for the destination call of a packet, or for the type code
of a Mic-E packet. Pure code; an unknown device is the empty string.

A destination call is a `tocall` (`APDR15` is APRSdroid): the list's own entry, an exact one before a wildcarded one, and of those the one with the most characters written out (`APAGW?` before `APAG??`).
A Mic-E packet carries its latitude in the destination, so its device is in the comment: the first byte after the 9 of the position, a type code, and the last one or two bytes, a suffix."""
import re
from collections.abc import Iterable
from functools import cache

from .aprsmice import mice_type
from .devicedata import MICE, MICE_LEGACY, TOCALLS
from .packet import Packet, Position

MICE_IDENTIFIERS = (b"'", b"`", b"\x1c", b"\x1d")   # the data type identifiers of a Mic-E packet
MICE_DUMB = b"'"                                    # the type-code prefix of a Mic-E radio that does not do messages, the first byte of its comment (aprs-deviceid: ` does, ' does not)
MICE_BODY = 9                                       # the bytes of a Mic-E information field before the comment: the identifier, the longitude, the speed and course, the symbol
_WILDCARDS = {"?": ".", "n": "[0-9]", "*": ".*"}    # `?` any one character, `n` a digit, `*` the rest of the call
_TWO_BYTE_SUFFIX = ("`", "'")                      # the type codes of a Mic-E device with a two-byte suffix


class DeviceTable:
    """The list, ready to look up: the tocalls without a wildcard in a dictionary, the others as patterns, the longest first."""

    def __init__(self, tocalls: Iterable[tuple[str, str]], mice: Iterable[tuple[str, str]], legacy: Iterable[tuple[str, str, str]]) -> None:
        self._exact: dict[str, str] = {}
        patterns: list[tuple[int, int, re.Pattern[str], str]] = []
        for order, (tocall, name) in enumerate(tocalls):
            if not any(c in _WILDCARDS for c in tocall):
                self._exact.setdefault(tocall, name)
                continue
            written = sum(c not in _WILDCARDS for c in tocall)
            patterns.append((-written, order, re.compile("".join(_WILDCARDS.get(c) or re.escape(c) for c in tocall)), name))
        self._patterns = [(pattern, name) for _, _, pattern, name in sorted(patterns, key=lambda p: p[:2])]
        self._mice = dict(mice)
        self._legacy = {(prefix, suffix): name for prefix, suffix, name in legacy}

    def by_tocall(self, destination: str) -> str:
        """The device of a destination call (an SSID is ignored); empty when the list does not know it."""
        tocall = destination.partition("-")[0].upper()
        if tocall in self._exact:
            return self._exact[tocall]
        return next((name for pattern, name in self._patterns if pattern.fullmatch(tocall)), "")

    def by_mice(self, comment: str) -> str:
        """The device of a Mic-E comment (what follows the 9 bytes of the position), by the type code and suffix `aprsmice.mice_type` reads from it: `` ` `` or `'` and two suffix characters, or a Kenwood's type code (`>`, `]`) with the one suffix character that tells its models apart."""
        found = mice_type(comment.encode("latin-1", "replace"))
        lead, suffix = found.lead.decode("latin-1"), found.suffix.decode("latin-1")
        if lead in _TWO_BYTE_SUFFIX:
            return self._mice.get(suffix, "")
        return self._legacy.get((lead, suffix)) or self._legacy.get((lead, ""), "")


@cache
def table() -> DeviceTable:
    """The snapshot of the list the program carries."""
    return DeviceTable(TOCALLS, MICE, MICE_LEGACY)


def packet_device(packet: Packet, devices: DeviceTable | None = None) -> str:
    """What the sender of a packet runs; empty when its destination is no tocall of the list and it is no Mic-E packet of a device the list knows. For a third-party packet that is the packet inside."""
    devices = devices or table()
    info = packet.inner_info
    if info[:1] in MICE_IDENTIFIERS and isinstance(packet.decoded, Position):
        return devices.by_mice(info[MICE_BODY:].decode("latin-1"))
    return devices.by_tocall(packet.destination if packet.third_party is None else packet.third_party.destination)
