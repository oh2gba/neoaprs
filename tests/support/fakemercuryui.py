"""The UI interface of a Mercury that is not one (tests/support/fakemercury.py, and the tests of the websocket client): a WebSocket server on the loopback that speaks as Mercury 1.9.21's does (`gui_interface/websocket`,
`ui_communication.c`): it upgrades a GET of /websocket, tells a `status` message twice a second (the transmit gain, the peak of the latest transmission, the audio's health), answers a text command with
`{"status":"ok"}` (an unknown one with `{"status":"error","code":-1}`), takes `set_waterfall` and `set_tx_gain`, and while the waterfall is on sends a binary spectrum frame (the magic, the number of bins, the sample rate and
the floats) every `spectrum_sec`. `commands` keeps every command it was given, as (command, value). The spectrum is white noise of a level the test sets (`noise_db`) with a tone of `tone_hz` at `tone_db` over it."""
import asyncio
import json
import math
import random
from pathlib import Path
import struct
from dataclasses import dataclass, field

from neoaprs.mercuryscope import spectrum_frame
from neoaprs.websocketclient import BINARY, CLOSE, PING, PONG, TEXT, accept_of, frame

BINS = 512
RATE = 8000


@dataclass
class FakeUi:
    port: int = 0
    status_sec: float = 0.5
    spectrum_sec: float = 0.05
    noise_db: float = -60.0
    tone_hz: float | None = None
    tone_db: float = -30.0
    gain_db: float = 0.0
    peak_dbfs: float = -120.0
    commands: list[tuple[str, str]] = field(default_factory=list)
    connections: int = 0
    waterfall: bool = False
    log_path: str = ""                         # a file each command is appended to (the program of the fake Mercury keeps it in its working directory)
    scene_path: str = ""                       # a JSON file read for every spectrum, so that a test can change the air of a program it started: {"blocks": [[1200, 1800, 12]]} lifts those frequencies by that many dB, {"noise_db": -50} moves the noise
    upgrade: bool = True                       # false: the server answers a GET with a plain 200, as a server that is no websocket does
    _server: asyncio.Server | None = None
    _clients: list[asyncio.StreamWriter] = field(default_factory=list)
    _tasks: list[asyncio.Task[None]] = field(default_factory=list)

    async def start(self, host: str = "127.0.0.1") -> None:
        self._server = await asyncio.start_server(self._client, host, self.port)
        self.port = self._server.sockets[0].getsockname()[1]
        self._tasks = [asyncio.get_running_loop().create_task(self._status()), asyncio.get_running_loop().create_task(self._spectrum())]

    async def aclose(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        for writer in list(self._clients):
            writer.close()
        self._clients.clear()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    def drop(self) -> None:
        """Closes every connection: the client's link is lost and opened again."""
        for writer in list(self._clients):
            writer.close()
        self._clients.clear()

    def status_text(self) -> str:
        return json.dumps({"type": "status", "bitrate": 0, "snr": 0.0, "tx_gain_db": self.gain_db, "tx_peak_dbfs": self.peak_dbfs, "waterfall": self.waterfall, "audio_ok": True, "audio_error": "", "busy": ""})

    def spectrum_db(self) -> list[float]:
        scene: dict[str, object] = {}
        if self.scene_path:
            try:
                scene = json.loads(Path(self.scene_path).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                scene = {}
        noise = scene.get("noise_db", self.noise_db)
        db = [float(noise) + random.gauss(0.0, 0.7) for _ in range(BINS)] if isinstance(noise, int | float) else [self.noise_db] * BINS
        if self.tone_hz is not None:
            db[round(self.tone_hz / (RATE / 2 / BINS))] = self.tone_db
        blocks = scene.get("blocks", [])
        for lo, hi, lift in blocks if isinstance(blocks, list) else []:
            for i in range(round(lo / (RATE / 2 / BINS)), round(hi / (RATE / 2 / BINS)) + 1):
                db[i] += lift
        return db

    def broadcast(self, payload: bytes, opcode: int) -> None:
        for writer in list(self._clients):
            try:
                writer.write(frame(opcode, payload))
            except OSError:
                pass

    async def _status(self) -> None:
        while True:
            await asyncio.sleep(self.status_sec)
            self.broadcast(self.status_text().encode(), TEXT)

    async def _spectrum(self) -> None:
        while True:
            await asyncio.sleep(self.spectrum_sec)
            if self.waterfall:
                self.broadcast(spectrum_frame(self.spectrum_db(), RATE), BINARY)

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = (await reader.readuntil(b"\r\n\r\n")).decode("latin-1")
            headers = {n.strip().lower(): v.strip() for n, _, v in (line.partition(":") for line in head.split("\r\n")[1:] if ":" in line)}
            if not self.upgrade or "sec-websocket-key" not in headers:
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
                await writer.drain()
                writer.close()
                return
            writer.write(f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: {accept_of(headers['sec-websocket-key'])}\r\n\r\n".encode())
            self.connections += 1
            self._clients.append(writer)
            writer.write(frame(TEXT, self.status_text().encode()))
            await self._read(reader, writer)
        except (OSError, asyncio.IncompleteReadError):
            pass
        finally:
            if writer in self._clients:
                self._clients.remove(writer)
            writer.close()

    async def _read(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while True:
            first, second = await reader.readexactly(2)
            size = second & 0x7F
            if size == 126:
                size = struct.unpack(">H", await reader.readexactly(2))[0]
            mask = await reader.readexactly(4)
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(await reader.readexactly(size)))
            opcode = first & 0x0F
            if opcode == CLOSE:
                writer.write(frame(CLOSE, data[:2]))
                return
            if opcode == PING:
                writer.write(frame(PONG, data))
            elif opcode == TEXT:
                writer.write(frame(TEXT, self._command(data.decode("utf-8")).encode()))

    def _command(self, text: str) -> str:
        try:
            message = json.loads(text)
            name, value = message["command"], message.get("value", "")
        except (ValueError, KeyError, TypeError):
            return '{"error":"malformed command JSON"}'
        self.commands.append((name, value))
        if self.log_path:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(f"{name} {value}\n")
        if name == "set_waterfall":
            self.waterfall = value != "off"
        elif name == "set_tx_gain":
            number = float(value) if value else 0.0
            self.gain_db = max(-20.0, min(20.0, number if math.isfinite(number) else 0.0))
            self.peak_dbfs = -6.4 + self.gain_db                       # (as if a frame had been sent at the new gain: Mercury's frames peak at -6.4 dBFS)
        else:
            return '{"status":"error","code":-1}'
        return '{"status":"ok"}'
