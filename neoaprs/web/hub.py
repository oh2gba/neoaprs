"""The state hub: named topics and the pages that follow them. The table of neoaprs/web/topics.py says what each topic holds and tells the hub when it changed.

A page follows every topic from the start and is sent each as it is (`state`); after that it is sent what changed (`patch`). A change is told on the hub's tick: what changed in a topic between
two ticks is one patch, with at most one op for a key, so a burst of 200 packets is one message. A topic is *keyed* (the stations by call, the packets by id: a change names the key and the item is
looked up when the patch is made, so an item that changed ten times is sent once, and one that is gone meanwhile is a `del`) or *whole* (the TNC, the settings: a change is a `replace` of the whole
value). A topic can ask for a gap between two patches (`interval`): the TNC changes with every line it sees and is told at most four times a second.

Back-pressure: the hub keeps nothing for a page. A page whose socket already holds more than `BEHIND` bytes (an eighth of what the socket is cut off at, `MAX_WRITE_BUFFER`) is not sent the patch;
the topic is marked stale for it and it is sent the whole `state` of the topic when its socket has been read down. A slow phone costs the daemon nothing, and a page that never reads is cut off by
the socket (neoaprs/web/pagesocket.py). Everything leaves as text through the page's `Connection`, which writes through the publisher (the cap on the size, the outgoing check).
"""
import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from .outbound import MAX_WRITE_BUFFER, encode

log = logging.getLogger("neoaprs.web")

TICK = 0.1                            # seconds between two flushes: what changed in between is one patch for a topic
BEHIND = MAX_WRITE_BUFFER // 8        # a socket that holds this much of what the page has not read is behind


class Link(Protocol):
    """What the hub needs of a page: a way to write a text frame, and how much the socket holds that the page has not read. It is the key of the page in the hub, so it is hashable."""
    def send_text(self, text: str) -> None: ...
    def buffered(self) -> int: ...


@dataclass(eq=False)
class Peer:
    link: Link
    topics: set[str] = field(default_factory=set)         # the topics it follows
    stale: set[str] = field(default_factory=set)          # the topics it was not sent a patch of because it was behind: it is sent the whole when it has read down its socket


class Topic:
    """A piece of the daemon's state the pages follow. `build` makes the whole value; `item` makes the item of a key, or None when it is gone (a topic without `item` is a whole value)."""

    def __init__(self, name: str, build: Callable[[], Any], item: Callable[[str], Any | None] | None = None, interval: float = 0.0) -> None:
        self.name = name
        self.build = build
        self.item = item
        self.interval = interval          # the least time between two patches
        self.rev = 0
        self.last = float("-inf")         # when the latest patch was made
        self._whole = False
        self._keys: dict[str, None] = {}  # in the order they changed

    def touch(self, key: str | None = None) -> None:
        """The topic changed: all of it (a `replace`), or the item of the key."""
        if key is None or self.item is None:
            self._whole = True
            self._keys.clear()
        elif not self._whole:
            self._keys[key] = None

    @property
    def pending(self) -> bool:
        return self._whole or bool(self._keys)

    def take(self) -> list[dict[str, Any]]:
        """The ops for what changed since the last patch, and the revision moves on."""
        ops: list[dict[str, Any]]
        if self._whole or self.item is None:
            ops = [{"op": "replace", "value": self.build()}]
        else:
            ops = []
            for key in self._keys:
                value = self.item(key)
                ops.append({"op": "del", "key": key} if value is None else {"op": "set", "key": key, "value": value})
        self._whole = False
        self._keys.clear()
        self.rev += 1
        return ops

    def discard(self) -> None:
        """What changed is dropped without being built: nobody follows the topic (a page that attaches later is sent the whole, as it is then)."""
        self._whole = False
        self._keys.clear()

    def state(self) -> dict[str, Any]:
        return {"type": "state", "topic": self.name, "rev": self.rev, "value": self.build()}


