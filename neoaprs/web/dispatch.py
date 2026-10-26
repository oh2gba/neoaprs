"""The commands of the page: a registry of handlers and the dispatcher that runs them.

A handler is a function `async def name(ctx: Ctx, cmd: TheModel) -> None` in neoaprs/web/handlers.py, registered by `@command(TheModel)`. What it needs is in `ctx` (the controller, the page that asked, the
hub). The page's answer to a failure is an exception: `raise UserError("text")` is turned into `{"type": "error"}` for the asker; any other exception is logged and answered as "name: text". Every
command of the protocol has exactly one handler (tests/test_protocol.py compares the registry with the protocol's COMMAND_NAMES).
"""
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, get_args

from pydantic import BaseModel, ValidationError

from neoaprs.coded import Param
from neoaprs.controller import Controller

from .hub import StateHub
from .pageerrors import PageErrors
from .problems import describe_errors
from .protocol import COMMAND_NAMES, COMMANDS, AnyCommand
from .session import Connection

log = logging.getLogger("neoaprs.web")


class UserError(Exception):
    """The command cannot be done and the page is told why: the text is the page's `error`, with the `code` and the `params` that say it in words of the page's own, and the `key` of the setting it is about."""

    def __init__(self, text: str, code: str = "other", key: str | None = None, params: Mapping[str, Param] | None = None) -> None:
        super().__init__(text)
        self.code = code
        self.key = key
        self.params: Mapping[str, Param] = params or {}


@dataclass(frozen=True)
class Ctx:
    """What a handler may use: the daemon, the page that asked, and the hub that tells the pages what changed."""
    ctl: Controller
    conn: Connection
    hub: StateHub
    status: Callable[[], Awaitable[dict[str, Any]]]          # the `status` message as it is now
    page_errors: PageErrors | None = None                    # where the errors the pages report about themselves are noted


type Fn[M: BaseModel] = Callable[[Ctx, M], Awaitable[None]]


@dataclass(frozen=True)
class Handler:
    name: str
    model: type[BaseModel]
    fn: Fn[Any]


REGISTRY: dict[str, Handler] = {}


def command_name(model: type[BaseModel]) -> str:
    return str(get_args(model.model_fields["cmd"].annotation)[0])


def command[M: BaseModel](model: type[M], into: dict[str, Handler] | None = None) -> Callable[[Fn[M]], Fn[M]]:
    """Registers the function as the handler of the command that `model` describes."""
    name = command_name(model)
    registry = REGISTRY if into is None else into

    def register(fn: Fn[M]) -> Fn[M]:
        if name in registry:
            raise ValueError(f"{name} has two handlers")
        registry[name] = Handler(name, model, fn)
        return fn
    return register


class Dispatcher:
    """Looks the command up, validates it, runs it, and answers a failure."""

    def __init__(self, ctl: Controller, hub: StateHub, status: Callable[[], Awaitable[dict[str, Any]]], registry: dict[str, Handler] | None = None, page_errors: PageErrors | None = None) -> None:
        self.ctl = ctl
        self.hub = hub
        self.status = status
        self.page_errors = page_errors
        self.registry = REGISTRY if registry is None else registry

    async def run(self, conn: Connection, raw: dict[str, Any]) -> None:
        name = raw.get("cmd")
        name = name if isinstance(name, str) else ""
        if name not in COMMAND_NAMES:
            conn.error(f"unknown command {name[:40]!r}" if name else "a command has a \"cmd\"", code="unknown_command" if name else "no_command", params={"name": name[:40]})
            return
        try:
            cmd = COMMANDS.validate_python(raw)
        except ValidationError as e:
            conn.error(describe_errors(name, e.errors(include_url=False, include_input=False)), name, "invalid")
            return
        try:
            await self._call(conn, name, cmd)
        except UserError as e:
            conn.error(str(e), name, e.code, e.key, e.params)
        except Exception as e:
            log.exception("command %s failed", name)
            conn.error(f"{name}: {e}", name, "failed")

    async def _call(self, conn: Connection, name: str, cmd: AnyCommand) -> None:
        await self.registry[name].fn(Ctx(self.ctl, conn, self.hub, self.status, self.page_errors), cmd)
