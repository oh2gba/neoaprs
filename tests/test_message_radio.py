"""The radio a message to a station goes out on while both radios are on (neoaprs/radios.py: `for_station`, `choose`, the state row MESSAGE_RADIOS), the pause before a retry on HF (message.retry_pause:
two stations that collided must not retry at the same moment again), and a station whose position takes no messages can still be written to (`may_not_message`). John and OH2GAX, 4 Nov 2026.

Messaging takes that radio from the station's radios as the registry gives them (services/radioset.py RadioPick, here tests/test_messaging.py `StubPick` with radio 1 and radio 2 on stub lines): the first
attempt asks `for_station` and records the id of the radio it went on, and the message keeps that radio until it ends (rule 3.2, services/messageradio.py), though the station is heard on another meanwhile,
also after a restart; the operator's choice of another radio for the station, or its radio switched off, gives it the station's radio of now, and one that radio cannot carry fails with the reason and no
attempt used. The pause before a retry is the radio's own (`limits`), an ack goes back on the radio the message came on (`for_packet`) and waits for it by its id, an email goes on the email radio (`email`)
and is refused while there is none, and with no radio at all a message is refused, a message that comes gets no ack and an answer is not given, and the log says so."""
import json
import logging
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from neoaprs.clock import utc
from neoaprs.config import DEFAULTS, MESSAGE_RADIOS
from neoaprs.message import EMAIL_GATEWAY, FIRST_WAIT_SEC, MessageRecord, MessagingError, due_at, retry_pause
from neoaprs.messagelog import MessageLog
from neoaprs.radiorules import FM
from neoaprs.radiospec import RadioHeard
from neoaprs.radiotype import FM_ID, HF_ID
from neoaprs.radiotypes.common import FM_LIMITS, HF_LIMITS
from neoaprs.packet import Message, Packet
from neoaprs.radios import Radios
from neoaprs.services.answers import Answers, as_pick
from neoaprs.services.messaging import Messaging
from neoaprs.station import Station
from neoaprs.stationbook import StationBook
from tests.support.air import on_air
from tests.support.env import remember_stop
from tests.support.fakedriver import Rig as AirRig
from tests.support.stubtnc import StubRadios
from tests.support.storedb import log_at
from tests.support.stubtnc import StubTnc
from tests.test_messaging import TICK, LineAir, Rig, with_hf
from tests.test_web import with_page

T0 = utc(2026, 11, 4, 7, 30)
BOTH = replace(DEFAULTS, fm_enabled=True, hf_enabled=True)


class Kept:
    """A Memory: the rows written."""
    def __init__(self) -> None:
        self.rows: dict[str, str] = {}

    async def setting(self, key: str) -> str | None:
        return self.rows.get(key)

    async def put_settings(self, data: dict[str, str]) -> bool:
        self.rows.update(data)
        return True


def station(call: str, fm: int = 0, hf: int = 0, **values: Any) -> Station:
    return Station(call, first_heard=T0, last_heard=T0, heard_fm=fm, heard_hf=hf, **values)


def radios(memory: Kept | None = None, config: Any = BOTH) -> tuple[Radios, StationBook, object, object]:
    book, fm, hf = StationBook(), object(), object()
    book.seed([station("OH2GAX-2", fm=40, hf=21), station("OH2FAR", hf=3), station("OH2NEAR", fm=5)])
    remember = (lambda text: memory.rows.update({MESSAGE_RADIOS: text})) if memory is not None else (lambda text: None)
    return Radios(fm, hf, lambda: config, book, remember), book, fm, hf          # type: ignore[arg-type]  # what is chosen is all that is asked of a radio here


async def test_a_station_heard_on_both_radios_goes_on_fm_until_the_operator_chooses_hf_and_the_choice_is_kept() -> None:
    kept = Kept()
    r, book, fm, hf = radios(kept)
    changed: list[str] = []
    book.changed.connect(lambda s: changed.append(f"{s.call}:{s.message_radio}"))
    assert r.for_station("OH2GAX-2") is fm and r.for_station("OH2FAR") is hf and r.for_station("OH2NEAR") is fm, "the daemon's choice: FM unless heard on HF alone"
    assert r.choose("OH2GAX-2", "hf") and r.for_station("OH2GAX-2") is hf and changed == ["OH2GAX-2:hf"], "the page hears of it with the station"
    assert r.choose("OH2NEAR", "hf") and r.choose("OH2FAR", "fm") and r.for_station("OH2FAR") is fm
    await r.flush()
    assert json.loads(kept.rows[MESSAGE_RADIOS]) == {"OH2FAR": "fm", "OH2GAX-2": "hf", "OH2NEAR": "hf"}
    assert r.choose("OH2NEAR", "") and r.for_station("OH2NEAR") is fm, "an empty choice gives it back to the daemon"
    assert not r.choose("OH2GAX-2", "lora") and r.choice("OH2GAX-2") == HF_ID, "an unknown radio is no choice"
    assert r.choose("OH2NOBODY", "hf") and r.choice("OH2NOBODY") == HF_ID and book.get("OH2NOBODY") is None, "a call the book does not hold keeps its choice by call (plan rule 3.2)"

    again, book2, fm2, hf2 = radios()
    again.restore(kept.rows[MESSAGE_RADIOS])
    assert again.for_station("OH2GAX-2") is hf2 and again.for_station("OH2FAR") is fm2, "after a restart"
    again.restore("not json") or again.restore('{"OH2GAX-2": "lora"}')
    assert book2.get("OH2GAX-2").message_radio == "hf"                     # type: ignore[union-attr]


