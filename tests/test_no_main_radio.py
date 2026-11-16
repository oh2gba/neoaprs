"""The update that takes the main radio away (migration 34, neoaprs/migrationsteps34.py, and the daemon without one) proved on the air: for each station of the design's section 4 and the shapes beside
it, a data folder as 0.20.0 and 0.20.1 left it (version 33, tests/support/migrated34.py; station g as 0.18.2 left it, version 26), started by the daemon on a fake clock for four hours with a status every
15 minutes, a bulletin and an object kept from before, an announcement, a mail, a message to a call no radio heard and one press of each Ask. The frames of ours are counted per radio and per kind, and held
to an ORACLE: 0.20.0's rules of the main radio, copied here (`main_radio`, `in_force_set`, the e-mail rule), never imported from today's code. Two things differ, each by its own number: a radio whose
airtime is everyone's (Mercury, LoRa) now has its floor of 30 minutes for the status and a bulletin's repeats (8 reports where there were 16, a bulletin 10 frames where it was 14), and a station with no
FM or LoRa radio on sends its mail (on the first radio that can send) where 0.20.0 refused it.

The day runs as tests/test_six_radios.py's (Dummy radios of every kind, a minute at a time, each timer looking at the clock in each step), radio by radio from the database the step wrote."""
import asyncio
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from neoaprs import ax25
from neoaprs.aprsmessage import parse_message
from neoaprs.clock import utc
from neoaprs.message import MessagingError
from neoaprs.packet import Packet
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.env import Env, until, until_started
from tests.support.migrated34 import Old, Radio, fm, hf, lora, monitor, version_33
from tests.test_migration_alert_markup import version_twenty_six
from tests.test_six_radios import STEP_WAIT_SEC, TICK_SEC, TICKED, quick

__all__ = ["quick"]                                         # (the fixture of the six radios' day: every timer looks at the clock several times in each step)

START = utc(2026, 11, 16, 6, 0, 0)
HOURS = 4
ME = "OH2GBA"
STATION_ROWS = {"station/call": ME, "station/lat": "60.17", "station/lon": "24.94", "beacon/interval_min": "30", "beacon/path": "WIDE1-1,WIDE2-1", "status/source": "text", "station/status": "QRV 145.500",
                "status/interval_min": "15", "status/last_sent_at": "2026-11-16T05:00:00Z", "messages/alert": "false"}
MAIL, NEW = "EMAIL-2", "OH2NEW"                             # (a call no radio of any made-up world has)
KINDS = ("beacon", "status", "bulletin", "announcement", "object", "query", "info", "mail", "new")

# ---- the ORACLE: 0.20.0's rules, copied (neoaprs/radiospec.py `main_radio` and `in_force_set`, neoaprs/emailrule.py `email_radio` of 48bea6ff), over the radios as the test wrote them

SENDS_0_20_0 = ("direwolf", "kiss", "kenwood-d710", "kenwood-tnc2", "kantronics", "kiss-tcp", "dummy", "dummy-hf", "mercury", "lora-tcp", "lora-serial", "dummy-lora")
HEARD_0_20_0 = ("fm", "lora")                               # the kinds whose types internet gateways hear (`Allowed.gateway_heard`)


def senders_0_20_0(radios: tuple[Radio, ...]) -> list[Radio]:
    return sorted((r for r in radios if not r.removed and r.enabled and r.type in SENDS_0_20_0), key=lambda r: (r.id if r.position is None else r.position, r.id))


def main_radio_0_20_0(radios: tuple[Radio, ...], chosen: int | None) -> int | None:
    """The main radio (plan §2): the one chosen while it is enabled and can send, else the first such by position, else None."""
    on = senders_0_20_0(radios)
    if chosen is not None and any(r.id == chosen for r in on):
        return chosen
    return on[0].id if on else None


