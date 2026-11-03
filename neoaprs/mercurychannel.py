"""What the Mercury HF modem's control port says about the channel and the radio, and what the Tnc is told of it: the half of the modem part (mercurymodem.py, whose `Mercury` inherits this) that keeps `keyed` (Mercury keys the
radio: `PTT ON` until `PTT OFF`), `busy` (its busy detector hears a signal: `BUSY ON` until `BUSY OFF`) and the signal-to-noise ratio of the latest frame, and answers `hold`, the carrier sense this plane lacks: while the
radio is keyed no frame is handed to Mercury, so that our own frames go one at a time and the services' pace counts from a frame that has really left; while the busy detector hears a signal no frame goes either, for at most
BUSY_HOLD_MAX_SEC, because the detector takes a step in the noise for a signal for a minute or two and traffic must not be stranded by it. It reads `test` (the tune tone and the keying test hold the radio too) and tells the
page that something changed (`changed`)."""
import logging
import time

from .mercury import BUSY_HOLD_MAX_SEC, FRAME_SEC, ControlEvent
from .signal import Signal

log = logging.getLogger("neoaprs.mercury")

TRANSMITTING = "the radio is transmitting"
CHANNEL_BUSY = "the channel is busy"
KEYED_MAX_SEC = 2 * FRAME_SEC + 5.0          # a `PTT ON` with no `PTT OFF` after this long (12.6 s, three frames' worth) is not believed: a transmitter that stayed keyed is Mercury's safety timer's business (its TUNE ends after 60 s), and ours is not to wait for ever; a choice, not a measurement (docs/mercury.md)


class Channel:
    test: str
    changed: Signal[[]]
    frames_keyed: int

    def _init_channel(self) -> None:
        self.keyed = False                                           # Mercury has keyed the radio (PTT ON)
        self.busy = False                                            # Mercury's busy detector hears a signal (BUSY ON)
        self.snr: float | None = None                                # the signal-to-noise ratio of the latest frame decoded, dB
        self._keyed_at = self._busy_at = 0.0
        self._keyed_since = self._busy_since = 0.0                   # when the PTT ON / BUSY ON that is under way came (for the log's "for 3.8 s")
        self._told_long: set[str] = set()                            # "keyed" / "busy": the hold has said it gives up on a state that lasts too long (once for each)

    def _event(self, event: ControlEvent) -> None:
        now = time.monotonic()
        if event.kind == "ptt":
            self._on_ptt(event.on, now)
        elif event.kind == "busy":
            self._on_busy(event.on, now)
        elif event.kind == "snr" and event.value is not None:
            self.snr = event.value
        else:
            return
        self.changed.emit()

    def _on_ptt(self, on: bool, now: float) -> None:
        """Mercury keyed the radio or let go: one line when it lets go, with how long it was keyed (a frame, 3.8 s; the tone of Tune or the test, as long as that)."""
        if on and not self.keyed:
            self.frames_keyed += 1
            self._keyed_since = now
            self._told_long.discard("keyed")
        elif not on and self.keyed:
            what = {"tune": "the tune tone", "key": "the keying test"}.get(self.test, f"frame {self.frames_keyed}")
            log.info("Mercury: the radio was keyed for %.1f s (%s)", now - self._keyed_since, what)
        self.keyed, self._keyed_at = on, now

    def _on_busy(self, on: bool, now: float) -> None:
        """Mercury's detector heard a signal or lost it: one line when the channel is clear again, with how long it was busy."""
        if on and not self.busy:
            self._busy_since = now
            self._told_long.discard("busy")
        elif not on and self.busy:
            held = now - self._busy_since
            log.info("Mercury: the channel was busy for %.1f s%s", held, f" (our frames were held for the first {BUSY_HOLD_MAX_SEC:g} s)" if held > BUSY_HOLD_MAX_SEC else "")
        self.busy, self._busy_at = on, now


    def hold(self) -> str:
        """Why no frame is to go now: the radio is keyed (by a frame, the tune tone or the keying test), or the channel is busy (and has been for less than BUSY_HOLD_MAX_SEC); "" when one may."""
        now = time.monotonic()
        if self.test or (self.keyed and now - self._keyed_at < KEYED_MAX_SEC):
            return TRANSMITTING
        if self.busy and now - self._busy_at < BUSY_HOLD_MAX_SEC:
            return CHANNEL_BUSY
        self._tell_long()
        return ""

    def _tell_long(self) -> None:
        """A keyed radio or a busy channel that has lasted longer than the hold believes it: told once for each, so that a person reading the log sees why frames go again under a signal."""
        if self.keyed and "keyed" not in self._told_long:
            self._told_long.add("keyed")
            log.warning("Mercury: PTT ON and no PTT OFF for over %g s: not believed, frames are sent again", KEYED_MAX_SEC)
        if self.busy and "busy" not in self._told_long:
            self._told_long.add("busy")
            log.warning("Mercury: the channel has been busy for over %g s: it no longer holds our frames", BUSY_HOLD_MAX_SEC)

