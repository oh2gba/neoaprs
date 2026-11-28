"""No sentence of the daemon's travels on the wire for the page to show: the daemon sends a code (a
`Literal`) and the values that go into the sentence, and the page's catalogue holds the words in
every language.
"""

import types
from typing import Annotated, Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from neoaprs.web.protocol import COMMAND_TYPES, AnyMessage, TopicValues
from neoaprs.web.wirebase import Iso

ISO = next(m.pattern for m in get_args(Iso)[1].metadata if getattr(m, "pattern", None))

# The operator's own text, a station's (what it sent, as it sent it), the project's (a note of the
# version page, its release notes) and the page's own (an error it reports).
OWN = {
    "AskQru.text",
    "BulletinPost.text",
    "BulletinRow.text",
    "DecodedMessage.text",
    "DecodedOther.text",
    "DecodedPosition.comment",
    "DecodedStatus.text",
    "DecodedTelemetry.comment",
    "DecodedUndecoded.text",
    "DecodedWeather.raw",
    "MessageRow.text",
    "NoteSection.text",
    "ObjectSet.comment",
    "OwnBulletinRow.text",
    "OwnObjectRow.comment",
    "PageError.message",
    "PageError.stack",
    "PositionFields.comment",
    "QruAsked.text",
    "QruServer.sent",
    "QueryStation.text",
    "SendMessage.text",
    "SkedPost.note",
    "SkedRow.note",
    "ChatLineRow.text",
    "ChatFreshMsg.text",
    "ChatSay.text",
    "SkedPast.note",
    "StationRow.last_comment",
    "StationRow.last_status",
    "Status.station_status",
    "TelemetryBit.name",
    "TelemetryChannel.name",
    "TelemetryChannel.unit",
    "TelemetryFields.comment",
    "TelemetryValues.comment",
    "TelemetryValues.project",
    "UpdateInfo.message",
}
# A name or a value: a call, a path, an id, a port or an address, a version, a setting's key and its
# text, a symbol, a frequency, a key of a topic's table.
NAME = {
    # The place of an airport, from the table the program carries
    "LayerThing.origin_place",
    "LayerThing.destination_place",
    "AskQru.path",
    "AttemptRow.internet",
    "BulletinDelete.sender",
    "BulletinDelete.slot",
    "BulletinPost.group",
    "BulletinRow.group",
    "BulletinRow.sender",
    "BulletinRow.slot",
    "BulletinUnpost.slot",
    "ClearStationPath.call",
    "ConfigValues.defaults",
    "ConfigValues.radio_defaults",
    "ConfigValues.radio_values",
    "ConfigValues.urls",
    "ConfigValues.values",
    "ConversationDelete.call",
    "DecodedItem.name",
    "DecodedMessage.ack_id",
    "DecodedMessage.addressee",
    "DecodedMessage.msg_id",
    "DecodedMessage.rej_id",
    "DecodedObject.name",
    "DecodedObject.timestamp",
    "DecodedOther.items",
    "DecodedOther.timestamp",
    "DecodedPosition.sign",
    "DecodedPosition.symbol_code",
    "DecodedPosition.symbol_table",
    "DecodedPosition.timestamp",
    "DecodedStatus.timestamp",
    "DecodedTelemetry.bits",
    "DelOp.key",
    "Error.cmd",
    "Error.code",
    "Error.key",
    "Error.params",
    "ForgetStation.call",
    "ForgetStationKey.call",
    "FrequencyRow.band",
    "FrequencyRow.dial",
    "FrequencyValues.dcs",
    "GeneralAsked.new",
    "GeneralAsked.path",
    "GeneralAsked.query",
    "GeneralQuery.path",
    "Hello.page",
    "Hello.topics",
    "Hello.version",
    "HopRow.call",
    "HttpsState.fingerprint",
    "IgateState.dropped",
    "IgateState.server",
    "InstallInfo.appimage",
    "InstallInfo.arch",
    "LocatorValues.grid",
    "LocatorValues.symbol_code",
    "LocatorValues.symbol_table",
    "MapFileInfo.build",
    "MapFileInfo.name",
    "MapProblem.params",
    "MapSizeEstimate.build",
    "MessageRow.from_call",
    "MessageRow.msg_id",
    "MessageRow.to_call",
    "ModemState.keying",
    "ModemState.mode",
    "ModemState.sound_card",
    "NoteSection.version",
    "ObjectKill.name",
    "ObjectSet.name",
    "ObjectSet.path",
    "ObjectSet.qru_group",
    "ObjectSet.symbol_code",
    "ObjectSet.symbol_table",
    "OverheardDelete.from_call",
    "OverheardDelete.to_call",
    "OwnBulletinRow.group",
    "OwnBulletinRow.slot",
    "OwnObjectRow.name",
    "OwnObjectRow.path",
    "OwnObjectRow.qru_group",
    "OwnObjectRow.symbol_code",
    "OwnObjectRow.symbol_table",
    "PacketHistory.call",
    "PacketHistoryMsg.call",
    "PacketRow.destination",
    "PacketRow.gate",
    "PacketRow.path",
    "PacketRow.sender",
    "PacketRow.source",
    "PageError.build",
    "PatchMsg.topic",
    "PortRow.device",
    "PortRow.usb_group",
    "PortsMsg.keying",
    "PositionFields.sign",
    "PositionFields.symbol_code",
    "PositionFields.symbol_table",
    "PositionFields.timestamp",
    "PositionHistoryMsg.stations",
    "QruGroup.name",
    "QruServer.call",
    "QruServer.received",
    "QruServer.request",
    "QueryStation.call",
    "RadioAdd.name",
    "RadioAdd.type",
    "RadioChange.name",
    "RadioChange.type",
    "RadioChoices.path",
    "RadioHold.value",
    "RadioProblem.params",
    "RadioRow.name",
    "RadioRow.type",
    "RadioSearchMsg.port",
    "RadioSearchMsg.profile",
    "RadioSearchMsg.radio_type",
    "ReachValues.hops",
    "ReachValues.igate",
    "ReleaseNotes.since",
    "ReleaseNotes.version",
    "ReleaseNotesMsg.since",
    "ReleaseNotesMsg.version",
    "RouteMarkValues.gate",
    "RouteMarkValues.hops",
    "SendKey.to",
    "SendMessage.to",
    "SetConfig.values",
    "SetOp.key",
    "SetStationAlert.call",
    "SetStationPath.call",
    "SatelliteCard.name",
    "SatelliteCard.path",
    "SatelliteMark.name",
    "SetStationPath.path",
    "SetStationRfOnly.call",
    "SignalSeries.call",
    "SignalSeriesMsg.call",
    "SkedDelete.id",
    "SkedFrequency.band",
    "SkedFrequency.dial",
    "SkedPost.dial",
    "SkedRow.call",
    "ChatLineRow.call",
    "ChatFreshMsg.call",
    "SkedPast.call",
    "SkedPast.dial",
    "SkedPast.id",
    "SkedRow.dial",
    "SkedRow.id",
    "SoundCardRow.id",
    "SoundCardRow.numbered",
    "SoundCardRow.usb_group",
    "SpeedSeries.call",
    "SpeedSeriesMsg.call",
    "StateMsg.topic",
    "StationAlertMsg.call",
    "StationKey.fingerprint",
    "StationPref.path",
    "StationRadio.call",
    "StationRow.call",
    "StationRow.heard",
    "StationRow.heard_path",
    "StationRow.heard_via",
    "StationRow.last_path",
    "StationRow.paths",
    "StationRow.replies",
    "StationRow.reported_by",
    "StationRow.sign",
    "StationRow.suggested_path",
    "StationRow.symbol_code",
    "StationRow.symbol_table",
    "StationTrack.call",
    "StationTrackMsg.call",
    "StationTraffic.call",
    "StationTrafficMsg.call",
    "Status.call",
    "Status.message_key",
    "Status.unavailable_types",
    "Status.version",
    "Subscribe.topics",
    "TelemetryFields.bits",
    "TopicValues.bulletins",
    "TopicValues.chat_lines",
    "TopicValues.messages",
    "TopicValues.own_bulletins",
    "TopicValues.own_objects",
    "TopicValues.packets",
    "TopicValues.radios",
    "TopicValues.station_keys",
    "TopicValues.station_prefs",
    "TopicValues.stations",
    "Unsubscribe.topics",
    "UpdateInfo.url",
    "UpdateInfo.version",
    "UpdateNow.version",
    "UpdateResultMsg.version",
    "UpdateState.version",
    "WeatherSeries.call",
    "WeatherSeriesMsg.call",
}
# The own words of a device or a program, as it says them: what the system calls a port or a sound
# card, the line of a TNC (its TNC2 text and the Terminal's lines), what a station's device is, the
# first line an alert command wrote.
DEVICE = {
    "AlertResultMsg.line",
    "PacketRow.tnc2",
    "PortRow.description",
    "PortRow.hwid",
    "SoundCardRow.name",
    "StationRow.device",
    "TncLine.text",
    # What an aircraft or a ship says of itself, as its source gave it
    "LayerThing.destination",
    "LayerThing.origin",
    "LayerThing.id",
    "LayerTrail.id",
    "LayerThing.name",
    "LayerThing.registration",
    "LayerThing.type",
    "LayerThing.category",
    "LayerThing.designator",
}
# A route as the daemon writes it (`direct`, `via A → B`, `via G (internet)`): the page takes it
# apart and says it in its words (lib/routes.ts `routeWords`).
ROUTE = {"MessageRow.route", "PacketRow.route", "StationRow.best_route", "StationRow.last_route"}
# The English of a refusal, for the log and the support bundle: the page says a refusal by its
# `code` (ui/src/i18n/errortext.ts) and never shows this.
LOG = {"Error.text"}

