"""The status's Send on (neoaprs/beaconrule.py `send_on_radios`, neoaprs/services/rigstatus.py): the
status goes out on the radios the operator ticked, one report per interval per radio, at
`status/interval_min` raised to the radio's floor. Counted per radio over a simulated day; the
upgrade runs on a whole daemon.
"""

import logging
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from neoaprs import ax25
from neoaprs.beaconrule import beacon_interval, send_on_radios
from neoaprs.clock import iso
from neoaprs.coded import code_of
from neoaprs.config import LISTENS_ONLY, Config
from neoaprs.packet import Packet
from neoaprs.radiospec import RadioId, RadioSpec
from neoaprs.radiotype import Limits
from neoaprs.services.beaconframe import BeaconFrames
from neoaprs.services.radioset import NO_RADIO
from neoaprs.services.rigstatus import RigStatus, memory_key_of
from neoaprs.source import Source
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR, Env, remember_stop, until
from tests.support.seamshapes import LiveShape
from tests.support.stubtnc import StubTnc

FM = RadioSpec(1, "fm", "kenwood-tnc2", "", True, 1, settings={"path": "WIDE1-1,WIDE2-1"})
HF = RadioSpec(2, "hf", "dummy-hf", "", True, 2)
LORA = RadioSpec(3, "lora", "dummy-lora", "", True, 3)
# A tick stored from another type: a radio that only receives has no such field
RX = RadioSpec(4, "fm", "tnc-text", "", True, 4, settings={"port": "/dev/ttyUSB7", "status": "true"})
DAY = 24 * 60
# The status interval of the day: the FM radio at it, HF and LoRa at their floor of 30
EVERY = 15


def ticked(spec: RadioSpec, on: bool = True) -> RadioSpec:
    return replace(spec, settings={**spec.settings, "status": "true" if on else "false"})


class Short(LiveShape):
    """A radio whose type carries less text than our status (no type does: the status is at most 55
    characters, a LoRa packet 252 bytes of text)."""

    @property
    def limits(self) -> Limits:
        return replace(super().limits, max_text=30)


class Registry:
    """The registry's choice of a radio over the settings as they are now: a radio that is on is
    there, with its own stub line."""

    def __init__(self, station: "Station") -> None:
        self.station = station

    def get(self, id: RadioId) -> LiveShape | None:
        c = self.station.config
        spec = c.radio(id)
        if spec is None or spec.removed or not spec.enabled:
            return None
        shape = Short if id in self.station.short else LiveShape
        return shape(spec, c.radios, self.station.lines[id])  # type: ignore[arg-type]  # (a stub, not a Tnc)

    def enabled(self) -> list[LiveShape]:
        return [r for s in self.station.config.enabled_radios if (r := self.get(s.id)) is not None]

    def senders(self) -> list[LiveShape]:
        return [r for r in self.enabled() if r.spec.rtype.can.transmit]

    def first(self) -> LiveShape | None:
        return next(iter(self.senders()), None)

    def for_station(self, call: str) -> LiveShape | None:
        return self.first()

    def for_packet(self, packet: Packet) -> LiveShape | None:
        return self.first()

    def email(self) -> LiveShape | None:
        return self.first()


class Station:
    """The status service of a station with these radios, a text of its own every EVERY minutes, the
    beacon on."""

    def __init__(self, *specs: RadioSpec, short: Sequence[RadioId] = (), **changes: object) -> None:
        self.clock = FixedClock()
        self.config: Config = replace(
            ON_AIR,
            **{
                "beacon_interval_min": 30,
                "status_interval_min": EVERY,
                "station_status": "QRV 145.500",
                "status_source": "text",
                "radios": specs,
                **changes,
            },
        )  # type: ignore[arg-type]
        self.lines: dict[RadioId, StubTnc] = {}
        self.short = tuple(short)
        for spec in specs:
            self.add(spec)
        self.status = RigStatus(
            Registry(self),
            lambda: self.config,
            BeaconFrames(lambda: self.config, None, self.clock),
            self.clock,
            poll_sec=0.01,
        )
        remember_stop(self.status.stop)

    def add(self, spec: RadioSpec) -> None:
        self.lines.setdefault(spec.id, StubTnc(max_frame=123 if spec.kind == "hf" else None, id=spec.id))
        if self.config.radio(spec.id) is None:
            self.config = replace(self.config, radios=(*self.config.radios, spec))

    def put(self, spec: RadioSpec) -> None:
        self.config = replace(self.config, radios=tuple(spec if s.id == spec.id else s for s in self.config.radios))

    async def day(self, minutes: int = DAY, at: dict[int, Callable[[], None]] | None = None) -> None:
        """A poll a minute for this long, from the clock as it is; `at` changes the settings before
        the poll of that minute."""
        for minute in range(minutes):
            if at and minute in at:
                at[minute]()
            await self.status.poll()
            self.clock.advance(60)

    def reports(self) -> dict[RadioId, int]:
        return {id: sum(1 for f in line.sent if f.info.startswith(b">")) for id, line in self.lines.items()}


