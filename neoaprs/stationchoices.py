"""The operator's radio by station (plan §2, "A choice that names a radio which is off or gone"): chosen on the page, told to the page with the station, kept in a state row (config.MESSAGE_RADIOS, which the
composition root writes) and put back on the stations of the book at the start; a call the book does not hold keeps its choice by call (plan rule 3.2), until it is forgotten. A choice is a radio's id, and the
row keeps the ids since migration 31 (`{"OH2GAX-2": 2}`). The radio registry (neoaprs/radioregistry.py) is one of these with the radios it has as the ones that can be chosen (`known`). No I/O."""
import json
from collections.abc import Awaitable, Callable

from .radiotype import RadioId, radio_id_of
from .stationbook import StationBook


class StationChoices:
    def __init__(self, book: StationBook, remember: Callable[[str], None] = lambda text: None, flush: Callable[[], Awaitable[None]] | None = None, *, known: Callable[[RadioId], bool]) -> None:
        self._book = book
        self._remember, self._wait_written = remember, flush                     # keep the choices (the state row), and wait for it
        self._known = known                                                       # whether a radio can be chosen: one the registry has
        self._choices: dict[str, RadioId] = {}                                    # the choices in force, by call: what the row says (a station the book lets go takes its choice with it)

    def choice(self, call: str) -> RadioId | None:
        """The radio the operator chose for messages to the station, as it is stored, for a call the book holds or not; None for the daemon's own choice."""
        station = self._book.get(call)
        return self._choices.get(call if station is None else station.call)

    def choose(self, call: str, radio: RadioId | None) -> bool:
        """The radio messages to the station go out on from now on (None gives the choice back to the daemon), told to the page with the station and kept across a restart; False for a radio that
        cannot be chosen. A call the book does not hold keeps its choice by call (plan rule 3.2), and its station has it once it is heard."""
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
        """The book let the station go (Forget, the daily prune): its choice goes too, from the row as well, so that a restart does not bring it back to a station heard again meanwhile."""
        if self._choices.pop(call, None) is not None:
            self._remember(self.choices_text())

    def forget_all(self) -> None:
        """The book let every station go (Forget all)."""
        if self._choices:
            self._choices.clear()
            self._remember(self.choices_text())

    def forget_radio(self, radio: RadioId) -> list[str]:
        """The radio was removed: every station's choice of it is the daemon's own again, told to the page with the station; the calls. The row is not written: the removal took the radio out of it in its
        own transaction (radiosql.remove_radio)."""
        calls = [call for call, id in self._choices.items() if id == radio]
        for call in calls:
            del self._choices[call]
            station = self._book.get(call)
            if station is not None:
                self._book.changed.emit(station)
        return calls

    def choices_text(self) -> str:
        """The choices by call, as the state row keeps them: by id (`{"OH2GAX-2": 2}`)."""
        return json.dumps(self._choices, sort_keys=True)

    async def flush(self) -> None:
        """Waits until a choice being written is written (the stop)."""
        if self._wait_written is not None:
            await self._wait_written()

    def restore(self, text: str | None) -> None:
        """The choices kept in the state row, on the stations of the book (at the start, once the book is seeded): an id, or today's word of radios 1 and 2 (a row of before); a row that is not one, and a
        radio that cannot be chosen, is no choice."""
        try:
            kept = json.loads(text or "{}")
        except ValueError:
            return
        for call, value in (kept.items() if isinstance(kept, dict) else ()):
            station = self._book.get(str(call))
            id = radio_id_of(value) if isinstance(value, str) else value if isinstance(value, int) and not isinstance(value, bool) else None
            if station is not None and id is not None and self._known(id):
                self._choices[station.call] = id
            elif station is None and id is not None and self._known(id):
                self._choices[str(call)] = id
