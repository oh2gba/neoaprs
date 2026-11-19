"""The limits of what the station sends again: the burst of a fast radio, the budget, the shares and the floor of a slow one, and the kinds of packet they count."""
from datetime import timedelta

import pytest

from neoaprs.aprsparse import parse
from neoaprs.packet import Packet
from neoaprs.services import passlimits
from neoaprs.services.passlimits import Burst, PassKind, SlowBudget, pass_kind
from tests.support.clock import FixedClock

SOURCE = "OH3ABC-9"


def packet(info: str, source: str = SOURCE, destination: str = "APRS") -> Packet:
    now = FixedClock().now
    raw = info.encode("latin-1")
    return Packet(now, "in", b"", source, destination, (), raw, parse(raw, source, destination, now))


def test_a_message_with_text_to_a_station_is_a_message_and_a_directed_query_is_one_too() -> None:
    assert pass_kind(packet(":OH2XYZ-1 :hello{12")) == "message"
    assert pass_kind(packet(":OH2XYZ-1 :?APRSP")) == "message"


def test_an_ack_and_a_rej_are_acks() -> None:
    assert pass_kind(packet(":OH2XYZ-1 :ack12")) == "ack"
    assert pass_kind(packet(":OH2XYZ-1 :rej12")) == "ack"


@pytest.mark.parametrize("text", ["PARM.A,B", "UNIT.V,A", "EQNS.0,1,0", "BITS.10101010,title"])
def test_a_telemetry_definition_is_other(text: str) -> None:
    assert pass_kind(packet(f":OH2XYZ-1 :{text}")) == "other"


def test_a_bulletin_and_a_group_message_are_other() -> None:
    assert pass_kind(packet(":BLN1     :weather is fine")) == "other"
    assert pass_kind(packet(":ALL      :hello everybody")) == "other"


def test_a_position_and_a_status_are_other() -> None:
    assert pass_kind(packet("!6016.00N/02455.00E-")) == "other"
    assert pass_kind(packet(">on the air")) == "other"


def test_a_burst_takes_four_frames_in_ten_seconds_and_a_radio_has_its_own() -> None:
    clock = FixedClock()
    burst = Burst(4, 10.0)
    for _ in range(4):
        assert not burst.full(1, clock.now)
        burst.take(1, clock.now)
    assert burst.full(1, clock.now)
    assert not burst.full(2, clock.now)
    clock.advance(10.0)
    assert not burst.full(1, clock.now)


def test_a_burst_lets_its_frames_go_one_at_a_time_and_asking_notes_nothing() -> None:
    clock = FixedClock()
    burst = Burst(4, 10.0)
    for _ in range(4):
        burst.take(1, clock.now)
        clock.advance(3.0)
    clock.advance(-2.5)
    assert burst.full(1, clock.now)
    assert burst.full(1, clock.now)
    clock.advance(0.5)
    assert not burst.full(1, clock.now)
    assert not burst.full(1, clock.now)


def at_pace(budget: SlowBudget, clock: FixedClock, source: str, kind: PassKind) -> str | None:
    """Asks the budget and, when it lets the frame go, takes it."""
    reason = budget.refusal(source, kind, clock.now)
    if reason is None:
        budget.take(source, kind, clock.now)
    return reason


def test_five_stations_messages_in_a_minute_give_four_and_then_the_budget_holds_the_fifth_until_the_first_is_five_minutes_old() -> None:
    clock = FixedClock()
    budget = SlowBudget(30)
    first = clock.now
    results = []
    for n in range(5):
        results.append(at_pace(budget, clock, f"OH3AB{n}", "message"))
        clock.advance(10)
    assert results == [None, None, None, None, "budget"]
    clock.now = first + timedelta(seconds=passlimits.SLOW_PASS_WINDOW_SEC)
    assert at_pace(budget, clock, "OH3AB5", "message") is None


def test_one_station_gets_two_messages_in_five_minutes_and_the_third_is_held_by_its_share() -> None:
    clock = FixedClock()
    budget = SlowBudget(30)
    results = []
    for _ in range(3):
        results.append(at_pace(budget, clock, SOURCE, "message"))
        clock.advance(20)
    assert results == [None, None, "share"]
    assert at_pace(budget, clock, "OH3XYZ", "message") is None


def test_a_station_is_one_whatever_the_case_or_the_zero_ssid() -> None:
    clock = FixedClock()
    budget = SlowBudget(30)
    assert at_pace(budget, clock, "OH3ABC", "message") is None
    assert at_pace(budget, clock, "oh3abc-0", "message") is None
    assert at_pace(budget, clock, "OH3ABC", "message") == "share"


def test_positions_of_one_station_ten_minutes_apart_give_one_and_the_floor_holds_the_next() -> None:
    clock = FixedClock()
    budget = SlowBudget(30)
    assert at_pace(budget, clock, SOURCE, "other") is None
    clock.advance(600)
    assert at_pace(budget, clock, SOURCE, "other") == "floor"


def test_positions_of_one_station_thirty_one_minutes_apart_give_two() -> None:
    clock = FixedClock()
    budget = SlowBudget(30)
    assert at_pace(budget, clock, SOURCE, "other") is None
    clock.advance(31 * 60)
    assert at_pace(budget, clock, SOURCE, "other") is None


def test_a_message_is_not_held_by_the_floor() -> None:
    clock = FixedClock()
    budget = SlowBudget(30)
    assert at_pace(budget, clock, SOURCE, "other") is None
    assert at_pace(budget, clock, SOURCE, "message") is None


def test_four_positions_from_four_stations_give_two_and_the_budget_holds_the_rest_but_a_message_still_goes() -> None:
    clock = FixedClock()
    budget = SlowBudget(30)
    results = [at_pace(budget, clock, f"OH3AB{n}", "other") for n in range(4)]
    assert results == [None, None, "budget", "budget"]
    assert at_pace(budget, clock, "OH3MSG", "message") is None
    assert at_pace(budget, clock, "OH3MSG", "ack") is None
    assert at_pace(budget, clock, "OH3MSG-1", "message") == "budget"


def test_an_ack_counts_in_the_budget_but_not_in_the_share_of_its_station() -> None:
    clock = FixedClock()
    budget = SlowBudget(30)
    assert at_pace(budget, clock, SOURCE, "message") is None
    assert at_pace(budget, clock, SOURCE, "ack") is None
    assert at_pace(budget, clock, SOURCE, "message") is None
    assert budget.refusal(SOURCE, "message", clock.now) == "share"


def test_a_question_to_the_budget_notes_nothing() -> None:
    clock = FixedClock()
    budget = SlowBudget(30)
    for _ in range(10):
        assert budget.refusal(SOURCE, "other", clock.now) is None


def test_a_floor_of_zero_minutes_holds_nothing_for_the_floor() -> None:
    clock = FixedClock()
    budget = SlowBudget(0)
    assert at_pace(budget, clock, SOURCE, "other") is None
    assert at_pace(budget, clock, SOURCE, "other") is None
