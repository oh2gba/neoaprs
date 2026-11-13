"""The budget of the answers (neoaprs/services/answers.py): all the answers of the station together are at most ANSWERS_PER_WINDOW frames in ANSWER_WINDOW_SEC, whoever asks and under whatever call; an honest
question is answered whole, an answer that does not fit is not given at all and is not counted as given, and a minute later there is room again."""
import asyncio
import logging

import pytest

from neoaprs.services.answers import ANSWER_FRAMES_MAX, ANSWER_WINDOW_SEC, ANSWERS_PER_WINDOW, AnswerBudget, Answers
from neoaprs.source import Source
from tests.support.clock import FixedClock
from tests.support.env import idle_for, remember_stop
from tests.test_queries import Rig as QueriesRig, general
from tests.support.rig import ServiceRig


class Rig(ServiceRig):
    def __init__(self) -> None:
        super().__init__()
        self.budget = AnswerBudget(self.clock)
        self.answers = Answers(self.tnc, lambda: self.config, lambda call: (), budget=self.budget)
        remember_stop(self.answers.stop)

    def ask(self, asker: str, query: str = "objects", frames: int = 1, paced: bool = False) -> bool:
        """The station `asker` is answered with that many messages."""
        return self.answers.deliver(asker, query, [self.answers.message(asker, f"answer {n}") for n in range(frames)], self.clock(), paced)


def test_the_budget_is_two_of_the_longest_honest_answers_in_a_minute() -> None:
    assert ANSWERS_PER_WINDOW == 2 * ANSWER_FRAMES_MAX and ANSWER_WINDOW_SEC == 60.0


def test_twenty_different_calls_asking_in_a_row_get_no_more_than_the_budget(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, "neoaprs.queries")
    rig = Rig()
    given = [rig.ask(f"OH2A{n:02d}", "position") for n in range(20)]
    assert given == [True] * ANSWERS_PER_WINDOW + [False] * (20 - ANSWERS_PER_WINDOW)
    assert len(rig.tnc.sent) == ANSWERS_PER_WINDOW
    assert len([r for r in caplog.records if "is not answered" in r.getMessage()]) == 20 - ANSWERS_PER_WINDOW


def test_an_honest_question_is_answered_whole_and_a_second_one_too() -> None:
    rig = Rig()
    assert rig.ask("OH2RDG", frames=ANSWER_FRAMES_MAX) and rig.ask("OH2XYZ", frames=ANSWER_FRAMES_MAX)
    assert len(rig.tnc.sent) == 2 * ANSWER_FRAMES_MAX


def test_an_answer_that_does_not_fit_whole_is_not_given_at_all_and_the_asker_may_ask_again() -> None:
    rig = Rig()
    for n in range(ANSWER_FRAMES_MAX + 2):
        assert rig.ask(f"OH2B{n}", "position")
    sent = len(rig.tnc.sent)
    assert rig.ask("OH2RDG", frames=ANSWER_FRAMES_MAX) is False
    assert len(rig.tnc.sent) == sent and not rig.answers.lately("OH2RDG", "objects", rig.clock())
    rig.clock.advance(ANSWER_WINDOW_SEC)
    assert rig.ask("OH2RDG", frames=ANSWER_FRAMES_MAX) and len(rig.tnc.sent) == sent + ANSWER_FRAMES_MAX


async def test_a_paced_answer_is_counted_for_all_its_frames_when_it_starts() -> None:
    rig = Rig()
    assert rig.ask("OH2RDG", frames=ANSWER_FRAMES_MAX, paced=True)
    assert rig.ask("OH2XYZ", frames=ANSWER_FRAMES_MAX, paced=True)
    assert rig.ask("OH2ABC", "position") is False


def test_a_single_frame_sent_without_an_answer_counts_too_and_is_refused_when_the_budget_is_spent() -> None:
    rig = Rig()
    frame = rig.answers.message("OH2RDG", "general")
    assert [rig.answers.send("OH2RDG", [frame]) for _ in range(ANSWERS_PER_WINDOW + 1)] == [True] * ANSWERS_PER_WINDOW + [False]


