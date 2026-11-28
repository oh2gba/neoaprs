"""One real Mercury driven over its two ports as the daemon drives it, for the tests of the program itself
(test_mercury_program.py on the Linux runner, test_windows.py on the Windows one): what it writes on its
control port, read with the daemon's parser, the frames it hands over on its broadcast port, and its
output."""

import asyncio
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from neoaprs import kiss
from neoaprs.mercury import ControlEvent, parse_control_line, split_control_lines

HOST = "127.0.0.1"
OPEN_SEC = 60.0  # the program up and its two ports open


class Modem:
    def __init__(self, name: str, argv: Sequence[str], folder: Path, env: dict[str, str], creationflags: int = 0):
        self.name = name
        self.folder = folder
        self.output = folder / f"{name}.out"
        with self.output.open("wb") as out:
            self.process = subprocess.Popen(
                list(argv),
                cwd=folder,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
        self.events: list[ControlEvent] = []
        self.frames: list[bytes] = []
        self._control: asyncio.StreamWriter | None = None
        self._broadcast: asyncio.StreamWriter | None = None
        self._tasks: list[asyncio.Task[None]] = []

    async def open(self, broadcast: int, control: int) -> None:
        deadline = time.monotonic() + OPEN_SEC
        for port, read in ((control, self._read_control), (broadcast, self._read_broadcast)):
            while True:
                if self.process.poll() is not None:
                    raise AssertionError(f"Mercury {self.name} ended with {self.process.returncode}:\n{self.said()}")
                try:
                    reader, writer = await asyncio.open_connection(HOST, port)
                    break
                except OSError as error:
                    if time.monotonic() > deadline:
                        raise AssertionError(
                            f"Mercury {self.name} did not open its port {port}:\n{self.said()}"
                        ) from error
                    await asyncio.sleep(0.2)
            if port == control:
                self._control = writer
            else:
                self._broadcast = writer
            self._tasks.append(asyncio.get_running_loop().create_task(read(reader)))

    async def _read_control(self, reader: asyncio.StreamReader) -> None:
        buffer = bytearray()
        while chunk := await reader.read(4096):
            buffer.extend(chunk)
            self.events.extend(parse_control_line(line) for line in split_control_lines(buffer))

    async def _read_broadcast(self, reader: asyncio.StreamReader) -> None:
        decoder = kiss.KissDecoder()
        while chunk := await reader.read(4096):
            self.frames.extend(f.payload for f in decoder.feed(chunk) if f.command == 0)

    def command(self, line: str) -> None:
        """A line on the control port, as the daemon writes it (CR-terminated)."""
        assert self._control is not None
        self._control.write(line.encode("ascii") + b"\r")

    def send(self, payload: bytes) -> None:
        assert self._broadcast is not None
        self._broadcast.write(kiss.encode(payload))

    def seen(self, kind: str, on: bool | None = None, after: int = 0) -> list[ControlEvent]:
        return [e for e in self.events[after:] if e.kind == kind and (on is None or e.on == on)]

    def said(self) -> str:
        return self.output.read_text(encoding="utf-8", errors="replace") if self.output.is_file() else ""

    async def until(self, what: str, condition: Callable[[], bool], seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while not condition():
            if time.monotonic() > deadline:
                lines = "\n".join(e.text for e in self.events[-20:])
                raise AssertionError(
                    f"Mercury {self.name}: no {what} within {seconds:g} s; its control port said:\n{lines}\n"
                    f"its output ended:\n" + "\n".join(self.said().splitlines()[-30:])
                )
            await asyncio.sleep(0.1)

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        for writer in (self._control, self._broadcast):
            if writer is not None:
                writer.close()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                await asyncio.to_thread(self.process.wait, 20)
            except subprocess.TimeoutExpired:
                self.process.kill()
                await asyncio.to_thread(self.process.wait)
