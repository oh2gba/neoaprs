"""The dispatcher of the page's commands (neoaprs/web/dispatch.py): registering a handler, what a
handler is given, and the `error` each kind of refusal is answered with, with its log line."""

import logging
from typing import Any

import pytest

from neoaprs.web.beaconwire import BeaconNow
from neoaprs.web.configwire import SetConfig
from neoaprs.web.dispatch import FAILED, REGISTRY, Ctx, Dispatcher, Handler, UserError, command, command_name
from neoaprs.web.hostwire import Ping
from neoaprs.web.session import Connection

CTL, HUB, ERRORS, SCOPES, LEVELS, LAYERS, SATELLITES = (object() for _ in range(7))


async def status() -> dict[str, Any]:
    return {}


class Out:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send(self, conn: Connection, message: dict[str, Any]) -> None:
        self.sent.append(message)

    def send_frame(self, conn: Connection, text: str) -> None: ...
    def send_binary(self, conn: Connection, data: bytes) -> None: ...


class Rig:
    """A dispatcher over a registry of its own, with handlers that do what each test asks."""

    def __init__(self) -> None:
        self.registry: dict[str, Handler] = {}
        self.out = Out()
        self.conn = Connection(client=None, out=self.out)  # type: ignore[arg-type]
        self.called: list[tuple[Ctx, Any]] = []
        self.raise_: Exception | None = None
        for model in (Ping, SetConfig, BeaconNow):
            command(model, self.registry)(self.handler)
        self.dispatcher = Dispatcher(
            CTL,  # type: ignore[arg-type]
            HUB,  # type: ignore[arg-type]
            status,
            self.registry,
            ERRORS,  # type: ignore[arg-type]
            SCOPES,  # type: ignore[arg-type]
            LEVELS,  # type: ignore[arg-type]
            LAYERS,  # type: ignore[arg-type]
            SATELLITES,  # type: ignore[arg-type]
        )

    async def handler(self, ctx: Ctx, cmd: Any) -> None:
        self.called.append((ctx, cmd))
        if self.raise_ is not None:
            raise self.raise_

    async def run(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        await self.dispatcher.run(self.conn, raw)
        assert len(self.out.sent) <= 1
        return self.out.sent.pop() if self.out.sent else None


def error(text: str, cmd: str, code: str, key: str | None = None, params: Any = None, **id: int) -> dict[str, Any]:
    return {"type": "error", "cmd": cmd, "key": key, "code": code, "params": params or {}, "text": text, **id}


@pytest.fixture
def rig() -> Rig:
    return Rig()


# ---- the registry


def test_the_name_of_a_command_is_the_literal_of_its_model() -> None:
    assert (command_name(Ping), command_name(SetConfig), command_name(BeaconNow)) == (
        "ping",
        "set_config",
        "beacon_now",
    )


def test_a_handler_goes_into_the_registry_it_is_given_and_a_second_for_one_command_is_refused() -> None:
    registry: dict[str, Handler] = {}
    before = dict(REGISTRY)

    async def first(ctx: Ctx, cmd: Ping) -> None: ...

    assert command(Ping, registry)(first) is first
    assert registry == {"ping": Handler("ping", Ping, first)} and REGISTRY == before
    with pytest.raises(ValueError, match="ping has two handlers"):
        command(Ping, registry)(first)
    assert registry["ping"].fn is first


def test_with_no_registry_given_the_dispatcher_runs_the_programs_own() -> None:
    assert Dispatcher(CTL, HUB, status).registry is REGISTRY  # type: ignore[arg-type]


# ---- what a handler gets


async def test_a_command_reaches_its_handler_as_its_model_with_everything_the_dispatcher_holds(rig: Rig) -> None:
    assert await rig.run({"cmd": "ping"}) is None
    [(ctx, cmd)] = rig.called
    assert isinstance(cmd, Ping)
    assert (ctx.ctl, ctx.conn, ctx.hub, ctx.status, ctx.page_errors) == (CTL, rig.conn, HUB, status, ERRORS)
    assert (ctx.scopes, ctx.levels, ctx.layers, ctx.satellites) == (SCOPES, LEVELS, LAYERS, SATELLITES)


async def test_set_config_reaches_its_handler_with_its_values_and_its_id(rig: Rig) -> None:
    await rig.run({"cmd": "set_config", "values": {"station/call": "OH2GBA"}, "id": 7})
    [(_, cmd)] = rig.called
    assert isinstance(cmd, SetConfig) and (cmd.values, cmd.id) == ({"station/call": "OH2GBA"}, 7)


# ---- commands that are none


async def test_a_frame_with_no_command_name_is_answered_so(rig: Rig) -> None:
    for raw in ({}, {"cmd": ""}, {"cmd": 5}, {"cmd": None}, {"cmd": ["ping"]}):
        assert await rig.run(raw) == error('a command has a "cmd"', "", "no_command", params={"name": ""})
    assert rig.called == []


async def test_an_unknown_command_is_answered_with_its_name_cut_to_forty_characters(rig: Rig) -> None:
    name = "x" * 50
    assert await rig.run({"cmd": name, "id": 3}) == error(
        f"unknown command {'x' * 40!r}", "", "unknown_command", params={"name": "x" * 40}
    )
    assert rig.called == []


# ---- a command that does not fit its model


async def test_a_command_that_does_not_fit_its_model_is_answered_invalid_and_logged(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="neoaprs.web"):
        answer = await rig.run({"cmd": "set_config", "values": "station/call", "id": 9})
    assert answer is not None and (answer["cmd"], answer["code"], answer["id"]) == ("set_config", "invalid", 9)
    assert answer["text"].startswith("set_config: values: "), "the text names the command and then the field"
    assert rig.called == []
    [record] = caplog.records
    assert record.levelno == logging.WARNING and record.getMessage().endswith(answer["text"])


# ---- the id of a request


@pytest.mark.parametrize("bad", ["7", 7.0, True, None, [7]], ids=["text", "float", "bool", "none", "list"])
async def test_only_a_whole_number_is_a_requests_id_and_only_set_configs(rig: Rig, bad: object) -> None:
    rig.raise_ = UserError("no", "setting.unknown")
    answer = await rig.run({"cmd": "set_config", "values": {}, "id": 7})
    assert answer is not None and answer["id"] == 7
    answer = await rig.run({"cmd": "set_config", "values": {}, "id": bad})
    assert answer is not None and "id" not in answer
    answer = await rig.run({"cmd": "beacon_now", "id": 7})
    assert answer is not None and "id" not in answer, "the id of another command is not a request's"


# ---- a refusal and a failure


async def test_a_refusal_is_answered_with_its_text_code_key_and_params_and_not_logged(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    rig.raise_ = UserError("the call is not set", "setting.missing", "station/call", {"max": 6})
    with caplog.at_level(logging.DEBUG, logger="neoaprs.web"):
        answer = await rig.run({"cmd": "set_config", "values": {}, "id": 4})
    assert answer == error("the call is not set", "set_config", "setting.missing", "station/call", {"max": 6}, id=4)
    assert caplog.records == []


async def test_a_refusal_the_operator_cannot_act_on_is_logged_as_a_warning_too(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    rig.raise_ = UserError("the radio's port could not be opened: busy", "failed")
    with caplog.at_level(logging.DEBUG, logger="neoaprs.web"):
        answer = await rig.run({"cmd": "beacon_now"})
    assert answer == error("the radio's port could not be opened: busy", "beacon_now", "failed")
    [record] = caplog.records
    assert (record.levelno, record.getMessage()) == (logging.WARNING, "the radio's port could not be opened: busy")


@pytest.mark.expects_errors
async def test_a_handler_that_breaks_is_logged_with_its_exception_and_answered_in_plain_words(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    rig.raise_ = RuntimeError("database gone at /home/x/neoaprs.sqlite")
    with caplog.at_level(logging.DEBUG, logger="neoaprs.web"):
        answer = await rig.run({"cmd": "set_config", "values": {}, "id": 12})
    assert answer == error(f"set_config: {FAILED}", "set_config", "failed", id=12)
    assert "database" not in answer["text"], "the exception goes to the log only"
    [record] = caplog.records
    assert record.levelno == logging.ERROR and record.getMessage() == "command set_config failed"
    assert record.exc_info is not None and record.exc_info[0] is RuntimeError
