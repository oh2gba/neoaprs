"""Tests for the radios a bulletin post goes out on (`bulletin_post`) over a station of six radios:
frames only on ticked radios that can send and are on, the repeat interval, and duplicate ids.
"""

from collections import Counter
from dataclasses import replace
from pathlib import Path

from neoaprs.ownlog import OwnLog
from neoaprs.services.ownbulletins import OwnBulletins
from neoaprs.services.sender import Sender
from tests.support.clock import FixedClock
from tests.support.env import remember_stop
from tests.support.radioconfig import radio
from tests.support.rig import OwnRig
from tests.support.seamshapes import LiveShape, RegistryShape
from tests.support.storedb import log_at
from tests.support.stubtnc import StubTnc

SIX = (
    radio(1, "kenwood-tnc2"),
    radio(2, "mercury", enabled=True),
    radio(3, "kiss"),
    radio(4, "lora-tcp"),
    radio(5, "lora-console"),
    radio(6, "kiss", enabled=False),
)


class Six(OwnRig):
    """The daemon's bulletins on six radios, each on a line of its own (`taken`, by id)."""

    def __init__(self, log: OwnLog, clock: FixedClock) -> None:
        super().__init__(log, clock)
        self.config = replace(self.config, radios=SIX)
        self.taken = {spec.id: StubTnc() for spec in SIX}
        self.sender = Sender(
            RegistryShape([LiveShape(spec, SIX, self.taken[spec.id]) for spec in SIX]),
            lambda: self.config,
            clock,
            spacing_sec=10.0,
        )  # type: ignore[arg-type]
        self.posts = OwnBulletins(self.sender, lambda: self.config, log, clock, tick_sec=3600.0)

    def run(self, seconds: int, step: int = 5) -> None:
        self.look(self.posts.tick, seconds, step)

    def counted(self) -> dict[int, int]:
        """The frames each radio took, by id (a radio that took none is left out)."""
        return {id: len(line.sent) for id, line in self.taken.items() if line.sent}

    def slots(self, id: int) -> Counter[str]:
        """The frames a radio took, by the bulletin's slot."""
        return Counter(frame.info[1:6].decode().strip() for frame in self.taken[id].sent)


async def six_at(tmp_path: Path) -> Six:
    log, _, clock = await log_at(tmp_path, OwnLog)
    rig = Six(log, clock)
    await rig.posts.start()
    remember_stop(rig.posts.stop)
    return rig


async def test_a_bulletin_ticked_for_every_radio_goes_on_those_that_send_and_are_on_every_30_minutes_while_one_is_mercury_or_lora(
    tmp_path: Path,
) -> None:
    rig = await six_at(tmp_path)
    rig.posts.post("BLN1", "Net tonight", [1, 2, 3, 4, 5, 6])
    rig.run(5 * 3600, step=10)
    assert rig.counted() == {1: 10, 2: 10, 3: 10, 4: 10}, (
        "0, 2, 6, 36 ... 216 minutes on each; none on the radio that only receives, none on the one that is off"
    )


async def test_a_bulletin_ticked_for_the_two_fm_radios_alone_repeats_every_20_minutes_on_each_and_one_on_mercury_alone_every_30(
    tmp_path: Path,
) -> None:
    rig = await six_at(tmp_path)
    rig.posts.post("BLN1", "Net tonight", [1, 3])
    rig.posts.post("BLN2", "HF sked", [2])
    rig.run(5 * 3600, step=10)
    assert rig.counted() == {1: 14, 2: 10, 3: 14}
    assert rig.slots(1) == Counter({"BLN1": 14}) and rig.slots(2) == Counter({"BLN2": 10}), (
        "each bulletin on its own radios"
    )


async def test_a_bulletin_ticked_only_for_radios_that_cannot_carry_it_sends_nothing_and_an_id_named_twice_is_one_radio(
    tmp_path: Path,
) -> None:
    rig = await six_at(tmp_path)
    rig.posts.post("BLN1", "Nowhere", [5, 6])
    rig.run(3600, step=10)
    assert rig.counted() == {}, "the radio that only receives and the one that is off: ticked nowhere is not sent"
    rig.posts.post("BLN2", "Twice", [4, 4])
    rig.run(400, step=10)
    assert rig.counted() == {4: 3}, "0, 2 and 6 minutes, once each"
