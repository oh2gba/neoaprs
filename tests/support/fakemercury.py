"""A Mercury HF modem stand-in: a broadcast port (KISS over TCP) and a control port on the loopback,
on one shared "air" with the other stations of the test, behaving as Mercury does on the air.
"""

import asyncio
import configparser
import os
import signal
import socket
import sys
import threading
import time
from pathlib import Path
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from neoaprs import kiss
from neoaprs.claims import Claims
from neoaprs.mercuryclaims import radio_folder
from neoaprs.radiotype import HF_ID, RadioId
from neoaprs.mercury import (
    CONTROL_OFFSET,
    FRAME_SEC,
    KEYING_OPEN_WINDOWS,
    MAX_PAYLOAD,
    RADIO_INIT_FAILED,
    SOURCE_COMMIT,
    VERSION,
)
from tests.support.fakemercuryui import FakeUi
from tests.support.fakeradio import FakeRadio
from tests.support import children

VERSION_LINE = f"Rhizomatica Mercury Version {VERSION} (fake, tests/support/fakemercury.py)"
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
    # The frames lost to an overlap (two that overlap are two)
    collisions: int = 0
    # (bytes given, bytes sent) of every frame that was cut
    truncated: list[tuple[int, int]] = field(default_factory=list)
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
        """The station keys and sends this frame, cut to the payload; the air decides at the end who
        hears it."""
        if len(payload) > self.max_payload:
            self.truncated.append((len(payload), self.max_payload))
            payload = payload[: self.max_payload]
        now = asyncio.get_running_loop().time()
        sending = Transmission(station, payload, now, now + self.frame_sec)
        for other in self._on_air:  # (two on the air at once: both lost)
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
            if (
                other is not sending.station
                and self.busy_detect
                and not any(t.station is not other for t in self._on_air)
            ):
                other.say_control("BUSY OFF")
        if sending.lost:
            self.collisions += 1
            return
        for other in self.stations:
            if other is not sending.station and not other.keyed:
                self.delivered.append((sending.station, other, sending.payload))
                other.feed(kiss.encode(sending.payload))


class FakeMercury(FakeRadio):
    """One Mercury station: its KISS port is the fake radio's, its control port 200 above it
    (Mercury's default distance, which the daemon expects of a Mercury it did not start)."""

    def __init__(self, air: Air) -> None:
        super().__init__()
        # The control port, held from here to the server that serves it: no other radio of the tests
        # can take it between
        self._control_sock: socket.socket | None = None
        while self._control_sock is None:
            assert self._sock is not None
            try:
                self._control_sock = self._listening(self.port + CONTROL_OFFSET)
            # Another radio of the tests has the KISS port's neighbour, or it is past the last port:
            # a KISS port again
            except (OSError, OverflowError):
                self._sock.close()
                self._sock = self._listening(0)
                self.port = self._sock.getsockname()[1]
                self.url = f"socket://127.0.0.1:{self.port}"
        self.air = air
        self.control_port = self.port + CONTROL_OFFSET
        self.keyed = False
        # Every payload a client handed in, as it came (before the cut)
        self.frames_in: list[bytes] = []
        self.control_said: list[str] = []  # every line said on the control port
        self._decoder = kiss.KissDecoder()
        self._control_server: asyncio.Server | None = None
        self._control_clients: list[asyncio.StreamWriter] = []
        self.control_connections = 0
        self.alive_sec: float | None = None  # how often IAMALIVE is said; None: never
        # The TUNE commands a client wrote, as they came
        self.tuned: list[str] = []

    async def start(self) -> None:
        await super().start()
        if self._control_server is None:
            if self._control_sock is None:
                self._control_sock = self._listening(self.control_port)
            self._control_server = await asyncio.start_server(self._control, sock=self._control_sock)
            self._control_sock = None  # (the server has it now)

    async def aclose(self) -> None:
        for writer in list(self._control_clients):
            writer.close()
        self._control_clients.clear()
        if self._control_server is not None:
            self._control_server.close()
            await self._control_server.wait_closed()
            self._control_server = None
        if self._control_sock is not None:  # made but never served
            self._control_sock.close()
            self._control_sock = None
        await super().aclose()

    def heard_bytes(self, data: bytes) -> None:
        """What a client wrote to the KISS port: kept as the fake radio keeps it, and every whole
        frame goes on the air."""
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
                for line in data.decode("ascii", "replace").split("\r"):
                    if line.startswith("TUNE"):
                        self.tuned.append(line)
                        writer.write(tune_answer(line))
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


def tune_answer(line: str) -> bytes:
    """What Mercury writes back for a TUNE line: OK and the PTT it switched, or WRONG for a line it
    does not take."""
    words = line.split()
    if len(words) != 2:
        return b"WRONG\r"
    if words[1].upper() == "OFF":
        return b"OK\rPTT OFF\r"
    try:
        level = float(words[1])
    except ValueError:
        return b"WRONG\r"
    return b"OK\rPTT ON\r" if -60.0 <= level <= 0.0 else b"WRONG\r"


