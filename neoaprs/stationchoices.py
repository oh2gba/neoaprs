"""The operator's radio per station (plan section 2).

Kept in a state row (config.MESSAGE_RADIOS) as radio ids (`{"OH2GAX-2": 2}`); a call the book
does not hold keeps its choice by call until forgotten. No I/O.
"""

import json
from collections.abc import Awaitable, Callable

from .radiotype import RadioId, radio_id_of
from .stationbook import StationBook


class StationChoices:
    def __init__(
        self,
        book: StationBook,
        remember: Callable[[str], None] = lambda text: None,
        flush: Callable[[], Awaitable[None]] | None = None,
        *,
        known: Callable[[RadioId], bool],
    ) -> None:
        self._book = book
        # keep the choices (the state row); wait for it
        self._remember, self._wait_written = remember, flush
        self._known = known  # whether a radio can be chosen: one the registry has
        # the choices in force, by call: what the row says (a station the book lets go takes its
        # choice with it)
        self._choices: dict[str, RadioId] = {}

    def choice(self, call: str) -> RadioId | None:
        """Return the radio the operator chose for messages to the station, or None."""
        station = self._book.get(call)
        return self._choices.get(call if station is None else station.call)

    def choose(self, call: str, radio: RadioId | None) -> bool:
        """Set the radio messages to the station go out on (None: the daemon chooses).

        Return False for a radio that cannot be chosen.
        """
        station = self._book.get(call)
        if radio is not None and not self._known(radio):
            return False
        key = call if station is None else station.call
        if radio is not None:
            self._choices[key] = radio
        else:
            self._choices.pop(key, None)
        if station is not None:
            self._book.changed.emit(station)
        self._remember(self.choices_text())
        return True

    def forget(self, call: str) -> None:
        """The book let the station go (Forget, the daily prune): its choice goes too."""
        if self._choices.pop(call, None) is not None:
            self._remember(self.choices_text())

    def forget_all(self) -> None:
        """The book let every station go (Forget all)."""
        if self._choices:
            self._choices.clear()
            self._remember(self.choices_text())

    def forget_radio(self, radio: RadioId) -> list[str]:
        """The radio was removed: choices of it revert to the daemon's.

        The row is not written: radiosql.remove_radio took the radio out of it.
        """
        calls = [call for call, id in self._choices.items() if id == radio]
        for call in calls:
            del self._choices[call]
            station = self._book.get(call)
            if station is not None:
                self._book.changed.emit(station)
        return calls

    def choices_text(self) -> str:
        """Return the choices by call as the state row keeps them: by id (`{"OH2GAX-2": 2}`)."""
        return json.dumps(self._choices, sort_keys=True)

    async def flush(self) -> None:
        """Wait until a choice being written is written (the stop)."""
        if self._wait_written is not None:
            await self._wait_written()

    def restore(self, text: str | None) -> None:
        """Put the choices kept in the state row on the stations of the book (at the start)."""
        try:
            kept = json.loads(text or "{}")
        except ValueError:
            return
        for call, value in kept.items() if isinstance(kept, dict) else ():
            station = self._book.get(str(call))
            id = (
                radio_id_of(value)
                if isinstance(value, str)
                else value
                if isinstance(value, int) and not isinstance(value, bool)
                else None
            )
            if station is not None and id is not None and self._known(id):
                self._choices[station.call] = id
            elif station is None and id is not None and self._known(id):
                self._choices[str(call)] = id