def in_force_set_0_20_0(ids: tuple[int, ...], radios: tuple[Radio, ...], main: int | None) -> tuple[int, ...]:
    """A stored set of radios as it is in force: with one radio that can send that one; else its ticks of such radios, by position; else the main radio; else none."""
    on = senders_0_20_0(radios)
    if len(on) == 1:
        return (on[0].id,)
    found = tuple(r.id for r in on if r.id in set(ids))
    return found or ((main,) if main is not None else ())


def email_radio_0_20_0(radios: tuple[Radio, ...], main: int | None) -> int | None:
    heard = [r.id for r in senders_0_20_0(radios) if r.kind in HEARD_0_20_0]
    return main if main is not None and main in heard else heard[0] if heard else None


def oracle(radios: tuple[Radio, ...], chosen: int | None, object_radios: tuple[int, ...]) -> dict[str, tuple[int, ...]]:
    """The radios each thing of the day went on in 0.20.0: the beacon by its ticks (none ticked: the main radio), an object by its own, everything else on the main radio, a mail on the e-mail radio."""
    main = main_radio_0_20_0(radios, chosen)
    beacon = tuple(r.id for r in radios if r.own.get("beacon", "true") != "false")
    one = () if main is None else (main,)
    mail = email_radio_0_20_0(radios, main)
    return {"beacon": in_force_set_0_20_0(beacon, radios, main), "status": one, "bulletin": one, "announcement": one, "object": in_force_set_0_20_0(object_radios, radios, main),
            "query": one, "info": one, "mail": () if mail is None else (mail,), "new": one}


# ---- what a radio sends of each in four hours, by its kind's rules (the ones the update does not change, and the two it does)

SLOW = ("hf", "lora")                                       # the kinds whose own floor is 30 minutes (beaconrule.own_floor_min)
OLD_STATUS, NEW_STATUS_SLOW = 16, 8                         # 4 hours at 15 minutes; on HF and LoRa raised to the floor of 30 (the first exception)
OLD_BULLETIN, NEW_BULLETIN_SLOW = 14, 10                    # 0, 2, 6, then every 20 minutes to 226; every 30 while a radio it goes on is HF or LoRa: to 216 (the first exception)
ANNOUNCEMENT = 6                                            # 0, 2, 6, 66, 126, 186 minutes
PRESS = 1                                                   # one press of Ask around (?APRS?) and of Local info (INFO)


@dataclass(frozen=True)
class Day:
    """What a station's day is: its data folder of before, and what the day adds (a radio the day after the update, `added`)."""
    name: str
    old: Old
    added: str = ""                                          # a type added once the daemon runs (station h)
    v26: bool = False                                        # the data folder of 0.18.2 (station g): made of `old.settings`


OBJECT = "CAMP"
STATIONS = [
    Day("a one FM radio", Old((fm(1),))),
    Day("b FM and HF never chosen", Old((fm(1), hf(2)))),
    Day("c FM and HF with HF chosen", Old((fm(1), hf(2)), chosen=2)),
    Day("d FM chosen and off, HF and LoRa on", Old((fm(1, enabled=False), hf(2), lora(3)), chosen=1)),
    Day("e the chosen radio removed", Old((fm(1), hf(2), hf(3, removed=True)), chosen=3)),
    Day("f LoRa beside a monitor", Old((monitor(1), lora(2)))),
    Day("h a radio added the day after", Old((fm(1), hf(2))), added="dummy-lora"),
    Day("no radio", Old(())),
    Day("every radio off", Old((fm(1, enabled=False), hf(2, enabled=False)), chosen=2)),
    Day("three on with every beacon tick off", Old((fm(1, beacon="false"), hf(2, beacon="false"), lora(3, beacon="false")))),
    Day("two FM radios with the second chosen", Old((fm(1), fm(2)), chosen=2)),
    Day("HF alone with FM off", Old((fm(1, enabled=False), hf(2)))),
]
G = Day("g 0.18.2 with FM and HF", Old((fm(1, type="kiss"), hf(2))), v26=True)