# ---- the program that stands in for the binary

ROOT = Path(__file__).resolve().parents[2]
# What the program's KISS port was given, in its working directory
BROADCAST_FILE = "fake-mercury-broadcast.bin"
# What its UI interface hears, as tests/support/fakemercuryui.py reads it, in the working directory
UI_SCENE_FILE = "fake-mercury-ui-scene.json"
# The commands its UI interface was given, one a line (`set_tx_gain 3`), when its ini turns the
# interface on; `--no-ui` is a Mercury that has none
UI_LOG_FILE = "fake-mercury-ui.log"
INI_FILE_FLAG = "-C"


# What Mercury prints, after the stamp, when it cannot open the sound card (it runs on all the
# same).
AUDIO_ERROR_LINE = "[ERR] [audio-play] error in audio->open(): 1: snd_pcm_hw_params_set_access: (-22) Invalid argument"
# What Mercury 1.9.25 on Windows printed once the radio's USB sound card was gone while it ran
AUDIO_LOST_LINE = "[ERR] [audio-cap] the capture device delivers no audio: 2 reopens in a row brought nothing (unplugged, or its USB codec reset?) -- still trying it"


def stamp(seconds: float, ran_sec: float, utc: bool = False) -> str:
    """The time and run time Mercury writes before a log line: `2026-11-02 23:15:57.123 [+0.003s]`,
    `Z` after the time in UTC."""
    moment = time.gmtime(seconds) if utc else time.localtime(seconds)
    run_ms = int(ran_sec * 1000)
    return f"{time.strftime('%Y-%m-%d %H:%M:%S', moment)}.{int(seconds * 1000) % 1000:03d}{'Z' if utc else ''} [+{run_ms // 1000}.{run_ms % 1000:03d}s]"


STARTED = time.monotonic()


def say(line: str) -> None:
    """A log line of the program as Mercury prints it, the stamp first."""
    print(f"{stamp(time.time(), time.monotonic() - STARTED)} {line}", flush=True)


def of_radio(data_dir: Path, holder: RadioId = HF_ID, claims: Claims | None = None) -> dict[str, Any]:
    """The keywords of `Mercury` for the modem of radio `holder`, as its driver makes it: the
    station's table of resources (a table of its own unless one is given, which radios side by side
    share), the radio's id and its own folder in the data folder (mercuryclaims.radio_folder)."""
    return {
        "claims": Claims() if claims is None else claims,
        "holder": holder,
        "folder": radio_folder(data_dir, holder),
    }


LINGER_SEC = [0.0]


def program(
    die_after_sec: float | None = None,
    audio_error: bool = False,
    no_ui: bool = False,
    audio_lost: bool = False,
    keying_fails: str = "",
    linger_sec: float = 0.0,
) -> list[str]:
    """The command that runs this module as the Mercury program, whatever the working directory (the
    daemon starts Mercury in the data folder): what the modem part's finder gives in a test. With
    `die_after_sec` it dies by itself; with `audio_error` it prints, once its ports listen, the line
    Mercury prints when its sound card cannot be opened, and runs on as Mercury does. With
    `keying_fails` ("COM10 (Windows error 5)") it says it cannot open its keying port, listens on
    nothing and waits until it is ended, as an unpatched Mercury does."""
    command = [
        sys.executable,
        "-c",
        f"import sys, runpy; sys.path.insert(0, {str(ROOT)!r}); runpy.run_module('tests.support.fakemercury', run_name='__main__')",
    ]
    if die_after_sec is not None:
        command += ["--die-after", str(die_after_sec)]
    return [
        *command,
        *(["--audio-error"] if audio_error else []),
        *(["--audio-lost"] if audio_lost else []),
        *(["--no-ui"] if no_ui else []),
        *(["--keying-fails", keying_fails] if keying_fails else []),
        *(["--linger", str(linger_sec)] if linger_sec else []),
    ]


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


def _ui_of(ini: str, no_ui: bool = False) -> tuple[int, float]:
    """The UI port the ini turns on (0: none) and the transmit gain it holds, read as Mercury reads
    them (`[main] ui_enabled`, `ui_port`, `[audio] tx_gain_db`); none in a Mercury that has no
    interface."""
    if not ini or no_ui:
        return 0, 0.0
    parser = configparser.ConfigParser()
    parser.read(ini, encoding="utf-8")
    on = parser.getboolean("main", "ui_enabled", fallback=False)
    return (parser.getint("main", "ui_port", fallback=10000) if on else 0), parser.getfloat(
        "audio", "tx_gain_db", fallback=0.0
    )


