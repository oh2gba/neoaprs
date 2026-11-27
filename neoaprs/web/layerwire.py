"""Wire models of the map traffic layers: `MapLayer`, `layer_look` and `layer_things`."""

from typing import Literal

from pydantic import Field

from .wirebase import Iso, _Command, _Message, _Model

LayerName = Literal["aircraft", "ships"]
SourceName = Literal["none", "adsbfi", "adsblol", "fintraffic", "aisstream", "radarcape", "receiver"]


class LayerReceiver(_Model):
    """The own receiver's state, for its line in Settings. It says nothing of addresses or ports."""

    state: Literal["looking", "connected", "receiving", "no_answer", "no_ais"] = Field(
        description="`looking` until its first answer or connection; `receiving` after an answer in the expected form (AIS: from the first AIS sentence of a connection); `no_answer` after a failure, a wrong answer or a lost connection; `connected` (AIS only) the connection is made and nothing has come yet (a receiver with no ship in range is silent); `no_ais` (AIS only) the source sent something that is not AIS first, or ended the connection without an AIS sentence"
    )
    things: int = Field(
        ge=0, description="what it gave with a position at its last answer (aircraft), or the ships held now (AIS)"
    )
    heard_at: Iso | None = Field(
        description="its last answer in the expected form (AIS: the last sentence decoded); null before one"
    )


class MapLayer(_Model):
    """One layer of traffic in the topic `map`: where its things come from now and what the station is offered."""

    layer: LayerName
    source: SourceName = Field(
        description="the source in force: the one chosen in Settings while it is offered, else `none` (nothing is asked, and the Layers box has no row)"
    )
    offered: list[SourceName] = Field(
        description="the sources the Settings list holds, `none` first: `fintraffic` only where the map's circle reaches its waters; `aisstream` (with the operator's own key, `map/ships_key`) everywhere"
    )
    receiver: LayerReceiver | None = Field(
        description="the own receiver's state while `source` is an own receiver (`radarcape` or `receiver`); else null"
    )
    problem: Literal["", "key_refused"] = Field(
        description="why the service in force gives nothing, where the operator can mend it: `key_refused` AISStream did not take the key of `map/ships_key` (asked again after a longer wait, and at once when the key is saved; cleared by a connection that is taken); empty otherwise"
    )


class LayerThing(_Model):
    """An aircraft or a ship, as its source tells it. Every field is always there; one that is not the layer's is empty or null."""

    id: str = Field(
        description="an aircraft's ICAO address as the source gives it, lower case (it may begin with `~`); a ship's MMSI"
    )
    lat: float
    lon: float
    at: Iso = Field(description="the time of its position")
    heading_deg: int | None = Field(
        ge=0, le=359, description="where the mark points; null: no direction (drawn as a diamond)"
    )
    speed_kmh: float | None = Field(ge=0)
    name: str = Field(description="an aircraft's flight, a ship's name; empty when none")
    emergency: bool = Field(description="an aircraft that says it is in an emergency (or squawks 7500, 7600 or 7700)")
    altitude_m: int | None = Field(description="an aircraft's height")
    vertical_ms: float | None = Field(
        description="an aircraft's vertical speed in metres a second, above zero climbing; null when not told (a ship's is null)"
    )
    registration: str = Field(description="an aircraft's registration (`OH-LZA`); empty when not known")
    type: str = Field(description="an aircraft's type as the source names it; empty when not known")
    category: str = Field(
        description="an aircraft's emitter category as the source gives it, upper case (`A3`, `A7`, `B1`); empty when not known"
    )
    designator: str = Field(
        description="an aircraft's ICAO type designator, upper case (`A321`, `EC35`); empty when not known"
    )
    ship_type: int | None = Field(ge=1, le=99, description="a ship's AIS type of ship and cargo; null when not known")
    course_deg: int | None = Field(
        ge=0,
        le=359,
        description="a ship's course over ground, an aircraft's ground track; null when not told (a heading is not a course)",
    )
    destination: str = Field(
        description="a ship's destination as it gave it; an aircraft's: the ICAO code of the airport it is going to, upper case; empty when not known"
    )
    origin: str = Field(
        description="an aircraft's departure: the ICAO code of the airport it left, upper case; empty when not known"
    )
    origin_place: str = Field(
        description="the place of the airport `origin` names, from the table the program carries; empty when `origin` is empty or not in the table"
    )
    destination_place: str = Field(
        description="the place of the airport `destination` names, from the table the program carries; empty for a ship, and when `destination` is empty or not in the table"
    )


class LayerLook(_Command):
    """With `on`, this page looks at the layer (its tick is on, the page is in front and the replay is closed: the page decides); with `on` false, or when the page closes, no more. While a page looks, the daemon
    asks the layer's source and sends the page `layer_things`. Never refused: a look at a layer whose source is `none` stands and is served once a source is chosen."""

    cmd: Literal["layer_look"]
    layer: LayerName
    on: bool


class LayerTrail(_Model):
    """The way one thing went: its id, and its places as [lon, lat, time], oldest first."""

    id: str
    points: list[tuple[float, float, Iso]]


class LayerThingsMsg(_Message):
    """A layer's whole table, to each page that looks at it and is not behind: at once on `layer_look`, after every answer of the source, at most every 5 s for an AIS receiver, when things grow too old, and
    when the source in force changes (then with the new `source` and no things)."""

    type: Literal["layer_things"]
    at: Iso = Field(
        description="the daemon's time when the table was sent; the age of each thing's `at` is told by it, not by the page's clock"
    )
    layer: LayerName
    source: SourceName = Field(description="the source in force that the things are from")
    away: bool = Field(
        description="true when the last question failed or was not in the expected form, the connection is down, or there is no position to ask for; `things` keeps the last things then"
    )
    things: list[LayerThing]
    trails: list[LayerTrail] = Field(
        description="only in the first table a page gets on `layer_look`, else empty: the way each thing of `things` went in the last 30 minutes while the source was asked (it is asked on for 2 minutes after the last page stopped looking), oldest first: the last minute whole, older points at most one a minute and only where the way bends by more than 50 m"
    )