def kind_of(frame: ax25.Frame) -> str:
    first = frame.info[:1]
    if first == b":":
        to = parse_message(frame.info[1:]).addressee
        return {"BLN1": "bulletin", "BLNA": "announcement", "QRU": "info", MAIL: "mail", NEW: "new"}.get(to, f"message to {to}")
    return {b">": "status", b";": "object", b"?": "query"}.get(first, "beacon" if first in (b"!", b"=", b"/", b"@") else "other")


class Running:
    """The daemon on the station's data folder, its clock, and every frame of ours with the time it went."""

    def __init__(self, tmp_path: Path, day: Day) -> None:
        self.clock = FixedClock(START)
        first = next((r for r in day.old.radios if r.id == 1), None)
        self.e = Env(tmp_path, clock=self.clock, radio=False, first_radio=False, settings={} if first is not None and first.enabled else {"fm/enabled": "false"})
        ctl = self.e.ctl
        ctl.messaging.tick_sec = ctl.ownobjects.tick_sec = ctl.ownbulletins.tick_sec = ctl.rigstatus.poll_sec = TICK_SEC
        ctl.messaging.pace.spacing_sec = 0.0
        self.senders: tuple[object, ...] = (ctl.ownobjects, ctl.ownbulletins, ctl.rigstatus)
        for repeater in (ctl.ownobjects, ctl.ownbulletins):
            repeater.tick = self._seen(repeater, repeater.tick)                       # type: ignore[method-assign]
        poll = ctl.rigstatus.poll

        async def polled() -> None:
            await poll()
            TICKED[ctl.rigstatus] = self.clock()
        ctl.rigstatus.poll = polled                                                   # type: ignore[method-assign]
        self.out: list[tuple[datetime, Packet]] = []
        ctl.radio_packet.connect(lambda p: self.out.append((self.clock(), p)) if p.direction == "out" else None)

    def _seen(self, owner: object, tick: Callable[[], bool]) -> Callable[[], bool]:
        def ticked() -> bool:
            sent = tick()
            TICKED[owner] = self.clock()
            return sent
        return ticked

    async def start(self) -> None:
        await self.e.start(connected=False)
        await until_started(lambda: all(r.usable and r.beacon.running for r in self.e.ctl.radios.senders()))

    async def until(self, at: datetime) -> None:
        while self.clock() < at:
            self.clock.advance(60)
            await asyncio.sleep(STEP_WAIT_SEC)
            await until(lambda: all(TICKED.get(r.beacon) == self.clock() for r in self.e.ctl.radios.all() if r.beacon.running) and all(TICKED.get(s) == self.clock() for s in self.senders))

    def frames(self) -> Counter[tuple[int, str]]:
        """Our frames in the four hours from the start, by radio and kind."""
        return Counter((p.radio_id or 0, kind_of(ax25.decode(p.raw))) for at, p in self.out if START <= at < START + timedelta(hours=HOURS) and ax25.decode(p.raw).source.call == ME)


