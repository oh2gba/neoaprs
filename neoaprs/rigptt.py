"""Key a radio through a rig program the operator runs: flrig's XML-RPC server or Hamlib's rigctld.

Each call is one short connection on the event loop; `set` returns once the program says the rig is
in the state asked for. Everything that goes wrong is a `RigRefused` whose text is ready for the log.
"""

import asyncio
import xmlrpc.client
from typing import Any, Protocol
from xml.parsers.expat import ExpatError

from . import nodevices

ANSWER_SEC = 2.0  # flrig's set_ptt waits up to 1 s for the rig's own state
MAX_ANSWER_BYTES = 65536


class RigRefused(Exception):
    """The rig program did not do what it was asked, did not answer, or cannot be reached.

    `answered`: the program answered, so the rig is in the state it said (not keyed by a refused key-down)."""

    def __init__(self, text: str, answered: bool = False) -> None:
        super().__init__(text)
        self.answered = answered


class Ptt(Protocol):
    def describe(self) -> str: ...
    async def set(self, on: bool) -> None: ...
    async def probe(self) -> None: ...


async def _exchange(host: str, port: int, what: str, talk: Any, timeout_sec: float) -> Any:
    """Run `talk(reader, writer)` on a fresh connection; raise RigRefused for any failure."""
    try:
        nodevices.check_host(host, what)
        async with asyncio.timeout(timeout_sec):
            reader, writer = await asyncio.open_connection(host, port)
            try:
                return await talk(reader, writer)
            finally:
                writer.transport.abort()
    except TimeoutError:
        raise RigRefused(f"{what} at {host}:{port} gave no answer in {timeout_sec:g} s") from None
    except ConnectionRefusedError:
        # nothing listens there, so nothing was keyed through it
        raise RigRefused(f"{what} at {host}:{port} refused the connection: is it running?", answered=True) from None
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError):
        raise RigRefused(f"{what} at {host}:{port} hung up") from None
    except OSError as e:
        raise RigRefused(f"{what} at {host}:{port}: {e.strerror or e}") from None


class Flrig:
    """flrig's XML-RPC server: `rig.set_ptt` then `rig.get_ptt` (flrig's src/server/xml_server.cxx)."""

    def __init__(self, host: str, port: int, timeout_sec: float = ANSWER_SEC) -> None:
        self.host, self.port, self.timeout_sec = host, port, timeout_sec

    def describe(self) -> str:
        return f"flrig at {self.host}:{self.port}"

    async def _call(self, method: str, *params: Any) -> Any:
        body = xmlrpc.client.dumps(params, method).encode()

        async def talk(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> Any:
            writer.write(
                (
                    f"POST /RPC2 HTTP/1.1\r\nHost: {self.host}:{self.port}\r\nContent-Type: text/xml\r\n"
                    f"Content-Length: {len(body)}\r\n\r\n"
                ).encode()
                + body
            )
            head = await reader.readuntil(b"\r\n\r\n")
            status, *fields = head.decode("latin-1").split("\r\n")
            if " 200 " not in f"{status} ":
                raise RigRefused(f"flrig answered {status.strip()!r}")
            length = next((f.split(":", 1)[1] for f in fields if f.lower().startswith("content-length:")), "")
            if not length.strip().isdigit() or int(length) > MAX_ANSWER_BYTES:
                raise RigRefused("flrig's answer has no length")
            return await reader.readexactly(int(length))

        answer = await _exchange(self.host, self.port, "flrig", talk, self.timeout_sec)
        try:
            values, _ = xmlrpc.client.loads(answer.decode("utf-8", "replace"))
        except xmlrpc.client.Fault as e:
            raise RigRefused(f"flrig refused {method}: {e.faultString}") from None
        except (ExpatError, ValueError, TypeError) as e:
            raise RigRefused(f"flrig's answer to {method} cannot be read: {e}") from None
        return values[0] if len(values) == 1 else None

    async def set(self, on: bool) -> None:
        # flrig answers set_ptt with 0 at once while it has no radio (or its XML-RPC is off), else with nothing
        if await self._call("rig.set_ptt", int(on)) == 0:
            raise RigRefused("flrig has no radio connected, or its XML-RPC control is switched off", answered=True)
        state = await self._call("rig.get_ptt")
        if state != int(on):
            raise RigRefused(f"flrig says the PTT is {state!r} after it was set to {int(on)}", answered=state == 0)

    async def probe(self) -> None:
        await self._call("main.get_version")


class Rigctld:
    """Hamlib's rigctld: `T 1` / `T 0`, answered `RPRT 0`, then `t` (rigctld(1), set_ptt and get_ptt)."""

    def __init__(self, host: str, port: int, timeout_sec: float = ANSWER_SEC) -> None:
        self.host, self.port, self.timeout_sec = host, port, timeout_sec

    def describe(self) -> str:
        return f"rigctld at {self.host}:{self.port}"

    async def _ask(self, lines: list[str]) -> list[str]:
        async def talk(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> list[str]:
            answers = []
            for line in lines:
                writer.write(f"{line}\n".encode())
                raw = await reader.readline()
                if not raw:
                    raise RigRefused(f"rigctld at {self.host}:{self.port} hung up")
                answers.append(raw.decode("latin-1").strip())
            return answers

        answers: list[str] = await _exchange(self.host, self.port, "rigctld", talk, self.timeout_sec)
        return answers

    async def set(self, on: bool) -> None:
        reply, state = await self._ask([f"T {int(on)}", "t"])
        if reply != "RPRT 0":
            raise RigRefused(f"rigctld answered {reply!r} to T {int(on)}", answered=on)
        if state != str(int(on)):
            raise RigRefused(f"rigctld says the PTT is {state!r} after it was set to {int(on)}", answered=state == "0")

    async def probe(self) -> None:
        (state,) = await self._ask(["t"])
        if state.startswith("RPRT"):
            raise RigRefused(f"rigctld answered {state!r} when asked for the PTT")


def ptt_for(kind: str, host: str, port: int) -> Ptt:
    """Return the client of the rig program `kind` (`flrig`, `rigctld`)."""
    return Flrig(host, port) if kind == "flrig" else Rigctld(host, port)