def test_with_one_radio_on_the_choice_is_not_asked() -> None:
    r, _, fm, _ = radios(config=replace(DEFAULTS, fm_enabled=True, hf_enabled=False))
    assert r.choose("OH2GAX-2", "hf") and r.for_station("OH2GAX-2") is fm, "the choice waits for both radios to be on"


def message(attempts: int, to: str = "OH2GAX-2", number: int = 556) -> MessageRecord:
    return MessageRecord(number, T0, "out", "OH2GBA", to, "going down 5W", "DN", "sending", attempts=attempts, last_attempt_at=T0 if attempts else None)


def test_a_retry_on_hf_waits_a_pause_of_its_own_and_one_on_fm_none() -> None:
    hf = HF_LIMITS.retry_jitter_sec                                       # (the pause of the radio's type: what messaging reads of the radio a message goes on)
    assert retry_pause(message(0), hf) == timedelta(0), "the first attempt goes at once"
    assert retry_pause(message(4), hf) == timedelta(0), "after the last attempt only the answer is waited for"
    assert retry_pause(message(1), FM_LIMITS.retry_jitter_sec) == timedelta(0) and FM_LIMITS.retry_jitter_sec == 0
    pause = retry_pause(message(1), hf)
    assert timedelta(0) <= pause <= timedelta(seconds=hf) and retry_pause(message(1), hf) == pause, "the same every time it is asked"
    assert due_at(message(1)) == T0 + timedelta(seconds=FIRST_WAIT_SEC)
    ours = [retry_pause(message(n), hf) for n in (1, 2, 3)]
    theirs = [retry_pause(message(n, to="OH2GBA", number=36), hf) for n in (1, 2, 3)]
    assert ours != theirs, "the two stations of a collision pause differently"
    spread = {round(retry_pause(message(1, number=n), hf).total_seconds()) for n in range(200)}
    assert len(spread) > 15, "the pauses cover the range"


def test_a_station_whose_position_takes_no_messages_can_be_written_to_and_is_marked() -> None:
    plain = station("OH2PLN", fm=1, position_messaging=False)
    assert plain.can_message and plain.may_not_message
    talker = station("OH2TLK", fm=1, position_messaging=False, sent_message=True)
    assert talker.can_message and not talker.may_not_message, "a station that sent a message does messages"
    assert not station("OH2ANY", fm=1).may_not_message and not station("FIRE", fm=1, kind="object").can_message


async def test_the_page_chooses_the_radio_of_a_station_and_its_row_says_it(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path, settings={"hf/enabled": "true", "hf/profile": "dummy-hf"})
    e.feed(on_air("OH2GAX-2", b"=6015.42N/02447.93E-Otso"))
    await page.until(lambda: "OH2GAX-2" in page.topics["stations"])
    assert page.topics["stations"]["OH2GAX-2"]["radio_choice"] is None
    await page.send({"cmd": "station_radio", "call": "OH2GAX-2", "radio": 2})
    await page.until(lambda: page.topics["stations"]["OH2GAX-2"]["radio_choice"] == 2)
    await page.send({"cmd": "station_radio", "call": "OH2GAX-2", "radio": 9})
    error = await page.expect("error")
    assert error["code"] == "radio.unknown"


def test_a_station_the_book_lets_go_takes_its_radio_along_and_a_restart_does_not_bring_it_back() -> None:
    kept = Kept()
    r, book, fm, _ = radios(kept)
    book.removed.connect(r.forget)                                       # (as wiring.py connects them)
    book.cleared.connect(r.forget_all)
    assert r.choose("OH2GAX-2", "hf") and r.choose("OH2FAR", "fm")
    assert book.forget("OH2GAX-2"), "the operator forgets the station (Forget on its card)"
    book.seed([station("OH2GAX-2", fm=1)])                                 # heard again: no choice, messaged on FM
    assert r.for_station("OH2GAX-2") is fm and json.loads(kept.rows[MESSAGE_RADIOS]) == {"OH2FAR": "fm"}
    again, book2, _, _ = radios()                                        # the daemon restarted
    again.restore(kept.rows[MESSAGE_RADIOS])
    assert book2.get("OH2GAX-2").message_radio == "" and book2.get("OH2FAR").message_radio == "fm"      # type: ignore[union-attr]
    book.forget_all()
    assert json.loads(kept.rows[MESSAGE_RADIOS]) == {}, "Forget all forgets the choices too"


