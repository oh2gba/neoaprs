"""Stateful properties of the KISS or text detector (neoaprs/tncmode.py ModeDetector), fed KISS frames, text lines,
noise and pieces split at any byte: the mode depends only on the bytes since the last rearm, not on how they were
cut; KISS stays KISS and MONITOR never falls back to UNKNOWN until a rearm; a whole UI frame makes it KISS; text,
FENDs inside it too, never does.
"""

from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from neoaprs import ax25, kiss
from neoaprs.tncmode import _TEXT_BYTES, Mode, ModeDetector

FEND = 0xC0
ROOM = 3000  # below the detector's tail of 4096 bytes, where the cut of the bytes cannot matter
CALLS = st.sampled_from(["APRS", "OH2XYZ-9", "W1AW", "N0CALL-15", "AB1C-7", "WIDE1-1", "WIDE2-2"])
LINES = st.one_of(
    st.sampled_from(
        [
            b"cmd:",
            b"\r\ncmd:\x11",
            b"OH2XYZ-9>APRS,WIDE1-1*:>hi\r\n",
            b"OH2XYZ>APRS:hello\r",
            b"OH2XYZ-9>APRS,WIDE1 <UI>:>hi\r",
            b"TH-D7 ver 2.0\r\n",
            b"hello world\r\n",
        ]
    ),
    st.binary(max_size=40).map(lambda b: bytes(c for c in b if c in _TEXT_BYTES) + b"\r\n"),
)


@st.composite
def ui_frames(draw: st.DrawFn) -> bytes:
    frame = ax25.Frame(
        ax25.Address.parse(draw(CALLS)),
        ax25.Address.parse(draw(CALLS)),
        tuple(ax25.Address.parse(c) for c in draw(st.lists(CALLS, max_size=3))),
        info=draw(st.binary(min_size=1, max_size=40)),
    )
    return kiss.encode(ax25.encode(frame), port=draw(st.integers(min_value=0, max_value=15)))


def pieces(data: bytes, cuts: list[int]) -> list[bytes]:
    at = sorted({c % (len(data) + 1) for c in cuts} | {0, len(data)})
    return [data[a:b] for a, b in zip(at, at[1:], strict=False)]


def mode_of(data: bytes) -> Mode:
    return ModeDetector().feed(data)


class Detector(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.detector = ModeDetector()
        self.since = b""  # the bytes fed since the last rearm
        self.before = Mode.UNKNOWN

    def feed(self, data: bytes, cuts: list[int]) -> None:
        self.before = self.detector.mode
        for piece in pieces(data, cuts):
            self.detector.feed(piece)
        self.since += data

    @precondition(lambda self: len(self.since) < ROOM)
    @rule(frame=ui_frames(), cuts=st.lists(st.integers(min_value=0), max_size=4))
    def a_whole_ui_frame(self, frame: bytes, cuts: list[int]) -> None:
        self.feed(frame, cuts)
        assert self.detector.mode is Mode.KISS

    @precondition(lambda self: len(self.since) < ROOM)
    @rule(
        frame=ui_frames(),
        command=st.integers(min_value=1, max_value=15),
        cuts=st.lists(st.integers(min_value=0), max_size=3),
    )
    def a_frame_of_another_command(self, frame: bytes, command: int, cuts: list[int]) -> None:
        self.feed(kiss.encode(kiss.KissDecoder().feed(frame)[0].payload, command=command), cuts)

    @precondition(lambda self: len(self.since) < ROOM)
    @rule(line=LINES, cuts=st.lists(st.integers(min_value=0), max_size=4))
    def a_text_line(self, line: bytes, cuts: list[int]) -> None:
        self.feed(line, cuts)

    @precondition(lambda self: len(self.since) < ROOM)
    @rule(line=LINES, fends=st.lists(st.integers(min_value=0), min_size=1, max_size=3))
    def a_text_line_with_fends_in_it(self, line: bytes, fends: list[int]) -> None:
        self.feed(bytes([FEND]).join(pieces(line, fends)), [])

    @precondition(lambda self: len(self.since) < ROOM)
    @rule(noise=st.binary(max_size=60), cuts=st.lists(st.integers(min_value=0), max_size=4))
    def noise(self, noise: bytes, cuts: list[int]) -> None:
        self.feed(noise, cuts)

    @precondition(lambda self: len(self.since) < ROOM)
    @rule(frame=ui_frames(), keep=st.integers(min_value=1))
    def the_start_of_a_frame(self, frame: bytes, keep: int) -> None:
        self.feed(frame[: keep % len(frame)], [])

    @rule()
    def rearm(self) -> None:
        self.detector.rearm()
        self.since = b""
        self.before = Mode.UNKNOWN

    @invariant()
    def the_cut_of_the_bytes_does_not_matter(self) -> None:
        assert self.detector.mode is mode_of(self.since)

    @invariant()
    def kiss_and_monitor_hold(self) -> None:
        if self.before is Mode.KISS:
            assert self.detector.mode is Mode.KISS
        if self.before is Mode.MONITOR:
            assert self.detector.mode is not Mode.UNKNOWN

    @invariant()
    def text_and_fends_alone_are_never_kiss(self) -> None:
        if all(b in _TEXT_BYTES or b == FEND for b in self.since):
            assert self.detector.mode is not Mode.KISS


Detector.TestCase.settings = settings(max_examples=150, stateful_step_count=25)
test_the_detector_keeps_its_promises = Detector.TestCase
