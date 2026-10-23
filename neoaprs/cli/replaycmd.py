"""`neoaprs replay [FILE] [--interval S] [--loop] [--port P]`: plays a capture of the radio's serial port (one made by `neoaprs capture`; with no FILE the sample capture that is part of the package, three minutes
of a TH-D7 in Finland) as a KISS TNC on a TCP port of the loopback, so that the daemon can be run without the radio, on every system:

    neoaprs replay                                                    # prints socket://127.0.0.1:PORT as its first line
    neoaprs run --port socket://127.0.0.1:PORT                        # in another terminal (the kiss-tcp profile also takes it)

The file is read as a KISS stream; its frames are sent one at a time, INTERVAL seconds apart, re-encoded, to everyone who is connected. Nothing is sent while nobody is: the frames go on from where they
were when the daemon connects again. With --loop the file starts again when it ends. Ctrl-C ends it. What the daemon writes (a KISS frame, a nudge) is read and shown on stderr.
--pty (Linux and macOS) plays on a pseudo-terminal instead and prints its path."""
import argparse
import asyncio
from collections.abc import Callable
from pathlib import Path

from neoaprs import kiss

from .output import SETTLE_SEC, ctrl_break_is_ctrl_c, say

HOST = "127.0.0.1"
SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "thd7.kiss"          # package data: neoaprs/samples/thd7.kiss


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="neoaprs replay", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", nargs="?", default=None, metavar="FILE", help="a capture of KISS bytes (`neoaprs capture` makes one); the sample capture of the package when left out")
    p.add_argument("--interval", type=float, default=2.0, help="seconds between two frames (default 2.0)")
    p.add_argument("--loop", action="store_true", help="start again when the file ends")
    p.add_argument("--port", type=int, default=0, metavar="P", help="the TCP port to listen on, on 127.0.0.1 (default: a free one, which is printed)")
    p.add_argument("--pty", action="store_true", help="play on a pseudo-terminal and print its path (Linux and macOS only)")
    return p


def frames_of(data: bytes) -> list[bytes]:
    """Every KISS frame of the bytes, encoded again as it is sent."""
    return [kiss.encode(f.payload, f.port, f.command) for f in kiss.KissDecoder().feed(data)]


class Replay:
    """A KISS TNC on a TCP port of the loopback that plays `frames`. `await replay.run()` serves until it is cancelled; `ready(port)` is called once it listens."""

    def __init__(self, frames: list[bytes], interval: float, loop: bool = False, port: int = 0, settle_sec: float = SETTLE_SEC,
                 ready: Callable[[int], None] | None = None) -> None:
        self.frames, self.interval, self.loop, self.port, self.settle_sec = frames, interval, loop, port, settle_sec
        self.ready = ready
        self.sent = 0
        self.clients: list[asyncio.StreamWriter] = []
        self._arrived = asyncio.Event()

    async def run(self) -> None:
        server = await asyncio.start_server(self._serve, HOST, self.port)
        try:
            self.port = server.sockets[0].getsockname()[1]
            if self.ready is not None:
                self.ready(self.port)
            await self._play()
        finally:
            server.close()
            for client in list(self.clients):
                client.close()
            await server.wait_closed()

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """One connection: it is a client until it closes; what it writes is shown."""
        self.clients.append(writer)
        say("replay: a port connected")
        self._arrived.set()
        try:
            while data := await reader.read(4096):
                say(f"replay: the daemon wrote {len(data)} bytes: {data[:60]!r}")
        except OSError:
            pass
        finally:
            if writer in self.clients:
                self.clients.remove(writer)
            if not self.clients:
                self._arrived.clear()
            writer.close()

    async def _wait_for_a_client(self) -> None:
        if self.clients:
            return
        say("replay: waiting for a port to connect")
        await self._arrived.wait()
        await asyncio.sleep(self.settle_sec)

    async def _send(self, frame: bytes) -> None:
        await self._wait_for_a_client()
        self.sent += 1
        for client in list(self.clients):
            try:
                client.write(frame)
                await client.drain()
            except OSError as e:
                say(f"replay: frame {self.sent} not sent to a port: {e}")
        say(f"replay: frame {self.sent} sent ({len(frame)} bytes)")

    async def _play(self) -> None:
        while True:
            for frame in self.frames:
                await self._send(frame)
                await asyncio.sleep(self.interval)
            if not self.loop:
                break
        say("replay: the file is played; Ctrl-C ends it")
        await asyncio.Event().wait()


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    ctrl_break_is_ctrl_c()
    source = Path(args.file) if args.file else SAMPLE
    try:
        frames = frames_of(source.read_bytes())
    except OSError as e:
        say(f"replay: {e}")
        return 1
    if not frames:
        say(f"replay: {source} holds no KISS frame")
        return 1
    say(f"replay: {len(frames)} frames from {source}, one every {args.interval:g} s{', in a loop' if args.loop else ''}; Ctrl-C ends it")
    if args.pty:
        from .replaypty import play_on_pty
        return play_on_pty(frames, args.interval, args.loop)

    def announce(port: int) -> None:
        print(f"socket://{HOST}:{port}", flush=True)

    try:
        asyncio.run(Replay(frames, args.interval, args.loop, args.port, ready=announce).run())
    except KeyboardInterrupt:
        say("replay: stopped")
    except OSError as e:
        say(f"replay: cannot listen on {HOST}:{args.port}: {e}")
        return 1
    return 0
