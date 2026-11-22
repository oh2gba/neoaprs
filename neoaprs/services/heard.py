"""Which messages have been heard already, when each was last acked, and reply-acks still owed.

The same message (sender, id and text) heard again within `window_sec` is a repeat. `ack_due`
answers the copies of one burst once; `owe_reply` and `reply_for` track reply-acks.
"""

from datetime import datetime, timedelta

from neoaprs.message import MessageRecord
from neoaprs.policy import DIGI_DUPLICATE_SEC

DUPLICATE_WINDOW_SEC = 30 * 60
# A copy is acked again only this long after our last ack; digipeaters drop duplicates for 30 s.
ACK_AGAIN_SEC = DIGI_DUPLICATE_SEC


class Heard:
    def __init__(self, window_sec: float = DUPLICATE_WINDOW_SEC) -> None:
        self.window = timedelta(seconds=window_sec)
        self._at: dict[tuple[str, str, str], datetime] = {}
        self._acked: dict[tuple[str, str, str], datetime] = {}
        self._reply: dict[str, tuple[str, datetime]] = {}  # per station: latest id and when heard

    @staticmethod
    def key_of(record: MessageRecord) -> tuple[str, str, str] | None:
        """Return the key that tells a repeat from a new message, or None for one of ours.

        An id with other text is a new message; without an id, or overheard, the key adds the addressee.
        """
        if record.direction != "in":
            return None
        if record.state == "overheard" or record.msg_id is None:
            return (
                f"{record.from_call}>{record.to_call}",
                record.msg_id or f"~{record.text}",
                record.text if record.msg_id is not None else "",
            )
        return (record.from_call, record.msg_id, record.text)

    def note(self, record: MessageRecord, at: datetime) -> bool:
        """Note the message; return False if heard within the window (DIGI_DUPLICATE_SEC if no id)."""
        key = self.key_of(record)
        if key is None:
            return True
        before = self._at.get(key)
        window = self.window if record.msg_id is not None else min(self.window, timedelta(seconds=DIGI_DUPLICATE_SEC))
        if before is not None and at - before < window:
            return False
        self._at[key] = at
        return True

    def ack_due(self, record: MessageRecord, at: datetime) -> bool:
        """Return whether to ack the message heard at `at`, noting the ack if so.

        A further copy is acked only after ACK_AGAIN_SEC: the sender did not hear us and retried.
        """
        key = self.key_of(record)
        if key is None:
            return False
        before = self._acked.get(key)
        if before is not None and at - before < timedelta(seconds=ACK_AGAIN_SEC):
            return False
        self._acked[key] = at
        return True

    def owe_reply(self, station: str, msg_id: str, at: datetime) -> None:
        """Note that `msg_id`, which had a reply-ack number, is acked on our next message to it."""
        self._reply[station] = (msg_id, at)

    def reply_for(self, station: str, at: datetime) -> str | None:
        """The reply-ack id for a message sent at `at`: its latest within the window, else None."""
        found = self._reply.get(station)
        if found is None or at - found[1] >= self.window:
            return None
        return found[0]

    def settled(self, station: str) -> None:
        """The station acked or rejected a message of ours, so the owed reply-ack has reached it."""
        self._reply.pop(station, None)

    def forget_before(self, cutoff: datetime) -> None:
        self._at = {key: at for key, at in self._at.items() if at >= cutoff}
        self._acked = {key: at for key, at in self._acked.items() if at >= cutoff}
        self._reply = {station: held for station, held in self._reply.items() if held[1] >= cutoff}
