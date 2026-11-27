"""Wire models of the map's satellites layer: `satellite_look` and `satellites`."""

from typing import Literal

from pydantic import Field

from .wirebase import Iso, _Command, _Message, _Model

SatelliteId = int


class SatellitePoint(_Model):
    """Where the point under the satellite is at a time."""

    at: Iso
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class SatelliteMark(_Model):
    """A satellite on the map: the points under it from 30 s ago to 5 minutes ahead, every 30 s; the page moves the mark between them."""

    id: SatelliteId = Field(ge=1, description="its catalogue (NORAD) number")
    name: str = Field(description="its name as the project's list has it (`ISS`, `SONATE-2`)")
    points: list[SatellitePoint]


class SatelliteTune(_Model):
    """A frequency of the list, and where to tune at the next pass: a downlink to hear, an uplink to send on."""

    hz: int = Field(gt=0)
    rise_hz: int | None = Field(description="at the rise; null without a pass")
    max_hz: int | None = Field(description="at the highest point; null without a pass")
    set_hz: int | None = Field(description="at the set; null without a pass")


class SatellitePass(_Model):
    """The pass under way or the next one whose highest point is 10 degrees or more, within a day."""

    rise: Iso
    set: Iso
    max_at: Iso
    max_el_deg: float = Field(ge=0, le=90)
    rise_az_deg: float = Field(ge=0, lt=360)
    set_az_deg: float = Field(ge=0, lt=360)


class SatelliteLookNow(_Model):
    """While the satellite is up: its elevation and the Doppler at a time, every 5 s for 90 s; the page tells now between them."""

    at: Iso
    el_deg: float = Field(ge=-90, le=90)
    down_hz: list[int] = Field(description="the shift heard on each downlink, in their order")
    up_hz: list[int] = Field(description="the offset to send by on each uplink, in their order")


class SatelliteCard(_Model):
    """A satellite whose card the page has open. A frequency, mode or path is there only where the project's list marks it sure."""

    id: SatelliteId = Field(ge=1)
    name: str
    downlinks: list[SatelliteTune]
    uplinks: list[SatelliteTune]
    mode: Literal["afsk1200", "gmsk9600"] | None
    path: str = Field(
        description="the digipeater path to put in a packet (`ARISS`); empty when the list has none it is sure of"
    )
    alt_km: float = Field(ge=0)
    footprint_km: float = Field(
        ge=0, description="the radius on the ground of the circle from which it is above the horizon"
    )
    track: list[SatellitePoint] = Field(description="the points under it for one orbit ahead, every minute")
    next_pass: SatellitePass | None = Field(
        description="null without the station's position or with no pass within a day"
    )
    looks: list[SatelliteLookNow] = Field(description="empty unless it is up now")


class SatelliteLook(_Command):
    """With `on`, this page shows the satellites layer (its tick is on, the page is in front and the replay is closed: the page decides) and has the cards of `cards` open; sent again whenever the cards change.
    With `on` false, or when the page closes, no more. While a page looks, the daemon tells it `satellites` every 30 s and at once on this command."""

    cmd: Literal["satellite_look"]
    on: bool
    cards: list[SatelliteId] = Field(max_length=64)


class SatellitesMsg(_Message):
    """The satellites layer of now, to each page that looks: every satellite shown (elements no older than 14 days) and the cards that page has open. Empty before the project's file has come."""

    type: Literal["satellites"]
    at: Iso
    elements_at: Iso | None = Field(
        description="when the project's server took the orbital elements; null before a file"
    )
    satellites: list[SatelliteMark]
    cards: list[SatelliteCard]
