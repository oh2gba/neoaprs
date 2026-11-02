"""A Mercury HF modem that is not one, for the tests: its broadcast port (KISS over TCP) and its control port behind two TCP servers of the loopback, on one shared "air" with the other stations of the test, behaving as
Mercury 1.9.21 does on the air (what the bench of two real Mercury instances over named pipes showed, 2 November 2026):

- a KISS frame handed in is **cut to the mode's payload** (123 bytes for DATAC3) without a word to the client, and goes out as one modem frame;
- a frame **takes the mode's time on the air** (`frame_sec`, 3.9 s for DATAC3; the tests scale it down), and the station says `PTT ON` and `PTT OFF` on its control port round it;
- **there is no carrier sense**: a station keys whenever it is asked, and two frames whose times on the air overlap are both lost (a station that transmits hears nothing either);
- every other station on the air hears a frame that went whole, with the sender's command byte, when its time on the air is over;
- with `busy_detect` the other stations say `BUSY ON` while a frame is on the air and `BUSY OFF` after it (Mercury's detector, switched on in the configuration the daemon writes).

    air = Air(frame_sec=0.2)
    a, b = air.station(), air.station()        # each a FakeMercury: `url` is its KISS port (socket://127.0.0.1:P), `control_port` is P + 200, as the daemon expects
    await air.start()                          # both listen
    ... the daemons connect to a.url and b.url, and to the control ports ...
    air.delivered                              # (sender, receiver, payload) of every frame that was heard
    air.collisions, air.truncated              # what was lost, and what was cut
    await air.aclose()

A `FakeMercury` is a `FakeRadio` (tests/support/fakeradio.py) with the air behind it, so an `Env` takes it as its radio. Run as a program (`python -m tests.support.fakemercury -b PORT -p PORT ...`) it stands in for the
`mercury` binary itself, for the tests of the daemon starting, watching and stopping the program: it takes Mercury's flags, listens on the two ports, echoes nothing, prints a Mercury-like line or two, lists made-up sound
cards for `-z`, and ends on SIGTERM; `--die-after SECONDS` in its command (or `FAKE_MERCURY_DIE_AFTER` in its environment) makes it die by itself, as a crashed Mercury would."""
import asyncio
import os
import signal
import socket
import sys
import time
from pathlib import Path
from collections.abc import Callable
from dataclasses import dataclass, field

from neoaprs import kiss
from neoaprs.mercury import CONTROL_OFFSET, FRAME_SEC, MAX_PAYLOAD
from tests.support.fakeradio import FakeRadio

VERSION_LINE = "Rhizomatica Mercury Version 1.9.21 (fake, tests/support/fakemercury.py)"
SOUND_CARDS = """Listing ALSA soundcards:
playback devices:
device: name: 'USB Audio CODEC'  id: 'plughw:1,0'  (system default)
device: name: 'HDA Intel PCH'  id: 'plughw:0,0'
capture devices:
device: name: 'USB Audio CODEC'  id: 'plughw:1,0'  (system default)
"""


@dataclass
class Transmission:
    station: "FakeMercury"
    payload: bytes
    start: float
    end: float
    lost: bool = False


