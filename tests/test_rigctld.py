"""The rig reading (neoaprs/rigctld.py) on a server that answers badly: a rigctld that hangs up, one that gives no mode, a network that cannot be reached. The good answers and the refusals are in tests/test_rigstatus.py."""
import asyncio
import errno

import pytest

from neoaprs.rigctld import RigError, read_rig
from tests.support.env import remember_stop
from tests.support.fakes import FakeLineServer


async def server(responder: object = None) -> FakeLineServer:
    fake = FakeLineServer()
    fake.responder = responder                                          # type: ignore[assignment]
    await fake.start()
    remember_stop(fake.stop)
    return fake


async def hanging_up() -> int:
    """A server that reads the whole request and closes the connection (an end of the stream, not a reset)."""
    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readexactly(len(b"f\nm\n"))
        writer.close()

    listening = await asyncio.start_server(serve, "127.0.0.1", 0)

    async def stop() -> None:
        listening.close()
        await listening.wait_closed()

    remember_stop(stop)
    return int(listening.sockets[0].getsockname()[1])


async def test_a_rigctld_that_hangs_up_before_it_answers_is_a_rig_error() -> None:
    port = await hanging_up()
    with pytest.raises(RigError, match="rigctld hung up"):
        await read_rig("127.0.0.1", port, 2.0)


async def test_a_rigctld_that_gives_an_empty_mode_is_a_rig_error() -> None:
    fake = await server(lambda line: b"14074000\n" if line == "f" else b"\n")
    with pytest.raises(RigError, match="no mode"):
        await read_rig("127.0.0.1", fake.port, 2.0)


async def test_a_network_that_cannot_be_reached_is_said_in_the_words_of_the_system(monkeypatch: pytest.MonkeyPatch) -> None:
    async def unreachable(host: str, port: int) -> None:
        raise OSError(errno.ENETUNREACH, "Network is unreachable")

    monkeypatch.setattr("asyncio.open_connection", unreachable)
    with pytest.raises(RigError, match="Network is unreachable"):
        await read_rig("10.9.9.9", 4532, 2.0)


async def test_an_error_with_no_words_of_its_own_is_said_as_the_error_is(monkeypatch: pytest.MonkeyPatch) -> None:
    async def odd(host: str, port: int) -> None:
        raise OSError("something odd")

    monkeypatch.setattr("asyncio.open_connection", odd)
    with pytest.raises(RigError, match="something odd"):
        await read_rig("10.9.9.9", 4532, 2.0)
