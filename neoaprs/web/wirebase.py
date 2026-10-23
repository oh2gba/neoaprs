"""The bases of the models of the wire format (the `neoaprs/web/*wire.py` modules and `neoaprs/web/protocol.py`): strict, no field the model does not know, and the titles the TypeScript names are made of; and
the scalar types and the models that several of those modules share (a time, the details of a position)."""
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Iso = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", description="UTC, ISO 8601 with a Z")]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


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
    shape: str = Field(description="open circle, line, open ellipse, open triangle, open box, filled circle, coloured line, filled ellipse, filled triangle or filled box")
    colour: str
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