async def the_day(tmp_path: Path, day: Day) -> tuple[Counter[tuple[int, str]], list[str], Running]:
    """The station's data folder of before, the update, and its four hours: the frames by radio and kind, and the codes of the presses that were refused."""
    path = tmp_path / DB_NAME
    object_radios = ",".join(str(r.id) for r in senders_0_20_0(day.old.radios)[:1]) or "1"            # (the object of before, on the first radio that sent: radio 1 where there was none)
    kept = Old(day.old.radios, day.old.chosen, {**STATION_ROWS, **day.old.settings}, {OBJECT: object_radios}, {"BLN1": "net tonight"})
    if day.v26:
        version_twenty_six(path, FixedClock(START), {**STATION_ROWS, "tnc/profile": "dummy", "hf/enabled": "true", "hf/profile": "dummy-hf"})
    else:
        version_33(path, kept, FixedClock(START))
    run = Running(tmp_path, day)
    await run.start()
    if day.v26:                                                                                          # (0.18.2 kept them by its words of a radio: here made as the update starts, on radio 1)
        run.e.ctl.ownobjects.set(OBJECT, "object", 60.2, 24.9, "/", "r", "ours", radios=(1,))
        run.e.ctl.ownbulletins.post("BLN1", "net tonight", (1,))
    if day.added:
        assert await run.e.ctl.add_radio(day.added) is not None
        await until_started(lambda: all(r.usable and r.beacon.running for r in run.e.ctl.radios.senders()))
    refused: list[str] = []
    ctl = run.e.ctl

    async def press(what: Callable[[], object]) -> None:
        try:
            done = what()
            if asyncio.iscoroutine(done):
                await done
        except MessagingError as e:
            refused.append(e.code)
    await run.until(START + timedelta(minutes=1))
    ctl.ownbulletins.post("BLNA", "hamfest saturday")
    await press(lambda: ctl.messaging.send(MAIL, "jane@example.org hello"))
    await press(lambda: ctl.messaging.send(NEW, "hello"))
    await run.until(START + timedelta(minutes=2))
    await press(lambda: ctl.generalask.ask("aprs"))
    await press(lambda: ctl.qruask.ask("INFO"))
    await run.until(START + timedelta(hours=HOURS, minutes=1))
    return run.frames(), refused, run


def counted(thing: str, radio: Radio, on: tuple[Radio, ...]) -> int:
    """How many frames of the thing a radio sends in the four hours, by today's rules: those the update does not change (the beacon at 30 minutes on every kind, an object's decay and its round at the
    slowest floor of its radios, a press, a mail's two attempts and a message's four), and the floor of the status and of a bulletin's repeats."""
    slow = radio.kind in SLOW
    if thing == "object":
        return 12 if any(r.kind in SLOW for r in on) else 16                         # (0, 1, 3, 7, 15, 31, then every 20 minutes by its path, or every 30 on a slow radio: on all of its radios alike)
    return {"beacon": 8, "status": NEW_STATUS_SLOW if slow else OLD_STATUS, "bulletin": NEW_BULLETIN_SLOW if slow else OLD_BULLETIN, "announcement": ANNOUNCEMENT, "query": PRESS, "info": PRESS,
            "mail": 2, "new": 4}[thing]


@pytest.mark.parametrize("day", [*STATIONS, G], ids=lambda day: day.name)
async def test_the_update_sends_what_0_20_0_sent_on_every_radio_but_the_floor_and_the_mail_of_a_station_without_fm_or_lora(tmp_path: Path, quick: None, day: Day) -> None:
    frames, refused, run = await the_day(tmp_path, day)
    try:
        radios = (*day.old.radios, *((lora(len(day.old.radios) + 1),) if day.added else ()))         # (the radio added the day after, as 0.20.0 would have taken it: last, its beacon ticked)
        first = senders_0_20_0(day.old.radios)[:1]
        sets = oracle(radios, day.old.chosen, (first[0].id,) if first else (1,))
        if day.v26:
            sets["object"] = sets["bulletin"]                                                             # (0.18.2's object was set on radio 1 by its word fm, which the update read: as the bulletin)
        by_id = {r.id: r for r in radios}
        expected = Counter({(id, thing): counted(thing, by_id[id], tuple(by_id[i] for i in ids)) for thing, ids in sets.items() for id in ids})
        main = main_radio_0_20_0(radios, day.old.chosen)
        if not sets["mail"] and main is not None:                                                         # (the second exception: 0.20.0 refused the mail of a station with no FM or LoRa radio on)
            assert by_id[main].kind == "hf" and all(r.kind == "hf" for r in senders_0_20_0(radios))
            expected[(main, "mail")] = 2
        assert frames == expected, day.name
        for (id, thing), count in frames.items():
            if thing in ("status", "bulletin") and by_id[id].kind in SLOW:                               # (the first exception, by its own numbers: 0.20.0 sent 16 status reports and 14 bulletins there)
                assert (count, OLD_STATUS if thing == "status" else OLD_BULLETIN) == ((NEW_STATUS_SLOW, 16) if thing == "status" else (NEW_BULLETIN_SLOW, 14)), (day.name, id, thing)
        assert refused == ([] if main is not None else ["radio.none"] * 4), "with no radio that can send on, the mail, the message and both Asks are refused, as in 0.20.0"
        assert not any(by_id[id].type == "tnc-text" or by_id[id].removed or not by_id[id].enabled for id, _ in frames), "never a frame on a radio that only receives, is off or removed"
    finally:
        await run.e.stop()


