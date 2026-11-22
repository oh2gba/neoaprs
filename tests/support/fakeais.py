"""A fake AIS receiver on a free loopback port: a TCP server that sends the test's NMEA lines to
each connection."""
import asyncio

from tests.support.env import remember_stop, until
from tests.support.loopbackserver import LoopbackServer


class FakeAis(LoopbackServer):
    def __init__(self) -> None:
        self.writers: list[asyncio.StreamWriter] = []
        self.connections = 0

    @property
    def address(self) -> str:
        return f"127.0.0.1:{self.port}"

    async def until_connected(self, count: int = 1) -> None:
        await until(lambda: len(self.writers) >= count, 15.0)

    def send(self, *lines: str) -> None:
        data = "".join(line + "\r\n" for line in lines).encode()
        for writer in self.writers:
            writer.write(data)

    def send_raw(self, data: bytes) -> None:
        for writer in self.writers:
            writer.write(data)

    def drop(self) -> None:
        for writer in self.writers:
            writer.close()
        self.writers.clear()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections += 1
        self.writers.append(writer)
        try:
            await reader.read()                         # (it reads nothing from us: this ends when we close)
        except ConnectionError:
            pass
        finally:
            writer.close()
            if writer in self.writers:
                self.writers.remove(writer)

    async def stop(self) -> None:
        self.drop()
        await super().stop()


async def ais_receiver() -> FakeAis:
    """A started fake receiver, stopped when the test is over."""
    receiver = await FakeAis().start()
    remember_stop(receiver.stop)
    return receiver
