"""Which messages have been heard already: the same message (sender, id and text) heard again within `window_sec` is a repeat (the sender did not hear our ack, or a digipeater copied it), not a new
message; when a message was last acked, so that the copies of one burst are answered once (`ack_due`); and which message of a station that knows reply-acks is still to be acknowledged on the next message
we send it (`owe_reply`, `reply_for`)."""
from datetime import datetime, timedelta

from neoaprs.message import MessageRecord

DUPLICATE_WINDOW_SEC = 30 * 60
ACK_AGAIN_SEC = 30                                          # a copy of a message is acked again only when it comes at least this long after our last ack of it (digipeaters drop a duplicate for 30 s)


class Heard:
    def __init__(self, window_sec: float = DUPLICATE_WINDOW_SEC) -> None:
        self.window = timedelta(seconds=window_sec)
        self._at: dict[tuple[str, str, str], datetime] = {}
        self._acked: dict[tuple[str, str, str], datetime] = {}   # when we last acked each message (the same key): kept in memory only, like the rest
        self._reply: dict[str, tuple[str, datetime]] = {}   # for each station that sent a message with a reply-ack number: the id of the latest of them and when it was heard

    @staticmethod
    def key_of(record: MessageRecord) -> tuple[str, str, str] | None:
        """What tells a repeat of a message from a new one. A message that came to us with an id: the sender, the id and the text (the same again is a repeat, and is acked again; the same id with another
        text is a new message, a sender that began its numbering again). One without an id, and one we only overheard: the sender, the addressee and the id, or (none) the text, so that two digipeaters' copies
        of "Thanks, 73" are one message."""
        if record.direction != "in":
            return None
        if record.state == "overheard" or record.msg_id is None:
            return (f"{record.from_call}>{record.to_call}", record.msg_id or f"~{record.text}", record.text if record.msg_id is not None else "")
        return (record.from_call, record.msg_id, record.text)

    def note(self, record: MessageRecord, at: datetime) -> bool:
        """Notes that the message was heard; False when it was, less than the window before, already. A message that was not heard (one of ours) has no key and is always new."""
        key = self.key_of(record)
        if key is None:
            return True
        before = self._at.get(key)
        if before is not None and at - before < self.window:
            return False
        self._at[key] = at
        return True

    def ack_due(self, record: MessageRecord, at: datetime) -> bool:
        """Whether to ack the message heard at `at`, and if so notes that we did. The first copy is acked at once; a further copy of the same message (the burst of a sender, two digipeaters and an iGate)
        only when at least ACK_AGAIN_SEC have passed since our last ack of it, which is a sender that did not hear us and tries again."""
        key = self.key_of(record)
        if key is None:
            return False
        before = self._acked.get(key)
        if before is not None and at - before < timedelta(seconds=ACK_AGAIN_SEC):
            return False
        self._acked[key] = at
        return True

    def owe_reply(self, station: str, msg_id: str, at: datetime) -> None:
        """Notes that the station's message `msg_id`, which came with a reply-ack number, is the latest to be acknowledged on our next message to it."""
        self._reply[station] = (msg_id, at)

    def reply_for(self, station: str, at: datetime) -> str | None:
        """The id to carry as the reply-ack of a message to the station sent at `at`: that of its latest message, heard less than the window before; None when there is none."""
        found = self._reply.get(station)
        if found is None or at - found[1] >= self.window:
            return None
        return found[0]

    def settled(self, station: str) -> None:
        """The station has answered a message of ours (it acked or rejected it): what it was owed has reached it."""
        self._reply.pop(station, None)

    def forget_before(self, cutoff: datetime) -> None:
        self._at = {key: at for key, at in self._at.items() if at >= cutoff}
        self._acked = {key: at for key, at in self._acked.items() if at >= cutoff}
        self._reply = {station: held for station, held in self._reply.items() if held[1] >= cutoff}
