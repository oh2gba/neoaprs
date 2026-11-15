"""The one maker of the station's own frames (plan §2, the beacon): our position, our status report and the position field, built from the settings for any radio. Each radio's beacon timer (services/beacon.py),
the status report (services/rigstatus.py), the answers to the queries (services/queries.py) and the iGate's position on APRS-IS (services/igate.py) take theirs from one `BeaconFrames`, so that a frame differs
from radio to radio only by what the radio itself decides: the digipeaters where it may carry any (its own "path" choice, which empty is the recommended path of the station's symbol and DIRECT none), and the
comment cut to the frame it carries whole.

The position (`position`): the tocall (`neoaprs.TOCALL`, not a setting), the radio's digipeaters and the symbol, the comment and the position (`=`, a station with messaging; always the plain uncompressed
form, which every receiver reads, rounded to the hundredth of a minute and never ambiguous) come from the settings. Right after the position, before the comment, goes the PHG data extension (`PHGphgd`: power,
height, gain and directivity of the antenna) when `beacon/power_w` is set; the comment may then be 36 characters, 43 otherwise (`Config.comment_limit`), and the frame is refused when it is longer. A moving
station's (`gps/source` is not `off`) is the GPS fix of now on every radio, the ones with SmartBeaconing and the ones that send it by time (services/mobilebeacon.py: a compressed position without PHG); with no
fix that is fresh (none yet, or none younger than GPS_STALE_SEC) there is no frame at all (`NoFix`), and the home position of the settings is never put in its place.
The status report (`status`): `>` and the time as `DDHHMMz`, then the text, at most 55 printable ASCII characters without `|` and `~`, by the same tocall and the radio's path. When it is sent is the status
service's; the beacon sends none after itself.
The position field (`position_info`): the information field of the position for a receive-only iGate, which puts it on APRS-IS: the same bytes a radio would carry, but nothing is transmitted, so the transmit
interlock is not asked, only that the call is one.
A frame too long for a radio with a fixed frame (the Mercury HF modem's 123 bytes) has its comment cut to fit, said once in the log for each radio and each cut; the report itself is never cut.

Until every caller gives the registry's radios (neoaprs/radioregistry.py), a radio may still come in the old shape of services/common.Radio (a Tnc, the old set of two, a test's stub): `air_of` reads it as an
`AirRadio` (`OldLine`: its kind by its type, fm radio 1 and hf radio 2; its limits and what it is allowed its type's; its choices those of the station's radio of that id)."""
import logging
import math
import re
from typing import Any, TypeIs, cast

from neoaprs import ax25
from neoaprs.aprsposition import uncompressed_position
from neoaprs.callsign import call_problem
from neoaprs.clock import Clock, utcnow
from neoaprs.config import ANTENNA_DIRECTIONS, SYMBOL_TABLES, Config, can_transmit
from neoaprs.configstatus import MAX_STATUS
from neoaprs.configtypes import over_the_air_problem, over_the_air_refusal
from neoaprs.gpsfix import Fix
from neoaprs.radiospec import FM_ID, HF_ID, RadioId, RadioSpec, log_name
from neoaprs.radiotype import Allowed, Kind, Limits
from neoaprs.radiotypes import kind_field
from neoaprs.services.common import ConfigSource, Radio
from neoaprs.services.mobilebeacon import Positions, mobile_info
from neoaprs.services.radioset import FRAME_ERRORS, AirRadio, fit_frame, fixed_prefix, our_frame, path_on
from neoaprs.source import Source
from neoaprs.tncwatchdog import TncStats
from neoaprs.units import FOOT_M

log = logging.getLogger("neoaprs.beacon")

_LOOKS_LIKE_EXTENSION = re.compile(r"\d{3}/\d{3}|PHG|RNG|DFS")        # the starts of the data extensions (course and speed, power-height-gain, range, signal strength): every receiver reads them right after the symbol or the PHG


class BeaconError(ValueError):
    """The settings do not make a frame."""


class NoFix(BeaconError):
    """A mobile station has no GPS fix to send (none yet, or none fresh): there is no beacon, and the home position is not sent instead."""


def _comment_text(comment: str) -> str:
    """The comment as it follows the position: one blank before a comment that starts like a data extension (`144/430 MHz` would be read as a course of 144 degrees and a speed), which a receiver then takes as the comment."""
    return " " + comment if _LOOKS_LIKE_EXTENSION.match(comment) else comment


def _round_half_up(x: float) -> int:
    return math.floor(x + 0.5)


