"""Properties of the page's commands on their way in (neoaprs/web/api.py on_command, neoaprs/web/dispatch.py):
any text a page could send is answered with one `error` or reaches its handler, and nothing escapes; an error reply
is a message of the protocol; a command built from its model's values, and every shape the page itself sends, passes
validation and reads back as itself.
"""

import asyncio
import json
import math
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import BaseModel

from neoaprs.ownobject import COURSE_MAX, SPEED_MAX_KMH
from neoaprs.pref import ALERT_KM_MAX, ALERT_KM_MIN
from neoaprs.web.api import Api
from neoaprs.web.chatwire import ChatSay
from neoaprs.web.dispatch import Ctx, Dispatcher, Handler, command
from neoaprs.web.hubwire import Subscribe, Unsubscribe
from neoaprs.web.messagewire import QueryStation
from neoaprs.web.ownwire import ObjectSet
from neoaprs.web.prefwire import SetStationAlert
from neoaprs.web.protocol import COMMAND_NAMES, COMMAND_TYPES, COMMANDS, MESSAGES, TOPIC_NAMES
from neoaprs.web.qruwire import AskQru
from neoaprs.web.radiowire import StationRadio
from neoaprs.web.session import Connection
from neoaprs.web.skedwire import SkedDelete, SkedPastDelete, SkedPost
from neoaprs.web.supportwire import PageError

BY_NAME: dict[str, type[BaseModel]] = {
    str(t.model_fields["cmd"].annotation.__args__[0]): t  # type: ignore[union-attr]
    for t in COMMAND_TYPES
}
REFUSALS = {"unknown_command", "no_command", "invalid"}

_LEAF = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.integers(min_value=-(10**400), max_value=10**400),
    st.floats(allow_nan=False),
    st.text(max_size=24),
)
JSON_VALUES = st.recursive(
    _LEAF,
    lambda inner: st.lists(inner, max_size=4) | st.dictionaries(st.text(max_size=8), inner, max_size=4),
    max_leaves=12,
)


def field_names(model: type[BaseModel]) -> list[str]:
    return sorted({f.alias or name for name, f in model.model_fields.items()} - {"cmd"})


@st.composite
def command_dicts(draw: st.DrawFn) -> dict[str, Any]:
    """A command of any registered name with some of its own fields and some others, of any JSON values."""
    name = draw(st.sampled_from(sorted(COMMAND_NAMES)))
    keys = st.sampled_from(field_names(BY_NAME[name]) or ["id"]) | st.text(max_size=8)
    return {"cmd": name, **draw(st.dictionaries(keys, JSON_VALUES, max_size=6))}


# ---- what the models can be built from: Hypothesis's own reading, with help where a field's rule is a validator
TIMES = st.integers(min_value=1_700_000_000, max_value=2_000_000_000)


def iso(seconds: int) -> str:
    return f"{datetime.fromtimestamp(seconds, UTC):%Y-%m-%dT%H:%M:%SZ}"


@st.composite
def sked_posts(draw: st.DrawFn) -> SkedPost:
    start = draw(TIMES)
    length = draw(st.integers(min_value=1, max_value=24 * 3600))
    dial = draw(st.sampled_from(["28.1800 MHz USB", "14.105 MHz USB", "7.0475 MHz LSB"]))
    return SkedPost.model_validate(
        {
            "cmd": "sked_post",
            "from": iso(start),
            "to": iso(start + length),
            "dial": dial,
            "note": draw(st.text(max_size=80)),
        }
    )


