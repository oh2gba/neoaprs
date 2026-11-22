"""The one maker of the station's own frames: position, status report and position field.

Frames differ between radios only by the radio's path and a comment cut to fit its frame; with no
fresh fix a moving station has no frame (`NoFix`). `air_of` wraps an old-shape radio.
"""

import logging
import math
import re
from dataclasses import replace
from typing import Any, TypeIs, cast

from neoaprs import ax25
from neoaprs.aprsposition import uncompressed_position
from neoaprs.callsign import call_problem
from neoaprs.clock import Clock, utcnow
from neoaprs.coded import CodedError, Reason
from neoaprs.config import ANTENNA_DIRECTIONS, SYMBOL_TABLES, Config, can_transmit
from neoaprs.configstatus import MAX_STATUS
from neoaprs.configtypes import over_the_air_refusal
from neoaprs.gpsfix import Fix
from neoaprs.radiospec import RadioId, RadioSpec, log_name
from neoaprs.radiotype import Allowed, Kind, Limits
from neoaprs.radiotypes import kind_field
from neoaprs.services.common import ConfigSource, Radio, old_id, old_spec
from neoaprs.services.mobilebeacon import Positions, mobile_info
from neoaprs.services.radioset import FRAME_ERRORS, AirRadio, fit_frame, fixed_prefix, our_frame, path_on
from neoaprs.tnc2line import text_of
from neoaprs.source import Source
from neoaprs.tncwatchdog import TncStats
from neoaprs.units import FOOT_M

log = logging.getLogger("neoaprs.beacon")

# starts of the data extensions
_LOOKS_LIKE_EXTENSION = re.compile(r"\d{3}/\d{3}|PHG|RNG|DFS")


class BeaconError(CodedError):
    """The settings do not make a frame."""


class NoFix(BeaconError):
    """A mobile station has no fresh GPS fix to send."""


def _comment_text(comment: str) -> str:
    """Prefix a blank to a comment that looks like a data extension (`144/430` is course/speed)."""
    return " " + comment if _LOOKS_LIKE_EXTENSION.match(comment) else comment


def _round_half_up(x: float) -> int:
    return math.floor(x + 0.5)


def phg_text(power_w: int, height_m: float, gain_db: int, direction: str) -> str:
    """Return the PHG data extension `PHGphgd` (APRS 1.0.1 chapter 7), each digit held to 0 to 9."""
    p = min(9, _round_half_up(math.sqrt(power_w)))
    feet = height_m / FOOT_M
    h = 0 if feet <= 10 else min(9, _round_half_up(math.log2(feet / 10)))
    return f"PHG{p}{h}{min(9, max(0, gain_db))}{ANTENNA_DIRECTIONS.index(direction)}"


class OldLine:
    """An old-shape radio seen as an AirRadio: radio 1 if FM, radio 2 if HF."""

    def __init__(self, line: Radio, config: ConfigSource) -> None:
        self.line = line
        self._config = config
        self._stats = TncStats()

    @property
    def kind(self) -> Kind:
        return "hf" if self.line.rtype.kind == "hf" else "fm"

    @property
    def id(self) -> RadioId:
        return old_id(self.kind)

    def _spec(self, key: str | None = None) -> RadioSpec | None:
        return old_spec(self._config(), self.id, key)

    @property
    def name(self) -> str:
        spec = self._spec()
        return "" if spec is None else log_name(spec, self._config().radios)

    @property
    def limits(self) -> Limits:
        return self.line.rtype.limits

    @property
    def allowed(self) -> Allowed:
        return self.line.rtype.allowed

    @property
    def stats(self) -> TncStats:
        stats = getattr(self.line, "stats", None)
        return stats if isinstance(stats, TncStats) else self._stats

    @property
    def state(self) -> Source.State:
        return self.line.state

    @property
    def usable(self) -> bool:
        return self.line.usable

    @property
    def max_frame(self) -> int | None:
        return self.line.max_frame

    def why_unusable(self) -> str:
        return self.line.why_unusable()

    def send_frame(self, frame: ax25.Frame, raw: bytes | None = None) -> bool:
        return self.line.send_frame(frame, raw)

    def choice(self, key: str) -> Any:
        if (spec := self._spec(key)) is not None:
            return spec.value(key)
        found = kind_field(self.kind, key) or kind_field("fm", key)  # no such radio: the default
        return None if found is None else found.parse(found.default)


