"""Scope, transmit gain and automatic channel-busy control of the Mercury modem (a mixin).

All of it uses Mercury's UI interface, opened only to the program the daemon started.
"""
import logging
import time

from .mercury import HOST, UI_OFFSET
from .channelbusy import OccupancyBusy
from .mercuryscope import KeptRow, RowMeter, ScopeHistory, bands_db, clamp_gain, parse_spectrum, parse_status, scope_clock
from .mercuryui import MercuryUi
from .signal import Signal
from .tasks import TaskSet

log = logging.getLogger("neoaprs.mercury")

# Mercury reports -120 before any transmission.
PEAK_SILENT_DBFS = -100.0
# The spectrum just after a transmission still holds the end of the frame (128 ms window).
AFTER_TX_SEC = 0.4


class Scoping:
    state: str
    keyed: bool
    _keyed_at: float
    attached: str
    speaker: bool
    test: str
    broadcast_port: int
    changed: Signal[[]]
    _tasks: TaskSet

    async def _retune(self) -> None:
        raise NotImplementedError

    def auto_busy(self, on: bool, now: float) -> None:
        raise NotImplementedError

    def auto_lost(self, now: float) -> None:
        raise NotImplementedError

    def _init_scoping(self) -> None:
        self.scope_row: Signal[[KeptRow]] = Signal("mercury.scope_row")
        self.scope_cleared: Signal[[]] = Signal("mercury.scope_cleared")
        self.scope_history = ScopeHistory()
        self.tx_gain_db = 0
        # Peak of the latest transmission in whole dBFS; None before one.
        self.tx_peak_dbfs: int | None = None
        self._ui: MercuryUi | None = None
        self._rows = RowMeter()
        self._auto = OccupancyBusy()

    # ---- the link
    @property
    def ui_port(self) -> int:
        """Return Mercury's UI port (broadcast port + UI_OFFSET), or 0 for a foreign program."""
        return 0 if self.attached or self.speaker else self.broadcast_port + UI_OFFSET

    @property
    def scope(self) -> bool:
        """True while the UI link is open."""
        return self._ui is not None and self._ui.connected

    @property
    def live_gain(self) -> bool:
        return self.scope

    def _start_ui(self) -> None:
        if self.ui_port == 0 or self._ui is not None:
            return
        self.forget_scope()
        self._auto = OccupancyBusy()
        self._ui = MercuryUi(HOST, self.ui_port, self._ui_text, self._ui_binary, self._ui_state)
        # The channel-busy control reads every spectrum.
        self._ui.want_waterfall = True
        self._ui.start()

    async def _stop_ui(self) -> None:
        ui, self._ui = self._ui, None
        if ui is not None:
            await ui.stop()
        self.tx_peak_dbfs = None

    def _ui_state(self, up: bool) -> None:
        if up:
            # A row is two consecutive spectra, never spanning a dropped link.
            self._rows.reset()
            self._ui_opened()
        else:
            self.auto_lost(time.monotonic())
        self.changed.emit()

    def _ui_opened(self) -> None:
        if self._ui is not None and self.tx_gain_db != 0:
            self._ui.tx_gain(self.tx_gain_db)

    # ---- what it says
    def _ui_text(self, text: str) -> None:
        status = parse_status(text)
        if status is None:
            return
        peak = None if status.tx_peak_dbfs < PEAK_SILENT_DBFS else round(status.tx_peak_dbfs)
        if peak != self.tx_peak_dbfs:
            self.tx_peak_dbfs = peak
            self.changed.emit()

    def _ui_binary(self, data: bytes) -> None:
        spectrum = parse_spectrum(data)
        if spectrum is None:
            return
        now = time.monotonic()
        if self.keyed or now - self._keyed_at < AFTER_TX_SEC:
            self._auto.pause()
            self.auto_busy(False, now)
        else:
            self.auto_busy(self._auto.update(now, bands_db(spectrum)), now)
        row = self._rows.feed(spectrum, self.keyed)
        if row is not None:
            self.scope_row.emit(self.scope_history.add(row, scope_clock()))

    # ---- the scope
    def forget_scope(self) -> None:
        """Drop the kept rows and the row under way."""
        self._rows.reset()
        if self.scope_history.clear():
            self.scope_cleared.emit()

    # ---- the transmit gain
    def set_tx_gain(self, db: float) -> None:
        """Set the transmit gain, sending it live if the link is open; the tune tone follows."""
        gain = clamp_gain(db)
        if gain == self.tx_gain_db:
            return
        self.tx_gain_db = gain
        if self._ui is not None and self.state == "running":
            sent = self._ui.tx_gain(gain)
            log.info("Mercury: the transmit gain is %+d dB%s", gain, "" if sent else " from the next start")
        if self.test == "tune":
            self._tasks.spawn(self._retune(), "mercury-retune")
        self.changed.emit()
