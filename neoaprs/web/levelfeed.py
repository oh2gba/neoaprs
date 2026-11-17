"""The pages that show a Sound card radio's receive level (`radio_level`, neoaprs/web/radiowire.py): each is sent the level its Direwolf says every LEVEL_NOW_MS (neoaprs/direwolfprogram.py `LevelNow`) while it asks,
as `radio_level` messages that name the radio, in the pattern of the scope's feed (neoaprs/web/scopefeed.py): a page whose socket holds more than the hub's `BEHIND` of what it has not read is sent no level, which it
would only add to the wait (the next one tells it what it missed); a page that begins to look is sent the level as it is now at once; a page that leaves is forgotten. While no page looks at a radio nothing is sent
and its level is not followed. Every other page has the radio's row in the topic `radios`, whose `modem.rx_level` changes every two seconds."""
from collections.abc import Callable, Mapping
from typing import Protocol

from neoaprs.direwolfprogram import LevelNow
from neoaprs.radiospec import RadioId

from .hub import BEHIND
from .session import Connection


class Leveled(Protocol):
    """A modem that says its receive level as it is now (neoaprs/direwolfmodem.py)."""
    level_now: LevelNow


def level_message(radio: RadioId, level: int | None) -> dict[str, object]:
    """The `radio_level` message: the radio's level on Direwolf's scale, null while its Direwolf does not run."""
    return {"type": "radio_level", "radio": radio, "level": level}


class LevelFeed:
    """The pages that look at one radio's level, and the level they are sent."""

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
    """The feeds of the radios' levels (`radio_level`): one for each radio some page looks at, followed while one does: `wire` connects a feed to its modem's level, or lets go of it (neoaprs/web/topics.py,
    which connects)."""

    def __init__(self, wire: Callable[[LevelFeed, Leveled, bool], None]) -> None:
        self._wire = wire
        self._feeds: dict[RadioId, tuple[LevelFeed, Leveled]] = {}

    def ask(self, conn: Connection, radio: RadioId, modem: Leveled) -> None:
        """This page shows the radio's level: it is sent the level now, and every level from then on. A page that has left meanwhile is not taken (the command ran after it closed)."""
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
        """This page shows the radio's level no more; the radio's level is no longer followed when no page looks."""
        held = self._feeds.get(radio)
        if held is not None:
            held[0].pages.discard(conn)
            if not held[0].pages:
                self._drop(radio)

    def forget(self, conn: Connection) -> None:
        """The page left: every feed forgets it."""
        for radio in list(self._feeds):
            self.stop(conn, radio)

    def pages(self, radio: RadioId) -> int:
        """How many pages look at the radio's level."""
        held = self._feeds.get(radio)
        return 0 if held is None else len(held[0].pages)

    def keep(self, modems: Mapping[RadioId, Leveled]) -> None:
        """The radios' modems as they are now: a radio whose modem is another one (its type changed) is followed on the new one by the pages that look, and those of a radio removed, or of one that has no level
        now, are told it has none."""
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
        """The pages are told nothing more: every radio's level is let go."""
        for radio in list(self._feeds):
            self._drop(radio)
