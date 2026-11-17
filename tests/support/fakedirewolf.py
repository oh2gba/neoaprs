"""A Direwolf that is not one, for the tests: run as a program (`program(...)` is its command) it stands in for the `direwolf` binary for the tests of the daemon starting, watching and stopping it, and behaves as the
Direwolf NeoAPRS builds does by its source (aprs-reference/direwolf-plan.md, section 3):

- it reads the configuration named by `-c` (ADEVICE, PTT, the last KISSPORT that is not 0) and prints its banner;
- with an ADEVICE of two numbers (Windows) it prints its two lists of WinMM devices with `*` on the one chosen (`WINMM_INPUTS`, `WINMM_OUTPUTS`);
- it listens on its KISS port on 127.0.0.1, says "Ready to accept KISS TCP client application 0 on port N ...", and gives back every frame it is sent as a frame heard: with `-d n` it says the frame came
  ("<<< Data frame from KISS client application ..." and its bytes), then `PTT 0 = 1` and `PTT 0 = 0` round the send, then `DCD 0 = 1`, the heard line with its level, `DCD 0 = 0` and the frame on the KISS port;
- with `-x` it is a calibration run: `PTT 0 = 1` at once and nothing on any port;
- it ends cleanly at the end of its standard input (`-Q`): `PTT 0 = 0` if it was keyed, "QRT", exit 0; and on SIGINT the same.

Every run writes its command line, one line each, to `fake-direwolf-runs.txt` in its working directory (the radio's folder), so that a test can see how it was started. Its modes, as flags after the command:
`--fail-card` (the sound card cannot be opened: the lines and exit 1), `--wrong-star` (Windows: the list stars another input), `--fail-keying` (the keying device cannot be opened: exit 1),
`--cm108-unknown` (`PTT CM108` finds no chip on the card: it says so and runs on unkeyed), `--hidraw-denied` (the chip's HID cannot be opened at each key: it says so after `PTT 0 = 1`), `--busy-sec SECONDS`
(each frame waits that long for a clear channel before it is sent), `--several-cm108`,
`--port-taken` (the KISS port is taken: it says so and runs on with no KISS), `--die-after SECONDS`, `--ignore-stdin` (the end of its input does nothing), `--ignore-sigint`, `--listen-any` (it binds every
interface), `--level N` (the level of the frames it hears, 48 by default). With `-R MS` it says "RXLEVEL 0 = N" every MS milliseconds, N the `--idle-level` (0 without it), as our Direwolf does
(packaging/direwolf/rxlevel.patch)."""
import asyncio
import os
import signal
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS_FILE = "fake-direwolf-runs.txt"
BANNER = "Dire Wolf Release 1.8.1, November 2025 (fake, tests/support/fakedirewolf.py)"
WINMM_INPUTS = ("Microphone (Realtek(R) Audio)", "Microphone (USB Audio CODEC)")
WINMM_OUTPUTS = ("Speakers (Realtek(R) Audio)", "Speakers (USB Audio CODEC)")
HEARD_FROM = "OH2XYZ"
MAX_CLIENTS = 3                         # kissnet.c MAX_NET_CLIENTS
MODES = ("--fail-card", "--wrong-star", "--fail-keying", "--cm108-unknown", "--hidraw-denied", "--several-cm108", "--port-taken", "--ignore-stdin", "--ignore-sigint", "--listen-any")


def program(*modes: str, die_after_sec: float | None = None, level: int | None = None, busy_sec: float | None = None, idle_level: int | None = None) -> list[str]:
    """The command that runs this module as the Direwolf program, whatever the working directory, with its modes (MODES) after it."""
    assert all(mode in MODES for mode in modes), modes
    command = [sys.executable, "-c", f"import sys, runpy; sys.path.insert(0, {str(ROOT)!r}); runpy.run_module('tests.support.fakedirewolf', run_name='__main__')", *modes]
    if die_after_sec is not None:
        command += ["--die-after", str(die_after_sec)]
    if busy_sec is not None:
        command += ["--busy-sec", str(busy_sec)]
    if idle_level is not None:
        command += ["--idle-level", str(idle_level)]                # (its `-a` line, with this as the receive level between the packets; not said without it)
    return command + (["--level", str(level)] if level is not None else [])


