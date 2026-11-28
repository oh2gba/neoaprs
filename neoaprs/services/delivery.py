"""The delivery chain of messages we sent: each attempt, its path and the hops heard back.

A copy of our own message heard again is linked to the latest attempt before it. Chains are
persisted and go with the message.
"""

from collections.abc import Iterable
from datetime import datetime

from neoaprs.chain import AT_GATE, INTERNET_PATH, Attempt, HopSeen, attempt_before, hops_used, internet_hops
from neoaprs.message import MessageRecord, same_call
from neoaprs.messagelog import MessageLog
from neoaprs.packet import Message, Packet
from neoaprs.radiotype import RadioId
from neoaprs.route import digipeaters


class Delivery:
    def __init__(self, messagelog: MessageLog) -> None:
        self._log = messagelog
        self._chains: dict[int, list[Attempt]] = {}

    async def load(self, held: Iterable[int]) -> None:
        """Load the chains of the held messages from the database."""
        every = await self._log.chains()
        self._chains = {number: every[number] for number in held if number in every}

    def attempts_of(self, number: int) -> tuple[Attempt, ...]:
        return tuple(self._chains.get(number, ()))

    def sent(
        self,
        record: MessageRecord,
        path: tuple[str, ...],
        at: datetime,
        radio: RadioId | None = None,
        internet: bool = False,
    ) -> None:
        """Record an attempt of `record` by `path` on `radio`, or over the Internet connection; RFONLY, NOGATE etc.
        are not hops."""
        attempt = Attempt(record.attempts, at, INTERNET_PATH if internet else digipeaters(path), radio_id=radio)
        self._chains.setdefault(record.id, []).append(attempt)
        self._log.add_attempt(record.id, attempt)

    def restart(self, number: int) -> None:
        """Drop the chain: the message restarts from its first attempt."""
        if self._chains.pop(number, None) is not None:
            self._log.clear_chain(number)

    def drop(self, number: int) -> None:
        """Forget the chain of a message that is gone."""
        self._chains.pop(number, None)

    def heard(self, records: Iterable[MessageRecord], packet: Packet, message: Message) -> MessageRecord | None:
        """Return our message that a heard copy matches if it shows a new hop, else None."""
        if not packet.on_air or message.ack_id is not None or message.rej_id is not None:
            return None
        for record in records:
            if (
                record.direction == "out"
                and record.msg_id == message.msg_id
                and (record.wire if record.wire is not None else record.text) == message.text
                and same_call(record.to_call, message.addressee)
            ):
                attempt = attempt_before(self._chains.get(record.id, []), packet.heard_at)
                if attempt is not None and self._keep(record, attempt, packet):
                    return record
        return None

    def _keep(self, record: MessageRecord, attempt: Attempt, packet: Packet) -> bool:
        """Keep the hops the copy shows for the attempt; return whether any was new."""
        gate = packet.gate
        if gate:
            inner = () if packet.third_party is None else packet.third_party.path
            found = [HopSeen(AT_GATE, gate, packet.heard_at, True)] + [
                HopSeen(p, c, packet.heard_at, True) for p, c in internet_hops(attempt.path, inner, gate)
            ]
        else:
            found = [HopSeen(p, c, packet.heard_at, False) for p, c in hops_used(attempt.path, packet.path)]
        new = [seen for seen in found if not attempt.has(seen.position, seen.via_internet)]
        for seen in new:
            attempt = attempt.with_seen(seen)
            self._log.add_hop(record.id, attempt.number, seen)
        if new:
            chain = self._chains[record.id]
            chain[next(i for i, a in enumerate(chain) if a.number == attempt.number)] = attempt
        return bool(new)
