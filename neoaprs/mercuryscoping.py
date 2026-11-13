"""The scope, the transmit level and the automatic channel-busy control of the Mercury HF modem, the half of the modem part (mercurymodem.py, whose `Mercury` inherits this) that uses Mercury's UI interface (mercuryui.py, mercuryscope.py): the link is opened to
the program the daemon started (not to one something else runs, whose UI port is not ours to know, and not to the speaker of the Dummy HF radio), `scope_row` tells a row of the waterfall at the modem's own resolution (every two spectra: about ten a second) while a page wants
them, and the transmit gain the settings hold is set live, with the tune tone following it.

The spectrum is asked for (`set_waterfall`) whenever the link is open, because the channel-busy control reads every spectrum (channelbusy.py: a signal as wide as a frame is busy, a step in the noise or a carrier is not; it stands still while the radio
transmits; `Channel.auto_busy` makes it the channel's state, Mercury's own detector being the state while the spectrum is not read); the rows of the scope are made only while a page has it open (`want_scope`). The status Mercury sends twice a second says the peak of the latest
transmission (`tx_peak_dbfs`), which the page shows beside the gain. When the link is not there (a Mercury without the interface, a connection that fails) there is no scope, the gain is applied at the next start of the program
(the ini has it), and the controller starts the program again at a change of the gain, since nothing else would apply it (`live_gain` is false then). A modem part of its own, not the program's life: it reads and sets the modem's
state (`state`, `keyed`, `attached`, `speaker`, the tasks) and asks it to tell the page (`changed`)."""
import logging
import time

from .mercury import UI_OFFSET
from .channelbusy import OccupancyBusy
from .mercuryscope import RowMeter, ScopeRow, bands_db, clamp_gain, parse_spectrum, parse_status
from .mercuryui import MercuryUi
from .signal import Signal
from .tasks import TaskSet

log = logging.getLogger("neoaprs.mercury")

HOST = "127.0.0.1"
PEAK_SILENT_DBFS = -100.0              # Mercury's peak is -120 before anything was transmitted
AFTER_TX_SEC = 0.4                     # the spectrum of a Mercury that has just let go of the radio holds the end of its own frame (a window of 128 ms, and Mercury's own busy detector waits 300 ms: BUSY_TX_HOLDOFF_MS)


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
        self.scope_row: Signal[[ScopeRow]] = Signal("mercury.scope_row")                 # a row of the waterfall at the modem's own resolution, every two spectra, while a page wants the scope
        self.tx_gain_db = 0                          # the transmit gain the modem runs with (the setting, applied at the start and live)
        self.tx_peak_dbfs: int | None = None         # the peak of the latest transmission in whole dBFS, as Mercury's status says; None before one
        self._ui: MercuryUi | None = None
        self._rows = RowMeter()
        self._auto = OccupancyBusy()                 # the automatic channel-busy control: it reads every spectrum of the program, whether a page has the scope open or not
        self._wanted = False

    # ---- the link
    @property
    def ui_port(self) -> int:
        """The port of Mercury's UI interface for this start (the broadcast port's, UI_OFFSET above), 0 when the program is not ours to configure."""
        return 0 if self.attached or self.speaker else self.broadcast_port + UI_OFFSET

    @property
    def scope(self) -> bool:
        """The link to the UI interface is open: the scope can be shown and the gain is set live."""
        return self._ui is not None and self._ui.connected

    @property
    def live_gain(self) -> bool:
        return self.scope

    def _start_ui(self) -> None:
        if self.ui_port == 0 or self._ui is not None:
            return
        self._rows.reset()
        self._auto = OccupancyBusy()
        self._ui = MercuryUi(HOST, self.ui_port, self._ui_text, self._ui_binary, self._ui_state)
        self._ui.want_waterfall = True               # (the busy control needs the spectrum all the time; what a page wants is the rows)
        self._ui.start()

    async def _stop_ui(self) -> None:
        ui, self._ui = self._ui, None
        if ui is not None:
            await ui.stop()
        self.tx_peak_dbfs = None

    def _ui_state(self, up: bool) -> None:
        if up:
            self._ui_opened()
        else:
            self.auto_lost(time.monotonic())
        self.changed.emit()

    def _ui_opened(self) -> None:
        if self._ui is not None and self.tx_gain_db != 0:
            self._ui.tx_gain(self.tx_gain_db)                       # (the ini carries it; this is for a program that read a file we did not write)

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
            self._auto.pause()                        # (what the radio hears now is its own signal)
            self.auto_busy(False, now)
        else:
            self.auto_busy(self._auto.update(now, bands_db(spectrum)), now)
        if self._wanted:
            row = self._rows.feed(spectrum, self.keyed)
            if row is not None:
                self.scope_row.emit(row)

    # ---- the scope
    def want_scope(self, wanted: bool) -> None:
        """A page has the scope open (or the last one closed it): the rows are made while one does, each from the spectra that came after it was asked."""
        if wanted != self._wanted:
            self._wanted = wanted
            self._rows.reset()

    # ---- the transmit gain
    def set_tx_gain(self, db: float) -> None:
        """The transmit gain of the settings: sent to the program when the link is open (the tune tone, which Mercury keeps out of its gain, is retuned to follow it)."""
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
