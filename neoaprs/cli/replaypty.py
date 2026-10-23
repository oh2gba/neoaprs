"""The pseudo-terminal mode of `neoaprs replay --pty` (Linux and macOS): the capture is played on a pseudo-terminal, whose path is printed as the first line, for a daemon given `--port /dev/pts/N`.
Nothing is sent while nobody has the pseudo-terminal open (a port that opens it throws away what was waiting), so the daemon may be started after this and restarted during it."""
import os
import select
import time
import tty

from .output import SETTLE_SEC, say


class Line:
    """The master side of the pseudo-terminal. Somebody has the other side open while poll() does not report a hang-up."""

    def __init__(self, master: int) -> None:
        self.master = master
        self.poller = select.poll()  # type: ignore[attr-defined, unused-ignore]
        self.poller.register(master, select.POLLIN)  # type: ignore[attr-defined, unused-ignore]
        self.was_open = False

    def is_open(self) -> bool:
        return not any(events & select.POLLHUP for _, events in self.poller.poll(0))  # type: ignore[attr-defined, unused-ignore]

    def pause(self, seconds: float) -> None:
        """Waits `seconds`, showing what the other end writes in the meantime."""
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
                time.sleep(min(left, 0.1))                   # (hung up: nothing to read, nothing to wait for)

    def wait_for_the_port(self) -> None:
        """Returns when a port has the pseudo-terminal open; after it opened, a moment is given for its clearing of the input."""
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
    os.close(slave)                                          # nobody has the slave open now: the master reports a hang-up until a port opens it
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
