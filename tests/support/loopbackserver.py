"""The part that the fake servers on the loopback share (the fake version page, the fake HTTP server of the download tests): a listening asyncio server on a free port that is started and stopped."""
import asyncio
from typing import Self


class LoopbackServer:
    port = 0
    _server: asyncio.Server | None = None

    async def start(self) -> Self:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        raise NotImplementedError