# ---- the rule ------------------------------------------------------------------------------------


def status_radios(specs: Sequence[RadioSpec]) -> tuple[RadioId, ...]:
    return send_on_radios("status", specs)


def test_the_status_goes_on_the_ticked_radios_exactly_and_with_one_radio_that_can_send_on_that_one() -> None:
    both = (FM, HF)
    assert status_radios(both) == () and status_radios((ticked(FM, False), ticked(HF, False))) == (), (
        "unticked by default, and ticked nowhere is not sent: no radio stands in"
    )
    assert (
        status_radios((ticked(FM), HF)) == (1,)
        and status_radios((ticked(FM), ticked(HF))) == (1, 2)
        and status_radios((FM, ticked(HF))) == (2,)
    )
    assert status_radios((HF,)) == (2,) and status_radios((ticked(FM, False), replace(HF, enabled=False))) == (1,), (
        "with one radio that can send, that one whatever its tick"
    )
    assert status_radios((FM, RX)) == (1,), "a radio that only receives is never one, its stored tick not read"
    assert status_radios((replace(ticked(HF), enabled=False), FM, LORA)) == (), "a ticked radio that is off is none"
    assert status_radios(()) == () and status_radios((RX,)) == (), "no radio that can send: none"
    for key in ("ask", "local_info"):
        assert send_on_radios(key, both) == () and send_on_radios(key, (FM, replace(HF, settings={key: "true"}))) == (
            2,
        ), "one rule for every thing that has a Send on"
        assert send_on_radios(key, (ticked(FM), HF)) == (), (
            "each thing by its own key: a status row is no tick of another thing"
        )


def test_the_status_on_a_radio_is_its_interval_raised_to_the_radios_own_floor_the_beacons_rule() -> None:
    assert [beacon_interval(EVERY, spec) for spec in (FM, HF, LORA)] == [15, 30, 30]
    assert [beacon_interval(120, spec) for spec in (FM, HF, LORA)] == [120, 120, 120]


# ---- what goes on the air over a day -------------------------------------------------------------


