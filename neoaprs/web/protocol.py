"""The wire format between the daemon and the page: pydantic models in two discriminated unions.

`Command` (tagged by `cmd`) is what the page sends; `Message` (tagged by `type`) is what the
daemon sends. `scripts/gen-protocol.py` builds PROTOCOL.md from the models.
"""

from typing import Annotated, Any, Union, cast, get_args, get_type_hints

from pydantic import Field, TypeAdapter

from .beaconwire import BeaconNow, StatusNow
from .bulletinwire import BulletinDelete, BulletinRow
from .configwire import ConfigValues, SetConfig
from .generalwire import GeneralQuery, GeneralState
from .gpswire import GpsState
from .igatewire import IgateState
from .historywire import (
    PacketHistory,
    PacketHistoryMsg,
    PacketStats,
    PacketStatsMsg,
    SignalSeries,
    SignalSeriesMsg,
    SpeedSeries,
    SpeedSeriesMsg,
)
from .hostwire import (
    AskStatus,
    CheckUpdate,
    Error,
    Hello,
    Ping,
    Pong,
    ReleaseNotes,
    ReleaseNotesMsg,
    Saved,
    Status,
    UpdateResultMsg,
)
from .hubwire import PatchMsg, StateMsg, Subscribe, Unsubscribe
from .layerwire import LayerLook, LayerThingsMsg
from .mapwire import MapCancel, MapEstimate, MapFetch, MapState, MapWanted
from .messagewire import (
    AlertResultMsg,
    AlertTest,
    ConversationDelete,
    ForgetStationKey,
    MessageCancel,
    MessageDelete,
    MessageRetry,
    MessageRow,
    NewMessageKey,
    OverheardDelete,
    QueryStation,
    SendKey,
    SendMessage,
    StationKey,
)
from .ownwire import BulletinPost, BulletinUnpost, ObjectKill, ObjectSet, OwnBulletinRow, OwnObjectRow
from .packetwire import PacketRow, StationTraffic, StationTrafficMsg
from .portwire import FindRadio, FindRadioCancel, ListPorts, PortsMsg, RadioSearchMsg
from .qruwire import AskQru, QruState
from .radiowire import (
    RadioAdd,
    RadioAddedMsg,
    RadioChange,
    RadioKeyTest,
    RadioLevel,
    RadioLevelMsg,
    RadioRemove,
    RadioScope,
    RadioTune,
    StationRadio,
)
from .replaywire import PositionHistory, PositionHistoryMsg
from .prefwire import ClearStationPath, SetStationAlert, SetStationPath, SetStationRfOnly, StationAlertMsg, StationPref
from .skedwire import SkedDelete, SkedPost, SkedsState, SkedsWanted
from .stationwire import ForgetAllStations, ForgetStation, StationRow, StationTrack, StationTrackMsg
from .supportwire import PageError
from .tncwire import Frequencies, RadioRow
from .updatewire import UpdateCancel, UpdateNow, UpdateState
from .weatherwire import WeatherSeries, WeatherSeriesMsg
from .wirebase import _Command, _Message, _Model


# ---- Client to server
AnyCommand = Union[
    Ping,
    AskStatus,
    CheckUpdate,
    ReleaseNotes,
    Subscribe,
    Unsubscribe,
    ForgetStation,
    ForgetAllStations,
    ListPorts,
    FindRadio,
    FindRadioCancel,
    SetConfig,
    BeaconNow,
    StatusNow,
    SendMessage,
    SendKey,
    ForgetStationKey,
    NewMessageKey,
    QueryStation,
    AskQru,
    GeneralQuery,
    MessageRetry,
    MessageCancel,
    MessageDelete,
    ConversationDelete,
    OverheardDelete,
    SetStationPath,
    ClearStationPath,
    SetStationRfOnly,
    SetStationAlert,
    WeatherSeries,
    PacketHistory,
    PacketStats,
    PositionHistory,
    SpeedSeries,
    SignalSeries,
    StationTraffic,
    AlertTest,
    BulletinDelete,
    ObjectSet,
    ObjectKill,
    BulletinPost,
    BulletinUnpost,
    MapEstimate,
    MapFetch,
    MapWanted,
    MapCancel,
    UpdateNow,
    UpdateCancel,
    SkedsWanted,
    SkedPost,
    SkedDelete,
    PageError,
    RadioAdd,
    RadioRemove,
    RadioChange,
    RadioTune,
    RadioKeyTest,
    RadioScope,
    RadioLevel,
    StationRadio,
    Frequencies,
    StationTrack,
    LayerLook,
]
Command = Annotated[AnyCommand, Field(discriminator="cmd")]
"""Every command the page may send."""

COMMAND_TYPES: tuple[type[_Command], ...] = get_args(AnyCommand)
COMMAND_NAMES: frozenset[str] = frozenset(t.model_fields["cmd"].annotation.__args__[0] for t in COMMAND_TYPES)  # type: ignore[union-attr]
COMMANDS = cast("TypeAdapter[AnyCommand]", TypeAdapter(Command))