async def test_a_bulletin_ticked_for_fm_and_hf_repeats_every_30_minutes_on_both_and_one_on_fm_alone_every_20(tmp_path: Path, quick: None) -> None:
    """A bulletin's own radios (the Post box's ticks, `bulletin_post` with `radios`), its round on all of them as an object's, and the floor of the slowest: 10 frames on each of FM and Mercury in four
    hours, 14 on FM alone; an announcement 6 on each in four hours (74 in its 72: tests/test_sendonrule.py)."""
    day = Day("b", Old((fm(1), hf(2))))
    version_33(tmp_path / DB_NAME, Old(day.old.radios, None, STATION_ROWS), FixedClock(START))
    run = Running(tmp_path, day)
    await run.start()
    try:
        ctl = run.e.ctl
        ctl.ownbulletins.post("BLN1", "net on both", (1, 2))
        ctl.ownbulletins.post("BLNA", "hamfest", (1, 2))
        assert ctl.ownbulletins.new_radios() == (1, 2), "a new bulletin starts with the radios of the one posted last"
        await run.until(START + timedelta(hours=HOURS, minutes=1))
        frames = run.frames()
        assert {key: frames[key] for key in frames if key[1] in ("bulletin", "announcement")} == {(1, "bulletin"): 10, (2, "bulletin"): 10, (1, "announcement"): 6, (2, "announcement"): 6}
        assert [p.radio_id for _, p in run.out if b":BLN1" in p.raw][:2] == [1, 2] or [p.radio_id for _, p in run.out if b":BLN1" in p.raw][:2] == [2, 1], "the round: one on each"
    finally:
        await run.e.stop()


async def test_a_radio_switched_off_and_on_again_after_the_update_takes_the_mail_back_and_no_status_goes_out_early(tmp_path: Path, quick: None) -> None:
    """Station b the day after: FM switched off for an hour carries nothing, HF carries it all, and once FM is on again the mail goes on FM, as 0.20.0 sent it (the step stored the e-mail radio; without
    it the radio left on would be written when FM comes back). HF's first status while it stands in comes at its next interval, from the station's latest report, not at once."""
    day = Day("b", Old((fm(1), hf(2))))
    version_33(tmp_path / DB_NAME, Old(day.old.radios, None, STATION_ROWS, {OBJECT: "1"}, {"BLN1": "net tonight"}), FixedClock(START))
    run = Running(tmp_path, day)
    await run.start()
    try:
        ctl = run.e.ctl
        await run.until(START + timedelta(minutes=30))
        assert await ctl.change_radio(1, enabled=False)
        await run.until(START + timedelta(minutes=90))
        assert await ctl.change_radio(1, enabled=True)
        await until_started(lambda: all(r.usable and r.beacon.running for r in ctl.radios.senders()))
        await run.until(START + timedelta(minutes=91))
        await ctl.messaging.send(MAIL, "jane@example.org hello")
        await run.until(START + timedelta(minutes=100))
        sent = [(int((at - START).total_seconds() // 60), p.radio_id, kind_of(ax25.decode(p.raw))) for at, p in run.out if ax25.decode(p.raw).source.call == ME]
        assert [(minute, radio) for minute, radio, kind in sent if kind == "mail"] == [(91, 1), (92, 1)], "the mail on FM, where 0.20.0 sent it"
        assert [minute for minute, radio, kind in sent if kind == "status" and radio == 2 and minute < 90] == [60], "HF stands in at its next interval: 30 minutes after FM's latest report"
    finally:
        await run.e.stop()
