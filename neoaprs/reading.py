"""The signal of a heard frame as the radio measured it: SNR (dB) and strength (dBm), if given.

Mercury says it before the frame (`Pending`), a LoRa board after it (`Following`). Pure code.
"""
from dataclasses import dataclass
from typing import Generic, Literal, TypeVar

ReadingKind = Literal["snr", "rssi"]
# how long a reading said before its frame waits for it
PAIR_SEC = 1.0
# how long a frame waits for the KISS command 7 sent after it
REPORT_WAIT_SEC = 0.5
# how long a frame waits for the iGate's list to say its reading
LIST_WAIT_SEC = 2.0
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Reading:
    snr: float | None = None
    rssi: float | None = None

    def only(self, kinds: tuple[ReadingKind, ...]) -> "Reading":
        """Return the reading with only the kinds a radio type gives; the others are None."""
        return Reading(self.snr if "snr" in kinds else None, self.rssi if "rssi" in kinds else None)


NO_READING = Reading()


class Pending:
    """A reading said before its frame, kept for the next frame for at most `pair_sec`."""

    def __init__(self, pair_sec: float = PAIR_SEC) -> None:
        self.pair_sec = pair_sec
        self._reading, self._at = NO_READING, 0.0

    def put(self, reading: Reading, now: float) -> None:
        self._reading, self._at = reading, now

    def take(self, now: float) -> Reading:
        """Return the reading of the frame that has just come, once; NO_READING if none."""
        reading, self._reading = self._reading, NO_READING
        return reading if now - self._at <= self.pair_sec else NO_READING

    def clear(self) -> None:
        self._reading = NO_READING


@dataclass
class _Held(Generic[T]):
    item: T
    key: str
    at: float
    reading: Reading | None = None


class Following(Generic[T]):
    """Frames held for a reading said after them; a frame goes on in arrival order."""

    def __init__(self, wait_sec: float) -> None:
        self.wait_sec = wait_sec
        self._held: list[_Held[T]] = []

    def hold(self, item: T, key: str, now: float) -> None:
        """Hold a frame that waits for its reading; `key` names it for `report` (its text)."""
        self._held.append(_Held(item, key, now))

    def report(self, reading: Reading, now: float, key: str | None = None) -> list[tuple[T, Reading]]:
        """Say a reading of the latest frame with none (or under `key`); return those due."""
        found = next((h for h in reversed(self._held) if h.reading is None and (key is None or h.key == key)), None)
        if found is not None:
            found.reading = reading
        return self.due(now)

    def due(self, now: float) -> list[tuple[T, Reading]]:
        """Return the frames that may go on now, up to the first that still waits."""
        out: list[tuple[T, Reading]] = []
        while self._held and (self._held[0].reading is not None or now - self._held[0].at >= self.wait_sec):
            first = self._held.pop(0)
            out.append((first.item, first.reading or NO_READING))
        return out

    def waiting(self) -> bool:
        return bool(self._held)

    def keys(self) -> list[str]:
        """Return the keys of the frames still waiting for their reading, in arrival order."""
        return [h.key for h in self._held if h.reading is None]

    def release(self) -> list[tuple[T, Reading]]:
        """Release every frame held, each with its reading or none: the readings' source is gone."""

        out, self._held = [(h.item, h.reading or NO_READING) for h in self._held], []
        return out