def phg_text(power_w: int, height_m: float, gain_db: int, direction: str) -> str:
    """The PHG data extension `PHGphgd`: p is the square root of the power in watts, h the base-2 logarithm of the height in tens of feet, g the gain in dB and d the directivity (0 omni, 1 NE,
    2 E ... 7 NW, 8 N, the specification's order); p and h rounded and held to 0 to 9."""
    p = min(9, _round_half_up(math.sqrt(power_w)))
    feet = height_m / FOOT_M
    h = 0 if feet <= 10 else min(9, _round_half_up(math.log2(feet / 10)))
    return f"PHG{p}{h}{min(9, max(0, gain_db))}{ANTENNA_DIRECTIONS.index(direction)}"


class OldLine:
    """A radio of the old shape (services/common.Radio) read as an AirRadio: radio 1 when its type is of the FM kind, radio 2 when it is of the HF kind; its limits and what it is allowed are its type's,
    read afresh on every call (a line's profile changes with the settings); its frame cap is the line's; its choices are those of the station's radio of that id, radio 1's where that kind has no such one."""

    def __init__(self, line: Radio, config: ConfigSource) -> None:
        self.line = line
        self._config = config
        self._stats = TncStats()                                # (the counters of a line that keeps none: a test's stub)

    @property
    def kind(self) -> Kind:
        return "hf" if self.line.rtype.kind == "hf" else "fm"

    @property
    def id(self) -> RadioId:
        return HF_ID if self.kind == "hf" else FM_ID

    def _spec(self, key: str | None = None) -> RadioSpec | None:
        c = self._config()
        spec = c.radio(self.id)
        return spec if spec is not None and (key is None or kind_field(spec.kind, key) is not None) else c.radio(FM_ID)

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
        found = kind_field(self.kind, key) or kind_field("fm", key)                # (settings with no radio of the id: the field's default)
        return None if found is None else found.parse(found.default)


def is_air(radio: AirRadio | Radio) -> TypeIs[AirRadio]:
    """Whether the radio is in the shape of the registry's radios (it has its limits and what it is allowed), not the old one."""
    return hasattr(radio, "allowed") and hasattr(radio, "limits")


def air_of(radio: AirRadio | Radio, config: ConfigSource, *, old: bool = False) -> AirRadio:
    """The radio as an AirRadio: itself, or an old one read as one (`OldLine`). In a call of the old shape (`old`: a beacon made without the maker, a status report given a beacon or a line) every radio
    that has a type of its own (`rtype`: a line, a test's stub) is read as the old one, as the beacon read it before, by the station's beacon/path: a test's stub is both shapes, and its own choices are not
    the station's."""
    if is_air(radio) and not (old and hasattr(radio, "rtype")):
        return radio
    return OldLine(cast(Radio, radio), config)


