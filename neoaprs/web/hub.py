"""The state hub: named topics and the pages that follow them (topics.py lists the topics).

A page is first sent each topic whole (`state`), then changes (`patch`) flushed on a tick. A page
whose socket holds more than `BEHIND` unread bytes is skipped and resent the whole state later.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from .outbound import MAX_WRITE_BUFFER, encode

log = logging.getLogger("neoaprs.web")

TICK = 0.1  # seconds between flushes
BEHIND = MAX_WRITE_BUFFER // 8  # a socket holding this many unread bytes is behind

# Failures already logged, bounded.
TOLD_LIMIT = 200


def _report(told: set[str], what: str, exc: Exception) -> None:
    """Log a failure from inside its `except`: the first time with the traceback, then one line."""
    if what in told:
        log.warning("%s (again): %r", what, exc)
        return
    if len(told) >= TOLD_LIMIT:
        told.clear()
    told.add(what)
    log.exception(what)


class Link(Protocol):
    def send_text(self, text: str) -> None: ...
    def buffered(self) -> int: ...


@dataclass(eq=False)
class Peer:
    link: Link
    topics: set[str] = field(default_factory=set)
    stale: set[str] = field(default_factory=set)  # skipped while behind; resent whole later


class Topic:
    """A piece of state the pages follow; `build` makes the whole value, `item` one keyed item."""

    def __init__(
        self,
        name: str,
        build: Callable[[], Any],
        item: Callable[[str], Any | None] | None = None,
        interval: float = 0.0,
    ) -> None:
        self.name = name
        self.build = build
        self.item = item
        self.interval = interval  # least time between two patches
        self.rev = 0
        self.last = float("-inf")  # when the latest patch was made
        self._whole = False
        self._keys: dict[str, None] = {}  # in the order they changed
        self._told: set[str] = set()  # keys whose build failure was already logged

    def touch(self, key: str | None = None) -> None:
        """Mark the whole topic (a `replace`) or one key as changed."""
        if key is None or self.item is None:
            self._whole = True
            self._keys.clear()
        elif not self._whole:
            self._keys[key] = None

    @property
    def pending(self) -> bool:
        return self._whole or bool(self._keys)

    def take(self) -> list[dict[str, Any]]:
        """Return the ops since the last patch; an item that cannot be built is left out."""
        ops: list[dict[str, Any]]
        if self._whole or self.item is None:
            ops = [{"op": "replace", "value": self.build()}]
        else:
            ops = []
            for key in self._keys:
                try:
                    value = self.item(key)
                except Exception as exc:
                    _report(self._told, f"the item {key} of {self.name} could not be built", exc)
                    continue
                ops.append({"op": "del", "key": key} if value is None else {"op": "set", "key": key, "value": value})
        self._whole = False
        self._keys.clear()
        self.rev += 1
        return ops

    def discard(self) -> None:
        """Drop pending changes unbuilt; a page that attaches later gets the whole value."""
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
        self._told: set[str] = set()  # topics whose failure was already logged

    def add(self, topic: Topic) -> Topic:
        if topic.name in self.topics:
            raise ValueError(f"{topic.name} is a topic of the hub already")
        self.topics[topic.name] = topic
        return topic

    # pages
    def attach(self, link: Link) -> None:
        """Make the page follow every topic and send each whole."""
        peer = self._peers[link] = Peer(link, set(self.topics))
        for topic in self.topics.values():
            self.deliver(peer, topic.state())

    def detach(self, link: Link) -> None:
        self._peers.pop(link, None)

    def subscribe(self, link: Link, names: list[str]) -> list[str]:
        """Make the page follow these topics, sending each whole; return the unknown names."""
        peer = self._peers.get(link)
        if peer is None:
            return []
        names = list(dict.fromkeys(names))  # each once, in the order given
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
        """Return how many pages follow the topic."""
        return sum(1 for p in self._peers.values() if name in p.topics)

    # changes
    def changed(self, name: str, key: str | None = None) -> None:
        """Record a change of the topic (one key or all); pages are told on the next tick."""
        self.topics[name].touch(key)
        self._schedule(TICK)

    def _schedule(self, delay: float) -> None:
        if self._timer is None:
            try:
                self._timer = asyncio.get_running_loop().call_later(delay, self._tick)
            except RuntimeError:
                # No loop: nothing is listening, and state is built when a page asks.
                pass

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
        """Stop ticking."""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def flush(self) -> float | None:
        """Send each due topic's patch; return the delay until the next flush, None if none waits."""
        now = self.clock()
        wait: float | None = None
        behind: dict[Peer, bool] = {}
        for topic in self.topics.values():
            try:
                due = self._flush_topic(topic, now, behind)
            except Exception as exc:
                _report(self._told, f"the topic {topic.name} could not be told to the pages", exc)
                topic.discard()
                continue
            if due is not None:
                wait = due if wait is None else min(wait, due)
        if self._catch_up(behind):
            wait = TICK if wait is None else min(wait, TICK)
        return wait

    def _flush_topic(self, topic: Topic, now: float, behind: dict[Peer, bool]) -> float | None:
        """Send the topic's patch when due; return the wait if not yet due."""
        if not topic.pending:
            return None
        if not self.following(topic.name):
            topic.discard()  # with no page open nothing is built
            return None
        due = topic.last + topic.interval - now
        if due > 0:
            return due
        topic.last = now
        self._tell(topic, topic.take(), behind)
        return None

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
        """Send the whole topic to pages that caught up; return True if some are still behind."""
        waiting = False
        for peer in list(self._peers.values()):
            if not peer.stale:
                continue
            if self._is_behind(peer, behind):
                waiting = True
                continue
            # Topic order matters: the radios arrive before the settings form that uses them.
            for name in [name for name in self.topics if name in peer.stale]:
                self.deliver(peer, self.topics[name].state())
            peer.stale.clear()
        return waiting

    def _is_behind(self, peer: Peer, known: dict[Peer, bool]) -> bool:
        if peer not in known:
            try:
                known[peer] = peer.link.buffered() > self.behind
            except Exception:
                known[peer] = True  # a socket that cannot report its backlog is not written to
        return known[peer]

    def deliver(self, peer: Peer, message: dict[str, Any]) -> None:
        self._deliver(peer, encode(message))

    @staticmethod
    def _deliver(peer: Peer, text: str) -> None:
        """Send to one page; a failure on its socket does not stop the others."""
        try:
            peer.link.send_text(text)
        except Exception:
            log.exception("a frame could not be sent to a page")
