"""The signal of a frame that was heard, as the radio measured it: the signal-to-noise ratio in dB and the received strength in dBm, each there or not. A radio type says which of the two it gives
(`Profile.readings`, tncprofile.py): the Mercury modem the SNR of each frame it decodes, a LoRa radio both, a KISS TNC neither. A reading is never worked out from anything else: the level of the receiver's
audio says how the sound card is driven, not how strong the station is, and is no RSSI.

The reading is tied to its frame where the frame is made (the Tnc's frame reader, tnc.py), not taken as "the latest the radio said". Mercury says the SNR on its control port (`SN -2.5`) before it hands the frame
to its broadcast port (modem.c of 1.9.24, as of 1.9.21: `tnc_send_sn` comes first in `process_received_frame`, and the broadcast port's thread looks for a whole frame every 100 ms), on another connection. So a reading that comes
alone waits (`Pending`) for the next frame, which takes it once; it waits at most PAIR_SEC, far less than the time a frame takes on the air (3.8 s for DATAC3), so that a reading whose frame never came (one
Mercury did not hand over, or one that came first) is never given to the frame after it, which is a whole frame's time later. Pure code."""
from dataclasses import dataclass
from typing import Literal

ReadingKind = Literal["snr", "rssi"]
PAIR_SEC = 1.0                         # how long a reading said before its frame waits for it: Mercury's broadcast port hands a frame over within 0.1 s of its SN line, and the next frame is 3.8 s away


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
