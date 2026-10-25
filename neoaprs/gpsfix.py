"""A GPS fix, and how one is made from what a receiver says: NMEA 0183 sentences (RMC and GGA) from a serial receiver, JSON reports (TPV and SKY) from gpsd.

`Fix.at` is when the fix was received, by the clock of the program, not the receiver's: a receiver that has just started may not know the date, and the program judges how old a fix is by its own clock.
The speed is in km/h, the course in whole degrees (0 to 359, north is 0), the altitude in metres above mean sea level (what APRS and a GGA sentence mean).

`NmeaFixes` and `GpsdFixes` keep what the stream said so far and give a fix for each report that has a position; a report that says there is no fix (RMC status V, GGA quality 0, gpsd mode below 2) clears the fix.
Pure code, like the rest of the foundation."""
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from neoaprs.aprsnmea import NmeaError, parse_nmea
from neoaprs.aprsposition import KNOT_KMH

MS_KMH = 3.6                                                   # km/h in a metre per second
_SENTENCE = re.compile(r"\$[A-Z]{2}(RMC|GGA),")
RMC_FRESH_SEC = 3.0                                            # a GGA gives a fix of its own only when no RMC came this recently (a receiver that sends both gives one fix a second, from the RMC)
GGA_FRESH_SEC = 5.0                                            # the altitude and the satellites of a GGA go with an RMC that comes this soon after it


@dataclass(frozen=True)
class Fix:
    lat: float
    lon: float
    at: datetime
    speed_kmh: float | None = None
    course_deg: int | None = None
    altitude_m: float | None = None
    satellites: int | None = None


def _number(value: object) -> float | None:
    """A finite number from a field of a sentence or a JSON value (a bool is none); None for anything else."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)                                  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _course(value: float | None) -> int | None:
    return None if value is None else round(value) % 360


class NmeaFixes:
    """The fixes of a stream of NMEA sentences. `feed(line, now)` takes one sentence (text or bytes, with or without its line end) and gives the fix it completes, else None. Other sentences are
    ignored; a damaged one (bad checksum) is counted in `damaged` and changes nothing. `fix` is the latest fix, None after a sentence that says there is none; `said_none` is whether the sentence
    fed last was such a one."""

    def __init__(self) -> None:
        self.fix: Fix | None = None
        self.said_none = False
        self.damaged = 0
        self._rmc_at: datetime | None = None
        self._altitude: tuple[datetime, float | None, int | None] | None = None        # (when, altitude, satellites) of the latest GGA

    def feed(self, line: str | bytes, now: datetime) -> Fix | None:
        text = (line.decode("latin-1") if isinstance(line, bytes) else line).strip()
        self.said_none = False
        found = _SENTENCE.match(text)
        if not found:
            return None
        try:
            position = parse_nmea(text.encode("latin-1"), "GPS", "GPS", now)
        except NmeaError:
            self.damaged += 1
            return None
        if position is None:                                   # RMC with status V, GGA with quality 0: the receiver has no fix
            self.fix, self._rmc_at, self._altitude, self.said_none = None, None, None, True
            return None
        fields = text.split("*")[0].split(",")[1:]
        return self._rmc(position.lat, position.lon, fields, now) if found.group(1) == "RMC" else self._gga(position.lat, position.lon, fields, now)

    def _rmc(self, lat: float, lon: float, fields: list[str], now: datetime) -> Fix:
        speed = _number(fields[6])
        altitude, satellites = self._recent_gga(now)
        self._rmc_at = now
        self.fix = Fix(lat, lon, now, None if speed is None else speed * KNOT_KMH, _course(_number(fields[7])), altitude, satellites)
        return self.fix

    def _gga(self, lat: float, lon: float, fields: list[str], now: datetime) -> Fix | None:
        altitude = _number(fields[8]) if len(fields) > 9 and fields[9].upper() == "M" else None
        satellites = _number(fields[6])
        self._altitude = (now, altitude, None if satellites is None else int(satellites))
        if self._rmc_at is not None and (now - self._rmc_at).total_seconds() <= RMC_FRESH_SEC and self.fix is not None:
            return None                                        # (the RMC of this second gives the fix; its altitude is the one of the GGA before it, and the next RMC has this one)
        self.fix = Fix(lat, lon, now, None, None, altitude, self._altitude[2])
        return self.fix

    def _recent_gga(self, now: datetime) -> tuple[float | None, int | None]:
        if self._altitude is None or (now - self._altitude[0]).total_seconds() > GGA_FRESH_SEC:
            return None, None
        return self._altitude[1], self._altitude[2]


def fix_from_nmea(line: str | bytes, now: datetime) -> Fix | None:
    """The fix of one sentence on its own: an RMC gives position, speed and course; a GGA position, altitude and satellites. None for another sentence, a damaged one, or one that says there is no fix.
    A stream is read with `NmeaFixes`, which puts the two together."""
    return NmeaFixes().feed(line, now)


def satellites_of_sky(report: Mapping[str, Any]) -> int | None:
    """The satellites used in a gpsd SKY report: `uSat` when it has it, else the satellites marked used; None when the report says neither."""
    used = report.get("uSat")
    if isinstance(used, int) and not isinstance(used, bool) and used >= 0:
        return used
    listed = report.get("satellites")
    if isinstance(listed, list):
        return sum(1 for s in listed if isinstance(s, Mapping) and s.get("used") is True)
    return None


def _altitude(report: Mapping[str, Any]) -> float | None:
    """The altitude above mean sea level: `altMSL`, else `alt` (what gpsd called it before), else `altHAE` (above the ellipsoid, a few tens of metres off)."""
    for key in ("altMSL", "alt", "altHAE"):
        if (value := _number(report.get(key))) is not None:
            return value
    return None


def fix_from_gpsd(report: Mapping[str, Any], now: datetime, satellites: int | None = None) -> Fix | None:
    """The fix of a gpsd TPV report: mode 2 (2D) or 3 (3D) with a latitude and a longitude. `speed` is metres per second, `track` degrees. None for any other report, a mode below 2, or a position
    that is not on the earth. `satellites` is the count of the latest SKY report."""
    if report.get("class") != "TPV":
        return None
    mode = report.get("mode")
    lat, lon = _number(report.get("lat")), _number(report.get("lon"))
    if not isinstance(mode, int) or isinstance(mode, bool) or mode < 2 or lat is None or lon is None or not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    speed = _number(report.get("speed"))
    return Fix(lat, lon, now, None if speed is None else max(0.0, speed * MS_KMH), _course(_number(report.get("track"))), _altitude(report), satellites)


class GpsdFixes:
    """The fixes of a stream of gpsd reports: `feed(report, now)` gives the fix of a TPV report with the satellites of the latest SKY, else None. A TPV without a fix clears `fix` and sets `said_none`."""

    def __init__(self) -> None:
        self.fix: Fix | None = None
        self.said_none = False
        self.satellites: int | None = None

    def feed(self, report: Mapping[str, Any], now: datetime) -> Fix | None:
        kind = report.get("class")
        self.said_none = False
        if kind == "SKY":
            self.satellites = satellites_of_sky(report)
        elif kind == "TPV":
            self.fix = fix_from_gpsd(report, now, self.satellites)
            self.said_none = self.fix is None
            return self.fix
        return None
