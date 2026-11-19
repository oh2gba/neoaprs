"""The messages a pair passed lately: the ack of one answers it once, on the radio it was sent on, within ten minutes."""
from datetime import datetime, timedelta

from neoaprs.services.passback import PASS_BACK_SEC, PASSED_KEEP_MAX, Passed, PassedMessages
from tests.support.clock import FixedClock


def passed(at: datetime, msg_id: str = "12", source: str = "OH3ABC-9", addressee: str = "OH2XYZ-1") -> Passed:
    return Passed(source, addressee, msg_id, heard_on=1, sent_on=2, at=at)


def test_the_ack_answers_the_message_once_and_a_second_copy_answers_nothing() -> None:
    clock = FixedClock()
    book = PassedMessages()
    note = passed(clock.now)
    book.note(note)
    clock.advance(30)
    assert book.answer("OH2XYZ-1", "OH3ABC-9", "12", 2, clock.now) == note
    assert book.answer("OH2XYZ-1", "OH3ABC-9", "12", 2, clock.now) is None


def test_another_id_another_pair_of_stations_and_the_radio_it_was_not_sent_on_answer_nothing() -> None:
    clock = FixedClock()
    book = PassedMessages()
    book.note(passed(clock.now))
    assert book.answer("OH2XYZ-1", "OH3ABC-9", "13", 2, clock.now) is None
    assert book.answer("OH3ABC-9", "OH2XYZ-1", "12", 2, clock.now) is None
    assert book.answer("OH2XYZ-1", "OH3ABC-9", "12", 1, clock.now) is None


def test_the_wrong_radio_does_not_use_the_entry_up() -> None:
    clock = FixedClock()
    book = PassedMessages()
    book.note(passed(clock.now))
    assert book.answer("OH2XYZ-1", "OH3ABC-9", "12", 1, clock.now) is None
    assert book.answer("OH2XYZ-1", "OH3ABC-9", "12", 2, clock.now) is not None


def test_after_ten_minutes_the_ack_answers_nothing_and_before_it_does() -> None:
    clock = FixedClock()
    book = PassedMessages()
    book.note(passed(clock.now))
    book.note(passed(clock.now, msg_id="13"))
    assert book.answer("OH2XYZ-1", "OH3ABC-9", "12", 2, clock.now + timedelta(seconds=PASS_BACK_SEC - 1)) is not None
    assert book.answer("OH2XYZ-1", "OH3ABC-9", "13", 2, clock.now + timedelta(seconds=PASS_BACK_SEC)) is None


def test_calls_are_compared_as_message_same_call_does() -> None:
    clock = FixedClock()
    book = PassedMessages()
    book.note(passed(clock.now, source="oh3abc-9", addressee="OH2XYZ-0"))
    assert book.answer("OH2XYZ", "OH3ABC-9", "12", 2, clock.now) is not None


def test_the_oldest_messages_go_first_when_too_many_are_kept() -> None:
    clock = FixedClock()
    book = PassedMessages()
    for n in range(PASSED_KEEP_MAX + 1):
        book.note(passed(clock.now, msg_id=str(n)))
    assert book.answer("OH2XYZ-1", "OH3ABC-9", "0", 2, clock.now) is None
    assert book.answer("OH2XYZ-1", "OH3ABC-9", "1", 2, clock.now) is not None
    assert book.answer("OH2XYZ-1", "OH3ABC-9", str(PASSED_KEEP_MAX), 2, clock.now) is not None
