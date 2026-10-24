"""A TNC that answers like the kinds the search for the radio meets, for the tests of Find my radio (neoaprs/services/radiofinder.py). `TncBrain` is what the TNC does with the bytes written to it; it is put behind a TCP server on
the loopback (`FakeTncServer`: the line is a `socket://127.0.0.1:PORT`, like the fake radio) or behind a port that takes a speed (`FakeEar`: nothing is opened, so the speed can matter and no device is touched).

    kiss        a TNC in KISS mode that has just heard a packet: it sends one KISS frame as soon as it is connected, and ignores whatever is written
    tnc2        a TNC-2 (Kenwood TH-D7) in command mode: a carriage return is answered with "cmd:", "KISS ON" and "RESTART" put it in KISS, where it is silent
    kantronics  the same, but it takes only INTFACE KISS and RESET; any other command is answered with "?" and the prompt
    d710        the same, but it takes only the D710's sequence, which ends with RESTART after TC 1, TN 2,0, HBAUD 1200 and KISS ON
    silent      a TNC that says nothing (switched off, or in KISS mode and with nothing to hear)
"""
import asyncio

from neoaprs import ax25, kiss
from neoaprs.serialport import SerialError
from neoaprs.services.radioprobe import Ear

PROMPT = b"\r\ncmd:"
UI = ax25.Frame(ax25.Address("APRS"), ax25.Address.parse("OH2GBA-7"), (), info=b"!6010.00N/02456.00E>hello")


class TncBrain:
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.in_kiss = kind == "kiss"
        self.writes: list[bytes] = []                 # everything written to it, as it was written

    def greeting(self) -> bytes:
        return kiss.encode(ax25.encode(UI)) if self.kind == "kiss" else b""

    def hear(self, data: bytes) -> bytes:
        """What the TNC sends back for what it was written."""
        self.writes.append(data)
        if self.kind in ("kiss", "silent") or self.in_kiss:
            return b""
        if data == b"\r":
            return PROMPT
        text = data.decode("ascii", "replace")
        if self._takes(text):
            self.in_kiss = text.rstrip("\r").endswith(("RESTART", "RESET"))
            return b"" if self.in_kiss else PROMPT
        return b"\r\n?EH" + PROMPT

    def _takes(self, text: str) -> bool:
        if self.kind == "tnc2":
            return "KISS ON" in text and "RESTART" in text
        if self.kind == "kantronics":
            return "INTFACE KISS" in text and "RESET" in text
        return self.kind == "d710" and text.strip("\r") in ("TC 1", "TN 2,0", "HBAUD 1200", "KISS ON", "RESTART")


GREETING_PAUSES = (0.05, 0.1)                       # when a TNC that has something to say says it after a connection, and says it once more

class FakeTncServer:
    """A TNC behind a TCP port of the loopback."""

    def __init__(self, kind: str) -> None:
        self.brain = TncBrain(kind)
        self.connections = 0
        self.closed = 0                               # connections the other side has closed
        self.url = ""
        self._server: asyncio.Server | None = None

    async def start(self) -> "FakeTncServer":
        self._server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        self.url = f"socket://127.0.0.1:{self._server.sockets[0].getsockname()[1]}"
        return self

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections += 1
        if greeting := self.brain.greeting():
            for pause in GREETING_PAUSES:                   # (not at the instant of the connection: pyserial's open of a socket drops what came before it was done; a real TNC hears its packets at any time)
                await asyncio.sleep(pause)
                writer.write(greeting)
        try:
            while data := await reader.read(4096):
                if answer := self.brain.hear(data):
                    writer.write(answer)
        except OSError:
            pass
        finally:
            self.closed += 1
            writer.close()

    async def aclose(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()


class FakeEar(Ear):
    """A port that is not one: opening it opens nothing. Which TNC answers is chosen by the path and the speed it is opened at (`brains`); a path in `refused` cannot be opened."""

    opened: list[tuple[str, int]] = []                # every open, in order (`ears` gives each class its own)
    closed: list[tuple[str, int]] = []
    brains: dict[tuple[str, int], TncBrain] = {}
    refused: set[str] = set()

    def __init__(self, path: str, baud: int) -> None:
        super().__init__(path, baud)
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    async def open(self) -> None:
        if self.path in self.refused:
            raise SerialError(f"{self.path}: cannot be opened")
        self._open = True
        self.opened.append((self.path, self.baud))
        if brain := self.brains.get((self.path, self.baud)):
            self.heard.extend(brain.greeting())

    def close(self) -> None:
        if self._open:
            self._open = False
            self.closed.append((self.path, self.baud))

    def write(self, data: bytes) -> int:
        if not self._open:
            raise SerialError(f"{self.path}: not open")
        if brain := self.brains.get((self.path, self.baud)):
            self.heard.extend(brain.hear(data))
        return len(data)


def ears(brains: dict[tuple[str, int], TncBrain] | None = None, refused: set[str] | None = None) -> type[FakeEar]:
    """A FakeEar class of its own, with its own record of the opens: what the finder is given as `line`."""
    return type("Ear", (FakeEar,), {"opened": [], "closed": [], "brains": brains or {}, "refused": refused or set()})
