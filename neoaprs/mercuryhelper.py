"""The Mercury program as a child of the daemon: where it is, the ports it is given, how it is started and watched, how it is stopped, and the list of its sound cards.

Mercury is the one NeoAPRS ships (bundled.py says where): the folder `mercury/` of the shipped programs, with the program and what it needs beside it, and never one found on the PATH or fetched, so that the
operator's system is left alone and the Mercury that runs is the one the suite ran against. On Linux the folder carries its own ALSA library and configuration (the operator's machine need not have them), and
the program is told where the configuration is through the one variable ALSA reads, ALSA_CONFIG_PATH.
It is started, read into the log, told to the loop when it ends and stopped as every program the daemon holds for a radio is (childprogram.py, whose Program this module's is). Two
NeoAPRS on one computer, or a Mercury that something else runs, must not fight over the ports: `free_ports` finds the first pair (the broadcast port and the control port 200 above it) that is free, from the defaults
up (a port whose last connection is still in TIME_WAIT counts as free, as it does for Mercury, which binds with SO_REUSEADDR: the pair a Mercury that died held is free for the one started in its place, so the HF Tnc finds
the modem where it left it; the modems of radios side by side are handed their pairs by the station's table of claims, `next_modem_ports`). The program NeoAPRS ships listens on 127.0.0.1 only (packaging/mercury/loopback.patch, on every system), and `foreign_listeners` reads the kernel's table of sockets to
hold a started program to that: its ports have no password, so one that listened on every interface would let any host on the LAN key the radio. A Mercury of ours left behind by a crash of the daemon holds the sound card: its process id is written beside the configuration (and removed again by a clean stop, only while it still names
the stopped program), and mercurystale.py ends it at the next start."""
import asyncio
import logging
import os
import signal
import socket
import subprocess
import sys
from collections.abc import Callable, Collection, Sequence
from pathlib import Path

from . import childprogram
from .bundled import tools_dir
from .childprogram import HIDDEN_WINDOW as HIDDEN_WINDOW, LAST_LINES as LAST_LINES, LOOPBACK_HEX as LOOPBACK_HEX, PROC_TCP as PROC_TCP, SAID_MAX as SAID_MAX, STARTUP_LINES as STARTUP_LINES
from .childprogram import Command as Command, _listeners as _listeners, environment as environment, foreign_listeners as foreign_listeners
from .claims import Claims
from .radiotype import RadioId
from .mercury import BROADCAST_PORT, CONTROL_OFFSET, PAIR, PORT_TRIES, UI_OFFSET, WASAPI_CAPTURE, WASAPI_PLAYBACK, Keying, SerialPort, SoundCard, audio_open_error, card_reason, card_with, choose_keying, choose_sound_card, keying_of, parse_sound_cards, unstamped

log = logging.getLogger("neoaprs.mercury")
mercury_log = logging.getLogger("neoaprs.mercury.program")         # what Mercury itself prints, one line each

NAME = "mercury"
LIST_TIMEOUT_SEC = 15.0              # `mercury -z` opens the sound system; a stuck one is given this long
STOP_WAIT_SEC = 5.0                  # how long a terminated Mercury is given to end before it is asked again, and then killed


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


def pair_ports(broadcast_port: int) -> tuple[int, int, int, int]:
    """The ports a Mercury of this broadcast port listens on: the broadcast port, its control port, the ARQ data port one above that (Mercury's too) and the UI port."""
    return broadcast_port, broadcast_port + CONTROL_OFFSET, broadcast_port + CONTROL_OFFSET + 1, broadcast_port + UI_OFFSET


def pair_free(broadcast_port: int) -> bool:
    """Whether every port of the pair (`pair_ports`) is free."""
    return all(_free(port) for port in pair_ports(broadcast_port))


def free_ports(first: int = BROADCAST_PORT, tries: int = PORT_TRIES) -> tuple[int, int]:
    """The first broadcast port from `first` up whose control port (CONTROL_OFFSET above it) is free as well, as the pair. Mercury's defaults when they are free, so that a Mercury of ours is where the manuals say;
    the next pair when another program (another NeoAPRS, a Mercury of the operator's own) holds them. OSError when none of `tries` pairs is free."""
    for port in range(first, first + tries):
        if pair_free(port):
            return port, port + CONTROL_OFFSET
    raise OSError(f"no free pair of ports from {first} to {first + tries}")


def next_modem_ports(claims: Claims, holder: RadioId, free: Callable[[int], bool] = pair_free, first: int = BROADCAST_PORT, tries: int = PORT_TRIES) -> int:
    """The broadcast port of the pair the modem of radio `holder` is to start on: the first from `first` up that no other radio's modem holds in the station's table (claims.py: the kind `modem_ports`, the broadcast
    port as text), none of whose four ports is one of such a pair's (pairs one apart share a port: the ARQ data port of the one is the control port of the next), and that `free` finds free on this computer. The table
    hands the pairs out, so that two modems started side by side never take one pair between the probe and the bind; the probe still passes over what another program holds. OSError when none of `tries` is."""
    taken = {port for held in claims.held_by_others(holder, "modem_ports") for port in pair_ports(int(held))}
    for port in range(first, first + tries):
        if taken.isdisjoint(pair_ports(port)) and free(port):
            return port
    raise OSError(f"no free pair of ports from {first} to {first + tries} that no other radio's modem holds")