KINDS = {"own": OWN, "name": NAME, "device": DEVICE, "route": ROUTE, "log": LOG}


def _is_time(annotation: Any) -> bool:
    return get_origin(annotation) is Annotated and any(
        getattr(m, "pattern", None) == ISO
        for f in get_args(annotation)[1:]
        if isinstance(f, FieldInfo)
        for m in f.metadata
    )


def _carries_text(annotation: Any) -> bool:
    """Whether a value of this type may be a text that is not a code and not a time."""
    if annotation is str:
        return True
    origin = get_origin(annotation)
    if origin is Literal or _is_time(annotation):
        return False
    if origin is Annotated:
        return _carries_text(get_args(annotation)[0])
    return origin in (Union, types.UnionType, list, dict, tuple) and any(_carries_text(a) for a in get_args(annotation))


def _models(annotation: Any) -> list[type[BaseModel]]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    return [m for a in get_args(annotation) for m in _models(a)]


def text_fields() -> set[str]:
    """Every field of every model of the wire that carries a text, as `Model.field`."""
    found: set[str] = set()
    seen: set[type[BaseModel]] = set()
    todo: list[type[BaseModel]] = [*COMMAND_TYPES, *(m for a in get_args(AnyMessage) for m in _models(a)), TopicValues]
    while todo:
        model = todo.pop()
        if model in seen:
            continue
        seen.add(model)
        for name, field in model.model_fields.items():
            if (
                field.annotation is not None
                and _carries_text(field.annotation)
                and not any(getattr(m, "pattern", None) == ISO for m in field.metadata)
            ):
                found.add(f"{model.__name__}.{name}")
            todo.extend(_models(field.annotation))
    return found


def test_every_text_on_the_wire_is_one_that_may_travel_and_none_is_a_sentence_of_the_daemons() -> None:
    declared = set().union(*KINDS.values())
    unknown = sorted(text_fields() - declared)
    assert unknown == [], (
        f"{', '.join(unknown)}: a text field this test does not know. Declare it in tests/test_wire_words.py as the operator's or a station's own text (OWN), a name or a value (NAME), a device's own words (DEVICE) "
        "or a route (ROUTE). If it is a sentence the daemon makes up (a reason, a note, a state, a problem), send a code instead: a Literal of the codes, with the values of the sentence beside it, and the page says "
        'it from its catalogue in every language (CONVENTIONS.md, "Errors and the wire"); the English stays in the log.'
    )


def test_every_text_declared_is_on_the_wire_and_of_one_kind() -> None:
    declared = [field for kind in KINDS.values() for field in kind]
    assert sorted(set(declared) - text_fields()) == [], (
        "a field declared here that the wire does not have (any more): take it out"
    )
    assert len(declared) == len(set(declared)), "a field declared as two kinds"
    assert LOG == {"Error.text"}, (
        "the English of the log travels only as the text of a refusal, which the page does not show"
    )