def test_two_services_that_share_a_budget_are_held_to_it_together() -> None:
    rig = Rig()
    other = Answers(rig.tnc, lambda: rig.config, lambda call: (), budget=rig.budget)
    for n in range(ANSWERS_PER_WINDOW // 2):
        assert rig.ask(f"OH2C{n}", "position")
        assert other.deliver(f"OH2D{n}", "position", [other.message(f"OH2D{n}", "x")], rig.clock(), False)
    assert other.deliver("OH2RDG", "position", [other.message("OH2RDG", "x")], rig.clock(), False) is False


def sent_now(budget: AnswerBudget, frames: int) -> None:
    """`frames` frames of an answer are taken and go on the air at once."""
    share = budget.take(frames)
    assert share is not None
    for _ in range(frames):
        share.went()
    share.close()


def test_the_window_slides_a_frame_is_free_again_a_minute_after_it_went() -> None:
    clock = FixedClock()
    budget = AnswerBudget(clock)
    sent_now(budget, ANSWERS_PER_WINDOW)
    assert budget.take(1) is None
    clock.advance(ANSWER_WINDOW_SEC - 1)
    assert budget.take(1) is None
    clock.advance(1)
    assert budget.take(1) is not None


def test_a_frame_of_a_paced_answer_counts_from_when_it_went_not_from_when_the_answer_was_taken() -> None:
    clock = FixedClock()
    budget = AnswerBudget(clock)
    shares = [budget.take(ANSWER_FRAMES_MAX), budget.take(ANSWER_FRAMES_MAX)]
    clock.advance(45)
    for share in shares:
        assert share is not None
        for _ in range(ANSWER_FRAMES_MAX):
            share.went()
        share.close()
    clock.advance(15)
    assert budget.take(1) is None, "the frames went at 45 s: a minute after the answers were taken they are still in the window"
    clock.advance(45)
    assert budget.take(ANSWERS_PER_WINDOW) is not None


def test_an_answer_that_did_not_go_gives_back_its_own_frames_not_those_of_another_that_went() -> None:
    clock = FixedClock()
    budget = AnswerBudget(clock)
    paced = budget.take(ANSWER_FRAMES_MAX)
    clock.advance(4)
    for _ in range(ANSWER_FRAMES_MAX):
        sent_now(budget, 1)
    clock.advance(1)
    assert paced is not None
    paced.close()
    paced.close()
    clock.advance(55)
    assert budget.take(ANSWER_FRAMES_MAX + 1) is None, "the five frames that went at 4 s count until 64 s"
    assert budget.take(ANSWER_FRAMES_MAX) is not None


def test_a_clock_set_back_does_not_hold_every_answer_back() -> None:
    clock = FixedClock()
    budget = AnswerBudget(clock)
    sent_now(budget, ANSWERS_PER_WINDOW)
    clock.advance(-3600)
    assert budget.take(1) is not None


def test_the_frames_of_an_answer_sent_at_once_go_together_or_not_at_all() -> None:
    rig = Rig()
    sent_now(rig.budget, ANSWERS_PER_WINDOW - 1)
    frames = [rig.answers.message("OH2RDG", "position"), rig.answers.message("OH2RDG", "status")]
    assert rig.answers.send("OH2RDG", frames) is False and rig.tnc.sent == []
    assert rig.answers.send("OH2RDG", frames[:1]) is True and len(rig.tnc.sent) == 1


async def test_the_general_query_with_room_for_one_frame_only_sends_neither_the_position_nor_the_status() -> None:
    rig = QueriesRig()
    rig.status_text = "QRV 145.500"
    sent_now(rig.q._answers._budget, ANSWERS_PER_WINDOW - 1)
    general(rig)
    await idle_for(0.1)
    assert rig.tnc.sent == []


def test_twenty_stations_asking_the_queries_under_twenty_calls_are_answered_ten_times_at_most() -> None:
    rig = QueriesRig()
    for n in range(20):
        rig.ask(f"OH2Q{n:02d}", "?APRSP")
    assert 0 < len(rig.tnc.sent) <= ANSWERS_PER_WINDOW


def test_frames_that_did_not_go_on_the_air_do_not_use_up_the_minute() -> None:
    rig = Rig()
    rig.tnc.state = Source.State.SILENT
    assert [rig.ask(f"OH2U{n:02d}", "position") for n in range(20)] == [False] * 20
    assert rig.answers.send("OH2RDG", [rig.answers.message("OH2RDG", "general")]) is False
    rig.tnc.state = Source.State.CONNECTED
    assert rig.ask("OH2RDG", frames=ANSWER_FRAMES_MAX) and rig.ask("OH2XYZ", frames=ANSWER_FRAMES_MAX)
    assert len(rig.tnc.sent) == ANSWERS_PER_WINDOW


async def test_a_paced_answer_that_is_stopped_gives_back_the_frames_it_did_not_send() -> None:
    rig = Rig()
    assert rig.ask("OH2RDG", frames=ANSWER_FRAMES_MAX, paced=True)
    await asyncio.sleep(0)
    await rig.answers.stop()
    assert rig.ask("OH2XYZ", frames=ANSWER_FRAMES_MAX) and rig.ask("OH2ABC", frames=ANSWER_FRAMES_MAX - 1)
