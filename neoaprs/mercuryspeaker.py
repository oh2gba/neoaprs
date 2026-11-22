"""Speaker of the Dummy Mercury radio: a Mercury that plays our frames on the sound output.

Mercury runs on its fifo audio backend; the daemon is the sound card's clock and feeds the
playback pipe to a system player. POSIX only. Nothing here is required: failures are only logged.
"""
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

from . import nodevices
from .source import Backoff, os_error_text

log = logging.getLogger("neoaprs.mercury")

CONNECT_SEC = 3.0
# Mercury's fifo backend: s32le mono samples a second, in sound-card-sized blocks.
RATE = 8000
SAMPLE_BYTES = 4
BLOCK_MS = 20
BLOCK_BYTES = RATE * BLOCK_MS // 1000 * SAMPLE_BYTES
SILENCE = bytes(BLOCK_BYTES)
CAPTURE_FIFO = "mercury-capture.fifo"
PLAYBACK_FIFO = "mercury-playback.fifo"
# Players of raw s32le mono at 8 kHz from stdin; the first found wins.
PLAYERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pw-play", ("--raw", "--rate", str(RATE), "--channels", "1", "--format", "s32", "-")),
    ("paplay", ("--raw", f"--rate={RATE}", "--format=s32le", "--channels=1")),
    ("aplay", ("-q", "-t", "raw", "-f", "S32_LE", "-r", str(RATE), "-c", "1", "-")),
)
NONBLOCK: int = getattr(os, "O_NONBLOCK", 0)


def player_command() -> list[str] | None:
    """Return the command of a system player of raw audio, or None.

    NEOAPRS_PLAYER_PATH replaces the PATH for the search.
    """
    if nodevices.refused("the Dummy Mercury radio's audio is not played", logging.INFO):
        return None
    path = os.environ.get("NEOAPRS_PLAYER_PATH")
    for name, args in PLAYERS:
        if (found := shutil.which(name, path=path)) is not None:
            return [found, *args]
    return None


class SpeakerAudio:
    """The sound card's clock for Mercury's fifo backend, run in a thread.

    Writes silence into the capture pipe every 20 ms and feeds the playback pipe to the player.
    """

    def __init__(self, folder: Path, player: Callable[[], list[str] | None] = player_command) -> None:
        self.capture = folder / CAPTURE_FIFO
        self.playback = folder / PLAYBACK_FIFO
        self._player_command = player
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._player: subprocess.Popen[bytes] | None = None
        self.blocks_written = 0
        self.bytes_played = 0
        self.player_said = False

    @property
    def possible(self) -> bool:
        """True if the system has named pipes (POSIX)."""
        return hasattr(os, "mkfifo")

    def prepare(self) -> bool:
        """Create both pipes anew, removing stale ones; return False (and log) on failure."""
        # POSIX only; the Windows type check knows no such name.
        make = getattr(os, "mkfifo", None)
        if make is None:
            return False
        try:
            for path in (self.capture, self.playback):
                path.unlink(missing_ok=True)
                make(path)
        except OSError as e:
            log.info("the pipes of the Dummy Mercury radio's speaker could not be made: %s", os_error_text(e))
            return False
        return True

    def start(self) -> None:
        """Start the clock thread, ending a previous one first."""
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
        self.player_said = False
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
        """Write one block of silence into the capture pipe.

        The pipe opens once Mercury reads it (ENXIO until then) and closes when Mercury goes.
        """
        if fd is None:
            try:
                fd = os.open(self.capture, os.O_WRONLY | NONBLOCK)
            except OSError:
                return None
        try:
            os.write(fd, SILENCE)
            self.blocks_written += 1
        except BlockingIOError:
            pass
        except OSError:
            with contextlib.suppress(OSError):
                os.close(fd)
            return None
        return fd

    def _read_audio(self, fd: int | None) -> int | None:
        """Pass what Mercury wrote since the last block to the player."""
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
                log.info("no player for the Dummy Mercury radio's audio (pw-play, paplay or aplay): the frames are not heard")
                return
            try:
                self._player = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                log.info("the Dummy Mercury radio's audio goes to %s", command[0])
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
            log.info("the player of the Dummy Mercury radio's audio ended: %s", os_error_text(e) if isinstance(e, OSError) else e)
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
    """TCP line to the speaker Mercury's broadcast port, kept open while the program runs.

    `play` writes KISS bytes there; a frame is dropped while the line is not open.
    """

    def __init__(self, host: str, port: Callable[[], int], running: Callable[[], bool]) -> None:
        self._host, self._port, self._running = host, port, running
        self._writer: asyncio.StreamWriter | None = None
        self.played = 0

    @property
    def open(self) -> bool:
        return self._writer is not None

    async def run(self, keep: Callable[[], bool]) -> None:
        """Keep the line open while `keep()` is true and the program runs."""
        backoff = Backoff([0.5, 1.0, 2.0, 5.0])
        while keep() and self._running():
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(self._host, self._port()), CONNECT_SEC)
            except (OSError, TimeoutError):
                await asyncio.sleep(backoff.next_delay_sec())
                continue
            self._writer = writer
            log.info("Mercury plays the frames of the Dummy Mercury radio on the computer's sound output")
            try:
                # The read ends when Mercury goes.
                while await reader.read(4096):
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
        """Hand a KISS frame to the program; drop it while the line is not open."""
        writer = self._writer
        if writer is None:
            log.debug("Mercury is not playing: nothing to hear for this frame")
            return
        try:
            writer.write(data)
            self.played += 1
        except OSError as e:
            log.debug("Mercury's broadcast port could not be written: %s", os_error_text(e))
