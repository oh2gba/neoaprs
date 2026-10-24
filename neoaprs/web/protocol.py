"""The wire format between the daemon and the page, as pydantic models.

One WebSocket per tab, JSON text frames both ways. Two discriminated unions describe everything that crosses it:

  * `Command`: what the page sends, tagged by `cmd`. The daemon validates every incoming frame against it before it does anything: a frame that does not fit is answered with
    `{"type": "error", "text": ...}` and changes nothing.
  * `Message`: what the daemon sends, tagged by `type`; with NEOAPRS_VALIDATE_OUT=1 every frame that leaves is checked against this union (the tests run so), so the models and the builders
    cannot drift apart.

The docstrings and field descriptions are the documentation: `scripts/gen-protocol.py` turns them into PROTOCOL.md, a JSON Schema and the TypeScript types of the page (ui/src/protocol).
Nothing else in the repository describes the format.

This module holds the two unions, the value of each topic (`TopicValues`) and the validators made from them. The models themselves are in the `neoaprs/web/*wire.py` modules, one for each area
(the daemon, the hub, the stations, the packets, the TNC, the settings, the beacon, the messages, the message board, the objects and bulletins of ours, the station preferences, the weather, the base map, Update now), which import `neoaprs/web/wirebase.py` and nothing else of neoaprs/web/, never this module.

Conventions: every time is UTC ISO 8601 ending in `Z` (`2026-10-21T12:00:00Z`); a station is referred to by its call and a packet by its id, never by a position in a list; the models are strict
(no `"5"` for 5, no `1` for true) and reject fields they do not know. pydantic lives in `neoaprs/web/` only: the rest of `neoaprs/` stays free of it.
"""
from typing import Annotated, Any, Union, cast, get_args, get_type_hints

from pydantic import Field, TypeAdapter

from .beaconwire import BeaconNow, StatusNow
from .bulletinwire import BulletinDelete, BulletinRow
from .configwire import ConfigValues, SetConfig
from .hostwire import AskStatus, CheckUpdate, Error, Hello, Ping, Pong, Status, UpdateResultMsg
from .hubwire import PatchMsg, StateMsg, Subscribe, Unsubscribe
from .mapwire import MapCancel, MapEstimate, MapFetch, MapState
from .messagewire import AlertResultMsg, AlertTest, ConversationDelete, MessageCancel, MessageDelete, MessageRetry, MessageRow, OverheardDelete, QueryStation, SendMessage
from .ownwire import BulletinPost, BulletinUnpost, ObjectKill, ObjectSet, OwnBulletinRow, OwnObjectRow
from .packetwire import PacketRow
from .portwire import FindRadio, FindRadioCancel, ListPorts, PortsMsg, RadioSearchMsg
from .prefwire import ClearStationPath, ClearStationTimeout, SetStationPath, SetStationRfOnly, SetStationTimeout, StationPref
from .stationwire import ForgetStation, StationRow
from .tncwire import TncReconnect, TncState
from .updatewire import UpdateCancel, UpdateNow, UpdateState
from .weatherwire import WeatherSeries, WeatherSeriesMsg
from .wirebase import _Command, _Message, _Model


# ---- Client to server
AnyCommand = Union[Ping, AskStatus, CheckUpdate, Subscribe, Unsubscribe, ForgetStation, TncReconnect, ListPorts, FindRadio, FindRadioCancel, SetConfig, BeaconNow, StatusNow, SendMessage, QueryStation, MessageRetry, MessageCancel, MessageDelete, ConversationDelete, OverheardDelete, SetStationPath, ClearStationPath, SetStationTimeout, ClearStationTimeout, SetStationRfOnly, WeatherSeries, AlertTest, BulletinDelete, ObjectSet, ObjectKill, BulletinPost, BulletinUnpost, MapEstimate, MapFetch, MapCancel, UpdateNow, UpdateCancel]
Command = Annotated[AnyCommand, Field(discriminator="cmd")]
"""Every command the page may send."""

COMMAND_TYPES: tuple[type[_Command], ...] = get_args(AnyCommand)      # the union above, once
COMMAND_NAMES: frozenset[str] = frozenset(t.model_fields["cmd"].annotation.__args__[0] for t in COMMAND_TYPES)      # type: ignore[union-attr]
COMMANDS = cast("TypeAdapter[AnyCommand]", TypeAdapter(Command))


