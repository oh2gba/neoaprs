"""The Mercury program as a child of the daemon: where it is, the ports it is given, how it is started and watched, how it is stopped, and the list of its sound cards.

Mercury is the one NeoAPRS ships (bundled.py says where): the folder `mercury/` of the shipped programs, with the program and what it needs beside it, and never one found on the PATH or fetched, so that the
operator's system is left alone and the Mercury that runs is the one the suite ran against. On Linux the folder carries its own ALSA library and configuration (the operator's machine need not have them), and
the program is told where the configuration is through the one variable ALSA reads, ALSA_CONFIG_PATH.
It is started with `subprocess.Popen` and read by a thread, as the serial line is: the daemon's loop may be the one Tornado forces on Windows, which cannot start subprocesses of its own, and what the program prints goes
to the daemon's log, never to the page. A thread waits for it to end and tells the loop with `call_soon_threadsafe`, with the exit code and its last lines, so that the owner (mercurymodem.py) can start it again. Two
NeoAPRS on one computer, or a Mercury that something else runs, must not fight over the ports: `free_ports` finds the first pair (the broadcast port and the control port 200 above it) that is free, from the defaults
up (a port whose last connection is still in TIME_WAIT counts as free, as it does for Mercury, which binds with SO_REUSEADDR: the pair a Mercury that died held is free for the one started in its place, so the HF Tnc finds
the modem where it left it). The program NeoAPRS ships listens on 127.0.0.1 only (packaging/mercury/loopback.patch, on every system), and `foreign_listeners` reads the kernel's table of sockets to
hold a started program to that: its ports have no password, so one that listened on every interface would let any host on the LAN key the radio. A Mercury of ours left behind by a crash of the daemon holds the sound card: its process id is written beside the configuration (and removed again by a clean stop), and the next start ends a process of that id
that is still a Mercury (on Windows, one whose program file is mercury.exe; where that cannot be read, nothing is ended)."""
import asyncio
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from .bundled import tools_dir
from .childenv import child_environment
from .mercury import BROADCAST_PORT, CONTROL_OFFSET, UI_OFFSET, Keying, SerialPort, SoundCard, audio_open_error, card_reason, choose_keying, choose_sound_card, keying_of, parse_sound_cards

log = logging.getLogger("neoaprs.mercury")
mercury_log = logging.getLogger("neoaprs.mercury.program")         # what Mercury itself prints, one line each

NAME = "mercury"
PORT_TRIES = 50                      # how many pairs of ports are tried from the defaults up
LIST_TIMEOUT_SEC = 15.0              # `mercury -z` opens the sound system; a stuck one is given this long
STOP_WAIT_SEC = 5.0                  # how long a terminated Mercury is given to end before it is killed
LAST_LINES = 8                       # how many of the program's last lines are kept for the problem text
STARTUP_LINES = 30                   # the first lines of each run of the program are in the log whatever they are (its version, its sound card, its keying); after them only warnings and errors are
SAID_MAX = 1000                      # distinct warnings of the program counted at once; the count starts over beyond that

Command = list[str]                  # how the program is run: its path, or an interpreter and a module that stands in for it (the tests' fake)
HIDDEN_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)         # Windows: the program gets no console window of its own; 0 elsewhere


def program_file(system: str | None = None) -> str:
    return f"{NAME}.exe" if (system or sys.platform).startswith("win") else NAME


def expected_program(tools: Path | None = None) -> Path:
    """Where the shipped Mercury is looked for: `mercury/mercury[.exe]` in the folder of the shipped programs (the log says it when there is none, so that a person can see where it ought to be)."""
    return (tools if tools is not None else tools_dir()) / NAME / program_file()


def find(tools: Path | None = None) -> Command | None:
    """The Mercury NeoAPRS ships: `mercury/mercury[.exe]` in the folder of the shipped programs (`tools`, by default this installation's); None when this installation has none (a wheel installed with pip or uv tool: the
    AppImage, the .deb and the Windows installer carry it)."""
    program = expected_program(tools)
    return [str(program)] if program.is_file() and os.access(program, os.X_OK) else None


def is_shipped(command: Command, tools: Path | None = None) -> bool:
    """Whether the command is the Mercury NeoAPRS ships, the one file `find` gives (the Windows installer's mercury.exe, the AppImage's, the .deb's, a checkout's build): the log says whether the program is the shipped one
    (not the tests' fake, an interpreter and a module; not a program named by its path elsewhere)."""
    shipped = (tools if tools is not None else tools_dir()) / NAME / program_file()
    return len(command) == 1 and Path(command[0]).resolve() == shipped.resolve()


