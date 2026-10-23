"""The delivery chain of the messages we sent (neoaprs/chain.py): each attempt with the path it went by, and which hops of that path we heard come back.

A copy of one of our own messages that the Tnc hears again (the same addressee, id and text, from our call; by RF, or wrapped by an iGate as a third-party packet) is linked to the message and to the attempt
it belongs to, the latest attempt sent before the copy was heard, and the hops its path shows used are kept for that attempt (the first time each was heard stays). An ack, a reject and a copy of a message
we did not send are not linked. The attempts and hops are held here for every message messaging holds and kept in the database (messagelog.py) so that a restart keeps them; they go with the message."""
from collections.abc import Iterable
from datetime import datetime

from neoaprs.chain import INTERNET, Attempt, HopSeen, attempt_before, hops_used, internet_hops
from neoaprs.message import MessageRecord, same_call
from neoaprs.messagelog import MessageLog
from neoaprs.packet import Message, Packet
from neoaprs.route import digipeaters


class Delivery:
    def __init__(self, messagelog: MessageLog) -> None:
        self._log = messagelog
        self._chains: dict[int, list[Attempt]] = {}

    async def load(self, held: Iterable[int]) -> None:
        """Takes the chains of the messages held from the database."""
        every = await self._log.chains()
        self._chains = {number: every[number] for number in held if number in every}

    def attempts_of(self, number: int) -> tuple[Attempt, ...]:
        return tuple(self._chains.get(number, ()))

    def sent(self, record: MessageRecord, path: tuple[str, ...], at: datetime) -> None:
        """Message `record` was transmitted at `at` by `path`; `record.attempts` is the number of this attempt. What is kept is the digipeaters: RFONLY, NOGATE and the like are not hops."""
        attempt = Attempt(record.attempts, at, digipeaters(path))
        self._chains.setdefault(record.id, []).append(attempt)
        self._log.add_attempt(record.id, attempt)

    def restart(self, number: int) -> None:
        """The message is sent again from its first attempt: what was kept of the run before is dropped."""
        if self._chains.pop(number, None) is not None:
            self._log.clear_chain(number)

    def drop(self, number: int) -> None:
        """The message is gone (the database removed its chain with it)."""
        self._chains.pop(number, None)

    def heard(self, records: Iterable[MessageRecord], packet: Packet, message: Message) -> MessageRecord | None:
        """A packet from our own call was heard: the message of ours it is a copy of, when it brings a hop that was not known; else None."""
        if message.ack_id is not None or message.rej_id is not None:
            return None
        for record in records:
            if record.direction == "out" and record.msg_id == message.msg_id and record.text == message.text and same_call(record.to_call, message.addressee):
                attempt = attempt_before(self._chains.get(record.id, []), packet.heard_at)
                if attempt is not None and self._keep(record, attempt, packet):
                    return record
        return None

    def _keep(self, record: MessageRecord, attempt: Attempt, packet: Packet) -> bool:
        """Notes what the copy shows for the attempt; whether any of it was new."""
        gate = packet.via
        if gate:
            inner = () if packet.third_party is None else packet.third_party.path
            found = [HopSeen(INTERNET, gate, packet.heard_at, True)] + [HopSeen(p, c, packet.heard_at, True) for p, c in internet_hops(attempt.path, inner, gate)]
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
