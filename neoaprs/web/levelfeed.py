"""Send a Sound card radio's receive level to the pages that look at it, as `radio_level` messages.

A page more than the hub's `BEHIND` bytes behind is skipped. A new viewer gets the current level
at once; the level is followed only while some page looks.
"""

from collections.abc import Callable, Mapping
from typing import Protocol

from neoaprs.direwolfprogram import LevelNow
from neoaprs.radiospec import RadioId

from .hub import BEHIND
from .session import Connection


class Leveled(Protocol):
    level_now: LevelNow


def level_message(radio: RadioId, level: int | None) -> dict[str, object]:
    """Return the `radio_level` message.

    The level is on Direwolf's scale, None while it is not running.
    """
    return {"type": "radio_level", "radio": radio, "level": level}


class LevelFeed:
    def __init__(self, radio: RadioId, level: LevelNow) -> None:
        self.radio, self.level = radio, level
        self.pages: set[Connection] = set()

    def said(self, level: int | None) -> None:
        for conn in list(self.pages):
            self.send(conn, level)

    def send(self, conn: Connection, level: int | None) -> None:
        if conn.buffered() <= BEHIND:
            conn.send(level_message(self.radio, level))


class RadioLevels:
    """One level feed per radio that a page looks at; `wire` connects or releases a feed's modem."""

    def __init__(self, wire: Callable[[LevelFeed, Leveled, bool], None]) -> None:
        self._wire = wire
        self._feeds: dict[RadioId, tuple[LevelFeed, Leveled]] = {}

    def ask(self, conn: Connection, radio: RadioId, modem: Leveled) -> None:
        """Send the page the radio's level now and on each change.

        A page that already closed is ignored.
        """
        if conn.closed:
            return
        held = self._feeds.get(radio)
        if held is None or held[1] is not modem:
            self._drop(radio)
            feed = LevelFeed(radio, modem.level_now)
            self._wire(feed, modem, True)
            held = self._feeds[radio] = (feed, modem)
        held[0].pages.add(conn)
        held[0].send(conn, modem.level_now.value)

    def stop(self, conn: Connection, radio: RadioId) -> None:
        """Stop sending the level to the page; stop following it when no page is left."""
        held = self._feeds.get(radio)
        if held is not None:
            held[0].pages.discard(conn)
            if not held[0].pages:
                self._drop(radio)

    def forget(self, conn: Connection) -> None:
        """Remove the page from every feed."""
        for radio in list(self._feeds):
            self.stop(conn, radio)

    def pages(self, radio: RadioId) -> int:
        """Return how many pages look at the radio's level."""
        held = self._feeds.get(radio)
        return 0 if held is None else len(held[0].pages)

    def keep(self, modems: Mapping[RadioId, Leveled]) -> None:
        """Follow the current modems: pages move to a replaced modem or get None if none remains."""
        for radio, (feed, modem) in list(self._feeds.items()):
            if (now := modems.get(radio)) is modem:
                continue
            self._drop(radio)
            for conn in feed.pages:
                if now is not None:
                    self.ask(conn, radio, now)
                else:
                    feed.send(conn, None)

    def _drop(self, radio: RadioId) -> None:
        held = self._feeds.pop(radio, None)
        if held is not None:
            self._wire(*held, False)

    def disconnect(self) -> None:
        """Release every radio's level."""
        for radio in list(self._feeds):
            self._drop(radio)
