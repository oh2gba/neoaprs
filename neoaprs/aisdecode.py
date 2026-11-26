"""Decode AIS ship messages (types 1-3, 5, 18, 19, 24) from NMEA `!AIVDM`/`!AIVDO` lines.

Checks the checksum and joins multi-part messages; other types and broken lines are skipped.
"""

from dataclasses import dataclass
from datetime import datetime

# a part still waiting for the rest after this long is dropped
PART_WAIT_SEC = 10
_SOG_NA, _COG_NA = 1023, 3600  # "not available" values: speed 102.3 kn, course 360 deg


@dataclass(frozen=True)
class AisPosition:
    """Where a ship is; fields the ship reports as not available are None."""

    mmsi: int
    lat: float
    lon: float
    at: datetime
    sog_kn: float | None
    cog_deg: float | None
    heading_deg: int | None


@dataclass(frozen=True)
class AisStatic:
    """What a ship says of itself; class B sends name and type apart, so empty/None means absent."""

    mmsi: int
    name: str
    ship_type: int | None
    destination: str


def _checked(line: str) -> list[str] | None:
    """Return the fields of a VDM or VDO sentence with a correct checksum, else None."""
    start = line.find("!")
    star = line.rfind("*")
    if start < 0 or star < start + 6 or len(line) < star + 3:
        return None
    body = line[start + 1 : star]
    try:
        given = int(line[star + 1 : star + 3], 16)
    except ValueError:
        return None
    sum_ = 0
    for char in body:
        sum_ ^= ord(char)
    fields = body.split(",")
    if sum_ != given or len(fields) != 7 or fields[0][2:] not in ("VDM", "VDO"):
        return None
    return fields


class _Bits:
    """Return the six-bit payload characters as one integer (bit 0 is the first bit)."""

    def __init__(self, payload: str, fill: int) -> None:
        value = 0
        for char in payload:
            code = ord(char) - 48
            if 40 <= code < 48:
                raise ValueError("not a six-bit character")
            if code > 40:
                code -= 8
            if not 0 <= code < 64:
                raise ValueError("not a six-bit character")
            value = (value << 6) | code
        self.size = 6 * len(payload) - fill
        self.value = value >> fill if fill else value

    def unsigned(self, start: int, length: int) -> int:
        if start + length > self.size:
            raise ValueError("the message is too short")
        return (self.value >> (self.size - start - length)) & ((1 << length) - 1)

    def signed(self, start: int, length: int) -> int:
        number = self.unsigned(start, length)
        return number - (1 << length) if number >= 1 << (length - 1) else number

    def text(self, start: int, length: int) -> str:
        chars = []
        for at in range(start, start + length, 6):
            code = self.unsigned(at, 6)
            chars.append(chr(code + 64 if code < 32 else code))
        return "".join(chars).rstrip("@ ").strip()


def _ship_type(number: int) -> int | None:
    return number if 1 <= number <= 99 else None


def _position(bits: _Bits, at: datetime, sog: int, lon: int, lat: int, cog: int, heading: int) -> AisPosition | None:
    longitude = bits.signed(lon, 28) / 600000
    latitude = bits.signed(lat, 27) / 600000
    if abs(longitude) > 180 or abs(latitude) > 90:  # 181 and 91 mean "no position"
        return None
    speed, course, head = bits.unsigned(sog, 10), bits.unsigned(cog, 12), bits.unsigned(heading, 9)
    return AisPosition(
        mmsi=bits.unsigned(8, 30),
        lat=latitude,
        lon=longitude,
        at=at,
        sog_kn=None if speed >= _SOG_NA else speed / 10,
        cog_deg=None if course >= _COG_NA else course / 10,
        heading_deg=None if head >= 360 else head,
    )


def _decode(bits: _Bits, at: datetime) -> AisPosition | AisStatic | None:
    kind = bits.unsigned(0, 6)
    if kind in (1, 2, 3):
        return _position(bits, at, sog=50, lon=61, lat=89, cog=116, heading=128)
    if kind in (18, 19):
        return _position(bits, at, sog=46, lon=57, lat=85, cog=112, heading=124)
    if kind == 5:
        return AisStatic(
            mmsi=bits.unsigned(8, 30),
            name=bits.text(112, 120),
            ship_type=_ship_type(bits.unsigned(232, 8)),
            destination=bits.text(302, 120),
        )
    if kind == 24:
        part = bits.unsigned(38, 2)
        if part == 0:
            return AisStatic(mmsi=bits.unsigned(8, 30), name=bits.text(40, 120), ship_type=None, destination="")
        if part == 1:
            return AisStatic(
                mmsi=bits.unsigned(8, 30), name="", ship_type=_ship_type(bits.unsigned(40, 8)), destination=""
            )
    return None


def is_ais(line: str) -> bool:
    """Return whether the line is an AIS sentence (VDM or VDO) with a correct checksum."""
    return _checked(line.strip()) is not None


class AisDecoder:
    """Read NMEA lines one at a time and join the sentences of a multi-part message."""

    def __init__(self) -> None:
        # (sequential id, channel) -> (time of first part, part count, payloads so far)
        self._waiting: dict[tuple[str, str], tuple[datetime, int, list[str]]] = {}

    def feed(self, line: str, at: datetime) -> AisPosition | AisStatic | None:
        """Return the position or static data the line completes, or None."""
        fields = _checked(line.strip())
        if fields is None:
            return None
        self._forget_old(at)
        try:
            count, number, fill = int(fields[1]), int(fields[2]), int(fields[6] or 0)
        except ValueError:
            return None
        payload = fields[5]
        if not 1 <= number <= count <= 9 or not payload or not 0 <= fill <= 5:
            return None
        if count > 1:
            key = (fields[3], fields[4])
            waiting = self._waiting.get(key)
            if number == 1:
                self._waiting[key] = (at, count, [payload])
                return None
            if waiting is None or waiting[1] != count or len(waiting[2]) != number - 1:
                self._waiting.pop(key, None)
                return None
            parts = [*waiting[2], payload]
            if number < count:
                self._waiting[key] = (waiting[0], count, parts)
                return None
            del self._waiting[key]
            payload = "".join(parts)
        try:
            return _decode(_Bits(payload, fill), at)
        except ValueError:
            return None

    def _forget_old(self, now: datetime) -> None:
        for key in [
            key for key, (since, _, _) in self._waiting.items() if (now - since).total_seconds() > PART_WAIT_SEC
        ]:
            del self._waiting[key]
