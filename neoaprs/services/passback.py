"""The messages a pair passed lately, so that the ack of one heard on the far radio goes back once (aprs-reference/cross-radio-digipeat-plan.md M2)."""
from dataclasses import dataclass
from datetime import datetime

from neoaprs.radiotype import RadioId
from neoaprs.services.passlimits import source_name

PASS_BACK_SEC = 600.0              # longer than NeoAPRS's own schedule of about 6 minutes
PASSED_KEEP_MAX = 200              # the most messages kept; the oldest go first


@dataclass(frozen=True)
class Passed:
    """A message a pair passed: from `source` to `addressee` with `msg_id`, heard on `heard_on` and sent on `sent_on` at `at`."""
    source: str
    addressee: str
    msg_id: str
    heard_on: RadioId
    sent_on: RadioId
    at: datetime


def _key(source: str, addressee: str, msg_id: str) -> tuple[str, str, str]:
    return source_name(source), source_name(addressee), msg_id


class PassedMessages:
    """The messages the pairs passed lately, by their two stations and id, the oldest first, at most PASSED_KEEP_MAX of them."""

    def __init__(self) -> None:
        self._passed: dict[tuple[str, str, str], Passed] = {}       # oldest first

    def note(self, passed: Passed) -> None:
        """A message went across; a second pass of the same message counts as the latest."""
        key = _key(passed.source, passed.addressee, passed.msg_id)
        self._passed.pop(key, None)
        self._passed[key] = passed
        while len(self._passed) > PASSED_KEEP_MAX:
            del self._passed[next(iter(self._passed))]

    def answer(self, sender: str, addressee: str, msg_id: str, heard_on: RadioId, now: datetime, take: bool = True) -> Passed | None:
        """The message an ack or rej from `sender` to `addressee` for `msg_id`, heard on `heard_on`, answers (one we passed from `addressee` to `sender` and sent on that radio, within PASS_BACK_SEC); with `take`
        it is taken out, so a second copy answers nothing (without, `forget` takes it once the copy is passed). Calls are compared as passlimits.source_name gives them."""
        key = _key(addressee, sender, msg_id)
        passed = self._passed.get(key)
        if passed is None:
            return None
        if (now - passed.at).total_seconds() >= PASS_BACK_SEC:
            del self._passed[key]
            return None
        if passed.sent_on != heard_on:
            return None
        if take:
            del self._passed[key]
        return passed

    def forget(self, passed: Passed) -> None:
        """The ack of the message has gone back: a further copy answers nothing."""
        self._passed.pop(_key(passed.source, passed.addressee, passed.msg_id), None)