async def _serve(
    broadcast_port: int,
    control_port: int,
    die_after: float | None,
    audio_error: bool = False,
    ini: str = "",
    no_ui: bool = False,
    audio_lost: bool = False,
) -> int:
    """Listens on both ports as Mercury would (nothing is echoed: there is no other station) until
    SIGTERM, or dies after `die_after` seconds."""
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for name in ("SIGTERM", "SIGINT"):
        if hasattr(signal, name) and sys.platform != "win32":
            loop.add_signal_handler(getattr(signal, name), stop.set)

    async def swallow(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while await reader.read(4096):
            pass
        writer.close()

    async def keep(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        say("[INF] [tcp-bcast] Broadcast client connected")
        while data := await reader.read(4096):
            with open(BROADCAST_FILE, "ab") as f:
                f.write(data)
        writer.close()

    async def control(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.write(b"IAMALIVE\r")
        while data := await reader.read(4096):
            for line in data.decode("ascii", "replace").split("\r"):
                if line.startswith("TUNE"):
                    say(f"[INF] [tcp-ctl] Command received: {line}")
                    writer.write(tune_answer(line))
        writer.close()

    ui_port, gain = _ui_of(ini, no_ui)
    ui = (
        FakeUi(
            port=ui_port, gain_db=gain, log_path=UI_LOG_FILE, scene_path=UI_SCENE_FILE, noise_db=-60.0, tone_hz=1500.0
        )
        if ui_port
        else None
    )
    if ui is not None:
        await ui.start()
        say(f"[INF] [websocket] Initialized (url=ws://127.0.0.1:{ui_port})")
    kiss_server = await asyncio.start_server(keep, "127.0.0.1", broadcast_port)
    control_server = await asyncio.start_server(control, "127.0.0.1", control_port)
    say(f"[INF] [main] Mercury {VERSION} (git {SOURCE_COMMIT[:8]})")
    say(f"[INF] [engine] Initialising TCP interfaces (arq={control_port}, bc={broadcast_port})")
    say("[INF] [engine] Mercury engine initialised")
    if audio_error:
        # The control port is up and the daemon has connected: the error comes while the modem says
        # "running", as it did on the station
        await asyncio.sleep(0.3)
        say(AUDIO_ERROR_LINE)
    if audio_lost:
        await asyncio.sleep(0.3)
        say(AUDIO_LOST_LINE)
    try:
        await asyncio.wait_for(stop.wait(), die_after)
    except TimeoutError:
        say("[ERR] [engine] the fake Mercury dies as told")
        sys.stdout.flush()
        # As a program that dies: at once, and with nothing after its last line. The loop's own end
        # can print a traceback on Windows, which would then be its last lines
        os._exit(3)
    finally:
        # --linger SEC: as a program slow to end, its ports listen a while after the TERM
        await asyncio.sleep(LINGER_SEC[0])
        kiss_server.close()
        control_server.close()
        if ui is not None:
            await ui.aclose()
    print("Signal received, shutting down...", flush=True)
    return 0


def hang_after_keying(what: str) -> int:
    """What Mercury does when its keying port cannot be opened (mercury_engine.c): it says so and its
    audio threads run on, the ports never listened on, until it is asked to end."""
    print("mercury_engine: radio init failed", flush=True)
    say(
        KEYING_OPEN_WINDOWS.format(port=what.split(" ", 1)[0], error=what.rsplit(" ", 1)[1].rstrip(")"))
        if "Windows error" in what
        else f"[ERR] [serial-ptt] Cannot open {what}"
    )
    say(RADIO_INIT_FAILED)
    stop = threading.Event()
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
    stop.wait()
    print("Mercury engine init failed.", flush=True)
    return 1


def main(argv: list[str] | None = None, out: Callable[[str], None] = print) -> int:
    args = _arguments(sys.argv[1:] if argv is None else argv)
    if "-V" in args:
        out(VERSION_LINE)
        return 0
    if "-z" in args:
        out(SOUND_CARDS.rstrip("\n"))
        return 0
    if args.get("--keying-fails"):
        return hang_after_keying(args["--keying-fails"])
    LINGER_SEC[0] = float(args.get("--linger") or 0)
    die_after = (
        float(args["--die-after"])
        if args.get("--die-after")
        else float(os.environ["FAKE_MERCURY_DIE_AFTER"])
        if os.environ.get("FAKE_MERCURY_DIE_AFTER")
        else None
    )
    # (no signal handlers on the Windows selector loop: SIGTERM ends the process as terminate()
    # does)
    if sys.platform == "win32":
        die_after = die_after if die_after is not None else 3600.0
    started = time.monotonic()
    code = asyncio.run(
        _serve(
            int(args.get("-b", "8100")),
            int(args.get("-p", "8300")),
            die_after,
            "--audio-error" in args,
            args.get(INI_FILE_FLAG, ""),
            "--no-ui" in args,
            "--audio-lost" in args,
        )
    )
    out(f"ran {time.monotonic() - started:.1f} s")
    return code


if __name__ == "__main__":
    children.end_with_the_run()
    sys.exit(main())
