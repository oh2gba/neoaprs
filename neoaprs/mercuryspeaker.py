"""The speaker of the Dummy HF radio: the Mercury the daemon starts to play our frames aloud (mercurymodem.py, `start(..., speaker=True)`), heard from the computer's own sound output.

Mercury runs on its `fifo` audio backend (raw s32le mono at 8000 samples a second over two named pipes, the backend the simulators use: tests/support/hfchannel.py), not on a sound card: a sound card is paced by its
clock, but a silent capture device of ALSA (`null`) is not, and Mercury read it a thousand times faster than real time, filled its decoder and wrote a warning every millisecond (tried 2 November 2026). So the
daemon is the sound card's clock: a thread (`SpeakerAudio`) writes a block of silence into Mercury's capture pipe every 20 ms, at the pace a sound card would, and reads what Mercury transmits from its playback
pipe, which it hands to the system's own player, `pw-play` (PipeWire), `paplay` (PulseAudio) or `aplay` (ALSA), whichever is there: those know the desktop's sound output, which the bundled ALSA library alone
does not. The frames to play come in on Mercury's broadcast port as KISS (`SpeakerLine`), as they would from the Tnc.

Nothing of it is a must: no player, no pipes (Windows has none), a Mercury that is not there, are each a line in the log, and the Dummy HF radio makes its traffic all the same."""
import asyncio
import contextlib
import logging
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

from .source import Backoff, os_error_text

log = logging.getLogger("neoaprs.mercury")

CONNECT_SEC = 3.0
RATE = 8000                                   # samples a second of Mercury's fifo backend
SAMPLE_BYTES = 4                              # s32le
BLOCK_MS = 20                                 # a sound card's block
BLOCK_BYTES = RATE * BLOCK_MS // 1000 * SAMPLE_BYTES
SILENCE = bytes(BLOCK_BYTES)
CAPTURE_FIFO = "mercury-capture.fifo"         # what Mercury hears (silence), in the data folder
PLAYBACK_FIFO = "mercury-playback.fifo"       # what Mercury transmits
PLAYERS: tuple[tuple[str, tuple[str, ...]], ...] = (                      # the system's players of raw s32le mono at 8 kHz from standard input, the first found wins
    ("pw-play", ("--raw", "--rate", str(RATE), "--channels", "1", "--format", "s32", "-")),
    ("paplay", ("--raw", f"--rate={RATE}", "--format=s32le", "--channels=1")),
    ("aplay", ("-q", "-t", "raw", "-f", "S32_LE", "-r", str(RATE), "-c", "1", "-")),
)
NONBLOCK: int = getattr(os, "O_NONBLOCK", 0)


def player_command() -> list[str] | None:
    """The system's player of raw audio from standard input, as a command; None when the machine has none of the three."""
    for name, args in PLAYERS:
        if (found := shutil.which(name)) is not None:
            return [found, *args]
    return None


