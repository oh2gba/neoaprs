"""`neoaprs capture OUT [--port PORT] [--seconds N]`: records what the radio sends on its serial port into a file, byte for byte, and prints one line per KISS frame to stderr so that you can see it
working. This is how the fixtures of the tests (tests/fixtures) are made from a real radio, and what to run first on a new setup to find which serial port the radio is on.

    neoaprs capture OUT                                  probe the USB serial ports (Linux), record 60 seconds
    neoaprs capture --port COM3 --seconds 300 OUT        a port you name: /dev/ttyUSB0, COM3, socket://127.0.0.1:8001

Without --port every port of the default serial/pattern (/dev/serial/by-id/*, /dev/ttyUSB*, /dev/ttyACM*) is listened to for up to 20 seconds and the first that delivers a complete KISS frame is used (a quiet
band may need --port; on Windows and macOS the port is always named). The daemon must not be running: the port is opened exclusively. OUT is not overwritten without --force. Stop early with Ctrl-C:
what came is kept."""
import argparse
import asyncio
from pathlib import Path
from typing import BinaryIO

from neoaprs.kiss import KissDecoder
from neoaprs.serialport import SerialError, SerialPort
from neoaprs.serialprobe import candidate_ports, can_search, probe

from .output import ctrl_break_is_ctrl_c, say

PROBE_SECONDS = 20.0
SHOWN_BYTES = 16


def parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="neoaprs capture", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", metavar="OUT", help="the file the raw bytes are written to")
    parser.add_argument("--port", help="the serial port (default: probe the USB serial ports)")
    parser.add_argument("--baud", type=int, default=9600, help="the baud rate (default 9600)")
    parser.add_argument("--seconds", type=float, default=60.0, help="how long to record (default 60)")
    parser.add_argument("--force", action="store_true", help="overwrite OUT if it exists")
    return parser.parse_args(argv)


async def find_port(baud: int) -> str | None:
    paths = candidate_ports() if can_search() else []
    if not paths:
        say("capture: no USB serial port to look at here; give the port with --port (COM3, /dev/ttyUSB0, socket://127.0.0.1:8001)")
        return None
    say(f"capture: listening for a KISS frame on {', '.join(paths)} ({PROBE_SECONDS:.0f} s each)")
    found = await probe(paths, baud, PROBE_SECONDS, lambda data: bool(KissDecoder().feed(data)))
    if found is None:
        say("capture: no port delivered a KISS frame; is the radio in KISS mode and hearing anything? try --port")
    return found


async def record(path: str, baud: int, seconds: float, out_path: str) -> int:
    decoder = KissDecoder()
    stopped = asyncio.Event()
    totals = {"bytes": 0, "frames": 0}
    exit_code = 0

    sink: list[BinaryIO] = []                         # the file, once the port has opened

    def on_data(chunk: bytes) -> None:
        sink[0].write(chunk)
        sink[0].flush()
        totals["bytes"] += len(chunk)
        for frame in decoder.feed(chunk):
            totals["frames"] += 1
            say(f"frame {totals['frames']}: port {frame.port} command {frame.command} {len(frame.payload)} bytes: {frame.payload[:SHOWN_BYTES].hex(' ')}")

    def on_dropped(reason: str) -> None:
        nonlocal exit_code
        say(f"capture: the port went away: {reason}")
        exit_code = 1
        stopped.set()

    port = SerialPort(path, baud)
    port.data.connect(on_data)
    port.dropped.connect(on_dropped)
    try:
        await port.open()
    except SerialError as e:
        say(f"capture: {e}")
        return 1
    with open(out_path, "wb") as handle:              # after the port opened, so that a failure leaves no empty file behind
        sink.append(handle)
        say(f"capture: reading {path} at {baud} baud for {seconds:g} s (Ctrl-C ends it early)")
        try:
            await asyncio.wait_for(stopped.wait(), seconds)
        except TimeoutError:
            pass
        finally:
            port.close()
    say(f"capture: {totals['bytes']} bytes, {totals['frames']} KISS frames, {decoder.dropped} dropped")
    return exit_code


async def run(args: argparse.Namespace) -> int:
    path = args.port or await find_port(args.baud)
    if path is None:
        return 1
    return await record(path, args.baud, args.seconds, args.out)


def main(argv: list[str]) -> int:
    args = parse(argv)
    ctrl_break_is_ctrl_c()
    if Path(args.out).exists() and not args.force:
        say(f"capture: {args.out} exists; use --force to overwrite it")
        return 2
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        say("capture: stopped; what came is in " + args.out)
        return 0