# ---- what the topics of the hub hold
class TopicValues(_Model):
    """The value of each topic a page follows (neoaprs/web/topics.py): what `state` carries as `value`, and what `patch` replaces."""

    stations: dict[str, StationRow] = Field(
        description="the station book by call: a station heard again is a `set` of its row, one that is forgotten or pruned a `del`"
    )
    packets: dict[str, PacketRow] = Field(
        description="the latest 200 packets by id (as text): a packet is a `set`, and the one that falls out of the 200 a `del`; the highest id is the newest"
    )
    radios: dict[str, RadioRow] = Field(
        description="every radio of the station by id (as text), removed ones too (marked): what it is, how it is set, its line, its beacon and its modem. A radio added is a `set`; a change of its state, counters, lines, beacon or "
        "modem a `set` of its row, at most four times a second; a change of the settings or of the devices held tells it whole. No radio leaves it"
    )
    config: ConfigValues = Field(
        description="the settings; told again after every save, though nothing differs: the settings form waits for it"
    )
    station_prefs: dict[str, StationPref] = Field(
        description="what the operator set for each station that has anything set, by call: its own path (null where none is set), whether it is RF only and its alert. "
        "`set_station_path`, `clear_station_path`, `set_station_rf_only` and `set_station_alert` each give a `set` of the entry, or a `del` when nothing is left in it"
    )
    messages: dict[str, MessageRow] = Field(
        description="every message by id (as text), all of them sent with the first `state`: a message that is new or changes is a `set` of its row, one that is deleted a `del`; none leaves on its own"
    )
    station_keys: dict[str, StationKey] = Field(
        description="the public key each station announced for encrypted messages, by call: the fingerprint and when it was heard. A key heard is a `set`, `forget_station_key` a `del`"
    )
    bulletins: dict[str, BulletinRow] = Field(
        description="the message board by `sender/slot` (`OH2XYZ/BLN1`): the bulletins, announcements, group bulletins and group messages heard and not deleted; one that is new or heard again is a `set` of its row, one that is deleted (`bulletin_delete`) a `del`"
    )
    own_objects: dict[str, OwnObjectRow] = Field(
        description="the objects and items of ours by name: `object_set` makes or changes one (a `set` of its row, each time it is sent too), `object_kill` ends one (its row changes to `killing`, and is a `del` once the kill has been sent); a live one is also a row of `stations`"
    )
    own_bulletins: dict[str, OwnBulletinRow] = Field(
        description="the bulletins, announcements and group bulletins of ours by slot (`BLN1`): `bulletin_post` posts one in a free slot (a `set` of its row, each time it is sent too), `bulletin_unpost` deletes one (a `del`)"
    )
    map: MapState = Field(
        description="the base map: the files, the area and detail the settings ask for, the size estimated, and the job that makes the maps, the ALOHA circle, and the layers of traffic; told whole as it changes, at most four times a second"
    )
    update: UpdateState = Field(
        description="Update now: whether this copy can update itself, and the steps of the update it is doing; told whole as it changes, at most four times a second"
    )
    gps: GpsState = Field(
        description="the GPS receiver and the moving station's beacon: the latest fix, its state, and when the next beacon by time is due; told whole as it changes, at most once a second"
    )
    igate: IgateState = Field(
        description="the receive-only iGate: whether it is connected to APRS-IS, the server's name, the packets gated and not gated; told whole as it changes, at most once a second"
    )
    qru: QruState = Field(
        description="local info (QRU): the last request sent from here and the servers that answered it, forgotten an hour after; told whole as it changes"
    )
    skeds: SkedsState = Field(
        description="the sked board (the page calls it HF tests): when people will be on the air, as the project's server keeps it, the dials the project suggests, and whether it can be reached or is closed; told whole as it changes"
    )
    general: GeneralState = Field(
        description="asking around: the last general query of each kind sent from here (?APRS?, ?IGATE?, ?WX?) and the stations heard after it that had been quiet before it; told whole as it changes"
    )


TOPIC_NAMES: tuple[str, ...] = tuple(get_type_hints(TopicValues))
TOPIC_VALUES = {name: TypeAdapter(annotation) for name, annotation in get_type_hints(TopicValues).items()}
"""A validator for the value of each topic, by the topic's name: the outgoing check looks at `state` and `patch` with it (neoaprs/web/outbound.py)."""
TOPIC_ITEMS: dict[str, "TypeAdapter[Any]"] = {
    "radios": TypeAdapter(RadioRow),
    "stations": TypeAdapter(StationRow),
    "packets": TypeAdapter(PacketRow),
    "messages": TypeAdapter(MessageRow),
    "bulletins": TypeAdapter(BulletinRow),
    "station_prefs": TypeAdapter(StationPref),
    "station_keys": TypeAdapter(StationKey),
    "own_objects": TypeAdapter(OwnObjectRow),
    "own_bulletins": TypeAdapter(OwnBulletinRow),
}
"""A validator for one item of a table topic: the outgoing check looks at the `set` ops with it."""


# ---- Server to client
AnyMessage = Union[
    Hello,
    Status,
    Pong,
    Error,
    Saved,
    PortsMsg,
    StateMsg,
    PatchMsg,
    WeatherSeriesMsg,
    PacketHistoryMsg,
    PacketStatsMsg,
    PositionHistoryMsg,
    SpeedSeriesMsg,
    SignalSeriesMsg,
    StationTrafficMsg,
    AlertResultMsg,
    UpdateResultMsg,
    ReleaseNotesMsg,
    RadioSearchMsg,
    StationAlertMsg,
    RadioAddedMsg,
    StationTrackMsg,
    RadioLevelMsg,
    LayerThingsMsg,
]
Message = Annotated[AnyMessage, Field(discriminator="type")]
"""Every message the daemon sends."""

MESSAGE_TYPES: tuple[type[_Message], ...] = get_args(AnyMessage)
MESSAGE_NAMES: frozenset[str] = frozenset(t.model_fields["type"].annotation.__args__[0] for t in MESSAGE_TYPES)  # type: ignore[union-attr]
MESSAGES = cast("TypeAdapter[AnyMessage]", TypeAdapter(Message))