class SpeakerAudio:
    """The sound card's clock for the Mercury on the fifo backend: silence into its capture pipe every 20 ms, what it plays out of its playback pipe into the system's player. A thread, as the air of the simulators is."""

    def __init__(self, folder: Path, player: Callable[[], list[str] | None] = player_command) -> None:
        self.capture = folder / CAPTURE_FIFO
        self.playback = folder / PLAYBACK_FIFO
        self._player_command = player
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._player: subprocess.Popen[bytes] | None = None
        self.blocks_written = 0                                 # of silence, into Mercury's capture
        self.bytes_played = 0                                   # of Mercury's audio, into the player
        self.player_said = False                                # the log line about the player (or none) was written

    @property
    def possible(self) -> bool:
        """Whether this system has named pipes (POSIX); without them Mercury runs on its default devices and nothing of this is started."""
        return hasattr(os, "mkfifo")

    def prepare(self) -> bool:
        """Makes the two pipes anew (a stale pair from an earlier run is removed); False, with a line in the log, when they cannot be made."""
        make = getattr(os, "mkfifo", None)              # (POSIX; the Windows type check knows no such name)
        if make is None:
            return False
        try:
            for path in (self.capture, self.playback):
                path.unlink(missing_ok=True)
                make(path)
        except OSError as e:
            log.info("the pipes of the Dummy HF radio's speaker could not be made: %s", os_error_text(e))
            return False
        return True

    def start(self) -> None:
        """The thread of the clock; one that runs from before (Mercury ended and came back without a stop) is ended first, so that two never write into the same pipe."""
        self._end_thread()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="mercury-speaker-audio", daemon=True)
        self._thread.start()

    def _end_thread(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(2.0)

    def stop(self) -> None:
        self._end_thread()
        self._end_player()
        self.player_said = False                                # (the next run starts its player again)
        for path in (self.capture, self.playback):
            with contextlib.suppress(OSError):
                path.unlink()

    # ---- the thread
    def _run(self) -> None:
        cap_fd: int | None = None
        play_fd: int | None = None
        next_at = time.monotonic()
        try:
            while not self._stop.is_set():
                cap_fd = self._write_silence(cap_fd)
                play_fd = self._read_audio(play_fd)
                next_at += BLOCK_MS / 1000
                time.sleep(max(0.0, next_at - time.monotonic()))
        finally:
            for fd in (cap_fd, play_fd):
                if fd is not None:
                    with contextlib.suppress(OSError):
                        os.close(fd)

    def _write_silence(self, fd: int | None) -> int | None:
        """One block of silence into Mercury's capture pipe; the pipe is opened once Mercury reads it (ENXIO until then) and closed again when Mercury goes."""
        if fd is None:
            try:
                fd = os.open(self.capture, os.O_WRONLY | NONBLOCK)
            except OSError:
                return None
        try:
            os.write(fd, SILENCE)
            self.blocks_written += 1
        except BlockingIOError:
            pass                                                # (Mercury is behind by a block: the next one is not owed)
        except OSError:
            with contextlib.suppress(OSError):
                os.close(fd)
            return None
        return fd

    def _read_audio(self, fd: int | None) -> int | None:
        """What Mercury wrote since the last block, into the player."""
        if fd is None:
            try:
                fd = os.open(self.playback, os.O_RDONLY | NONBLOCK)
            except OSError:
                return None
        try:
            data = os.read(fd, 1 << 16)
        except BlockingIOError:
            return fd
        except OSError:
            with contextlib.suppress(OSError):
                os.close(fd)
            return None
        if data:
            self._play(data)
        return fd

    def _play(self, data: bytes) -> None:
        if self._player is None and not self.player_said:
            command = self._player_command()
            self.player_said = True
            if command is None:
                log.info("no player for the Dummy HF radio's audio (pw-play, paplay or aplay): the frames are not heard")
                return
            try:
                self._player = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                log.info("the Dummy HF radio's audio goes to %s", command[0])
            except OSError as e:
                log.info("the player %s could not be started: %s", command[0], os_error_text(e))
                return
        if self._player is None or self._player.stdin is None:
            return
        try:
            self._player.stdin.write(data)
            self._player.stdin.flush()
            self.bytes_played += len(data)
        except (OSError, ValueError) as e:
            log.info("the player of the Dummy HF radio's audio ended: %s", os_error_text(e) if isinstance(e, OSError) else e)
            self._end_player()

    def _end_player(self) -> None:
        player, self._player = self._player, None
        if player is None:
            return
        with contextlib.suppress(OSError):
            if player.stdin is not None:
                player.stdin.close()
        try:
            player.wait(1.0)
        except subprocess.TimeoutExpired:
            player.kill()


class SpeakerLine:
    """The line to the broadcast port of that Mercury: a TCP connection kept open while the program runs, tried again after the back-off while it starts, and written the KISS bytes the dummy line is given (`play`),
    which Mercury modulates. Nothing comes back on the broadcast port of a station alone; a line that is not open drops the frame with a line in the log at DEBUG."""

    def __init__(self, host: str, port: Callable[[], int], running: Callable[[], bool]) -> None:
        self._host, self._port, self._running = host, port, running       # where the program's broadcast port is, and whether the program still runs (the loop ends with it)
        self._writer: asyncio.StreamWriter | None = None
        self.played = 0                                                   # how many frames were handed to the program

    @property
    def open(self) -> bool:
        return self._writer is not None

    async def run(self, keep: Callable[[], bool]) -> None:
        """Keeps the line open while `keep` says so and the program runs; a task of the owner, cancelled by it."""
        backoff = Backoff([0.5, 1.0, 2.0, 5.0])
        while keep() and self._running():
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(self._host, self._port()), CONNECT_SEC)
            except (OSError, TimeoutError):
                await asyncio.sleep(backoff.next_delay_sec())
                continue
            self._writer = writer
            log.info("Mercury plays the frames of the Dummy HF radio on the computer's sound output")
            try:
                while await reader.read(4096):                          # (nothing comes back on a broadcast port with no other station; the read ends when Mercury goes)
                    pass
            except OSError:
                pass
            finally:
                if self._writer is writer:
                    self._writer = None
                writer.close()
            await asyncio.sleep(backoff.next_delay_sec())

    def close(self) -> None:
        writer, self._writer = self._writer, None
        if writer is not None:
            writer.close()

    def play(self, data: bytes) -> None:
        """A frame as KISS bytes, handed to the program to be heard; dropped while the line is not open."""
        writer = self._writer
        if writer is None:
            log.debug("Mercury is not playing: nothing to hear for this frame")
            return
        try:
            writer.write(data)
            self.played += 1
        except OSError as e:
            log.debug("Mercury's broadcast port could not be written: %s", os_error_text(e))