async def test_one_fm_radio_sends_as_today() -> None:
    station = Station(FM)
    await station.day()
    assert station.reports() == {1: DAY // EVERY}


async def test_fm_and_hf_ticked_nowhere_send_nothing_and_a_tick_moved_at_noon_moves_the_status() -> None:
    station = Station(FM, HF)
    await station.day()
    assert station.reports() == {1: 0, 2: 0}, "ticked nowhere: no status"
    moved = Station(ticked(FM), HF)

    def move() -> None:
        moved.put(ticked(FM, False))
        moved.put(ticked(HF))

    await moved.day(at={720: move})
    assert moved.reports() == {1: 48, 2: 24}, (
        "FM until noon; HF from the next interval after the last FM report (11:45 + 30 min), at its floor"
    )
    assert [f.info[1:8] for f in moved.lines[2].sent][:1] == [b"220015z"], (
        "the first on HF at 00:15, half an hour after the last on FM at 23:45"
    )


async def test_both_ticked_the_fm_radio_sends_at_the_interval_and_the_hf_radio_at_its_floor() -> None:
    station = Station(ticked(FM), ticked(HF))
    await station.day()
    assert station.reports() == {1: 96, 2: 48}
    assert all(f.tnc2().startswith("OH2GBA>APZNEO:>") for f in station.lines[2].sent), "HF carries no path"
    texts = {f.info[8:] for line in station.lines.values() for f in line.sent}
    assert texts == {b"QRV 145.500"}, "the same text on every radio"


async def test_only_hf_ticked_sends_on_hf_alone_at_its_floor() -> None:
    station = Station(FM, ticked(HF))
    await station.day()
    assert station.reports() == {1: 0, 2: 48}


async def test_with_every_tick_stored_unticked_the_status_goes_on_no_radio() -> None:
    station = Station(ticked(FM, False), ticked(HF, False))
    await station.day()
    assert station.reports() == {1: 0, 2: 0}
    nothing = Station(RX)
    await nothing.day(60)
    assert (
        nothing.reports() == {4: 0} and nothing.lines[4].asked == 0 and await nothing.status.send_now() == LISTENS_ONLY
    ), "no radio that can send: none sent, and the interlock says why"
    assert nothing.status.on_radio(4) == (None, None, 0)


async def test_with_no_radio_the_status_is_not_sent_and_the_log_says_so_once(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.status")
    station = Station(replace(ticked(FM), enabled=False), replace(ticked(HF), enabled=False))
    await station.day(60)
    assert station.reports() == {1: 0, 2: 0} and await station.status.send_now() == NO_RADIO
    assert [r.getMessage() for r in caplog.records] == [f"no status sent: {NO_RADIO}"]


async def test_a_third_radio_added_and_ticked_while_running_joins_at_the_next_interval_at_its_floor() -> None:
    station = Station(ticked(FM), ticked(HF))
    await station.day(at={360: lambda: station.add(ticked(LORA))})
    assert station.reports() == {1: 96, 2: 48, 3: 36}, (
        "LoRa from 06:15, half an hour after the latest report of 05:45, every 30 minutes"
    )


async def test_a_ticked_radio_removed_sends_no_more_and_the_others_go_on() -> None:
    station = Station(ticked(FM), ticked(HF))
    removed = replace(ticked(HF), enabled=False, removed_at=station.clock() + timedelta(hours=12))
    await station.day(at={720: lambda: station.put(removed)})
    assert station.reports() == {1: 96, 2: 24}
    assert station.status.on_radio(2)[1:] == (None, 0)


async def test_a_radio_that_only_receives_is_never_sent_on() -> None:
    station = Station(ticked(FM), RX)
    await station.day()
    assert station.reports() == {1: 96, 4: 0} and station.lines[4].asked == 0
    assert await station.status.send_now() == "" and station.lines[4].asked == 0


async def test_a_text_too_long_for_a_radio_is_not_sent_there_nor_reported_sent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, "neoaprs.status")
    station = Station(ticked(FM), ticked(LORA), short=(3,))
    await station.day()
    assert station.reports() == {1: 96, 3: 0} and station.lines[3].asked == 0
    assert station.status.on_radio(3)[0] is None and station.status.sent_on.get(3) is None, "not reported sent"
    told = [r.getMessage() for r in caplog.records if "longer than the radio carries" in r.getMessage()]
    assert len(told) == 1 and "it is not cut, and not sent there" in told[0], "said once"


async def test_a_radio_that_is_not_connected_is_waited_for_and_gets_one_report_when_it_is_back() -> None:
    station = Station(ticked(FM), ticked(HF))
    station.lines[2].held = "the channel is busy"
    await station.day(120)
    assert station.reports() == {1: 8, 2: 0}
    station.lines[2].held = ""
    await station.day(1)
    assert station.reports() == {1: 9, 2: 1}, "one report when it is back, however many intervals went by"


async def test_a_radio_that_waited_left_and_is_ticked_again_later_joins_at_the_next_interval_not_at_once() -> None:
    station = Station(ticked(FM), ticked(HF))
    station.lines[2].held = "the channel is busy"  # (a radio of the status that never sent: it waits)

    def leave() -> None:
        station.put(ticked(HF, False))
        station.lines[2].held = ""

    def back() -> None:
        station.put(ticked(FM, False))
        station.put(ticked(HF))

    await station.day(240, at={60: leave, 180: back})
    assert [f.info[1:7] for f in station.lines[1].sent][-1:] == [b"211445"]
    assert [f.info[1:7] for f in station.lines[2].sent] == [b"211515", b"211545"], (
        "half an hour after the latest report, not at the change"
    )


# ---- Send status now -----------------------------------------------------------------------------


async def test_send_status_now_sends_once_on_each_ticked_radio_that_takes_it_now_and_the_interval_counts_from_it() -> (
    None
):
    station = Station(ticked(FM), ticked(HF), LORA)
    station.lines[2].held = "the channel is busy"
    assert await station.status.send_now() == ""
    assert station.reports() == {1: 1, 2: 0, 3: 0}, (
        "on the FM radio; the HF radio cannot take it now, LoRa is not ticked"
    )
    station.lines[2].held = ""
    assert await station.status.send_now() == ""
    assert station.reports() == {1: 2, 2: 1, 3: 0}
    station.clock.advance(60)
    await station.day(14)
    assert station.reports() == {1: 2, 2: 1, 3: 0}, "inside the interval of each"
    await station.day(1)
    assert station.reports() == {1: 3, 2: 1, 3: 0}


async def test_why_send_status_now_sent_nothing_is_a_code_with_its_values_never_only_a_sentence() -> None:
    """Every reason Send status now gives has a code and the values of its sentence, which the page
    says in its own language inside `status.not_sent` (for example a Dutch page showing
    "there is no status text"): one with the code `other` would be shown as the plain words of a
    failure, and an English sentence must never reach the page."""

    async def why(station: Station) -> tuple[str, dict[str, object]]:
        return code_of(await station.status.send_now())

    assert await why(Station(replace(ticked(FM), enabled=False))) == ("radio.none", {})
    assert await why(Station(ticked(FM), status_source="off")) == ("status.off", {})
    assert await why(Station(ticked(FM), station_status="")) == ("status.no_text", {})
    assert await why(Station(ticked(FM), station_status="x" * 56)) == ("status.too_long", {"length": 56, "max": 55})
    assert await why(Station(ticked(LORA), short=(3,))) == (
        "status.too_long_for_radio",
        {"radio": 3, "name": "LoRa"},
    ), "the radio by its id: the page says its own name for it"
    refusing = Station(ticked(FM), ticked(HF))
    refusing.lines[1].takes = refusing.lines[2].takes = False
    assert await why(refusing) == ("radio.not_taken", {"radio": 1, "name": "Packet"}), (
        "none took it: the first radio's reason"
    )
    silent = Station(ticked(FM))
    silent.lines[1].state = Source.State.SILENT
    assert (await why(silent))[0] == "radio.silent"
    placeholder = Station(ticked(FM), station_call="N0CALL")
    assert await why(placeholder) == ("call.placeholder", {"call": "N0CALL"})


async def test_the_status_of_my_radio_says_the_same_frequency_on_every_radio() -> None:
    readings = iter([(14074000, "USB"), (7074000, "LSB")])

    async def read(host: str, port: int) -> Any:
        from neoaprs.rigctld import Reading

        hz, mode = next(readings)
        return Reading(hz, mode)

    station = Station(ticked(FM), ticked(HF), status_source="rig", status_rigctld="127.0.0.1:4532")
    station.status = RigStatus(
        Registry(station),
        lambda: station.config,
        BeaconFrames(lambda: station.config, None, station.clock),
        station.clock,
        poll_sec=0.01,
        read=read,
    )
    await station.status.poll()
    assert [f.info[8:] for f in (*station.lines[1].sent, *station.lines[2].sent)] == [b"QRV 14.074 MHz USB"] * 2, (
        "read once, sent on both"
    )


async def test_each_radio_keeps_its_last_report_in_its_own_row(tmp_path: Path) -> None:
    from tests.support.storedb import store_at

    store = await store_at(tmp_path / "neoaprs.sqlite", FixedClock())
    station = Station(ticked(FM), ticked(HF))
    station.status = RigStatus(
        Registry(station),
        lambda: station.config,
        BeaconFrames(lambda: station.config, None, station.clock),
        station.clock,
        poll_sec=0.01,
        memory=store,
    )
    await station.status.poll()
    await station.status.stop()
    assert (await store.setting(memory_key_of(1)), await store.setting(memory_key_of(2))) == (
        iso(station.clock()),
        iso(station.clock()),
    ) and memory_key_of(2) == "radio/2/status_last_sent_at"
    station.clock.advance(20 * 60)
    again = RigStatus(
        Registry(station),
        lambda: station.config,
        BeaconFrames(lambda: station.config, None, station.clock),
        station.clock,
        poll_sec=0.01,
        memory=store,
    )
    remember_stop(again.stop)
    await again.start()
    await until(lambda: station.reports()[1] == 2)
    await again.poll()
    await again.stop()
    assert station.reports() == {1: 2, 2: 1}, (
        "a restart 20 minutes on: the FM radio is due (15), the HF radio is not (30)"
    )


async def test_each_radios_own_row_says_its_last_report_after_a_start(tmp_path: Path) -> None:
    from neoaprs.config import STATUS_SENT
    from tests.support.storedb import store_at

    store = await store_at(tmp_path / "neoaprs.sqlite", FixedClock())
    station = Station(ticked(FM), HF)
    last = station.clock() - timedelta(minutes=10)
    # As migration 34 leaves them: the station's latest is every radio's own
    await store.put_settings(
        {STATUS_SENT: iso(last) or "", memory_key_of(1): iso(last) or "", memory_key_of(2): iso(last) or ""}
    )
    station.status = RigStatus(
        Registry(station),
        lambda: station.config,
        BeaconFrames(lambda: station.config, None, station.clock),
        station.clock,
        poll_sec=3600,
        memory=store,
    )
    remember_stop(station.status.stop)
    await station.status.start()
    assert station.status.on_radio(1) == (last, last + timedelta(minutes=EVERY), EVERY) and station.status.on_radio(
        2
    ) == (last, None, 0), "the ticked radio's line: the report of before; the other is no radio of the status"
    await station.status.stop()


# ---- the wire ------------------------------------------------------------------------------------


async def test_each_radios_row_says_its_last_report_and_the_next() -> None:
    station = Station(ticked(FM), ticked(HF), LORA)
    sent = station.clock()
    await station.status.poll()
    assert station.status.on_radio(1) == (sent, sent + timedelta(minutes=15), 15)
    assert station.status.on_radio(2) == (sent, sent + timedelta(minutes=30), 30)
    assert station.status.on_radio(3) == (None, None, 0), "not a radio of the status"
    station.config = replace(station.config, beacon_interval_min=0)
    assert station.status.on_radio(1) == (sent, None, 15), "the beacon off: no timed status"


# ---- the upgrade ---------------------------------------------------------------------------------


async def test_a_daemon_with_both_radios_sends_the_status_on_the_ticked_one_and_a_tick_on_the_other_moves_it(
    tmp_path: Path,
) -> None:
    clock = FixedClock()
    last = clock() - timedelta(minutes=10)
    settings = {
        "hf/enabled": "true",
        "hf/profile": "dummy-hf",
        "beacon/interval_min": "60",
        "status/source": "text",
        "station/status": "QRV 145.500",
        "status/interval_min": "30",
        # The rows the older version kept; its radios have no `status` of their own.
        "status/last_sent_at": iso(last) or "",
        "status/last_text": "QRV 145.500",
    }
    e = Env(tmp_path, clock=clock, settings=settings)
    # No program: the Dummy HF radio works without its speaker
    e.mercury._finder = lambda: None
    out: list[tuple[RadioId | None, bytes]] = []
    e.ctl.radio_packet.connect(
        lambda p: out.append((p.radio_id, ax25.decode(p.raw).info)) if p.direction == "out" else None
    )
    await e.start()
    await until(lambda: e.tnc.usable and e.hf.usable)
    assert status_radios(e.ctl.config.radios) == (1,), (
        "radio 1 ticked when radio 2 came beside it (sendonrule), as the operator's radios are"
    )
    await e.ctl.rigstatus.poll()
    reports = lambda: Counter(id for id, info in out if info.startswith(b">"))  # noqa: E731
    assert reports() == Counter(), "inside the interval kept from before the update"
    for _ in range(3 * 60):
        clock.advance(60)
        await e.ctl.rigstatus.poll()
    await until(lambda: reports()[1] == 6)
    assert reports() == Counter({1: 6}), "on the FM radio, every 30 minutes, from 20 minutes on"
    assert await e.ctl.save_radio_settings(1, {"status": "false"}) and await e.ctl.save_radio_settings(
        2, {"status": "true"}
    )
    for _ in range(60):
        clock.advance(60)
        await e.ctl.rigstatus.poll()
    await until(lambda: reports()[2] == 2)
    assert reports() == Counter({1: 6, 2: 2}), "ticked on HF alone: the FM radio is no longer one"
    await e.stop()