def is_air(radio: AirRadio | Radio) -> TypeIs[AirRadio]:
    """Whether the radio has the registry shape rather than the old one."""
    return hasattr(radio, "allowed") and hasattr(radio, "limits")


def air_of(radio: AirRadio | Radio, config: ConfigSource, *, old: bool = False) -> AirRadio:
    """Return `radio` as an AirRadio, wrapping an old-shape one (`old` forces it)."""
    if is_air(radio) and not (old and hasattr(radio, "rtype")):
        return radio
    return OldLine(cast(Radio, radio), config)


class BeaconFrames:
    """Our frames for any radio, from the settings (and GPS fix) at the time a frame is made."""

    def __init__(self, config: ConfigSource, gps: Positions | None = None, clock: Clock = utcnow) -> None:
        self._config = config
        self.gps = gps
        self.clock = clock
        # per radio, the last cut information field, so each cut is logged once
        self._cut_told: dict[RadioId, bytes] = {}

    def position(self, radio: AirRadio) -> ax25.Frame:
        """Return our position frame for `radio`; BeaconError, or NoFix without a fresh fix."""
        return self.position_and_fix(radio)[0]

    def position_and_fix(self, radio: AirRadio) -> tuple[ax25.Frame, Fix | None]:
        """Return the position frame and the fix it was made from (None for a fixed station)."""
        c = self._config()
        if reason := can_transmit(c):
            raise BeaconError.of(reason)
        info, fix = self._position(c)
        return self.frame_for(radio, info), fix

    def position_info(self) -> bytes:
        """Return the position information field for the receive-only iGate (no interlock check)."""
        c = self._config()
        if problem := call_problem(c.station_call):
            raise BeaconError.of(problem)
        info = self._position(c)[0]
        if len(info) > ax25.MAX_INFO:
            raise BeaconError(
                f"the information field is {len(info)} bytes, more than the {ax25.MAX_INFO} AX.25 allows",
                "frame.too_long",
                length=len(info),
                max=ax25.MAX_INFO,
            )
        return info

    def _position(self, c: Config) -> tuple[bytes, Fix | None]:
        """Return the position information field and its fix (None for a fixed station)."""
        if c.mobile:
            return self._mobile_info(c)
        if refusal := c.comment_refusal():
            raise BeaconError.of(refusal)
        if c.station_lat is None or c.station_lon is None:
            raise BeaconError("set your position first", "beacon.no_position")
        if not (-90.0 <= c.station_lat <= 90.0 and -180.0 <= c.station_lon <= 180.0):
            raise BeaconError(
                f"the position {c.station_lat}, {c.station_lon} is not on the earth",
                "object.position",
                lat=c.station_lat,
                lon=c.station_lon,
            )
        _check_symbol(c)
        try:
            position = uncompressed_position(
                c.station_lat, c.station_lon, c.station_symbol_table, c.station_symbol_code
            )
        except ValueError as e:
            raise BeaconError.of(e) from None
        return b"=" + position + _phg(c) + _comment_text(c.station_comment).encode("ascii"), None

    def _mobile_info(self, c: Config) -> tuple[bytes, Fix]:
        fix = self.gps.current() if self.gps is not None else None
        if fix is None:
            raise NoFix(self.gps.why_none() if self.gps is not None else "no GPS is set up")
        if refusal := over_the_air_refusal(c.station_comment):
            raise BeaconError.of(refusal, f"station/comment: {refusal}")
        _check_symbol(c)
        try:
            return mobile_info(c, fix), fix
        except ValueError as e:
            raise BeaconError.of(e) from None

    def status(self, text: str, radio: AirRadio) -> ax25.Frame | None:
        """Return a status frame (`>`, `DDHHMMz`, text); None if empty; BeaconError if none."""
        if not text:
            return None
        if refusal := over_the_air_refusal(text):
            raise BeaconError.of(refusal, f"the status: {refusal}")
        if len(text) > MAX_STATUS:
            raise BeaconError(
                f"the status is {len(text)} characters, more than the {MAX_STATUS} that fit after its time",
                "status.too_long",
                length=len(text),
                max=MAX_STATUS,
            )
        info = b">" + self.clock().strftime("%d%H%M").encode("ascii") + b"z" + text.encode("ascii")
        if over := self._over(radio, info):
            fits_not = Reason(
                f"the status is too long for radio {radio.name}",
                "status.too_long_for_radio",
                radio=radio.id,
                name=radio.name,
            )
            raise BeaconError.of(
                fits_not, f"the status is longer than the radio carries ({over}): it is not cut, and not sent there"
            )
        return self.frame_for(radio, info)

    def _over(self, radio: AirRadio, info: bytes) -> str:
        """Return why the frame is longer than the radio carries (Limits.too_long), or ""."""
        c = self._config()
        try:
            frame = our_frame(c, path_on(radio, c, None), info)
        except FRAME_ERRORS:
            return ""
        return replace(radio.limits, max_frame=radio.max_frame).too_long(ax25.encode(frame), text_of(frame)) or ""

    def frame_for(self, radio: AirRadio, info: bytes) -> ax25.Frame:
        """Return our frame for `info` on `radio` by its path, cut to fit; BeaconError if none."""
        c = self._config()
        if reason := can_transmit(c):
            raise BeaconError.of(reason)
        if len(info) > ax25.MAX_INFO:
            raise BeaconError(
                f"the information field is {len(info)} bytes, more than the {ax25.MAX_INFO} AX.25 allows",
                "frame.too_long",
                length=len(info),
                max=ax25.MAX_INFO,
            )
        if problem := _path_problem(radio, c):
            raise BeaconError.of(problem)
        try:
            frame = our_frame(c, path_on(radio, c, None), info)
            fitted = fit_frame(frame, radio.max_frame, radio.limits.max_text, radio.limits.max_kiss)
        except FRAME_ERRORS as e:
            raise BeaconError.of(e) from None
        if fitted is not frame and self._cut_told.get(radio.id) != fitted.info:
            self._cut_told[radio.id] = fitted.info
            log.warning(
                "the beacon is %d bytes more than the radio carries (%d): its comment is cut to %r",
                len(ax25.encode(frame)),
                radio.max_frame,
                fitted.info[fixed_prefix(info) :].decode("ascii", "replace"),
            )
        return fitted


