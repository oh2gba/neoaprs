"""The commands of the page: a registry of handlers and the dispatcher that runs them.

A handler is `async def name(ctx: Ctx, cmd: TheModel) -> None`, registered by `@command(TheModel)`.
`UserError` is answered to the asker as an `error` message; any other exception is logged first.
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
from .layerfeed import LayerLooks
from .levelfeed import RadioLevels
from .scopefeed import RadioScopes
from .session import Connection

log = logging.getLogger("neoaprs.web")
FAILED = "that did not work; the log says why"  # the page shows it by the code `failed`


class UserError(Exception):
    """The command cannot be done.

    The page gets an `error` with `text`, `code`, `params` and `key`.
    """

    def __init__(
        self, text: str, code: str = "other", key: str | None = None, params: Mapping[str, Param] | None = None
    ) -> None:
        super().__init__(text)
        self.code = code
        self.key = key
        self.params: Mapping[str, Param] = params or {}


@dataclass(frozen=True)
class Ctx:
    ctl: Controller
    conn: Connection
    hub: StateHub
    status: Callable[[], Awaitable[dict[str, Any]]]  # the current `status` message
    page_errors: PageErrors | None = None
    scopes: RadioScopes | None = None
    levels: RadioLevels | None = None
    layers: LayerLooks | None = None


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
    """Register the function as the handler of the command that `model` describes."""
    name = command_name(model)
    registry = REGISTRY if into is None else into

    def register(fn: Fn[M]) -> Fn[M]:
        if name in registry:
            raise ValueError(f"{name} has two handlers")
        registry[name] = Handler(name, model, fn)
        return fn

    return register


class Dispatcher:
    def __init__(
        self,
        ctl: Controller,
        hub: StateHub,
        status: Callable[[], Awaitable[dict[str, Any]]],
        registry: dict[str, Handler] | None = None,
        page_errors: PageErrors | None = None,
        scopes: RadioScopes | None = None,
        levels: RadioLevels | None = None,
        layers: LayerLooks | None = None,
    ) -> None:
        self.ctl = ctl
        self.hub = hub
        self.status = status
        self.page_errors = page_errors
        self.scopes, self.levels, self.layers = scopes, levels, layers
        self.registry = REGISTRY if registry is None else registry

    async def run(self, conn: Connection, raw: dict[str, Any]) -> None:
        name = raw.get("cmd")
        name = name if isinstance(name, str) else ""
        if name not in COMMAND_NAMES:
            conn.error(
                f"unknown command {name[:40]!r}" if name else 'a command has a "cmd"',
                code="unknown_command" if name else "no_command",
                params={"name": name[:40]},
            )
            return
        try:
            cmd = COMMANDS.validate_python(raw)
        except ValidationError as e:
            text = describe_errors(name, e.errors(include_url=False, include_input=False))
            # Only a page that is not this daemon's own sends such a command.
            log.warning("a command that does not fit its model: %s", text)
            conn.error(text, name, "invalid")
            return
        try:
            await self._call(conn, name, cmd)
        except UserError as e:
            if e.code == "failed":
                # A refusal the operator cannot act on: the page shows plain words, the log the
                # sentence.
                log.warning("%s", e)
            conn.error(str(e), name, e.code, e.key, e.params)
        except Exception:
            log.exception("command %s failed", name)
            # The page words it from the code; the exception goes to the log only.
            conn.error(f"{name}: {FAILED}", name, code="failed")

    async def _call(self, conn: Connection, name: str, cmd: AnyCommand) -> None:
        await self.registry[name].fn(
            Ctx(self.ctl, conn, self.hub, self.status, self.page_errors, self.scopes, self.levels, self.layers), cmd
        )