def say(line: str) -> None:
    print(line, flush=True)


def runs(folder: Path) -> list[list[str]]:
    """The command lines of the runs in this folder, oldest first (each without the interpreter and the module that stand in for the program)."""
    path = folder / RUNS_FILE
    return [line.split("\t") for line in path.read_text(encoding="utf-8").splitlines()] if path.is_file() else []


def _option(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else ""


def _conf(path: str) -> dict[str, str]:
    """ADEVICE, PTT and the KISS port of the configuration (the last KISSPORT that is not 0)."""
    found: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        words = line.split(None, 1)
        if len(words) == 2 and words[0] in ("ADEVICE", "PTT"):
            found[words[0]] = words[1].strip()
        elif len(words) == 2 and words[0] == "KISSPORT" and words[1].strip() != "0":
            found["KISSPORT"] = words[1].strip()
    return found


def _lists(adevice: str, wrong: bool) -> None:
    numbers = adevice.split()
    if len(numbers) != 2 or not all(n.isdigit() for n in numbers):
        return
    chosen_in, chosen_out = int(numbers[0]), int(numbers[1])
    if wrong:
        chosen_in = (chosen_in + 1) % len(WINMM_INPUTS)
    say("Available audio input devices for receive (*=selected):")
    for n, name in enumerate(WINMM_INPUTS):
        say(f" {'*' if n == chosen_in else ' '}  {n}: {name}" + ("   (channel 0)" if n == chosen_in else ""))
    say("Available audio output devices for transmit (*=selected):")
    for n, name in enumerate(WINMM_OUTPUTS):
        say(f" {'*' if n == chosen_out else ' '}  {n}: {name}" + ("   (channel 0)" if n == chosen_out else ""))


class Fake:
    def __init__(self, argv: list[str]) -> None:
        self.argv = argv
        self.conf = _conf(_option(argv, "-c"))
        self.keyed = False
        self.clients: set[int] = set()          # the places of the KISS clients attached now
        self.level = int(_option(argv, "--level") or 48)
        self.done: asyncio.Event | None = None
        self.loop: asyncio.AbstractEventLoop | None = None

    def ptt(self, on: bool) -> None:
        if on != self.keyed:
            self.keyed = on
            say(f"PTT 0 = {int(on)}")
            if on and "--hidraw-denied" in self.argv:
                say("Could not open /dev/hidraw3 for write, errno=13")

    def quit(self) -> None:
        """Direwolf's cleanup: every output to 0, QRT, the end."""
        self.ptt(False)
        say("")
        say("QRT")
        if self.loop is not None and self.done is not None:
            self.loop.call_soon_threadsafe(self.done.set)

    def watch_stdin(self) -> None:
        sys.stdin.read()
        if "--ignore-stdin" not in self.argv:
            self.quit()

    async def kiss(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        port, slot = self.conf["KISSPORT"], min(set(range(MAX_CLIENTS + 1)) - self.clients)
        if slot == MAX_CLIENTS:                                          # (kissnet.c MAX_NET_CLIENTS: a fourth client is not taken)
            writer.close()
            return
        self.clients.add(slot)
        say(f"Attached to KISS TCP client application {slot} on port {port} ...")            # kissnet.c: said at every client, and then the next free place is offered
        if len(self.clients) < MAX_CLIENTS:
            say(f"Ready to accept KISS TCP client application {min(set(range(MAX_CLIENTS)) - self.clients)} on port {port} ...")
        try:
            await self.frames(reader, writer)
        finally:
            self.clients.discard(slot)
            say(f"KISS client application {slot} on TCP port {port} has gone away.")
            if len(self.clients) == MAX_CLIENTS - 1:                     # (every place was taken: the one that is free again is offered)
                say(f"Ready to accept KISS TCP client application {slot} on port {port} ...")

    async def statistics(self, every: float, level: int) -> None:
        """Direwolf's `-a`: the sample rate, the audio errors and the receive level as it is now, every so many seconds (audio_stats.c)."""
        while True:
            await asyncio.sleep(every)
            say(f"ADEVICE0: Sample rate approx. 44.1 k, 0 errors, receive audio level CH0 {level}")

    async def levels_now(self, every_ms: int, level: int) -> None:
        """Our Direwolf's `-R`: the receive level of channel 0 every so many milliseconds (packaging/direwolf/rxlevel.patch)."""
        while True:
            await asyncio.sleep(every_ms / 1000)
            say(f"RXLEVEL 0 = {level}")

    async def frames(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while data := await reader.read(4096):
            if "n" in _option(self.argv, "-d"):
                say("")
                say(f"<<< Data frame from KISS client application, channel 0, total length = {len(data)}")
                say("  000:  " + " ".join(f"{b:02x}" for b in data[:16]))
            await asyncio.sleep(float(_option(self.argv, "--busy-sec") or 0))
            self.ptt(True)
            await asyncio.sleep(0.05)
            self.ptt(False)
            say("DCD 0 = 1")
            say(f"{HEARD_FROM} audio level = {self.level}(12/9)   [NONE]   ___|||___")
            say("DCD 0 = 0")
            writer.write(data)
            await writer.drain()
        writer.close()

    async def run(self) -> int:
        self.loop, self.done = asyncio.get_running_loop(), asyncio.Event()
        if sys.platform != "win32":
            self.loop.add_signal_handler(signal.SIGINT, lambda: None if "--ignore-sigint" in self.argv else self.quit())
        threading.Thread(target=self.watch_stdin, daemon=True).start()
        say(BANNER)
        say("Includes optional support for:  cm108-ptt")
        _lists(self.conf.get("ADEVICE", ""), "--wrong-star" in self.argv)
        if "--fail-card" in self.argv:
            say(f"Could not open audio device {self.conf.get('ADEVICE', '')} for input")
            say("Pointless to continue without audio device.")
            return 1
        if "--cm108-unknown" in self.argv:
            say(f"Config file line 6: Could not determine USB Audio GPIO PTT device for audio output {self.conf.get('ADEVICE', '')}.")
            say("You must explicitly mention a device name such as /dev/hidraw1.")
        if "--several-cm108" in self.argv:
            say("There are multiple USB Audio Devices with GPIO capability.")
        if "--fail-keying" in self.argv:
            say(f"ERROR can't open device {self.conf.get('PTT', '').split(' ')[0]} for channel 0 PTT control.")
            return 1
        server = None
        if "-x" in self.argv:
            self.ptt(True)
            say("Sending calibration tones on channel 0.")
        elif "--port-taken" in self.argv:
            say("Bind failed with error: 98")
            say(f"Some other application is probably already using port {self.conf.get('KISSPORT', '')}.")
        else:
            server = await asyncio.start_server(self.kiss, "0.0.0.0" if "--listen-any" in self.argv else "127.0.0.1", int(self.conf["KISSPORT"]))
            say(f"Ready to accept KISS TCP client application 0 on port {self.conf['KISSPORT']} ...")
            if "--idle-level" in self.argv:
                stats = asyncio.ensure_future(self.statistics(float(_option(self.argv, "-a") or 60), int(_option(self.argv, "--idle-level"))))
                stats.add_done_callback(lambda _: None)
            if "-R" in self.argv:
                now = asyncio.ensure_future(self.levels_now(int(_option(self.argv, "-R")), int(_option(self.argv, "--idle-level") or 0)))
                now.add_done_callback(lambda _: None)
        die_after = float(_option(self.argv, "--die-after")) if "--die-after" in self.argv else None
        try:
            await asyncio.wait_for(self.done.wait(), die_after)
        except TimeoutError:
            say("the fake Direwolf dies as told")
            return 3
        finally:
            if server is not None:
                server.close()
        return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    with open(RUNS_FILE, "a", encoding="utf-8") as f:
        f.write("\t".join(args) + "\n")
    return asyncio.run(Fake(args).run())


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    sys.exit(main())
