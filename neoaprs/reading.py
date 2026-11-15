"""The signal of a frame that was heard, as the radio measured it: the signal-to-noise ratio in dB and the received strength in dBm, each there or not. A radio type says which of the two it gives
(`Profile.readings`, tncprofile.py): the Mercury modem the SNR of each frame it decodes, a LoRa board both where its firmware says them (the CA2RXU iGate's list of heard packets, DL9SAU's
element of the path, esp32_loraprs's KISS command 7, the CA2RXU iGate's log on USB; a CA2RXU Tracker none), a KISS TNC neither. A reading is never worked out from anything else: the level of the receiver's
audio says how the sound card is driven, not how strong the station is, and is no RSSI.

The reading is tied to its frame where the frame is made (the Tnc's frame reader, tnc.py), not taken as "the latest the radio said". Mercury says the SNR on its control port (`SN -2.5`) before it hands the frame
to its broadcast port (modem.c of 1.9.24, as of 1.9.21: `tnc_send_sn` comes first in `process_received_frame`, and the broadcast port's thread looks for a whole frame every 100 ms), on another connection. So a reading that comes
alone waits (`Pending`) for the next frame, which takes it once; it waits at most PAIR_SEC, far less than the time a frame takes on the air (3.8 s for DATAC3), so that a reading whose frame never came (one
Mercury did not hand over, or one that came first) is never given to the frame after it, which is a whole frame's time later.

A LoRa board says the reading after its frame, or answers it when asked: esp32_loraprs sends its KISS command 7 right after the data frame, and the CA2RXU iGate keeps its last packets with their readings in a
list that is asked for after a frame (loralist.py). So such a frame waits (`Following`) for its reading, at most REPORT_WAIT_SEC or LIST_WAIT_SEC, and goes on with it or without it, never before a frame that came
earlier. Pure code."""
from dataclasses import dataclass
from typing import Generic, Literal, TypeVar

ReadingKind = Literal["snr", "rssi"]
PAIR_SEC = 1.0                         # how long a reading said before its frame waits for it: Mercury's broadcast port hands a frame over within 0.1 s of its SN line, and the next frame is 3.8 s away
REPORT_WAIT_SEC = 0.5                  # how long a frame waits for the KISS command 7 that esp32_loraprs sends right after it (not measured: the board writes the two at once)
LIST_WAIT_SEC = 2.0                    # how long a frame waits for the CA2RXU iGate's list to say its reading (not measured: one request over the local network; a LoRa frame took 1 to 9 s on the air)
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Reading:
    snr: float | None = None           # the signal-to-noise ratio, dB (Mercury's is scaled to 3 kHz: docs/mercury.md)
    rssi: float | None = None          # the received signal strength, dBm

    def only(self, kinds: tuple[ReadingKind, ...]) -> "Reading":
        """The reading with only the kinds a radio type gives; the others are None."""
        return Reading(self.snr if "snr" in kinds else None, self.rssi if "rssi" in kinds else None)


NO_READING = Reading()


class Pending:
    """A reading said before its frame, kept for the next frame to take (`take`), for at most `pair_sec`. A second reading before a frame replaces the first: the first one's frame did not come."""

    def __init__(self, pair_sec: float = PAIR_SEC) -> None:
        self.pair_sec = pair_sec
        self._reading, self._at = NO_READING, 0.0

    def put(self, reading: Reading, now: float) -> None:
        self._reading, self._at = reading, now

    def take(self, now: float) -> Reading:
        """The reading of the frame that has just come: the one said within `pair_sec` before it, once; NO_READING when none was."""
        reading, self._reading = self._reading, NO_READING
        return reading if now - self._at <= self.pair_sec else NO_READING

    def clear(self) -> None:
        self._reading = NO_READING


@dataclass
class _Held(Generic[T]):
    item: T
    key: str
    at: float
    reading: Reading | None = None     # None: not said yet


class Following(Generic[T]):
    """Frames held for a reading said after them, in arrival order: a frame goes on with its reading, or without one when its wait is over; a frame is never handed on before one that came earlier."""

    def __init__(self, wait_sec: float) -> None:
        self.wait_sec = wait_sec
        self._held: list[_Held[T]] = []

    def hold(self, item: T, key: str, now: float) -> None:
        """A frame that waits for its reading; `key` names it for `report` (the board's list says a frame by its text)."""
        self._held.append(_Held(item, key, now))

    def report(self, reading: Reading, now: float, key: str | None = None) -> list[tuple[T, Reading]]:
        """A reading is said: of the latest frame held that has none yet (None: the KISS command 7 that follows its frame), or of the latest held under this key. The frames that may go on now, each with its reading."""
        found = next((h for h in reversed(self._held) if h.reading is None and (key is None or h.key == key)), None)
        if found is not None:
            found.reading = reading
        return self.due(now)

    def due(self, now: float) -> list[tuple[T, Reading]]:
        """The frames that may go on now, from the first held: each one whose reading was said or whose wait is over, up to the first that still waits."""
        out: list[tuple[T, Reading]] = []
        while self._held and (self._held[0].reading is not None or now - self._held[0].at >= self.wait_sec):
            first = self._held.pop(0)
            out.append((first.item, first.reading or NO_READING))
        return out

    def waiting(self) -> bool:
        return bool(self._held)

    def keys(self) -> list[str]:
        """The keys of the frames that still wait for their reading, in arrival order."""
        return [h.key for h in self._held if h.reading is None]

    def release(self) -> list[tuple[T, Reading]]:
        """Every frame held, at once, each with the reading said of it or none: the source of the readings is gone."""
        out, self._held = [(h.item, h.reading or NO_READING) for h in self._held], []
        return out