@dataclass
class Air:
    """One frequency that the stations share."""
    frame_sec: float = FRAME_SEC
    busy_detect: bool = True
    max_payload: int = MAX_PAYLOAD
    stations: list["FakeMercury"] = field(default_factory=list)
    delivered: list[tuple["FakeMercury", "FakeMercury", bytes]] = field(default_factory=list)
    collisions: int = 0                                                      # the frames lost to an overlap (two that overlap are two)
    truncated: list[tuple[int, int]] = field(default_factory=list)          # (bytes given, bytes sent) of every frame that was cut
    _on_air: list[Transmission] = field(default_factory=list)
    _tasks: set[asyncio.Task[None]] = field(default_factory=set)

    def station(self) -> "FakeMercury":
        station = FakeMercury(self)
        self.stations.append(station)
        return station

    async def start(self) -> None:
        for station in self.stations:
            await station.start()

    async def aclose(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        for station in self.stations:
            await station.aclose()

    @property
    def transmitting(self) -> list["FakeMercury"]:
        return [t.station for t in self._on_air]

    def transmit(self, station: "FakeMercury", payload: bytes) -> None:
        """The station keys and sends this frame, cut to the payload; the air decides at the end who hears it."""
        if len(payload) > self.max_payload:
            self.truncated.append((len(payload), self.max_payload))
            payload = payload[:self.max_payload]
        now = asyncio.get_running_loop().time()
        sending = Transmission(station, payload, now, now + self.frame_sec)
        for other in self._on_air:                                        # (two on the air at once: both lost)
            other.lost = sending.lost = True
        self._on_air.append(sending)
        station.keyed = True
        station.say_control("PTT ON")
        for listener in self.stations:
            if listener is not station and self.busy_detect:
                listener.say_control("BUSY ON")
        task = asyncio.get_running_loop().create_task(self._finish(sending), name="fake-mercury-frame")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _finish(self, sending: Transmission) -> None:
        await asyncio.sleep(self.frame_sec)
        self._on_air.remove(sending)
        sending.station.keyed = False
        sending.station.say_control("PTT OFF")
        for other in self.stations:
            if other is not sending.station and self.busy_detect and not any(t.station is not other for t in self._on_air):
                other.say_control("BUSY OFF")
        if sending.lost:
            self.collisions += 1
            return
        for other in self.stations:
            if other is not sending.station and not other.keyed:
                self.delivered.append((sending.station, other, sending.payload))
                other.feed(kiss.encode(sending.payload))


class FakeMercury(FakeRadio):
    """One Mercury station: its KISS port is the fake radio's, its control port 200 above it (Mercury's default distance, which the daemon expects of a Mercury it did not start)."""

    def __init__(self, air: Air) -> None:
        super().__init__()
        while not _free(self.port + CONTROL_OFFSET):                     # (the control port must be free too: another radio of the tests may have the KISS port's neighbour)
            assert self._sock is not None
            self._sock.close()
            self._sock = self._listening(0)
            self.port = self._sock.getsockname()[1]
            self.url = f"socket://127.0.0.1:{self.port}"
        self.air = air
        self.control_port = self.port + CONTROL_OFFSET
        self.keyed = False
        self.frames_in: list[bytes] = []                                  # every payload a client handed in, as it came (before the cut)
        self.control_said: list[str] = []                                  # every line said on the control port
        self._decoder = kiss.KissDecoder()
        self._control_server: asyncio.Server | None = None
        self._control_clients: list[asyncio.StreamWriter] = []
        self.control_connections = 0
        self.alive_sec: float | None = None                                # how often IAMALIVE is said; None: never

    async def start(self) -> None:
        await super().start()
        if self._control_server is None:
            self._control_server = await asyncio.start_server(self._control, "127.0.0.1", self.control_port)

    async def aclose(self) -> None:
        for writer in list(self._control_clients):
            writer.close()
        self._control_clients.clear()
        if self._control_server is not None:
            self._control_server.close()
            await self._control_server.wait_closed()
            self._control_server = None
        await super().aclose()

    def heard_bytes(self, data: bytes) -> None:
        """What a client wrote to the KISS port: kept as the fake radio keeps it, and every whole frame goes on the air."""
        super().heard_bytes(data)
        for frame in self._decoder.feed(data):
            if frame.command == 0:
                self.frames_in.append(frame.payload)
                self.air.transmit(self, frame.payload)

    async def _control(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.control_connections += 1
        self._control_clients.append(writer)
        try:
            while True:
                if self.alive_sec is not None:
                    try:
                        data = await asyncio.wait_for(reader.read(1024), self.alive_sec)
                    except TimeoutError:
                        writer.write(b"IAMALIVE\r")
                        continue
                else:
                    data = await reader.read(1024)
                if not data:
                    break
        except (OSError, asyncio.CancelledError):
            pass
        finally:
            if writer in self._control_clients:
                self._control_clients.remove(writer)
            writer.close()

    def say_control(self, line: str) -> None:
        """A line on the control port, CR-terminated as Mercury writes it, to every client."""
        self.control_said.append(line)
        for writer in list(self._control_clients):
            try:
                writer.write(line.encode("ascii") + b"\r")
            except OSError:
                pass

    def drop_control(self) -> None:
        """Closes the control connections: the daemon's control line is lost and opened again."""
        for writer in list(self._control_clients):
            writer.close()
        self._control_clients.clear()


def _free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


# ---- the program that stands in for the binary

ROOT = Path(__file__).resolve().parents[2]


def program(die_after_sec: float | None = None) -> list[str]:
    """The command that runs this module as the Mercury program, whatever the working directory (the daemon starts Mercury in the data folder): what the modem part's finder gives in a test. With `die_after_sec` it dies by itself."""
    command = [sys.executable, "-c", f"import sys, runpy; sys.path.insert(0, {str(ROOT)!r}); runpy.run_module('tests.support.fakemercury', run_name='__main__')"]
    return command if die_after_sec is None else [*command, "--die-after", str(die_after_sec)]


def _arguments(argv: list[str]) -> dict[str, str]:
    """Mercury's flags as a dict: `-b 8100 -p 8300 -z` is {"-b": "8100", "-p": "8300", "-z": ""}."""
    out: dict[str, str] = {}
    i = 0
    while i < len(argv):
        flag = argv[i]
        value = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("-") else ""
        out[flag] = value
        i += 2 if value else 1
    return out


async def _serve(broadcast_port: int, control_port: int, die_after: float | None) -> int:
    """Listens on both ports as Mercury would (nothing is echoed: there is no other station) until SIGTERM, or dies after `die_after` seconds."""
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for name in ("SIGTERM", "SIGINT"):
        if hasattr(signal, name) and sys.platform != "win32":
            loop.add_signal_handler(getattr(signal, name), stop.set)

    async def swallow(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while await reader.read(4096):
            pass
        writer.close()

    async def control(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.write(b"IAMALIVE\r")
        await swallow(reader, writer)

    kiss_server = await asyncio.start_server(swallow, "127.0.0.1", broadcast_port)
    control_server = await asyncio.start_server(control, "127.0.0.1", control_port)
    print(f"[INF] [engine] Initialising TCP interfaces (arq={control_port}, bc={broadcast_port})", flush=True)
    print("[INF] [engine] Mercury engine initialised", flush=True)
    try:
        await asyncio.wait_for(stop.wait(), die_after)
    except TimeoutError:
        print("[ERR] [engine] the fake Mercury dies as told", flush=True)
        return 3
    finally:
        kiss_server.close()
        control_server.close()
    print("Signal received, shutting down...", flush=True)
    return 0


def main(argv: list[str] | None = None, out: Callable[[str], None] = print) -> int:
    args = _arguments(sys.argv[1:] if argv is None else argv)
    if "-V" in args:
        out(VERSION_LINE)
        return 0
    if "-z" in args:
        out(SOUND_CARDS.rstrip("\n"))
        return 0
    die_after = float(args["--die-after"]) if args.get("--die-after") else float(os.environ["FAKE_MERCURY_DIE_AFTER"]) if os.environ.get("FAKE_MERCURY_DIE_AFTER") else None
    if sys.platform == "win32":                                          # (no signal handlers on the Windows selector loop: SIGTERM ends the process as terminate() does)
        die_after = die_after if die_after is not None else 3600.0
    started = time.monotonic()
    code = asyncio.run(_serve(int(args.get("-b", "8100")), int(args.get("-p", "8300")), die_after))
    out(f"ran {time.monotonic() - started:.1f} s")
    return code


if __name__ == "__main__":
    sys.exit(main())
