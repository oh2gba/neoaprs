"""Keyed, busy and SNR state of the Mercury HF modem from its control port (mixin of `Mercury`).

`hold` supplies the carrier sense the modem lacks: no frame goes while keyed or busy.
"""

import logging
import math
import time

from .mercury import BUSY_HOLD_MAX_SEC, FRAME_SEC, ControlEvent
from .reading import Pending, Reading
from .signal import Signal
from .coded import Reason

log = logging.getLogger("neoaprs.mercury")

TRANSMITTING = Reason("the radio is transmitting", "radio.transmitting")
CHANNEL_BUSY = Reason("the channel is busy", "radio.channel_busy")
AUTO_STALE_SEC = 1.0
# A `PTT ON` without `PTT OFF` for this long is not believed (a choice, not a measurement).
KEYED_MAX_SEC = 2 * FRAME_SEC + 5.0


class Channel:
    test: str
    changed: Signal[[]]
    frames_keyed: int

    def _init_channel(self) -> None:
        self.keyed = False
        self.busy = False
        self._mercury_busy = False
        self._auto_at = 0.0
        # SNR of the latest decoded frame, dB.
        self.snr: float | None = None
        self._reading = Pending()
        # -inf, not 0: a zero would mean "keyed at boot" on a machine that was just switched on.
        self._keyed_at, self._busy_at = -math.inf, 0.0
        self._keyed_since = self._busy_since = 0.0
        self._told_long: set[str] = set()

    def _clear_channel(self) -> None:
        """Forget the state the modem reported."""
        self.keyed = self.busy = self._mercury_busy = False
        self._auto_at = 0.0
        self._reading.clear()

    def _event(self, event: ControlEvent) -> None:
        now = time.monotonic()
        if event.kind == "ptt":
            self._on_ptt(event.on, now)
        elif event.kind == "busy":
            self._on_busy(event.on, now)
        elif event.kind == "snr" and event.value is not None:
            self.snr = event.value
            self._reading.put(Reading(snr=event.value), now)
        else:
            return
        self.changed.emit()

    def take_reading(self) -> Reading:
        """Return the SNR reported for the frame that just arrived on the broadcast port, if any."""
        return self._reading.take(time.monotonic())

    def _on_ptt(self, on: bool, now: float) -> None:
        """Record keying or release; on release log how long the radio was keyed."""
        if on and not self.keyed:
            self.frames_keyed += 1
            self._keyed_since = now
            self._told_long.discard("keyed")
        elif not on and self.keyed:
            what = {"tune": "the tune tone", "key": "the keying test"}.get(self.test, f"frame {self.frames_keyed}")
            log.info("Mercury: the radio was keyed for %.1f s (%s)", now - self._keyed_since, what)
        self.keyed, self._keyed_at = on, now

    def _on_busy(self, on: bool, now: float) -> None:
        """Record Mercury's detector state, used while the spectrum is not read."""
        self._mercury_busy = on
        if not self.auto_live(now):
            self._set_busy(on, now, "")

    def auto_live(self, now: float) -> bool:
        """Return True if the automatic control has a spectrum younger than AUTO_STALE_SEC."""
        return now - self._auto_at < AUTO_STALE_SEC

    def auto_busy(self, on: bool, now: float) -> None:
        """Record the automatic control's verdict; it rules while it is fed."""
        was = self.auto_live(now)
        self._auto_at = now
        if not was:
            log.info("Mercury: the channel is judged by the spectrum, not by the modem's fixed threshold")
        if on != self.busy:
            self._set_busy(on, now, " (by the spectrum)")
            self.changed.emit()

    def auto_lost(self, now: float) -> None:
        """Fall back to Mercury's own detector when the spectrum is lost."""
        if self._auto_at:
            self._auto_at = 0.0
            log.info("Mercury: the spectrum is not read any more, the channel is judged by the modem's own detector")
            if self.busy != self._mercury_busy:
                self._set_busy(self._mercury_busy, now, "")
                self.changed.emit()

    def _set_busy(self, on: bool, now: float, how: str) -> None:
        """Record busy or clear; on clear log how long the channel was busy."""
        if on and not self.busy:
            self._busy_since = now
            self._told_long.discard("busy")
        elif not on and self.busy:
            held = now - self._busy_since
            log.info(
                "Mercury: the channel was busy for %.1f s%s%s",
                held,
                how,
                f" (our frames were held for the first {BUSY_HOLD_MAX_SEC:g} s)" if held > BUSY_HOLD_MAX_SEC else "",
            )
        self.busy, self._busy_at = on, now

    def keyed_now(self, now: float) -> bool:
        """Return whether the radio is keyed as far as it is believed (`now` monotonic)."""
        return self.keyed and now - self._keyed_at < KEYED_MAX_SEC

    def hold(self) -> str:
        """Return why no frame may go now (keyed, or recently busy), or ""."""
        now = time.monotonic()
        # The spectrum may stop without the link reporting it.
        if self._auto_at and not self.auto_live(now):
            self.auto_lost(now)
        if self.test or self.keyed_now(now):
            return TRANSMITTING
        if self.busy and now - self._busy_at < BUSY_HOLD_MAX_SEC:
            return CHANNEL_BUSY
        self._tell_long()
        return ""

    def _tell_long(self) -> None:
        """Log once per state that a keyed or busy state outlasted the hold."""
        if self.keyed and "keyed" not in self._told_long:
            self._told_long.add("keyed")
            log.warning(
                "Mercury: PTT ON and no PTT OFF for over %g s: not believed, frames are sent again", KEYED_MAX_SEC
            )
        if self.busy and "busy" not in self._told_long:
            self._told_long.add("busy")
            log.warning(
                "Mercury: the channel has been busy for over %g s: it no longer holds our frames", BUSY_HOLD_MAX_SEC
            )