# ---- messaging on the radios by id (services/radioset.py RadioPick)

async def on_two(tmp_path: Path, **changes: Any) -> Rig:
    """Messaging on radio 1 (the rig's stub line) and radio 2 (an HF line of its own), OH2FAR heard on HF alone."""
    log, _, clock = await log_at(tmp_path, MessageLog)
    rig = Rig(log, clock, **{"hf_enabled": True, **changes})
    with_hf(rig, rig.radios)
    rig.radios.hf_stations = ("OH2FAR",)
    await rig.start()
    return rig


def radio_ids(rig: Rig, number: int) -> list[int | None]:
    return [attempt.radio_id for attempt in rig.m.delivery.attempts_of(number)]


async def test_each_attempt_goes_on_the_radio_the_station_is_reached_on_now_and_records_its_id(tmp_path: Path) -> None:
    rig = await on_two(tmp_path)
    hf = rig.radios.lines[HF_ID]
    near = await rig.m.send("OH2NEAR", "on fm")
    far = await rig.m.send("OH2FAR", "over hf")
    assert rig.tnc.lines() == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2NEAR  :on fm{01}"] and hf.lines() == ["OH2GBA>APZNEO::OH2FAR   :over hf{02}"], "each on its station's radio, built for it: no path on HF"
    assert radio_ids(rig, near.id) == [FM_ID] and radio_ids(rig, far.id) == [HF_ID]
    held = rig.m.get(far.id)
    assert held is not None and rig.m.retries._due[far.id] == held.at + timedelta(seconds=32) + retry_pause(held, HF_LIMITS.retry_jitter_sec), "the pause before its retry is the HF radio's"
    rig.radios.chosen["OH2FAR"] = FM_ID                                    # (the operator chooses the FM radio for the station: the next attempt goes on the station's radio of now)
    await rig.pass_time(55)
    assert radio_ids(rig, far.id) == [HF_ID, FM_ID] and radio_ids(rig, near.id) == [FM_ID, FM_ID] and len(hf.sent) == 1
    assert [attempt.radio for attempt in rig.m.delivery.attempts_of(far.id)] == ["hf", "fm"], "kept as the word of the radio's slot until the attempts keep the id"


async def test_an_ack_goes_back_on_the_radio_the_message_came_on_and_waits_for_it_by_its_id(tmp_path: Path) -> None:
    rig = await on_two(tmp_path)
    hf = rig.radios.lines[HF_ID]
    hf.held = "the channel is busy"
    rig.m.on_packet(replace(rig.heard("OH2NEAR", "OH2GBA", "over hf", "7"), radio="hf"))             # (a station near on FM, but this message came over HF)
    await rig.settled()
    assert [(ack.to, ack.radio) for ack in rig.m.acks.waiting] == [("OH2NEAR", HF_ID)] and rig.tnc.sent == [], "it waits for the HF radio, not sent on FM"
    hf.held = ""
    await rig.pass_time(1)
    assert hf.lines() == ["OH2GBA>APZNEO::OH2NEAR  :ack7"] and rig.m.acks.waiting == [] and rig.tnc.sent == []


async def test_an_email_goes_on_the_email_radio_and_is_refused_while_there_is_none_and_with_no_radio_a_message_is_refused(tmp_path: Path) -> None:
    rig = await on_two(tmp_path)
    rig.radios.hf_stations = ("OH2FAR", EMAIL_GATEWAY)
    await rig.m.send(EMAIL_GATEWAY, "oh2gba@example.org hello")
    assert len(rig.tnc.sent) == 1 and rig.radios.lines[HF_ID].sent == [], "on radio 1, whatever the station's choice"
    rig.radios.on.discard(FM_ID)                                          # (radio 1 off)
    with pytest.raises(MessagingError) as refused:
        await rig.m.send(EMAIL_GATEWAY, "oh2gba@example.org again")
    assert refused.value.code == "message.email_fm_off"
    await rig.m.send("OH2NEAR", "on the one radio there is")
    assert len(rig.radios.lines[HF_ID].sent) == 1, "the main radio is the HF one"
    rig.radios.on.discard(HF_ID)                                          # (no radio at all: what the settings refuse, and a fresh installation of the round)
    with pytest.raises(MessagingError, match="there is no radio"):
        await rig.m.send("OH2NEAR", "nowhere")



