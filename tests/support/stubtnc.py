"""A Tnc that is a stub, for the tests of the parts that send frames by a schedule (services/sender.py and what uses it): a state the test sets, whether it takes a frame, and every frame it was given.

    tnc = StubTnc()
    tnc.state = Source.State.SILENT         # the radio is switched off: `usable` is False
    tnc.takes = False                       # it is settling after KISS ON: the write is refused
    tnc.infos()                             # the information fields of the frames it took
    tnc.lines()                             # the same frames as TNC-2 lines ("OH2GBA>APNEO1:text")
    tnc.asked                               # how many times it was asked to send, taken or not
"""
from neoaprs import ax25
from neoaprs.source import Source, unusable_because


class StubTnc:
    def __init__(self, state: Source.State = Source.State.CONNECTED) -> None:
        self.state = state
        self.sent: list[ax25.Frame] = []
        self.takes = True
        self.asked = 0

    @property
    def usable(self) -> bool:
        return self.state is Source.State.CONNECTED

    def why_unusable(self) -> str:
        return unusable_because(self.state)

    def send_frame(self, frame: ax25.Frame) -> bool:
        self.asked += 1
        if self.takes:
            self.sent.append(frame)
        return self.takes

    def infos(self) -> list[bytes]:
        return [f.info for f in self.sent]

    def lines(self) -> list[str]:
        return [f.tnc2() for f in self.sent]
