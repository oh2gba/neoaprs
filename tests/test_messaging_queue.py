"""One message to a station on the air at a time (neoaprs/services/messaging.py, `Messaging.queued`) on the stub Tnc and clock of tests/test_messaging.py: a second message to a station waits, with no attempt
made, while the first is being sent, and goes as soon as the first is acked, rejected, failed or cancelled; three go in the order written; messages to different stations do not wait for each other; the
email gateway, a bulletin and a query never wait nor hold one up; the order holds over a restart; a waiting message can be cancelled; a retry waits its turn; and the page is told `queued`, then `sending`."""
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from neoaprs.web.messagewire import MessageRow
from neoaprs.web.views import message_row
from tests.support.air import ack_info, on_air
from tests.test_messaging import RUN_OUT, Rig, started_rig
from tests.test_web import with_page


@pytest.fixture
async def rig(tmp_path: Path) -> Rig:
    return await started_rig(tmp_path)


@pytest.fixture
def another(rig: Rig) -> Callable[..., Rig]:
    """A second messaging on the same database, as after a restart of the daemon."""
    def make(**changes: object) -> Rig:
        return Rig(rig.log, rig.clock, rig.tnc, **changes)
    return make


def texts(rig: Rig) -> list[str]:
    """What went on the air, as the text and number of each message (`a{01}`)."""
    return [line.split(":", 3)[3] for line in rig.lines()]


async def acked(rig: Rig, msg_id: str, call: str = "OH2RDG") -> None:
    """The station acks our message `msg_id`, and the ticker has had its look."""
    rig.m.on_packet(rig.heard(call, "OH2GBA", ack=msg_id))
    await rig.pass_time(0)


async def test_a_second_message_to_a_station_waits_with_no_attempt_while_the_first_is_unacked_and_goes_when_it_is_acked(rig: Rig) -> None:
    await rig.m.send("OH2RDG", "a")
    second = await rig.m.send("OH2RDG", "b")
    assert (second.state, second.attempts) == ("sending", 0) and rig.m.queued(second) and not rig.m.queued(rig.state(1))
    assert texts(rig) == ["a{01}"]
    await rig.pass_time(32)
    await rig.pass_time(32)
    assert texts(rig) == ["a{01}"] * 3 and rig.state(2).attempts == 0, "the first is sent again; the second waits for it, however long"
    await acked(rig, "01")
    assert texts(rig) == ["a{01}"] * 3 + ["b{02}"] and not rig.m.queued(rig.state(2))
    await rig.pass_time(32)
    assert texts(rig)[-1] == "b{02}" and rig.state(2).attempts == 2, "and it has its own schedule from its first attempt"


@pytest.mark.parametrize("how", ["failed", "rejected", "cancelled"])
async def test_the_waiting_message_goes_when_the_first_fails_is_rejected_or_is_cancelled(rig: Rig, how: str) -> None:
    await rig.m.send("OH2RDG", "a")
    await rig.m.send("OH2RDG", "b")
    if how == "cancelled":
        rig.m.cancel(1)
        await rig.pass_time(0)
    elif how == "rejected":
        rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", rej="01"))
        await rig.pass_time(0)
    else:
        for step in RUN_OUT:
            await rig.pass_time(step)
    assert rig.state(1).state == how
    assert texts(rig)[-1] == "b{02}" and rig.state(2).attempts == 1
    assert rig.lines().count(rig.lines()[-1]) == 1, "it goes once, when the first is settled, and not before"


async def test_three_messages_to_a_station_go_one_after_the_other_in_the_order_they_were_written(rig: Rig) -> None:
    for text in "abc":
        await rig.m.send("OH2RDG", text)
    assert texts(rig) == ["a{01}"] and [rig.m.queued(rig.state(n)) for n in (1, 2, 3)] == [False, True, True]
    await acked(rig, "01")
    assert texts(rig) == ["a{01}", "b{02}"] and rig.m.queued(rig.state(3))
    await acked(rig, "02")
    assert texts(rig) == ["a{01}", "b{02}", "c{03}"]


async def test_messages_to_two_stations_go_side_by_side_and_a_queue_of_one_does_not_hold_up_the_other(rig: Rig) -> None:
    await rig.m.send("OH2RDG", "a")
    await rig.m.send("OH2AAA", "x")
    await rig.m.send("OH2RDG", "b")
    await rig.m.send("OH2AAA-7", "y")                                             # (another ssid is another station)
    assert texts(rig) == ["a{01}", "x{02}", "y{04}"] and rig.m.queued(rig.state(3))
    await acked(rig, "02", "OH2AAA")
    assert texts(rig) == ["a{01}", "x{02}", "y{04}"], "the ack of the other station's message lets nothing of OH2RDG's go"
    await acked(rig, "01")
    assert texts(rig)[-1] == "b{03}" and rig.state(3).attempts == 1