CALLS = st.sampled_from(["OH2GBA", "OH2XYZ-9", "W1AW", "N0CALL-15", "OH2GBA-7"])
TOPICS = st.lists(st.sampled_from(TOPIC_NAMES), max_size=5)
HELPED: dict[type[BaseModel], st.SearchStrategy[Any]] = {
    Subscribe: st.builds(Subscribe, cmd=st.just("subscribe"), topics=TOPICS),
    Unsubscribe: st.builds(Unsubscribe, cmd=st.just("unsubscribe"), topics=TOPICS),
    QueryStation: st.one_of(
        st.builds(
            QueryStation,
            cmd=st.just("query"),
            call=CALLS,
            kind=st.sampled_from(["position", "status", "heard", "trace", "weather"]),
        ),
        st.builds(
            QueryStation,
            cmd=st.just("query"),
            call=CALLS,
            kind=st.just("custom"),
            text=st.sampled_from(["?APRSH OH2GBA-15", "?PING?", "?APRSP", "?aprss"]),
        ),
    ),
    AskQru: st.builds(
        AskQru,
        cmd=st.just("qru_ask"),
        text=st.from_regex(r"\A[A-Za-z0-9]{1,8}( [0-9]{1,5})?\Z"),
        radio=st.none() | st.integers(min_value=1, max_value=99),
    ),
    SetStationAlert: st.builds(
        SetStationAlert,
        cmd=st.just("set_station_alert"),
        call=CALLS,
        within_km=st.none() | st.integers(min_value=ALERT_KM_MIN, max_value=ALERT_KM_MAX),
    ),
    ObjectSet: st.builds(
        ObjectSet,
        cmd=st.just("object_set"),
        course_deg=st.none() | st.integers(min_value=0, max_value=COURSE_MAX),
        speed_kmh=st.none() | st.floats(min_value=0, max_value=SPEED_MAX_KMH),
    ),
    SkedPost: sked_posts(),
    SkedDelete: st.builds(SkedDelete, cmd=st.just("sked_delete"), id=st.from_regex(r"\A[0-9a-f]{12}\Z")),
    SkedPastDelete: st.builds(
        SkedPastDelete,
        cmd=st.just("sked_past_delete"),
        ids=st.lists(st.from_regex(r"\A[0-9a-f]{12}\Z"), min_size=1, max_size=3),
    ),
    ChatSay: st.builds(ChatSay, cmd=st.just("chat_say"), text=st.from_regex(r"\A[A-Za-z0-9][A-Za-z0-9 ]{0,40}\Z")),
    PageError: st.builds(
        PageError, cmd=st.just("page_error"), at=TIMES.map(iso), source=st.sampled_from(["vue", "window", "promise"])
    ),
    StationRadio: st.builds(
        StationRadio, cmd=st.just("station_radio"), call=CALLS, radio=st.none() | st.integers(min_value=1, max_value=99)
    ),
}
MODELS = st.one_of(*(HELPED.get(t, st.builds(t)) for t in COMMAND_TYPES))


# ---- a dispatcher whose handlers only note what they were given
class Out:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send(self, conn: Connection, message: dict[str, Any]) -> None:
        self.sent.append(message)

    def send_frame(self, conn: Connection, text: str) -> None: ...
    def send_binary(self, conn: Connection, data: bytes) -> None: ...


async def status() -> dict[str, Any]:
    return {}


class Rig:
    def __init__(self) -> None:
        self.out = Out()
        self.conn = Connection(client=None, out=self.out)  # type: ignore[arg-type]
        self.registry: dict[str, Handler] = {}
        self.called: list[Any] = []
        for model in COMMAND_TYPES:
            command(model, self.registry)(self.handler)
        self.dispatcher = Dispatcher(None, None, status, self.registry)  # type: ignore[arg-type]

    async def handler(self, ctx: Ctx, cmd: Any) -> None:
        self.called.append(cmd)

    def run(self, raw: dict[str, Any]) -> None:
        asyncio.run(self.dispatcher.run(self.conn, raw))


class Tasks:
    def spawn(self, coro: Coroutine[Any, Any, None], name: str) -> None:
        coro.close()


class ApiStandIn:
    """What Api.on_command reads of its api: the page's connection, its tasks and its runner."""

    def __init__(self) -> None:
        self.out = Out()
        self.client = object()
        self.clients = {self.client: Connection(client=None, out=self.out)}  # type: ignore[arg-type]
        self.tasks = Tasks()
        self.taken: list[Any] = []

    def _run(self, conn: Connection, raw: Any) -> Coroutine[Any, Any, None]:
        self.taken.append(raw)
        return asyncio.sleep(0)


def on_command(text: str) -> tuple[list[dict[str, Any]], list[Any]]:
    """Return the errors the page is sent and the commands that go on to the dispatcher for this text."""
    api = ApiStandIn()
    Api.on_command(api, api.client, text)  # type: ignore[arg-type]
    return api.out.sent, api.taken


def a_wire_error(message: dict[str, Any]) -> None:
    """The reply is an `error` of the protocol that JSON can carry."""
    assert message["type"] == "error"
    MESSAGES.validate_python(message)
    json.dumps(message, allow_nan=False)