class BeaconFrames:
    """Our frames for any radio, from the settings as they are when a frame is made (and the GPS fix of then, for a moving station)."""

    def __init__(self, config: ConfigSource, gps: Positions | None = None, clock: Clock = utcnow) -> None:
        self._config = config
        self.gps = gps                                          # the fix of a moving station (services/gps.py); None: no GPS is set up
        self.clock = clock
        self._cut_told: dict[RadioId, bytes] = {}               # by radio, the information field as it last went out cut to the radio's frame, so that each cut is said once in the log

    # ---- the position
    def position(self, radio: AirRadio) -> ax25.Frame:
        """The frame of our position for `radio`. Raises BeaconError when the settings do not make one (a call that is not a call, a comment too long), and NoFix, a BeaconError, for a moving station
        with no fresh fix."""
        return self.position_and_fix(radio)[0]

    def position_and_fix(self, radio: AirRadio) -> tuple[ax25.Frame, Fix | None]:
        """The frame of our position for `radio` and the fix it was made from (None for a station that stays where it is): a beacon's timer plans SmartBeaconing from it."""
        c = self._config()
        if reason := can_transmit(c):
            raise BeaconError(reason)
        info, fix = self._position(c)
        return self.frame_for(radio, info), fix

    def position_info(self) -> bytes:
        """The information field of our position for a receive-only iGate that puts it on APRS-IS (services/igate.py): the bytes a radio would carry, but nothing is transmitted, so the transmit interlock
        is not asked, only that the call is one. Raises BeaconError (NoFix for a moving station with no fresh fix) as `position()` does."""
        c = self._config()
        if problem := call_problem(c.station_call):
            raise BeaconError(problem)
        info = self._position(c)[0]
        if len(info) > ax25.MAX_INFO:
            raise BeaconError(f"the information field is {len(info)} bytes, more than the {ax25.MAX_INFO} AX.25 allows")
        return info

    def _position(self, c: Config) -> tuple[bytes, Fix | None]:
        """The information field of the position and the fix it was made from (None for a station that stays where it is). A moving station's says where it is now on every radio (on one without
        SmartBeaconing, HF, its timed beacon carries the fix), and is nothing without a fresh fix."""
        if c.mobile:
            return self._mobile_info(c)
        if problem := c.comment_problem():
            raise BeaconError(problem)
        if c.station_lat is None or c.station_lon is None:
            raise BeaconError("set your position first")
        if not (-90.0 <= c.station_lat <= 90.0 and -180.0 <= c.station_lon <= 180.0):
            raise BeaconError(f"the position {c.station_lat}, {c.station_lon} is not on the earth")
        _check_symbol(c)
        try:
            position = uncompressed_position(c.station_lat, c.station_lon, c.station_symbol_table, c.station_symbol_code)
        except ValueError as e:
            raise BeaconError(str(e)) from None
        return b"=" + position + _phg(c) + _comment_text(c.station_comment).encode("ascii"), None

    def _mobile_info(self, c: Config) -> tuple[bytes, Fix]:
        fix = self.gps.current() if self.gps is not None else None
        if fix is None:
            raise NoFix(self.gps.why_none() if self.gps is not None else "no GPS is set up")
        if refusal := over_the_air_refusal(c.station_comment):
            raise BeaconError(f"station/comment: {refusal}")
        _check_symbol(c)
        try:
            return mobile_info(c, fix), fix
        except ValueError as e:
            raise BeaconError(str(e)) from None

    # ---- the status report
    def status(self, text: str, radio: AirRadio) -> ax25.Frame | None:
        """The frame of a status report with this text for `radio`: `>`, the time as day, hour and minute in UTC with a `z` (`211200z`), then the text. None for an empty text. Raises BeaconError when the
        settings or the text make no frame."""
        if not text:
            return None
        if problem := over_the_air_problem(text):
            raise BeaconError(f"the status: {problem}")
        if len(text) > MAX_STATUS:
            raise BeaconError(f"the status is {len(text)} characters, more than the {MAX_STATUS} that fit after its time")
        return self.frame_for(radio, b">" + self.clock().strftime("%d%H%M").encode("ascii") + b"z" + text.encode("ascii"))

    # ---- the frame
    def frame_for(self, radio: AirRadio, info: bytes) -> ax25.Frame:
        """Our frame with this information field for the radio it goes on: from `station/call` to the tocall by way of the radio's path where it may carry one; its comment cut to what a radio with a
        fixed frame carries (said once in the log), the report itself never. Raises BeaconError when the settings make no frame."""
        c = self._config()
        if reason := can_transmit(c):
            raise BeaconError(reason)
        if len(info) > ax25.MAX_INFO:
            raise BeaconError(f"the information field is {len(info)} bytes, more than the {ax25.MAX_INFO} AX.25 allows")
        if problem := _path_problem(radio, c):
            raise BeaconError(problem)
        try:
            frame = our_frame(c, path_on(radio, c, None), info)
            fitted = fit_frame(frame, radio.max_frame, radio.limits.max_text, radio.limits.max_kiss)
        except FRAME_ERRORS as e:
            raise BeaconError(str(e)) from None
        if fitted is not frame and self._cut_told.get(radio.id) != fitted.info:
            self._cut_told[radio.id] = fitted.info
            log.warning("the beacon is %d bytes more than the radio carries (%d): its comment is cut to %r", len(ax25.encode(frame)), radio.max_frame, fitted.info[fixed_prefix(info):].decode("ascii", "replace"))
        return fitted


def _path_problem(radio: AirRadio, c: Config) -> str:
    """Why the stored path of the radio makes no frame, "" when it does: a path the settings check refuses (only a Config made by hand holds one) stops our frame, as it always did, and is not
    replaced by the default path."""
    if not radio.allowed.paths:
        return ""
    spec = c.radio(radio.id)
    if spec is None or kind_field(spec.kind, "path") is None:
        spec = c.radio(FM_ID)                                   # (a radio whose kind has no path of its own goes by radio 1's, as OldLine.choice does)
    found = None if spec is None else kind_field(spec.kind, "path")
    text = None if spec is None else spec.settings.get("path")
    if found is None or text is None:
        return ""
    try:
        found.parse(text)
    except ValueError as e:
        return f"the path: {e}"
    return ""


def _check_symbol(c: Config) -> None:
    if c.station_symbol_table not in SYMBOL_TABLES or len(c.station_symbol_table) != 1 or not "!" <= c.station_symbol_code <= "~" or len(c.station_symbol_code) != 1:
        raise BeaconError(f"the symbol {c.station_symbol_table!r} {c.station_symbol_code!r} is not a table (/ \\ A-Z 0-9) and one printable character")


def _phg(c: Config) -> bytes:
    if c.beacon_power_w is None:
        return b""
    return phg_text(c.beacon_power_w, c.beacon_antenna_height_m, c.beacon_antenna_gain_db, c.beacon_antenna_direction).encode("ascii")