async def test_with_no_radio_at_all_a_message_that_comes_gets_no_ack_and_an_answer_is_not_given_and_the_log_says_why(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    rig = await on_two(tmp_path)
    rig.radios.on.clear()                                                 # (no radio at all: what the settings refuse, and a fresh installation of the round)
    rig.m.on_packet(rig.heard("OH2NEAR", "OH2GBA", "hello", "7"))
    await rig.settled()
    assert rig.tnc.sent == [] and rig.radios.lines[HF_ID].sent == [] and rig.m.acks.waiting == []
    assert any(r.getMessage() == "no ack for message 7 from OH2NEAR: there is no radio" for r in caplog.records)
    answers = Answers(rig.radios, lambda: rig.config, lambda call, attempt=None, radio=1: ())
    assert not answers.deliver("OH2NEAR", "position", [answers.message("OH2NEAR", "an answer")], rig.clock(), False)
    assert any(r.getMessage() == "a query of OH2NEAR is not answered: there is no radio" for r in caplog.records)
    assert rig.tnc.sent == [] and rig.radios.lines[HF_ID].sent == []

def test_what_the_services_are_given_until_the_registry_is_read_as_a_radio_pick_with_the_same_choices() -> None:
    old = StubRadios(hf_stations=("OH2C",))                               # (the old set of two of before the round, which a test may still give)
    pick = as_pick(old, lambda: BOTH)
    hf_packet = Packet(T0, "in", b"", "OH2C", "APRS", (), b"", Message("OH2GBA", "over hf", None), None, "rf", "hf")
    assert [(r.id, r.kind, r.name) for r in pick.enabled()] == [(FM_ID, "fm", "FM"), (HF_ID, "hf", "HF")]
    assert [r.radio for r in (pick.main, pick.for_station("OH2C"), pick.for_station("OH2B"), pick.for_packet(hf_packet), pick.email(), pick.get(HF_ID))] == [old, old.hf, old.fm, old.hf, old.fm, old.hf]  # type: ignore[union-attr, attr-defined]
    assert pick.get(HF_ID).limits == HF_LIMITS and not pick.get(HF_ID).allowed.paths and pick.get(FM_ID).allowed.paths and pick.get(3) is None      # type: ignore[union-attr]
    old.enabled = {"hf"}
    assert pick.email() is None and pick.get(FM_ID) is None and pick.main.id == HF_ID and pick.for_station("OH2B").radio is old.hf, "the FM radio off"     # type: ignore[union-attr, attr-defined]
    one = as_pick(old.hf, lambda: BOTH)                                    # (one plain radio, a test's stub: every choice)
    assert all(r is not None and r.radio is old.hf for r in (one.main, one.for_station("OH2B"), one.get(HF_ID))) and one.get(FM_ID) is None and one.email() is None     # type: ignore[union-attr, attr-defined]
    assert as_pick(pick, lambda: BOTH) is pick, "a RadioPick is taken as it is"


# ---- a message keeps the radio of its first attempt (rule 3.2)

async def test_a_message_keeps_the_radio_of_its_first_attempt_though_the_station_is_heard_on_another_meanwhile(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    rig = await on_two(tmp_path)
    hf = rig.radios.lines[HF_ID]
    near = await rig.m.send("OH2NEAR", "on fm")
    far = await rig.m.send("OH2FAR", "over hf")
    rig.radios.hf_stations = ("OH2NEAR",)                                   # (heard over HF now, and the FM radio no longer hears OH2FAR: the rule would choose the other radio for each)
    await rig.pass_time(55)                                                 # (the second attempts: 32 s, and the HF radio's pause)
    assert radio_ids(rig, near.id) == [FM_ID, FM_ID] and radio_ids(rig, far.id) == [HF_ID, HF_ID], "each attempt on the radio of the first"
    assert len(hf.sent) == 2 and len(rig.tnc.sent) == 2
    assert not any("goes on the radio the station is reached on now" in r.getMessage() for r in caplog.records)
    newer = await rig.m.send("OH2NEAR", "a new one", once=True)
    assert radio_ids(rig, newer.id) == [HF_ID], "a new message asks the rule"


async def test_the_operator_choosing_a_radio_moves_a_message_on_its_way_and_it_keeps_the_new_one(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    rig = await on_two(tmp_path)
    rig.radios.chosen["OH2NEAR"] = HF_ID
    record = await rig.m.send("OH2NEAR", "chosen hf")
    del rig.radios.chosen["OH2NEAR"]                                        # (Route back to automatic: the rule says FM)
    await rig.pass_time(55)
    assert radio_ids(rig, record.id) == [HF_ID, FM_ID]
    assert any(r.getMessage() == f"message {record.id} to OH2NEAR goes on the radio the station is reached on now: no radio is chosen for the station any more" for r in caplog.records), "true also of a station forgotten"
    rig.radios.hf_stations = ("OH2NEAR",)                                   # (the rule would say HF now: it keeps the one it was given)
    await rig.pass_time(90)
    assert radio_ids(rig, record.id) == [HF_ID, FM_ID, FM_ID]


async def test_a_chosen_radio_that_was_off_takes_the_message_when_it_is_switched_on(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    rig = await on_two(tmp_path)
    rig.radios.chosen["OH2NEAR"] = HF_ID                                    # (Route HF, while the HF radio is off: the message goes on FM)
    rig.radios.on.discard(HF_ID)
    record = await rig.m.send("OH2NEAR", "chosen hf")
    rig.radios.on.add(HF_ID)                                                # (the choice is in force again: the radio the operator chose)
    await rig.pass_time(55)
    assert radio_ids(rig, record.id) == [FM_ID, HF_ID]
    assert any(r.getMessage() == f"message {record.id} to OH2NEAR goes on the radio the station is reached on now: the radio chosen for the station applies now" for r in caplog.records)
    await rig.pass_time(90)
    assert radio_ids(rig, record.id) == [FM_ID, HF_ID, HF_ID], "and it keeps it"


async def test_a_message_whose_radio_is_switched_off_goes_on_the_stations_radio_of_now_and_stays_there(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    rig = await on_two(tmp_path)
    record = await rig.m.send("OH2FAR", "over hf")
    rig.radios.on.discard(HF_ID)                                            # (the HF radio switched off)
    await rig.pass_time(55)
    assert radio_ids(rig, record.id) == [HF_ID, FM_ID]
    assert any(r.getMessage() == f"message {record.id} to OH2FAR goes on the radio the station is reached on now: the radio it went out on is off" for r in caplog.records)
    rig.radios.on.add(HF_ID)                                                # (back on: the message keeps the radio it was given; the rig's double has no station book)
    await rig.pass_time(90)
    assert radio_ids(rig, record.id) == [HF_ID, FM_ID, FM_ID]


async def test_a_message_its_new_radio_cannot_carry_fails_with_the_reason_and_uses_no_attempt(tmp_path: Path) -> None:
    log, _, clock = await log_at(tmp_path, MessageLog)
    rig = Rig(log, clock, hf_enabled=True)
    rig.radios.radios.append(LineAir(StubTnc(max_frame=60), lambda: rig.config))    # (radio 2 with a frame of 60 bytes)
    rig.radios.on.add(HF_ID)
    await rig.start()
    text = "a message of fifty characters that HF cannot carry"
    record = await rig.m.send("OH2FAR", text)
    assert radio_ids(rig, record.id) == [FM_ID]
    rig.radios.chosen["OH2FAR"] = HF_ID                                    # (the operator chooses the HF radio for the station)
    await rig.pass_time(55)
    failed = rig.state(record.id)
    assert (failed.state, failed.failure, failed.attempts, radio_ids(rig, record.id)) == ("failed", "too_long_for_radio", 1, [FM_ID]), "nothing more went on the air"


async def test_after_a_restart_a_message_being_sent_keeps_the_radio_its_first_attempt_went_on(tmp_path: Path) -> None:
    rig = await on_two(tmp_path)
    record = await rig.m.send("OH2FAR", "over hf")
    await rig.settled()
    await rig.m.stop()
    again = Rig(rig.log, rig.clock, rig.tnc, hf_enabled=True)              # (the daemon restarted: OH2FAR no longer heard on HF alone, the rule says FM)
    hf = with_hf(again, again.radios)
    await again.start()
    await again.pass_time(55)
    assert [a.radio_id for a in again.m.delivery.attempts_of(record.id)] == [HF_ID, HF_ID] and len(hf.sent) == 1, "the second attempt on HF, as the first"


async def restarted(rig: Rig, **chosen: int) -> tuple[Rig, StubTnc]:
    """The daemon of `rig` stopped and started again on the same database, with the operator's choices `chosen` (kept in the settings across it): the new rig, and its HF line."""
    await rig.settled()
    await rig.m.stop()
    again = Rig(rig.log, rig.clock, rig.tnc, hf_enabled=True)
    hf = with_hf(again, again.radios)
    again.radios.chosen.update(chosen)
    await again.start()
    return again, hf


async def test_after_a_restart_a_message_the_operator_moved_stays_on_the_radio_chosen(tmp_path: Path) -> None:
    rig = await on_two(tmp_path)
    record = await rig.m.send("OH2NEAR", "on fm")
    rig.radios.chosen["OH2NEAR"] = HF_ID                                    # (the operator sets Route HF after the first attempt)
    await rig.pass_time(55)
    assert radio_ids(rig, record.id) == [FM_ID, HF_ID]
    again, hf = await restarted(rig, OH2NEAR=HF_ID)
    await again.pass_time(90)
    assert radio_ids(again, record.id) == [FM_ID, HF_ID, HF_ID] and len(hf.sent) == 1, "not back on the radio of the first attempt"


async def test_a_choice_made_before_a_restart_moves_the_message_at_its_next_attempt(tmp_path: Path) -> None:
    rig = await on_two(tmp_path)
    record = await rig.m.send("OH2NEAR", "on fm")
    rig.radios.chosen["OH2NEAR"] = HF_ID                                    # (Route HF, and the daemon restarts before the second attempt)
    again, hf = await restarted(rig, OH2NEAR=HF_ID)
    await again.pass_time(55)
    assert radio_ids(again, record.id) == [FM_ID, HF_ID] and len(hf.sent) == 1


async def test_after_a_restart_a_message_moved_off_its_radio_keeps_the_one_it_was_moved_to(tmp_path: Path) -> None:
    rig = await on_two(tmp_path)
    record = await rig.m.send("OH2FAR", "over hf")
    rig.radios.on.discard(HF_ID)                                            # (the HF radio switched off: the second attempt on FM)
    await rig.pass_time(55)
    assert radio_ids(rig, record.id) == [HF_ID, FM_ID]
    again, hf = await restarted(rig)                                        # (HF on again after the restart, OH2FAR heard on HF alone: it stays where it went; the rig's double has no station book)
    again.radios.hf_stations = ("OH2FAR",)
    await again.pass_time(90)
    assert radio_ids(again, record.id) == [HF_ID, FM_ID, FM_ID] and hf.sent == []



async def test_the_path_of_a_frame_is_asked_for_the_radio_it_goes_out_on(tmp_path: Path) -> None:
    """The station's path on the radio of the frame (services/prefbook.py `path_for(call, attempt, radio_id)`): a message on HF asks for HF's, its ack on the radio the message came on."""
    rig = await on_two(tmp_path)
    asked: list[tuple[str, int | None, int]] = []
    given = rig.m._paths
    rig.m._paths = lambda call, attempt, radio: asked.append((call, attempt, radio)) or given(call, attempt, radio)
    await rig.m.send("OH2FAR", "over hf")
    await rig.m.send("OH2NEAR", "on fm")
    rig.m.on_packet(replace(rig.heard("OH2NEAR", "OH2GBA", "over hf", "7"), radio="hf"))
    await rig.settled()
    assert asked == [("OH2FAR", None, HF_ID), ("OH2FAR", 1, HF_ID), ("OH2NEAR", None, FM_ID), ("OH2NEAR", 1, FM_ID), ("OH2NEAR", None, HF_ID)], "the check of the text, the first attempt, the ack"


# ---- a radio that only stood in for the station's own is left when that is on again (R2b)

async def over_the_registry(tmp_path: Path, **heard: dict[int, int]) -> tuple[Rig, AirRig]:
    """Messaging over the registry itself (neoaprs/radioregistry.py, on fake drivers: tests/support/fakedriver.py) with its station book and the real rule: FM radio 1 and HF radio 2, both on; each
    station of `heard` heard by the radios named, as {radio id: packets}, now."""
    log, _, clock = await log_at(tmp_path, MessageLog)
    rig = Rig(log, clock, hf_enabled=True)
    air = AirRig(rig.config, clock)
    air.registry.sync(air.config)
    for driver in air.drivers.values():
        await driver.start()
    seen(air, **heard)
    rig.m = on_registry(rig, air)
    await rig.start()
    return rig, air


def on_registry(rig: Rig, air: AirRig) -> Messaging:
    m = Messaging(air.registry, lambda: air.config, rig.log, rig.prefs.path_for, rig.clock, tick_sec=TICK)
    remember_stop(m.stop)
    return m


def seen(air: AirRig, **heard: dict[int, int]) -> None:
    """The stations heard now, each by the radios named ({radio id: packets})."""
    now = air.clock()
    air.book.seed([Station(call, first_heard=now, last_heard=now, heard_by={id: RadioHeard(count, now) for id, count in by.items()}) for call, by in heard.items()])


def switch(air: AirRig, **on: bool) -> None:
    """A save that switches the FM radio (`fm`) or the HF radio (`hf`) on or off."""
    air.put(replace(air.config, **{f"{kind}_enabled": value for kind, value in on.items()}))


async def all_attempts(rig: Rig, number: int) -> list[int | None]:
    """The clock moved on in steps until the message has had its four attempts: the radio of each."""
    for _ in range(60):
        if len(radio_ids(rig, number)) == 4:
            break
        await rig.pass_time(15)
    return radio_ids(rig, number)


async def registry_restarted(rig: Rig, air: AirRig) -> Rig:
    """The daemon stopped and started again on the same database, the registry and the station book as they were (what the book is seeded with at a start)."""
    await rig.settled()
    await rig.m.stop()
    again = Rig(rig.log, rig.clock, rig.tnc, hf_enabled=True)
    again.m = on_registry(again, air)
    await again.start()
    return again


async def test_a_message_that_went_over_hf_while_fm_was_off_goes_on_fm_when_it_is_on_again_and_stays(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """The integration's story with the real daemon (I3 A1): OH2NR heard on FM alone, the FM radio off when the message is written, so its first attempt goes over HF, the only radio on; HF never heard
    the station. When FM is on again the retries go on FM, not three times over a shared HF channel to a station HF cannot reach."""
    caplog.set_level(logging.INFO)
    rig, air = await over_the_registry(tmp_path, OH2NR={FM_ID: 5})
    switch(air, fm=False)
    record = await rig.m.send("OH2NR", "while fm is off")
    assert radio_ids(rig, record.id) == [HF_ID]
    switch(air, fm=True)
    assert await all_attempts(rig, record.id) == [HF_ID, FM_ID, FM_ID, FM_ID]
    assert [r.getMessage() for r in caplog.records if "goes on the radio the station is reached on now" in r.getMessage()] == [
        f"message {record.id} to OH2NR goes on the radio the station is reached on now: a radio that heard the station is on now"], "said once"


async def test_the_radio_that_stood_in_is_left_after_a_restart_too(tmp_path: Path) -> None:
    """The same with the daemon restarted between the first attempt and FM coming on again: nothing new is stored; the attempts and what each radio heard tell that HF only stood in."""
    rig, air = await over_the_registry(tmp_path, OH2NR={FM_ID: 5})
    switch(air, fm=False)
    record = await rig.m.send("OH2NR", "while fm is off")
    again = await registry_restarted(rig, air)
    await again.pass_time(15)
    switch(air, fm=True)
    assert await all_attempts(again, record.id) == [HF_ID, FM_ID, FM_ID, FM_ID]


async def test_a_message_over_hf_to_a_station_hf_heard_too_keeps_hf_when_fm_is_on_again(tmp_path: Path) -> None:
    """HF heard the station as well: it was the rule's choice while FM was off, and the message keeps it (as before R2b), across a restart too."""
    rig, air = await over_the_registry(tmp_path, OH2BOTH={FM_ID: 5, HF_ID: 1})
    switch(air, fm=False)
    record = await rig.m.send("OH2BOTH", "while fm is off")
    switch(air, fm=True)
    await rig.pass_time(55)
    again = await registry_restarted(rig, air)
    assert await all_attempts(again, record.id) == [HF_ID, HF_ID, HF_ID, HF_ID]


async def test_a_message_the_operator_routed_over_hf_keeps_hf_though_hf_never_heard_the_station(tmp_path: Path) -> None:
    """Route HF for a station FM alone heard: the operator's choice is no stand-in, FM off or on."""
    rig, air = await over_the_registry(tmp_path, OH2NR={FM_ID: 5})
    assert air.registry.choose("OH2NR", HF_ID)
    switch(air, fm=False)
    record = await rig.m.send("OH2NR", "routed over hf")
    switch(air, fm=True)
    await rig.pass_time(55)
    again = await registry_restarted(rig, air)
    assert await all_attempts(again, record.id) == [HF_ID, HF_ID, HF_ID, HF_ID]


@pytest.mark.parametrize("restart", [False, True], ids=["running", "restarted"])
async def test_a_message_to_a_station_never_heard_keeps_the_main_radio_when_another_is_switched_on_and_hears_it(tmp_path: Path, restart: bool) -> None:
    """A station no radio had heard goes on the main radio, which is the rule's choice and kept: the FM radio switched on (the main radio now) and hearing the station after the first attempt does not
    move it, and after a restart the station's first packet, later than the attempt, tells the same."""
    rig, air = await over_the_registry(tmp_path)
    switch(air, fm=False)
    record = await rig.m.send("OH2NEW", "never heard")
    switch(air, fm=True)
    await rig.pass_time(5)
    seen(air, OH2NEW={FM_ID: 2})
    assert air.registry.for_station("OH2NEW").id == FM_ID, "the rule would say FM now"
    m = await registry_restarted(rig, air) if restart else rig
    assert await all_attempts(m, record.id) == [HF_ID, HF_ID, HF_ID, HF_ID]


async def test_the_radio_that_stood_in_is_left_when_fm_comes_on_in_the_tick_a_retry_is_due(tmp_path: Path) -> None:
    rig, air = await over_the_registry(tmp_path, OH2NR={FM_ID: 5})
    switch(air, fm=False)
    record = await rig.m.send("OH2NR", "while fm is off")
    await rig.pass_time(20)
    held = rig.m.retries._due[record.id]
    rig.clock.advance((held - rig.clock()).total_seconds())                # (the second attempt due now, and FM switched on before the ticker looks)
    switch(air, fm=True)
    await rig.pass_time(0)
    assert radio_ids(rig, record.id) == [HF_ID, FM_ID]
    assert len(air.drivers[FM_ID].line.sent) == 1 and len(air.drivers[HF_ID].line.sent) == 1


async def test_a_message_the_stations_own_radio_cannot_carry_fails_when_that_radio_is_on_again(tmp_path: Path) -> None:
    """R2's rule for a message its new radio cannot carry: when the station's own radio is on again and its frame is too short for the message, the message fails as too long for the radio, with no
    attempt used and nothing more on the air (the FM radio here with a frame of 60 bytes; the registry's station book as the double's `station_of`)."""
    log, _, clock = await log_at(tmp_path, MessageLog)
    rig = Rig(log, clock, StubTnc(max_frame=60, rules=FM), hf_enabled=True)
    hf = with_hf(rig, rig.radios)
    book = StationBook(clock)
    book.seed([Station("OH2NR", first_heard=clock(), last_heard=clock(), heard_by={FM_ID: RadioHeard(5, clock())})])
    rig.radios.station_of = book.get                                       # type: ignore[attr-defined]  # (what the registry's station_of reads: its book)
    await rig.start()
    rig.radios.on.discard(FM_ID)
    record = await rig.m.send("OH2NR", "a message of fifty characters that FM cannot carry")
    rig.radios.on.add(FM_ID)
    await rig.pass_time(55)
    failed = rig.state(record.id)
    assert (failed.state, failed.failure, failed.attempts, radio_ids(rig, record.id)) == ("failed", "too_long_for_radio", 1, [HF_ID])
    assert len(hf.sent) == 1 and rig.tnc.sent == []


@pytest.mark.parametrize("restart", [False, True], ids=["running", "restarted"])
async def test_a_message_moved_off_the_stations_own_radio_goes_back_to_it_when_it_is_on_again(tmp_path: Path, restart: bool) -> None:
    """The stand-in is the same when the station's own radio is switched off while the message is on its way: OH2NR heard on FM alone, its first attempt on FM, FM switched off (the second over HF,
    which never heard it), FM on again: the rest on FM, with or without a restart before FM comes back. (The rig's double has no station book, so test_a_message_whose_radio_is_switched_off_... keeps FM there.)"""
    rig, air = await over_the_registry(tmp_path, OH2NR={FM_ID: 5})
    record = await rig.m.send("OH2NR", "fm then off")
    switch(air, fm=False)
    for _ in range(10):
        if len(radio_ids(rig, record.id)) == 2:
            break
        await rig.pass_time(15)
    assert radio_ids(rig, record.id) == [FM_ID, HF_ID]
    m = await registry_restarted(rig, air) if restart else rig
    switch(air, fm=True)
    assert await all_attempts(m, record.id) == [FM_ID, HF_ID, FM_ID, FM_ID]


async def test_a_message_moved_off_its_radio_to_one_that_heard_the_station_too_stays_there_when_it_is_on_again(tmp_path: Path) -> None:
    """R2's rule where the other radio is the station's as well: OH2BOTH heard on both, its first attempt on FM, FM off (the second over HF, which heard it), FM on again: it keeps HF."""
    rig, air = await over_the_registry(tmp_path, OH2BOTH={FM_ID: 5, HF_ID: 1})
    record = await rig.m.send("OH2BOTH", "fm then off")
    switch(air, fm=False)
    for _ in range(10):
        if len(radio_ids(rig, record.id)) == 2:
            break
        await rig.pass_time(15)
    switch(air, fm=True)
    assert await all_attempts(rig, record.id) == [FM_ID, HF_ID, HF_ID, HF_ID]


@pytest.mark.parametrize("restart", [False, True], ids=["running", "restarted"])
async def test_the_pages_radio_of_a_message_is_the_one_its_next_attempt_takes_when_a_radio_only_stood_in(tmp_path: Path, caplog: pytest.LogCaptureFixture, restart: bool) -> None:
    """What the page is told (the message row's `radio_now`: Messaging.radio_now) over the radio a message keeps: OH2NR heard on FM alone, its first attempt over HF while FM is off; FM on again, the row
    says FM before the next attempt goes on FM, with or without a restart between. Reading it keeps nothing and says nothing in the log: the line comes once, with the attempt that leaves HF."""
    caplog.set_level(logging.INFO)
    rig, air = await over_the_registry(tmp_path, OH2NR={FM_ID: 5})
    switch(air, fm=False)
    record = await rig.m.send("OH2NR", "while fm is off")
    m = await registry_restarted(rig, air) if restart else rig

    def told() -> int | None:
        [now] = [r for r in m.m.records() if r.id == record.id]
        radio = m.m.radio_now(now)
        return None if radio is None else radio.id

    kept = dict(m.m.message_radios._kept)
    assert told() == told() == HF_ID and m.m.message_radios._kept == kept, "HF while FM is off, and the read keeps nothing"
    switch(air, fm=True)
    assert told() == FM_ID and m.m.message_radios._kept == kept, "FM as soon as it is on, before any attempt"
    assert not [r for r in caplog.records if "goes on the radio the station is reached on now" in r.getMessage()], "nothing said by a read"
    ahead, went = [], []
    for _ in range(60):
        done = radio_ids(m, record.id)
        if len(done) == 4:
            break
        before = told()
        await m.pass_time(15)
        if len(radio_ids(m, record.id)) > len(done):
            ahead.append(before)
            went.append(radio_ids(m, record.id)[-1])
    assert radio_ids(m, record.id) == [HF_ID, FM_ID, FM_ID, FM_ID] and ahead == went == [FM_ID, FM_ID, FM_ID], "each attempt on the radio the page was told just before"
    assert len([r for r in caplog.records if "goes on the radio the station is reached on now" in r.getMessage()]) == 1, "said once, by the attempt"