async def test_the_email_gateway_a_bulletin_and_a_query_neither_wait_nor_hold_one_up(rig: Rig) -> None:
    await rig.m.send("EMAIL-2", "me@example.org one")
    await rig.m.send("EMAIL-2", "me@example.org two")
    assert len(rig.lines()) == 2 and not any(rig.m.queued(r) for r in rig.m.records()), "the gateway is not expected to ack: both go at once"
    await rig.m.send("OH2RDG", "a")
    await rig.m.asking.ask("OH2RDG", "status")
    await rig.m.send("BLN1", "Road closed")
    await rig.m.send("BLN1", "Road open")
    assert texts(rig)[2:] == ["a{03}", "?APRSS", "Road closed", "Road open"], "a query to a station a message is being sent to goes at once, and so do bulletins"
    await rig.m.send("OH2RDG", "b")
    assert texts(rig)[-1] == "Road open" and rig.m.queued(rig.state(rig.m.records()[-1].id)), "the query did not take the place of the message on the air"


async def test_after_a_restart_the_message_on_the_air_goes_on_and_the_waiting_one_still_waits_for_it(rig: Rig, another: Callable[..., Rig]) -> None:
    await rig.m.send("OH2RDG", "a")
    await rig.m.send("OH2RDG", "b")
    await rig.settled()
    await rig.m.stop()
    again = another()
    await again.start()
    again.tnc.sent.clear()
    assert again.m.queued(again.state(2)) and not again.m.queued(again.state(1))
    await again.pass_time(32)
    assert texts(again) == ["a{01}"]
    await acked(again, "01")
    assert texts(again) == ["a{01}", "b{02}"]
    await again.m.stop()


async def test_a_waiting_message_can_be_cancelled_and_is_never_sent_and_the_next_one_takes_its_turn(rig: Rig) -> None:
    for text in "abc":
        await rig.m.send("OH2RDG", text)
    cancelled = rig.m.cancel(2)
    assert (cancelled.state, cancelled.attempts) == ("cancelled", 0) and not rig.m.queued(cancelled)
    await acked(rig, "01")
    for step in RUN_OUT:
        await rig.pass_time(step)
    assert texts(rig) == ["a{01}"] + ["c{03}"] * 4, "b never went; c went when a was acked and had its four attempts"
    assert (rig.state(2).attempts, rig.state(3).state) == (0, "failed")


async def test_a_retry_while_another_message_to_the_station_is_on_the_air_waits_its_turn_and_then_goes_before_newer_ones(rig: Rig) -> None:
    await rig.m.send("OH2RDG", "a")
    for step in RUN_OUT:
        await rig.pass_time(step)
    assert rig.state(1).state == "failed"
    await rig.m.send("OH2RDG", "b")
    again = rig.m.retry(1)
    await rig.m.send("OH2RDG", "c")
    assert (again.state, again.attempts) == ("sending", 0) and rig.m.queued(again) and rig.m.queued(rig.state(3))
    assert texts(rig)[-1] == "b{02}"
    await acked(rig, "02")
    assert texts(rig)[-1] == "a{01}", "the retried message is the oldest of those waiting (the lowest number), so it goes before c, which was written after it"
    await acked(rig, "01")
    assert texts(rig)[-1] == "c{03}"


async def test_the_page_row_says_queued_for_the_waiting_one_and_sending_when_its_turn_comes_and_it_is_told_again_then(rig: Rig) -> None:
    await rig.m.send("OH2RDG", "a")
    await rig.m.send("OH2RDG", "b")
    row = message_row(rig.state(2), queued=rig.m.queued(rig.state(2)))
    assert (row["state"], row["attempts"]) == ("queued", 0) and message_row(rig.state(1), queued=rig.m.queued(rig.state(1)))["state"] == "sending"
    rig.changed.clear()
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", ack="01"))
    assert [(r.id, r.state, r.attempts) for r in rig.changed] == [(1, "acked", 1), (2, "sending", 0)], "the waiting one is told again when the first settles: the page asks again whether it waits"
    assert message_row(rig.state(2), queued=rig.m.queued(rig.state(2)))["state"] == "sending"


async def test_the_pages_see_the_second_message_as_queued_and_then_as_sending_when_the_first_is_acked(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    await page.send({"cmd": "send_message", "to": "OH2RDG", "text": "first"})
    await page.until(lambda: page.topics["messages"].get("1", {}).get("attempts") == 1)
    await page.send({"cmd": "send_message", "to": "OH2RDG", "text": "second"})
    await page.until(lambda: "2" in page.topics["messages"])
    second = MessageRow.model_validate_json(json.dumps(page.topics["messages"]["2"]))
    assert (second.state, second.attempts) == ("queued", 0) and page.topics["messages"]["1"]["state"] == "sending"
    e.feed(on_air("OH2RDG", ack_info("OH2GBA", "01")))
    await page.until(lambda: page.topics["messages"]["2"]["attempts"] == 1)
    assert (page.topics["messages"]["1"]["state"], page.topics["messages"]["2"]["state"]) == ("acked", "sending")
    assert page.of("error") == []