def choose_setup(program: Command, sound_card: str, keying: str, ports: Callable[[], list[SerialPort]], leave: Sequence[str] = (), held_cards: Collection[str] = (), key: Callable[[str], str | None] = str) -> tuple[str, Keying]:
    """The sound card and the keying the modem runs with: the settings (`mercury/sound_card`, `mercury/keying`) where they are set, else the daemon's own choice from the sound cards Mercury lists and the serial ports the
    system lists (`ports`; mercury.py says how and why), the ports in `leave` left out of the choice (the FM radio's, the GPS receiver's, the skipped ones: the one USB serial port the choice keys the radio on must not be
    one that another part of the station holds, or Mercury toggles its RTS at every frame), and the cards in `held_cards` (another radio's modem runs on them) out of the choice of a card. Runs the program and reads the system's lists: for a thread."""
    lone = PAIR not in sound_card and sound_card.startswith((WASAPI_CAPTURE, WASAPI_PLAYBACK))        # (one device of a Windows card: a setting made before the two were one choice)
    cards = list_sound_cards(program) if not sound_card or not keying or lone else []
    paired = card_with(cards, sound_card) if lone else ""
    card = paired or sound_card or choose_sound_card([c for c in cards if c.id not in held_cards])
    if paired:
        log.info("Mercury sound card: %r, both devices of the card whose one device the setting names (%s)", next((c.name for c in cards if c.id == paired), paired), sound_card)
    else:
        log.info("Mercury sound card: %s", card_reason(card, sound_card, cards))
    if keying:
        log.info("Mercury keys the radio by %s, from the settings", keying)
        return card, keying_of(keying)
    name = next((c.name for c in cards if c.id == card), "") if card else next((c.name for c in cards if c.default and c.capture), "")
    found = [p for p in ports() if key(p.device) not in leave]       # (`leave` as the station's table compares a port, and `key` makes a listed port's name that form: mercurymodem.left_out gives both;
                                                                      # the key is handed in so that this module needs no serial library: scripts/mercury-sim imports it)
    chosen = choose_keying(name, found)
    log.info("Mercury keys the radio by %s (chosen from the sound card %r and the serial ports %s)", chosen.text, name or "the system's default", ", ".join(p.device for p in found) or "none")
    return card, chosen


def alsa_card_names(root: Path | None = None) -> dict[int, str]:
    """The name ALSA knows each sound card by (/proc/asound/cardN/id), by its number; empty where there is no ALSA (Windows, macOS) or it cannot be read. NEOAPRS_ALSA_ROOT names another folder (the tests
    point it at none: no test reads the machine's cards)."""
    root = root or Path(os.environ.get("NEOAPRS_ALSA_ROOT") or "/proc/asound")
    names: dict[int, str] = {}
    try:
        for folder in root.glob("card[0-9]*"):
            if folder.name[4:].isdigit():
                name = (folder / "id").read_text(encoding="utf-8", errors="replace").strip()
                if name:
                    names[int(folder.name[4:])] = name
    except OSError:
        return names
    return names


def list_sound_cards(command: Command, timeout_sec: float = LIST_TIMEOUT_SEC) -> list[SoundCard]:
    """The sound cards Mercury lists (`-z`): run in the calling thread (not on the loop). None, with a line in the log, when the program cannot be run or says nothing a list is made of."""
    try:
        done = subprocess.run([*command, "-z"], capture_output=True, text=True, errors="replace", timeout=timeout_sec, env=environment(command), creationflags=HIDDEN_WINDOW, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("mercury -z could not be run: %s", e)
        return []
    cards = parse_sound_cards(done.stdout, alsa_card_names())
    if not cards:
        log.info("mercury -z listed no sound card (exit %d): %s", done.returncode, (done.stdout or done.stderr).strip()[-300:])
    return cards


# ---- the process

def _end_tree(process: subprocess.Popen[str]) -> None:
    """Windows: the process and every child of it ended (childprogram.end_tree)."""
    childprogram.end_tree(process, STOP_WAIT_SEC)


class Program(childprogram.Program):
    """One run of Mercury: started, read, and told when it ends (childprogram.Program); told, on the loop, the line that says the sound card could not be opened (the program runs on without it)."""
    name = "Mercury"

    def __init__(self, on_ended: Callable[[int | None, list[str]], None], on_audio_error: Callable[[str], None] | None = None) -> None:
        super().__init__(on_ended, log, mercury_log)
        self._on_audio_error = on_audio_error

    def _heard(self, line: str, loop: asyncio.AbstractEventLoop) -> None:
        if self._on_audio_error is not None and audio_open_error(line):
            loop.call_soon_threadsafe(self._on_audio_error, line)

    def _warning(self, line: str) -> str | None:
        """Mercury's warnings and errors say so ([WRN], [ERR]); each line carries the time it was written, so the same warning again is the same words after it."""
        return unstamped(line) if "[WRN]" in line or "[ERR]" in line else None

    def _end(self, process: subprocess.Popen[str]) -> None:
        """Asked to end, asked again after STOP_WAIT_SEC, killed after another STOP_WAIT_SEC. The second request is Mercury's own way to drop the transmitter at once (a kill leaves a radio keyed whose keying is a GPIO
        pin or a serial line). On Windows there is no request, only the hard end, and it ends the process with its children (`taskkill /T`); mercury.exe has no children and loses nothing."""
        if sys.platform == "win32":
            _end_tree(process)
        elif not self.ask(process, signal.SIGTERM, STOP_WAIT_SEC) and not self.ask(process, signal.SIGTERM, STOP_WAIT_SEC):
            self.kill(process)
