"""Recently passed messages, so an ack heard on the far radio goes back once."""

from dataclasses import dataclass
from datetime import datetime

from neoaprs.radiotype import RadioId
from neoaprs.services.passlimits import source_name

PASS_BACK_SEC = 600.0  # longer than our own retry schedule of about 6 minutes
PASSED_KEEP_MAX = 200  # the oldest go first


@dataclass(frozen=True)
class Passed:
    """A message passed from radio `heard_on` to radio `sent_on` at `at`."""

    source: str
    addressee: str
    msg_id: str
    heard_on: RadioId
    sent_on: RadioId
    at: datetime


def _key(source: str, addressee: str, msg_id: str) -> tuple[str, str, str]:
    return source_name(source), source_name(addressee), msg_id


class PassedMessages:
    """Passed messages by (source, addressee, id), oldest first, at most PASSED_KEEP_MAX."""

    def __init__(self) -> None:
        self._passed: dict[tuple[str, str, str], Passed] = {}

    def note(self, passed: Passed) -> None:
        """Record a passed message; passing the same message again replaces the entry."""
        key = _key(passed.source, passed.addressee, passed.msg_id)
        self._passed.pop(key, None)
        self._passed[key] = passed
        while len(self._passed) > PASSED_KEEP_MAX:
            del self._passed[next(iter(self._passed))]

    def answer(
        self, sender: str, addressee: str, msg_id: str, heard_on: RadioId, now: datetime, take: bool = True
    ) -> Passed | None:
        """Return the passed message an ack or rej answers (sent on `heard_on`), or None.

        With `take` the entry is removed; otherwise `forget` removes it."""
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
        """Remove the entry once its ack has gone back, so a further copy answers nothing."""
        self._passed.pop(_key(passed.source, passed.addressee, passed.msg_id), None)
