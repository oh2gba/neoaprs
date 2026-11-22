"""The pseudo-terminal mode of `neoaprs replay --pty` (Linux and macOS).

The path is printed first, for a daemon given `--port /dev/pts/N`. Nothing is sent while nobody
has it open, because opening a port discards pending input."""
import os
import select
import time
import tty

from .output import SETTLE_SEC, say


class Line:
    """The master side of the pseudo-terminal; the far side is open while poll() has no hang-up."""

    def __init__(self, master: int) -> None:
        self.master = master
        self.poller = select.poll()  # type: ignore[attr-defined, unused-ignore]
        self.poller.register(master, select.POLLIN)  # type: ignore[attr-defined, unused-ignore]
        self.was_open = False

    def is_open(self) -> bool:
        return not any(events & select.POLLHUP for _, events in self.poller.poll(0))  # type: ignore[attr-defined, unused-ignore]

    def pause(self, seconds: float) -> None:
        """Wait `seconds`, showing what the other end writes meanwhile."""
        end = time.monotonic() + seconds
        while (left := end - time.monotonic()) > 0:
            events = self.poller.poll(min(left, 0.2) * 1000)
            if any(e & select.POLLIN and not e & select.POLLHUP for _, e in events):  # type: ignore[attr-defined, unused-ignore]
                try:
                    data = os.read(self.master, 4096)
                except OSError:
                    continue
                say(f"replay: the daemon wrote {len(data)} bytes: {data[:60]!r}")
            elif events:
                # Hung up: nothing to read, so avoid a busy loop.
                time.sleep(min(left, 0.1))

    def wait_for_the_port(self) -> None:
        """Return once a port has it open, after a pause for the port to clear its input."""
        if self.is_open():
            return
        say("replay: waiting for a port to open the pseudo-terminal")
        while not self.is_open():
            self.pause(0.2)
        say("replay: a port opened it")
        self.pause(SETTLE_SEC)

    def send(self, frame: bytes, number: int) -> None:
        self.wait_for_the_port()
        try:
            os.write(self.master, frame)
            say(f"replay: frame {number} sent ({len(frame)} bytes)")
        except BlockingIOError:
            say(f"replay: frame {number} dropped: the pseudo-terminal is full, nobody reads it")
        except OSError as e:
            say(f"replay: frame {number} not sent: {e}")


def play_on_pty(frames: list[bytes], interval: float, loop: bool) -> int:
    master, slave = os.openpty()  # type: ignore[attr-defined, unused-ignore]
    tty.setraw(slave)  # type: ignore[attr-defined, unused-ignore]
    path = os.ttyname(slave)  # type: ignore[attr-defined, unused-ignore]
    # With the slave closed the master reports a hang-up until a port opens it.
    os.close(slave)
    os.set_blocking(master, False)
    print(path, flush=True)
    line = Line(master)
    number = 0
    try:
        while True:
            for frame in frames:
                number += 1
                line.send(frame, number)
                line.pause(interval)
            if not loop:
                break
        say("replay: the file is played; Ctrl-C ends it")
        while True:
            line.pause(1.0)
    except KeyboardInterrupt:
        say("replay: stopped")
    return 0
