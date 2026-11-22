"""The Mercury program as a child of the daemon: location, ports, start, watch, stop, sound cards.

Only the shipped Mercury is used, never one from the PATH.
"""
import asyncio
import errno
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
from .mercury import BROADCAST_PORT, CONTROL_OFFSET, HOST, PAIR, PORT_TRIES, UI_OFFSET, WASAPI_CAPTURE, WASAPI_PLAYBACK, Keying, SerialPort, SoundCard, audio_open_error, card_reason, card_with, choose_keying, choose_sound_card, keying_of, parse_sound_cards, unstamped

log = logging.getLogger("neoaprs.mercury")
mercury_log = logging.getLogger("neoaprs.mercury.program")

NAME = "mercury"
LIST_TIMEOUT_SEC = 15.0
# Time a terminated Mercury is given to end before it is asked again, then killed.
STOP_WAIT_SEC = 5.0


def program_file(system: str | None = None) -> str:
    return childprogram.program_file(NAME, system)


def expected_program(tools: Path | None = None) -> Path:
    """Return the path of the shipped Mercury."""
    return (tools if tools is not None else tools_dir()) / NAME / program_file()


def find(tools: Path | None = None) -> Command | None:
    """Return the shipped Mercury, or None if this installation has none (such as a pip wheel)."""
    return childprogram.found(expected_program(tools))


def is_shipped(command: Command, tools: Path | None = None) -> bool:
    """Return True if the command is the file `find` gives."""
    return childprogram.runs_shipped(command, expected_program(tools))


def _free(port: int) -> bool:
    """Return True if nothing listens on the loopback port, in IPv4 or IPv6.

    The probe binds with SO_REUSEADDR as Mercury does, so a port in TIME_WAIT is free (not on Windows).
    """
    if childprogram.listened([port]):
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if sys.platform != "win32":
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((HOST, port))
        except OSError:
            return False
    return not socket.has_ipv6 or _free_v6(port)


def _free_v6(port: int) -> bool:
    """Return True if no IPv6 socket listens on the port, or the system has no IPv6."""
    try:
        probe = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    except OSError:
        return True
    with probe:
        probe.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        if sys.platform != "win32":
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("::", port))
        except OSError as e:
            return e.errno not in (errno.EADDRINUSE, errno.EACCES)
    return True


def pair_ports(broadcast_port: int) -> tuple[int, int, int, int]:
    """Return the broadcast, control, ARQ data and UI ports of a Mercury."""
    return broadcast_port, broadcast_port + CONTROL_OFFSET, broadcast_port + CONTROL_OFFSET + 1, broadcast_port + UI_OFFSET


def pair_free(broadcast_port: int) -> bool:
    return all(_free(port) for port in pair_ports(broadcast_port))


def free_ports(first: int = BROADCAST_PORT, tries: int = PORT_TRIES) -> tuple[int, int]:
    """Return the first free (broadcast, control) pair from `first` up; raise OSError if none."""
    for port in range(first, first + tries):
        if pair_free(port):
            return port, port + CONTROL_OFFSET
    raise OSError(f"no free pair of ports from {first} to {first + tries}")


def next_modem_ports(claims: Claims, holder: RadioId, free: Callable[[int], bool] = pair_free, first: int = BROADCAST_PORT, tries: int = PORT_TRIES) -> int:
    """Return the first broadcast port whose four ports overlap no other radio's pair and are free.

    Raise OSError if none of `tries` fits.
    """
    taken = {port for held in claims.held_by_others(holder, "modem_ports") for port in pair_ports(int(held))}
    for port in range(first, first + tries):
        if taken.isdisjoint(pair_ports(port)) and free(port):
            return port
    raise OSError(f"no free pair of ports from {first} to {first + tries} that no other radio's modem holds")


def choose_setup(program: Command, sound_card: str, keying: str, ports: Callable[[], list[SerialPort]], leave: Sequence[str] = (), held_cards: Collection[str] = (), key: Callable[[str], str | None] = str) -> tuple[str, Keying]:
    """Return the sound card and keying the modem runs with; the settings win.

    Ports in `leave` are excluded (Mercury would toggle their RTS). Blocks: call from a thread.
    """
    lone = PAIR not in sound_card and sound_card.startswith((WASAPI_CAPTURE, WASAPI_PLAYBACK))
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
    # `key` normalises a port name for `leave`; passed in so this module needs no serial library.
    found = [p for p in ports() if key(p.device) not in leave]
    chosen = choose_keying(name, found)
    log.info("Mercury keys the radio by %s (chosen from the sound card %r and the serial ports %s)", chosen.text, name or "the system's default", ", ".join(p.device for p in found) or "none")
    return card, chosen


def alsa_card_names(root: Path | None = None) -> dict[int, str]:
    """Return ALSA's name of each sound card by number; empty without ALSA."""
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
    """Return the sound cards `mercury -z` lists; empty if it cannot be run. Blocks."""
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
    childprogram.end_tree(process, STOP_WAIT_SEC)


class Program(childprogram.Program):
    """One run of Mercury; `on_audio_error` gets the line saying the sound card did not open."""
    name = "Mercury"

    def __init__(self, on_ended: Callable[[int | None, list[str]], None], on_audio_error: Callable[[str], None] | None = None) -> None:
        super().__init__(on_ended, log, mercury_log)
        self._on_audio_error = on_audio_error

    def _heard(self, line: str, loop: asyncio.AbstractEventLoop) -> None:
        if self._on_audio_error is not None and audio_open_error(line):
            loop.call_soon_threadsafe(self._on_audio_error, line)

    def _warning(self, line: str) -> str | None:
        """Return a [WRN] or [ERR] line without its timestamp, so that repeats compare equal."""
        return unstamped(line) if "[WRN]" in line or "[ERR]" in line else None

    def _end(self, process: subprocess.Popen[str]) -> None:
        """Ask to end, ask again after STOP_WAIT_SEC, kill after another.

        A kill could leave a radio keyed; Windows has only the hard end.
        """
        if sys.platform == "win32":
            _end_tree(process)
        elif not self.ask(process, signal.SIGTERM, STOP_WAIT_SEC) and not self.ask(process, signal.SIGTERM, STOP_WAIT_SEC):
            self.kill(process)
