"""A Tnc that is a stub, for the tests of the parts that send frames by a schedule (services/sender.py and what uses it): a state the test sets, whether it takes a frame, and every frame it was given.

    tnc = StubTnc()
    tnc.state = Source.State.SILENT         # the radio is switched off: `usable` is False
    tnc.takes = False                       # it is settling after KISS ON: the write is refused
    tnc.infos()                             # the information fields of the frames it took
    tnc.lines()                             # the same frames as TNC-2 lines ("OH2GBA>APNEO1:text")
    tnc.asked                               # how many times it was asked to send, taken or not
    tnc.raw                                 # the bytes it took with a frame (send_frame's `raw`: the digipeater's), as they were given
"""
from neoaprs import ax25
from neoaprs.radiorules import FM, HF, RadioRules
from neoaprs.source import Source, unusable_because


class StubTnc:
    def __init__(self, state: Source.State = Source.State.CONNECTED, max_frame: int | None = None, rules: RadioRules | None = None) -> None:
        self.state = state
        self.sent: list[ax25.Frame] = []
        self.raw: list[bytes] = []                  # the bytes given with a frame (the digipeater's), as they were given
        self.takes = True
        self.asked = 0
        self.max_frame = max_frame                  # the longest frame the radio carries (the Mercury HF modem's 123), None for the AX.25 limit alone
        self.rules = rules if rules is not None else HF if max_frame is not None else FM         # the rules of the kind of radio: the HF radio's when it has a frame cap, else the FM radio's; a test may give others (a frame cap with paths)

    @property
    def usable(self) -> bool:
        return self.state is Source.State.CONNECTED

    def why_unusable(self) -> str:
        return unusable_because(self.state)

    def send_frame(self, frame: ax25.Frame, raw: bytes | None = None) -> bool:
        self.asked += 1
        if self.takes:
            self.sent.append(frame)
            if raw is not None:
                assert ax25.decode(raw) == frame, "the bytes are the frame's"
                self.raw.append(raw)
        return self.takes

    def infos(self) -> list[bytes]:
        return [f.info for f in self.sent]

    def lines(self) -> list[str]:
        return [f.tnc2() for f in self.sent]