def environment(command: Command) -> dict[str, str]:
    """The environment the program runs with: the daemon's reduced one (childenv.py), and ALSA_CONFIG_PATH pointing at the ALSA configuration shipped beside the program when there is one (Linux: the bundled ALSA library
    would otherwise look for the system's /usr/share/alsa/alsa.conf, which a machine without ALSA installed does not have, and open no sound card)."""
    env = child_environment()
    conf = Path(command[0]).resolve().parent / "share" / "alsa" / "alsa.conf"
    if len(command) == 1 and conf.is_file():
        env["ALSA_CONFIG_PATH"] = str(conf)
    return env


def _free(port: int) -> bool:
    """Whether nothing listens on the port of the loopback. The probe binds as Mercury does, with SO_REUSEADDR, so that a port whose last connection is in TIME_WAIT (the HF Tnc's line to a Mercury that just died) is free,
    as it is for Mercury (Linux lets a bind through a TIME_WAIT when both sockets have the option: Mercury's listener sets it and the connections it accepts inherit it); not on Windows, where that option would also take a
    port another program listens on."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if sys.platform != "win32":
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def pair_free(broadcast_port: int) -> bool:
    """Whether this broadcast port, its control port, the ARQ data port one above that (Mercury's too) and the UI port are all free."""
    return _free(broadcast_port) and _free(broadcast_port + CONTROL_OFFSET) and _free(broadcast_port + CONTROL_OFFSET + 1) and _free(broadcast_port + UI_OFFSET)


def free_ports(first: int = BROADCAST_PORT, tries: int = PORT_TRIES) -> tuple[int, int]:
    """The first broadcast port from `first` up whose control port (CONTROL_OFFSET above it) is free as well, as the pair. Mercury's defaults when they are free, so that a Mercury of ours is where the manuals say;
    the next pair when another program (another NeoAPRS, a Mercury of the operator's own) holds them. OSError when none of `tries` pairs is free."""
    for port in range(first, first + tries):
        if pair_free(port):
            return port, port + CONTROL_OFFSET
    raise OSError(f"no free pair of ports from {first} to {first + tries}")


class HeldPorts:
    """The pair of ports of one start of the program: chosen once (`choose`), and kept for a program started again in the place of one that died, so that the HF Tnc, which waits on its port with its back-off, finds
    the modem where it left it (the pair is free for the new program: the old connections are in TIME_WAIT, which the probe and Mercury's own bind allow); another pair only when something else took the old one
    meanwhile, which `choose` says by giving the pair that was taken, so that the owner can point the Tnc at the new one. `forget` is a fresh start."""

    def __init__(self) -> None:
        self.pair: tuple[int, int] = (BROADCAST_PORT, BROADCAST_PORT + CONTROL_OFFSET)
        self._held = False

    def forget(self) -> None:
        self._held = False

    def choose(self, free: Callable[[], tuple[int, int]] = free_ports) -> tuple[int, int] | None:
        """The pair to start the program on, kept in `pair`: the one held when it is still free, else a fresh one from `free` (OSError from it when none is); the pair that was taken, when one was, else None."""
        if self._held and pair_free(self.pair[0]):
            return None
        taken, self.pair, self._held = self.pair if self._held else None, free(), True
        return taken


def choose_setup(program: Command, sound_card: str, keying: str, ports: Callable[[], list[SerialPort]], leave: Sequence[str] = ()) -> tuple[str, Keying]:
    """The sound card and the keying the modem runs with: the settings (`mercury/sound_card`, `mercury/keying`) where they are set, else the daemon's own choice from the sound cards Mercury lists and the serial ports the
    system lists (`ports`; mercury.py says how and why), the ports in `leave` left out of the choice (the FM radio's, the GPS receiver's, the skipped ones: the one USB serial port the choice keys the radio on must not be
    one that another part of the station holds, or Mercury toggles its RTS at every frame). Runs the program and reads the system's lists: for a thread."""
    cards = list_sound_cards(program) if not sound_card or not keying else []
    card = sound_card or choose_sound_card(cards)
    log.info("Mercury sound card: %s", card_reason(card, sound_card, cards))
    if keying:
        log.info("Mercury keys the radio by %s, from the settings", keying)
        return card, keying_of(keying)
    name = next((c.name for c in cards if c.id == card), "") if card else next((c.name for c in cards if c.default and c.capture), "")
    found = [p for p in ports() if p.device not in leave]
    chosen = choose_keying(name, found)
    log.info("Mercury keys the radio by %s (chosen from the sound card %r and the serial ports %s)", chosen.text, name or "the system's default", ", ".join(p.device for p in found) or "none")
    return card, chosen


# ---- where the program listens

LOOPBACK_HEX = ("0100007F", "00000000000000000000000001000000")        # 127.0.0.1 and ::1 as /proc/net/tcp and tcp6 write a local address (the kernel's byte order, hex)
PROC_TCP = ("/proc/net/tcp", "/proc/net/tcp6")


def _listeners(tables: Sequence[str], ports: Iterable[int]) -> dict[int, set[str]]:
    """The local addresses, as the kernel writes them, of the sockets in LISTEN on these ports in the texts of /proc/net/tcp and tcp6."""
    wanted = set(ports)
    found: dict[int, set[str]] = {}
    for text in tables:
        for line in text.splitlines()[1:]:
            fields = line.split()
            if len(fields) < 4 or fields[3] != "0A":                                # (0A is LISTEN)
                continue
            address, _, port = fields[1].rpartition(":")
            if int(port, 16) in wanted:
                found.setdefault(int(port, 16), set()).add(address)
    return found


def foreign_listeners(ports: Iterable[int]) -> list[str]:
    """The listeners on these ports that are not on the loopback, as `address:port` in the kernel's hex, from the kernel's table of sockets (Linux: /proc/net/tcp and tcp6); empty where that table is not there
    (Windows, macOS: nothing can be said here; the shipped program binds the loopback in its source), and empty when every listener is 127.0.0.1 or ::1. Reads two small files: for a thread or a quick call."""
    tables: list[str] = []
    for name in PROC_TCP:
        try:
            tables.append(Path(name).read_text(encoding="ascii"))
        except OSError:
            continue
    return [f"{address}:{port}" for port, addresses in sorted(_listeners(tables, ports).items()) for address in sorted(addresses) if address not in LOOPBACK_HEX]


def list_sound_cards(command: Command, timeout_sec: float = LIST_TIMEOUT_SEC) -> list[SoundCard]:
    """The sound cards Mercury lists (`-z`): run in the calling thread (not on the loop). None, with a line in the log, when the program cannot be run or says nothing a list is made of."""
    try:
        done = subprocess.run([*command, "-z"], capture_output=True, text=True, timeout=timeout_sec, env=environment(command), creationflags=HIDDEN_WINDOW, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("mercury -z could not be run: %s", e)
        return []
    cards = parse_sound_cards(done.stdout)
    if not cards:
        log.info("mercury -z listed no sound card (exit %d): %s", done.returncode, (done.stdout or done.stderr).strip()[-300:])
    return cards


# ---- a Mercury left behind

def _is_mercury(pid: int) -> bool:
    """Whether the process of this id is a Mercury (Linux: "mercury" is in its command line, the program's or the module that stands in for it). On Windows it is when the process is running and its program file is
    mercury.exe (Windows reuses process ids, after a reboot most of all, so an id in an old file may belong to anything); os.kill(pid, 0) there is TerminateProcess, which would end whatever process has the id before
    anything is known of it, so the questions are asked of the process's exit code and image path. Where the image cannot be read, the answer is no."""
    cmdline = Path(f"/proc/{pid}/cmdline")
    if cmdline.exists():
        try:
            return NAME in cmdline.read_bytes().decode("utf-8", "replace").lower()
        except OSError:
            return False
    if sys.platform == "win32":
        return _running_windows(pid) and image_is_mercury(_windows_image(pid))
    else:                                                          # (a system with neither /proc nor Windows: nothing is known of the process, and nothing is ended)
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return False


def _running_windows(pid: int) -> bool:
    """Whether the Windows process of this id is still running (STILL_ACTIVE as its exit code); a process that ended but whose handle someone still holds is not."""
    import ctypes
    kernel32 = ctypes.windll.kernel32                              # type: ignore[attr-defined, unused-ignore]
    handle = kernel32.OpenProcess(0x1000, False, pid)              # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == 259                                   # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _windows_image(pid: int) -> str | None:
    """The full path of the program file of the Windows process of this id; None when the process cannot be opened or the path cannot be read."""
    import ctypes
    kernel32 = ctypes.windll.kernel32                              # type: ignore[attr-defined, unused-ignore]
    handle = kernel32.OpenProcess(0x1000, False, pid)              # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        size = ctypes.c_ulong(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        return buffer.value[:size.value]
    finally:
        kernel32.CloseHandle(handle)


def image_is_mercury(image: str | None) -> bool:
    """Whether the program file at this Windows path (either kind of slash) is mercury.exe, the name case aside; no when the path is not known: where that cannot be read, nothing is ended."""
    return image is not None and image.replace("\\", "/").rsplit("/", 1)[-1].lower() == "mercury.exe"


def end_stale(pid_file: Path) -> bool:
    """Ends a Mercury of ours that an earlier daemon left running (its id is in the file beside the configuration), so that it does not hold the sound card and the ports; whether one was ended."""
    try:
        text = pid_file.read_text(encoding="ascii")
    except OSError:
        return False
    pid_file.unlink(missing_ok=True)
    try:
        pid = int(text.strip())
    except ValueError:
        return False
    if pid == os.getpid() or pid <= 0 or not _is_mercury(pid):
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    log.warning("a Mercury left behind by an earlier run (process %d) was ended", pid)
    return True


# ---- the process

def _end_tree(process: subprocess.Popen[str]) -> None:
    """Windows: the process and every child of it ended (`taskkill /T /F`, the system's own tool: there is no tree in the Win32 API), then the process waited for; the process alone when taskkill is not there."""
    try:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=STOP_WAIT_SEC, check=False, creationflags=HIDDEN_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.debug("taskkill could not end the Mercury tree: %s", e)
    try:
        process.wait(STOP_WAIT_SEC)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


class Program:
    """One run of Mercury: started, read, and told when it ends."""

    def __init__(self, on_ended: Callable[[int | None, list[str]], None], on_audio_error: Callable[[str], None] | None = None) -> None:
        self._on_ended = on_ended
        self._on_audio_error = on_audio_error                    # told, on the loop, the line that says the sound card could not be opened (the program runs on without it)
        self._process: subprocess.Popen[str] | None = None
        self._pid_file: Path | None = None
        self.last_lines: deque[str] = deque(maxlen=LAST_LINES)
        self._said: dict[str, int] = {}                     # how many times each distinct warning of the program has come (a stuck sound device says the same line a thousand times a second)
        self.lines_read = 0                                 # how many lines this run has printed (the reader thread's alone)

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process is not None else None

    def start(self, argv: Command, cwd: Path, pid_file: Path | None = None) -> None:
        """Starts the program and the thread that reads it; OSError when it cannot be started (not there, not executable, the wrong architecture)."""
        loop = asyncio.get_running_loop()
        self._process = subprocess.Popen(argv, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                                         env=environment(argv), creationflags=HIDDEN_WINDOW)
        self._pid_file = pid_file
        self.lines_read = 0
        if pid_file is not None:
            try:
                pid_file.write_text(str(self._process.pid), encoding="ascii")
            except OSError as e:
                log.debug("the Mercury pid file could not be written: %s", e)
        log.info("Mercury started (process %d): %s", self._process.pid, " ".join(argv))
        threading.Thread(target=self._read, args=(self._process, loop), name="mercury-output", daemon=True).start()

    def _read(self, process: subprocess.Popen[str], loop: asyncio.AbstractEventLoop) -> None:
        """Reads the program's lines into the log until it ends, then tells the loop."""
        assert process.stdout is not None
        for raw in process.stdout:
            line = raw.rstrip()
            if line:
                self.last_lines.append(line)
                self._tell(line)
                if self._on_audio_error is not None and self._process is process and audio_open_error(line):
                    loop.call_soon_threadsafe(self._on_audio_error, line)
        code = process.wait()
        if self._process is process:
            loop.call_soon_threadsafe(self._on_ended, code, list(self.last_lines))

    def _tell(self, line: str) -> None:
        """One line of the program into the log: its warnings and errors at INFO the first, the tenth and every hundredth time the same line comes (a stuck sound device repeats one warning every millisecond, which
        would rotate the log in minutes and bury the day's lines; the count is said with the line); the first STARTUP_LINES lines of a run at INFO whatever they say (how it found its sound card and its keying is
        what a person helping from the log needs), everything else at DEBUG."""
        self.lines_read += 1
        if "[WRN]" not in line and "[ERR]" not in line:
            mercury_log.log(logging.INFO if self.lines_read <= STARTUP_LINES else logging.DEBUG, "%s", line)
            return
        if len(self._said) >= SAID_MAX:
            self._said.clear()
        count = self._said[line] = self._said.get(line, 0) + 1
        if count in (1, 10) or count % 100 == 0:
            mercury_log.info("%s%s", line, f" (the {count}th time)" if count > 1 else "")

    def stop(self) -> None:
        """Ends the program: asked to end, asked again after STOP_WAIT_SEC, killed after another STOP_WAIT_SEC. The second request is Mercury's own way to drop the transmitter at once (a kill leaves a radio keyed whose
        keying is a GPIO pin or a serial line). On Windows there is no request, only the hard end, and it ends the process with its children (`taskkill /T`): a program started through a launcher (a venv's python.exe,
        which the tests' fake runs under, starts the interpreter as its child) would otherwise leave the child, and its sockets, alive; mercury.exe has no children and loses nothing. The pid file is removed once the
        program has ended: a clean stop leaves nothing for the next start to look at. Waited for in the calling thread (a few milliseconds for a Mercury that ends as asked)."""
        process, self._process = self._process, None
        pid_file, self._pid_file = self._pid_file, None
        try:
            if process is None or process.poll() is not None:
                return
            if sys.platform == "win32":
                _end_tree(process)
            else:
                process.terminate()
                try:
                    process.wait(STOP_WAIT_SEC)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(STOP_WAIT_SEC)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            log.info("Mercury stopped (exit %s)", process.returncode)
        finally:
            if pid_file is not None and process is not None:
                pid_file.unlink(missing_ok=True)
