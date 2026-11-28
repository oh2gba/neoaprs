"""Properties of the watch for a KISS radio that sends something else (neoaprs/tncmode.py TextWatch): lines of
text that go on for HOLD_SEC with no frame raise it whatever the chunking, and noise or a start-up banner
followed by KISS never do; the first frame clears it. Then the same through a radio's line."""

import random
import threading
import time
from types import SimpleNamespace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from neoaprs import ax25, serialport
from neoaprs.claims import Claims
from neoaprs.kiss import encode
from neoaprs.radiospec import RadioSpec
from neoaprs.radiotype import FM_ID
from neoaprs.source import Backoff
from neoaprs.tnc import Tnc
from neoaprs.tncmode import TextWatch
from neoaprs.tncprofile import KISS
from neoaprs.web.radioview import radio_row
from tests.support.env import until

HOLD = TextWatch.HOLD_SEC


def frame_bytes(info: bytes = b"!6010.00N/02450.00E>test") -> bytes:
    frame = ax25.Frame(ax25.Address("APZNEO"), ax25.Address.parse("N0CALL-9"), (ax25.Address("WIDE1", 1),), info=info)
    return encode(ax25.encode(frame))


# what a tracker sends when it is not set to KISS: its own settings name them UI, GPWPL, GPS and KISS Asc
SAMPLES = {
    "monitor": [
        b"N0CALL-9>APRS,WIDE1-1:!6010.00N/02450.00E>on the road\r\n",
        b"N0CALL-7>APDR16,WIDE1-1,WIDE2-1:=6012.34N/02456.78E$ 145.800 MHz\r\n",
    ],
    "nmea": [
        b"$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n",
        b"$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47\r\n",
        b"$GPWPL,4807.038,N,01131.000,E,WPTNME*5C\r\n",
    ],
    "kiss hex": [frame_bytes().hex().upper().encode() + b"\r\n"],
    "kiss hex unbroken": [frame_bytes().hex().upper().encode() * 3],
}
BANNER = b"\r\nNinoTNC v3.40\r\nMode 6: 1200 AFSK AX.25 with KISS on the USB port\r\n"


def cut(data: bytes, points: list[int]) -> list[bytes]:
    marks = sorted({min(p, len(data)) for p in points} | {0, len(data)})
    return [data[a:b] for a, b in zip(marks, marks[1:])]


@given(
    st.sampled_from(sorted(SAMPLES)),
    st.integers(2, 12),
    st.floats(0.5, 30.0),
    st.lists(st.integers(0, 400), max_size=8),
)
def test_text_that_goes_on_with_no_frame_raises_the_watch_whatever_the_chunking(
    kind: str, count: int, gap: float, points: list[int]
) -> None:
    watch, went_on = TextWatch(), []
    for n in range(count):
        line = SAMPLES[kind][n % len(SAMPLES[kind])]
        for chunk in cut(line, points):
            went_on.append(watch.feed(chunk, n * gap))
    assert watch.alarm is ((count - 1) * gap >= HOLD)
    assert went_on.count(True) == int(watch.alarm), "said once"


@given(
    st.lists(st.integers(0, 120), max_size=6),
    st.floats(0.0, 300.0),
    st.integers(1, 5),
    st.floats(0.1, 600.0),
    st.integers(0, 2**32 - 1),
)
def test_noise_or_a_banner_before_kiss_frames_never_raises_it(
    points: list[int], first_frame_at: float, frames: int, gap: float, seed: int
) -> None:
    noise = random.Random(seed).randbytes(4096)
    watch = TextWatch()
    for i, chunk in enumerate(cut(noise, [p * 32 for p in points])):
        watch.feed(chunk, i * 0.5)
    for chunk in cut(BANNER, points):
        watch.feed(chunk, first_frame_at)
    for n in range(frames):
        at = first_frame_at + 1 + n * gap
        for chunk in cut(frame_bytes(b"heard a station\rwith a long comment in its info field\r"), points):
            watch.feed(chunk, at)
        watch.frame()  # the reader tells it of each frame it decoded
        assert not watch.alarm


@given(st.sampled_from(sorted(SAMPLES)))
def test_the_first_frame_clears_it_and_text_must_go_on_again_to_raise_it(kind: str) -> None:
    watch = TextWatch()
    lines = SAMPLES[kind]
    watch.feed(lines[0], 0.0)
    watch.feed(lines[-1], HOLD)
    assert watch.alarm
    assert watch.frame() and not watch.alarm
    assert not watch.frame()
    watch.feed(lines[0], HOLD + 1)
    assert not watch.alarm


# ---- through a radio's line


class FeedSer:
    """A pyserial object of a port that brings what the test gives it."""

    def __init__(self) -> None:
        self.incoming, self.lock, self.in_waiting = b"", threading.Lock(), 0

    def give(self, data: bytes) -> None:
        with self.lock:
            self.incoming += data

    def open(self) -> None:
        pass

    def read(self, size: int = 1) -> bytes:
        time.sleep(0.005)
        with self.lock:
            data, self.incoming = self.incoming, b""
        return data

    def write(self, data: bytes) -> int:
        return len(data)

    def close(self) -> None:
        pass


def problem_of(tnc: Tnc) -> object:
    spec = RadioSpec(FM_ID, "fm", "kiss", "", True, 1)
    at_work = SimpleNamespace(
        line=tnc,
        beacon=SimpleNamespace(last_sent=None, next_due=None, interval_min=0, problem=""),
        driver=SimpleNamespace(card=None),
        driver_key="tnc",
    )
    row = radio_row(spec, [spec], at_work, Claims())
    return row["state"], row["problem"]


async def test_a_kiss_radio_that_sends_gps_sentences_says_so_until_its_first_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ser = FeedSer()
    monkeypatch.setattr(serialport, "_build", lambda path, baud: ser)
    monkeypatch.setattr(TextWatch, "HOLD_SEC", 0.0)  # (the hold is the property above's)
    tnc = Tnc("COM7", profile=KISS, backoff=Backoff([30.0]), check_sec=0)
    try:
        await tnc.start()
        assert problem_of(tnc) == ("connected", None)
        for line in SAMPLES["nmea"]:
            ser.give(line)
        await until(lambda: tnc.sends_text)
        assert problem_of(tnc) == ("connected", {"code": "radio.sends_text", "params": {}})
        assert any("the device sends text, not KISS" in line for line in tnc.lines)
        ser.give(frame_bytes())
        await until(lambda: tnc.stats.packets == 1)
        assert problem_of(tnc) == ("connected", None)
    finally:
        await tnc.stop()