# ---- what the topics of the hub hold
class TopicValues(_Model):
    """The value of each topic a page follows (neoaprs/web/topics.py): what `state` carries as `value`, and what `patch` replaces."""
    stations: dict[str, StationRow] = Field(description="the station book by call: a station heard again is a `set` of its row, one that is forgotten or pruned a `del`")
    packets: dict[str, PacketRow] = Field(description="the latest 200 packets by id (as text): a packet is a `set`, and the one that falls out of the 200 a `del`; the highest id is the newest")
    tnc: TncState = Field(description="the radio; told whole as it changes, at most four times a second")
    config: ConfigValues = Field(description="the settings; told again after every save, though nothing differs: the settings form waits for it")
    station_prefs: dict[str, StationPref] = Field(description="what the operator set for each station that has anything set, by call: its own path and its own timeout, each null where none is set, and whether it is RF only. "
                                                   "`set_station_path`, `clear_station_path`, `set_station_timeout`, `clear_station_timeout` and `set_station_rf_only` each give a `set` of the entry, or a `del` when nothing is left in it")
    messages: dict[str, MessageRow] = Field(description="every message by id (as text), all of them sent with the first `state`: a message that is new or changes is a `set` of its row, one that is deleted a `del`; none leaves on its own")
    bulletins: dict[str, BulletinRow] = Field(description="the message board by `sender/slot` (`OH2XYZ/BLN1`): the bulletins, announcements, group bulletins and group messages heard and not deleted; one that is new or heard again is a `set` of its row, one that is deleted (`bulletin_delete`) a `del`")
    own_objects: dict[str, OwnObjectRow] = Field(description="the objects and items of ours by name: `object_set` makes or changes one (a `set` of its row, each time it is sent too), `object_kill` ends one (its row changes to `killing`, and is a `del` once the kill has been sent); a live one is also a row of `stations`")
    own_bulletins: dict[str, OwnBulletinRow] = Field(description="the bulletins, announcements and group bulletins of ours by slot (`BLN1`): `bulletin_post` posts one (a `set` of its row, each time it is sent too), `bulletin_unpost` deletes one (a `del`)")
    map: MapState = Field(description="the base map: the files, the area and detail the settings ask for, the size estimated, and the job that makes the maps, and the ALOHA circle; told whole as it changes, at most four times a second")
    update: UpdateState = Field(description="Update now: whether this copy can update itself, and the steps of the update it is doing; told whole as it changes, at most four times a second")


TOPIC_NAMES: tuple[str, ...] = tuple(get_type_hints(TopicValues))
TOPIC_VALUES = {name: TypeAdapter(annotation) for name, annotation in get_type_hints(TopicValues).items()}
"""A validator for the value of each topic, by the topic's name: the outgoing check looks at `state` and `patch` with it (neoaprs/web/outbound.py)."""
TOPIC_ITEMS: dict[str, "TypeAdapter[Any]"] = {"stations": TypeAdapter(StationRow), "packets": TypeAdapter(PacketRow), "messages": TypeAdapter(MessageRow), "bulletins": TypeAdapter(BulletinRow), "station_prefs": TypeAdapter(StationPref), "own_objects": TypeAdapter(OwnObjectRow), "own_bulletins": TypeAdapter(OwnBulletinRow)}
"""A validator for one item of a table topic: the outgoing check looks at the `set` ops with it."""


# ---- Server to client
AnyMessage = Union[Hello, Status, Pong, Error, PortsMsg, StateMsg, PatchMsg, WeatherSeriesMsg, AlertResultMsg, UpdateResultMsg, RadioSearchMsg]
Message = Annotated[AnyMessage, Field(discriminator="type")]
"""Every message the daemon sends."""

MESSAGE_TYPES: tuple[type[_Message], ...] = get_args(AnyMessage)      # the union above, once
MESSAGE_NAMES: frozenset[str] = frozenset(t.model_fields["type"].annotation.__args__[0] for t in MESSAGE_TYPES)      # type: ignore[union-attr]
MESSAGES = cast("TypeAdapter[AnyMessage]", TypeAdapter(Message))