TEXTS = st.one_of(
    st.text(max_size=60),
    JSON_VALUES.map(json.dumps),
    command_dicts().map(json.dumps),
    st.integers(min_value=1, max_value=3000).map(lambda n: "[" * n + "]" * n),
    st.integers(min_value=1, max_value=3000).map(lambda n: '{"a":' * n + "1" + "}" * n),
    st.sampled_from(["NaN", "Infinity", "-Infinity", '{"cmd": NaN}', "1e999", "9" * 5000, '{"cmd": "ping"', ""]),
)


@settings(max_examples=300)
@given(TEXTS)
def test_any_text_is_one_error_or_one_command_object(text: str) -> None:
    """on_command never raises: text that is no JSON object is one `error`, a JSON object goes on to the dispatcher."""
    errors, taken = on_command(text)
    assert len(errors) + len(taken) == 1
    for message in errors:
        a_wire_error(message)
        assert message["code"] in ("not_json", "not_object")
    for raw in taken:
        assert isinstance(raw, dict)


@settings(max_examples=400)
@given(st.one_of(command_dicts(), st.dictionaries(st.text(max_size=8), JSON_VALUES, max_size=4)))
def test_any_object_is_refused_with_one_error_or_handled_once(raw: dict[str, Any]) -> None:
    """The dispatcher answers any JSON object with one `error` of a refusal code, or runs the command's handler once
    with its model, and raises nothing."""
    rig = Rig()
    rig.run(raw)
    assert len(rig.out.sent) + len(rig.called) == 1
    for message in rig.out.sent:
        a_wire_error(message)
        assert message["code"] in REFUSALS
    for cmd in rig.called:
        assert type(cmd) is BY_NAME[raw["cmd"]]


@settings(max_examples=400)
@given(MODELS, st.data())
def test_a_valid_command_with_one_field_spoiled_is_still_answered(cmd: BaseModel, data: st.DataObject) -> None:
    """A command one field away from a valid one (any JSON value in place of a field) is refused or handled, never a
    crash: the field's validators see every kind of value."""
    raw = cmd.model_dump(mode="json", by_alias=True)
    names = field_names(type(cmd))
    if names:
        raw[data.draw(st.sampled_from(names))] = data.draw(JSON_VALUES)
    rig = Rig()
    rig.run(raw)
    assert len(rig.out.sent) + len(rig.called) == 1
    for message in rig.out.sent:
        a_wire_error(message)


@settings(max_examples=400)
@given(MODELS)
def test_a_command_built_from_its_model_is_accepted_and_reads_back_as_itself(cmd: BaseModel) -> None:
    """The JSON of any valid command passes validation and gives the same command, and reaches its handler."""
    raw = json.loads(json.dumps(cmd.model_dump(mode="json", by_alias=True)))
    assert COMMANDS.validate_python(raw) == cmd
    rig = Rig()
    rig.run(raw)
    assert rig.out.sent == [] and rig.called == [cmd]