def _path_problem(radio: AirRadio, c: Config) -> str:
    """Return why the radio's stored path makes no frame, or ""."""
    if not radio.allowed.paths:
        return ""
    spec = old_spec(c, radio.id, "path")
    found = None if spec is None else kind_field(spec.kind, "path")
    text = None if spec is None else spec.settings.get("path")
    if found is None or text is None:
        return ""
    try:
        found.parse(text)
    except ValueError as e:
        return Reason.of(e, f"the path: {e}")
    return ""


def _check_symbol(c: Config) -> None:
    if (
        c.station_symbol_table not in SYMBOL_TABLES
        or len(c.station_symbol_table) != 1
        or not "!" <= c.station_symbol_code <= "~"
        or len(c.station_symbol_code) != 1
    ):
        raise BeaconError(
            f"the symbol {c.station_symbol_table!r} {c.station_symbol_code!r} is not a table (/ \\ A-Z 0-9) and one printable character",
            "object.symbol",
            table=c.station_symbol_table,
            symbol=c.station_symbol_code,
        )


def _phg(c: Config) -> bytes:
    if c.beacon_power_w is None:
        return b""
    return phg_text(
        c.beacon_power_w, c.beacon_antenna_height_m, c.beacon_antenna_gain_db, c.beacon_antenna_direction
    ).encode("ascii")