class StateHub:
    def __init__(self, behind: int = BEHIND, clock: Callable[[], float] = time.monotonic) -> None:
        self.behind = behind
        self.clock = clock
        self.topics: dict[str, Topic] = {}
        self._peers: dict[Link, Peer] = {}
        self._timer: asyncio.TimerHandle | None = None

    def add(self, topic: Topic) -> Topic:
        if topic.name in self.topics:
            raise ValueError(f"{topic.name} is a topic of the hub already")
        self.topics[topic.name] = topic
        return topic

    # ---- the pages
    def attach(self, link: Link) -> None:
        """A page opened: it follows every topic from now on and is sent each whole."""
        peer = self._peers[link] = Peer(link, set(self.topics))
        for topic in self.topics.values():
            self.deliver(peer, topic.state())

    def detach(self, link: Link) -> None:
        self._peers.pop(link, None)

    def subscribe(self, link: Link, names: list[str]) -> list[str]:
        """The page follows these topics (again): each is sent whole. The names that are no topic are returned."""
        peer = self._peers.get(link)
        if peer is None:
            return []
        names = list(dict.fromkeys(names))                        # (each once, in the order given: a name repeated is not sent again)
        unknown = [n for n in names if n not in self.topics]
        for name in names:
            if name in self.topics:
                peer.topics.add(name)
                peer.stale.discard(name)
                self.deliver(peer, self.topics[name].state())
        return unknown

    def unsubscribe(self, link: Link, names: list[str]) -> None:
        peer = self._peers.get(link)
        if peer is not None:
            peer.topics.difference_update(names)
            peer.stale.difference_update(names)

    def following(self, name: str) -> int:
        """How many pages follow the topic."""
        return sum(1 for p in self._peers.values() if name in p.topics)

    # ---- changes
    def changed(self, name: str, key: str | None = None) -> None:
        """The topic changed (the item of the key, or all of it): the pages are told on the next tick."""
        self.topics[name].touch(key)
        self._schedule(TICK)

    def _schedule(self, delay: float) -> None:
        if self._timer is None:
            try:
                self._timer = asyncio.get_running_loop().call_later(delay, self._tick)
            except RuntimeError:
                pass                                  # no loop: nothing is listening, and the state is built when a page asks

    def _tick(self) -> None:
        self._timer = None
        try:
            wait = self.flush()
        except Exception:
            log.exception("the hub's tick failed")
            wait = TICK if any(t.pending for t in self.topics.values()) else None
        if wait is not None:
            self._schedule(wait)

    def stop(self) -> None:
        """The daemon stops: no more ticks."""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def flush(self) -> float | None:
        """Tells the pages what changed since the last flush: for each topic that is due one patch (one text for all the pages) to every page that follows it. A page that is behind is not sent
        it. Returns when to flush again, None when nothing is waiting."""
        now = self.clock()
        wait: float | None = None
        behind: dict[Peer, bool] = {}
        for topic in self.topics.values():
            if not topic.pending:
                continue
            if not self.following(topic.name):
                topic.discard()                                          # (a daemon with no page open builds nothing)
                continue
            due = topic.last + topic.interval - now
            if due > 0:
                wait = due if wait is None else min(wait, due)
                continue
            topic.last = now
            self._tell(topic, topic.take(), behind)
        if self._catch_up(behind):
            wait = TICK if wait is None else min(wait, TICK)
        return wait

    def _tell(self, topic: Topic, ops: list[dict[str, Any]], behind: dict[Peer, bool]) -> None:
        text = encode({"type": "patch", "topic": topic.name, "rev": topic.rev, "ops": ops})
        for peer in list(self._peers.values()):
            if topic.name not in peer.topics or topic.name in peer.stale:
                continue
            if self._is_behind(peer, behind):
                peer.stale.add(topic.name)
            else:
                self._deliver(peer, text)

    def _catch_up(self, behind: dict[Peer, bool]) -> bool:
        """Sends the whole topic to the pages that were behind and have read down their sockets; whether some are still behind."""
        waiting = False
        for peer in list(self._peers.values()):
            if not peer.stale:
                continue
            if self._is_behind(peer, behind):
                waiting = True
                continue
            for name in sorted(peer.stale):
                self.deliver(peer, self.topics[name].state())
            peer.stale.clear()
        return waiting

    def _is_behind(self, peer: Peer, known: dict[Peer, bool]) -> bool:
        if peer not in known:
            try:
                known[peer] = peer.link.buffered() > self.behind
            except Exception:
                known[peer] = True                      # a socket that cannot say how much it holds is not one to write more to
        return known[peer]

    def deliver(self, peer: Peer, message: dict[str, Any]) -> None:
        self._deliver(peer, encode(message))

    @staticmethod
    def _deliver(peer: Peer, text: str) -> None:
        """What goes wrong with this page's socket is this page's: the others are sent theirs."""
        try:
            peer.link.send_text(text)
        except Exception:
            log.exception("a frame could not be sent to a page")