# ---- the shapes ui/src sends, as it sends them (the composables and lib files named)
PAGE_SENDS: list[dict[str, Any]] = [
    {"cmd": "ping"},
    {"cmd": "subscribe", "topics": ["stations"]},
    {"cmd": "beacon_now"},
    {"cmd": "status_now"},
    {"cmd": "map_cancel"},
    {"cmd": "map_fetch"},
    {"cmd": "map_estimate"},
    {"cmd": "map_wanted"},
    {"cmd": "message_retry", "id": 12},
    {"cmd": "message_cancel", "id": 12},
    {"cmd": "message_delete", "id": 12},
    {"cmd": "weather_series", "call": "OH2XYZ-13", "hours": 24},
    {"cmd": "packet_history", "call": "OH2XYZ-9", "hours": 24},
    {"cmd": "signal_series", "call": "OH2XYZ-9", "hours": 24},
    {"cmd": "station_traffic", "call": "OH2XYZ-9"},
    {"cmd": "packet_stats"},
    {"cmd": "position_history", "hours": 6},
    {"cmd": "list_ports"},
    {"cmd": "list_ports", "radio": 2},
    {"cmd": "find_radio"},
    {"cmd": "find_radio", "radio": 1},
    {"cmd": "find_radio_cancel", "radio": 1},
    {"cmd": "radio_add", "type": "dummy"},
    {"cmd": "radio_remove", "radio": 2},
    {"cmd": "radio_tune", "radio": 2, "on": True},
    {"cmd": "radio_key_test", "radio": 2},
    {"cmd": "frequencies"},
    {"cmd": "forget_station", "call": "OH2XYZ-9"},
    {"cmd": "forget_all_stations"},
    {"cmd": "set_station_alert", "call": "OH2XYZ-9", "on_air": True, "within_km": 25, "direct": False},
    {"cmd": "set_station_alert", "call": "OH2XYZ-9", "on_air": False, "within_km": None, "direct": True},
    {"cmd": "set_station_rf_only", "call": "OH2XYZ-9", "on": True},
    {"cmd": "set_station_path", "call": "OH2XYZ-9", "path": "WIDE1-1"},
    {"cmd": "set_station_path", "call": "OH2XYZ-9", "path": "DIRECT", "radio": 1},
    {"cmd": "clear_station_path", "call": "OH2XYZ-9", "radio": 1},
    {"cmd": "station_radio", "call": "OH2XYZ-9", "radio": None},
    {"cmd": "send_message", "to": "EMAIL-2", "text": "a@b.fi hello"},
    {"cmd": "query", "call": "OH2XYZ-9", "kind": "position"},
    {"cmd": "query", "call": "OH2XYZ-9", "kind": "custom", "text": "?PING?"},
    {"cmd": "qru_ask", "text": "INFO 250"},
    {"cmd": "qru_ask", "text": "RP70", "path": "WIDE1-1", "radio": 1},
    {"cmd": "bulletin_post", "kind": "bulletin", "text": "Net at 20 UTC", "hours": 24},
    {"cmd": "bulletin_post", "kind": "group", "group": "CLUB", "text": "Hi", "hours": 4, "radios": [1]},
    {"cmd": "bulletin_unpost", "slot": "BLN1"},
    {"cmd": "bulletin_delete", "sender": "OH2XYZ", "slot": "BLN1"},
    {
        "cmd": "object_set",
        "name": "REPEATER",
        "kind": "object",
        "lat": 60.17,
        "lon": 24.94,
        "symbol_table": "/",
        "symbol_code": "r",
        "comment": "145.600",
        "course_deg": None,
        "speed_kmh": None,
        "path": None,
        "qru_group": "",
        "on_request": False,
        "radios": [1],
    },
    {"cmd": "object_kill", "name": "REPEATER"},
    # skeds.ts cuts the time to the second
    {
        "cmd": "sked_post",
        "from": "2026-11-28T12:00:00Z",
        "to": "2026-11-28T13:00:00Z",
        "dial": "28.1800 MHz USB",
        "note": "",
    },
    {"cmd": "sked_delete", "id": "0123456789ab"},
    {"cmd": "sked_past_delete", "ids": ["0123456789ab", "0123456789ac"]},
    {"cmd": "skeds_wanted"},
    {"cmd": "chat_say", "text": "hello"},
    {"cmd": "satellite_look", "on": True, "cards": []},
    {"cmd": "layer_look", "layer": "aircraft", "on": True},
    {"cmd": "igate_look", "on": False},
    {"cmd": "alert_test"},
    {"cmd": "update_check"},
    {"cmd": "update_cancel"},
    {"cmd": "set_config", "values": {"station/call": "oh2gba"}, "id": 3},
    {"cmd": "set_config", "values": {"station/lat": "60.1699", "radio/1/enabled": "true"}},
]


@pytest.mark.parametrize("raw", PAGE_SENDS, ids=[str(raw["cmd"]) for raw in PAGE_SENDS])
def test_a_command_as_the_page_sends_it_is_accepted(raw: dict[str, Any]) -> None:
    rig = Rig()
    rig.run(raw)
    assert rig.out.sent == [] and len(rig.called) == 1


def test_a_page_error_as_pageerrors_ts_sends_it_in_whole_seconds_is_accepted() -> None:
    rig = Rig()
    rig.run(
        {
            "cmd": "page_error",
            "message": "x is undefined (in SettingsForm)",
            "stack": "",
            "source": "vue",
            "at": "2026-10-21T12:00:00Z",
            "build": "index-abc123.js",
        }
    )
    assert rig.out.sent == [] and len(rig.called) == 1


def test_a_number_json_cannot_carry_comes_back_as_text_in_the_error() -> None:
    rig = Rig()
    rig.run({"cmd": "position_history", "hours": math.inf})
    [message] = rig.out.sent
    a_wire_error(message)
