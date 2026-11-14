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
from neoaprs.radiotype import FM_ID, HF_ID
from neoaprs.radiotypes.common import FM_LIMITS, HF_LIMITS
from neoaprs.packet import Message, Packet
from neoaprs.radios import Radios
from neoaprs.services.answers import Answers, as_pick
from neoaprs.station import Station
from neoaprs.stationbook import StationBook
from tests.support.air import on_air
from tests.support.stubtnc import StubRadios
from tests.support.storedb import log_at
from tests.support.stubtnc import StubTnc
from tests.test_messaging import LineAir, Rig, with_hf
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
    assert not r.choose("OH2NOBODY", "hf") and not r.choose("OH2GAX-2", "lora"), "an unknown station or radio is no choice"

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
    e, page = await with_page(tmp_path, settings={"hf/enabled": "false"})              # (a station whose HF radio was set up: the page offers the choice only while both radios are on)
    e.feed(on_air("OH2GAX-2", b"=6015.42N/02447.93E-Otso"))
    await page.until(lambda: "OH2GAX-2" in page.topics["stations"])
    assert page.topics["stations"]["OH2GAX-2"]["message_radio"] == ""
    await page.send({"cmd": "message_radio", "call": "OH2GAX-2", "radio": "hf"})
    await page.until(lambda: page.topics["stations"]["OH2GAX-2"]["message_radio"] == "hf")
    await page.send({"cmd": "message_radio", "call": "OH2NOBODY", "radio": "hf"})
    error = await page.expect("error")
    assert error["code"] == "station.unknown"


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
    answers = Answers(rig.radios, lambda: rig.config, lambda call: ())
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
    rig.radios.on.add(HF_ID)                                                # (back on: the message keeps the radio it was given)
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
    again, hf = await restarted(rig)                                        # (HF on again after the restart, OH2FAR heard on HF alone: it stays where it went)
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
