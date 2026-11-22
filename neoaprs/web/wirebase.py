"""Base classes of the wire models (strict, TypeScript titles) and the types they share."""
from dataclasses import fields, is_dataclass
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from neoaprs.ax25 import MAX_PATH
from neoaprs.clock import iso
from neoaprs.policy import LOG_KEEP_DAYS

# How far back a command that reads the logs may ask: all the logs keep.
HISTORY_MAX_HOURS = LOG_KEEP_DAYS * 24
# The wire limits typed text by size only, with room over what the core allows. The core reports
# what is wrong with a call, path or message text as a code, so the page can show it translated with
# its numbers.
CALL_ROOM = 64  # a call as typed; the longest real one is 9
TEXT_ROOM = 512  # a message text as typed; a message carries 67 characters
PATH_TEXT_MAX = MAX_PATH * 32  # MAX_PATH calls of up to 9 characters, plus separators

Iso = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", description="UTC, ISO 8601 with a Z")]
Call = Annotated[str, Field(min_length=1, max_length=CALL_ROOM)]
PathText = Annotated[str, Field(max_length=PATH_TEXT_MAX)]
MessageText = Annotated[str, Field(max_length=TEXT_ROOM)]


def plain(value: Any) -> Any:
    """Return the wire form of a value.

    A time becomes ISO text, a tuple a list, a named tuple or dataclass a dict.
    """
    kind = type(value)
    if kind in _SCALARS:
        return value
    if kind is datetime:
        return iso(value)
    if kind is tuple or kind is list:
        return [plain(item) for item in value]
    if hasattr(value, "_asdict"):
        return {name: plain(item) for name, item in value._asdict().items()}
    if is_dataclass(value):
        return {f.name: plain(getattr(value, f.name)) for f in fields(value)}
    return value


_NAMES: dict[type, dict[str, None]] = {}  # field names of each model, in order
_SCALARS = frozenset({type(None), str, int, float, bool})


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    @classmethod
    def row(cls, source: Any, /, **given: Any) -> dict[str, Any]:
        """Return the wire dict: each field from `source`'s same-named attribute or from `given`."""
        names = _NAMES.get(cls)
        if names is None:
            names = _NAMES[cls] = dict.fromkeys(cls.model_fields)
        if given and not given.keys() <= names.keys():
            raise TypeError(f"{cls.__name__} has no field {', '.join(sorted(given.keys() - names.keys()))}")
        out: dict[str, Any] = {}
        for name in names:
            if name in given:
                out[name] = given[name]
            else:
                value = getattr(source, name)
                out[name] = value if type(value) in _SCALARS else plain(value)
        return out


def _command_title(cls: type) -> str:
    return cls.__name__ + "Command"


def _message_title(cls: type) -> str:
    return cls.__name__.removesuffix("Msg") + "Message"


class _Command(_Model):
    """Base of every command. `cmd` names it."""
    model_config = ConfigDict(model_title_generator=_command_title)


class _Message(_Model):
    """Base of every message. `type` names it."""
    model_config = ConfigDict(model_title_generator=_message_title)


class PhgValues(_Model):
    """A station's power, antenna height above average terrain, antenna gain and directivity (`PHG5132`), and the radio range that the formula of the APRS specification gives them."""
    power_w: int
    height_m: float
    gain_db: int
    direction_deg: int | None = Field(description="the direction of the best gain, degrees from north; null for an omni antenna")
    range_km: float


class DfsValues(_Model):
    """The strength of a signal heard by a direction finder (`DFS2360`) with the height, gain and directivity of its antenna."""
    strength: int = Field(ge=0, le=9, description="0 to 9; 0 is where the signal is not heard")
    height_m: float
    gain_db: int
    direction_deg: int | None


class DfBearingValues(_Model):
    """The bearing and quality of a DF report (`/270/729` after the course and speed)."""
    bearing_deg: int
    hits: int = Field(description="0 nothing, 1 to 8 the share of the possible samples that hit, 9 a manual report")
    range_km: float = Field(description="the length the line is drawn to")
    quality: int = Field(ge=0, le=9)


class AreaValues(_Model):
    """An area object (the symbol `\\l`): its shape and colour, and how far down and to the right of the object's position it reaches."""
    shape: Literal["open circle", "line", "open ellipse", "open triangle", "open box", "filled circle", "line down-left", "filled ellipse", "filled triangle", "filled box"] = Field(description="the shape, which the page says in its words")
    colour: Literal["black", "blue", "green", "cyan", "red", "violet", "yellow", "gray", "dim black", "dim blue", "dim green", "dim cyan", "dim red", "dim violet", "dim yellow", "dim gray", "unknown"] = Field(
        description="the colour, which the page says in its words; `unknown` for a number the specification has no colour for")
    lat_offset_deg: float
    lon_offset_deg: float


class ExtensionValues(_Model):
    """The data extensions after the symbol of an uncompressed position (taken off the comment); null for what the position did not have."""
    phg: PhgValues | None
    range_km: float | None = Field(description="a pre-calculated radio range (`RNG0050`)")
    dfs: DfsValues | None
    df_bearing: DfBearingValues | None
    area: AreaValues | None


class LocatorValues(_Model):
    """A Maidenhead locator (grid square) with the symbol that came with it, in a status report or in the status text of a Mic-E packet; the position is the centre of the square."""
    grid: str = Field(description="4 or 6 characters, `IO91sx`")
    lat: float
    lon: float
    symbol_table: str
    symbol_code: str


class FrequencyValues(_Model):
    """A frequency to call on, from the local information at the start of a comment, a status text or the name of a frequency object (`145.775MHz T100 -060 R40k`); null where the text did not say."""
    mhz: float = Field(description="the transmit frequency, MHz")
    tone_hz: int | None = Field(description="the CTCSS tone of `Tnnn` or `Cnnn`, whole hertz (the tenths are dropped: 107 is 107.2)")
    tone_both: bool = Field(description="`Cnnn`: the tone is needed to receive as well")
    tone_off: bool = Field(description="`Toff`: no tone and no DCS code")
    dcs: str | None = Field(description="the DCS code of `Dnnn`, three digits as sent")
    tone_burst: bool = Field(description="`1750`: a 1750 Hz tone burst opens the repeater")
    narrow: bool = Field(description="the first letter of the tone field was lower case: narrow modulation")
    offset_khz: int | None = Field(description="the offset from the transmit frequency in kHz (`-060` is -600); 0 is simplex; null when the standard offset is meant")
    range_km: float | None = Field(description="the nominal range (`R25m` is 40.2 km)")
    rx_mhz: float | None = Field(description="a separate receive frequency (`FFF.FFFrx`), MHz")


class StormValues(_Model):
    """The storm data of a tropical storm, hurricane or tropical depression (APRS101, chapter 12), in metric units; null where the report did not have the field. The movement is the course and speed of the position."""
    storm_type: Literal["TS", "HC", "TD"] = Field(description="TS tropical storm, HC hurricane, TD tropical depression")
    wind_kmh: float | None = Field(description="the sustained wind")
    gust_kmh: float | None
    pressure_hpa: int | None = Field(description="the central pressure")
    hurricane_radius_km: float | None = Field(description="the radius of hurricane winds")
    storm_radius_km: float | None = Field(description="the radius of tropical storm winds")
    gale_radius_km: float | None = Field(description="the radius of whole gale (50 knot) winds")
