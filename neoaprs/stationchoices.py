"""The operator's radio by station (plan §2, "A choice that names a radio which is off or gone"): chosen on the page, told to the page with the station, kept in a state row (config.MESSAGE_RADIOS, which the
composition root writes) and put back on the stations of the book at the start. A choice is a radio's id, and the row keeps the ids since migration 31 (`{"OH2GAX-2": 2}`); the station's own field
(`Station.message_radio`, which the wire carries until wave 4) says today's word of radios 1 and 2 (`fm`, `hf`) and nothing for any other radio. The radio registry (neoaprs/radioregistry.py) is
one of these with the radios it has as the ones that can be chosen; a set made by itself (the tests' two radios of before, neoaprs/radios.py) keeps the row in today's words and lets radios 1 and 2
alone be chosen. No I/O."""
import json
from collections.abc import Awaitable, Callable

from .packet import radio_word
from .radiotype import FM_ID, HF_ID, RadioId, radio_id_of
from .stationbook import StationBook

TWO_RADIOS = (FM_ID, HF_ID)          # what can be chosen where nothing else is said: today's two radios


class StationChoices:
    def __init__(self, book: StationBook, remember: Callable[[str], None] = lambda text: None, flush: Callable[[], Awaitable[None]] | None = None, *,
                 by_id: bool = False, known: Callable[[RadioId], bool] = lambda id: id in TWO_RADIOS) -> None:
        self._book = book
        self._remember, self._wait_written = remember, flush                     # keep the choices (the state row), and wait for it
        self._by_id = by_id                                                       # the row keeps the radios' ids (the registry), else today's words (the two radios of before)
        self._known = known if by_id else (lambda id: id in TWO_RADIOS)          # whether a radio can be chosen: one the registry has; the two of before have no other
        self._choices: dict[str, RadioId] = {}                                    # the choices in force, by call: what the row says (a station the book lets go takes its choice with it)
        self._unplaced: dict[str, RadioId] = {}                                   # by call: a choice of a radio not in force in a run whose radios could not be read, kept in the row as it is

    def choice(self, call: str) -> RadioId | None:
        """The radio the operator chose for messages to the station, as it is stored; None for the daemon's own choice."""
        station = self._book.get(call)
        return None if station is None else self._choices.get(station.call, radio_id_of(station.message_radio))

    def choose(self, call: str, radio: RadioId | str | None) -> bool:
        """The radio messages to the station go out on from now on (None, or "", gives the choice back to the daemon), told to the page with the station and kept across a restart; False for a station that
        is not in the book and for a radio that cannot be chosen. Today's words `fm` and `hf` name radios 1 and 2 (the page says them until its commands carry ids)."""
        station = self._book.get(call)
        id = radio_id_of(radio) if isinstance(radio, str) else radio
        if station is None or (isinstance(radio, str) and radio and id is None) or (id is not None and not self._known(id)):
            return False
        station.message_radio = radio_word(id)
        self._unplaced.pop(station.call, None)
        if id is not None:
            self._choices[station.call] = id
        else:
            self._choices.pop(station.call, None)
        self._book.changed.emit(station)
        self._remember(self.choices_text())
        return True

    def forget(self, call: str) -> None:
        """The book let the station go (Forget, the daily prune): its choice goes too, from the row as well, so that a restart does not bring it back to a station heard again meanwhile."""
        if (self._choices.pop(call, None), self._unplaced.pop(call, None)) != (None, None):
            self._remember(self.choices_text())

    def forget_all(self) -> None:
        """The book let every station go (Forget all)."""
        if self._choices or self._unplaced:
            self._choices.clear()
            self._unplaced.clear()
            self._remember(self.choices_text())

    def forget_radio(self, radio: RadioId) -> list[str]:
        """The radio was removed: every station's choice of it is the daemon's own again, told to the page with the station; the calls. The row is not written: the removal took the radio out of it in its
        own transaction (radiosql.remove_radio)."""
        calls = [call for call, id in self._choices.items() if id == radio]
        self._unplaced = {call: id for call, id in self._unplaced.items() if id != radio}
        for call in calls:
            del self._choices[call]
            station = self._book.get(call)
            if station is not None:
                station.message_radio = ""
                self._book.changed.emit(station)
        return calls

    def choices_text(self) -> str:
        """The choices of the stations in the book, as the state row keeps them: by id (`{"OH2GAX-2": 2}`), or in today's words for the two radios of before; with them the choices kept as they are
        in a run whose radios could not be read."""
        return json.dumps({call: id if self._by_id else radio_word(id) for call, id in {**self._unplaced, **self._choices}.items()}, sort_keys=True)

    async def flush(self) -> None:
        """Waits until a choice being written is written (the stop)."""
        if self._wait_written is not None:
            await self._wait_written()

    def restore(self, text: str | None, *, keep_unknown: bool = False) -> None:
        """The choices kept in the state row, on the stations of the book (at the start, once the book is seeded): an id, or today's word of radios 1 and 2 (a row of before); a row that is not one, and a
        radio that cannot be chosen, is no choice. `keep_unknown`: the radios could not be read (the stand-in), so a choice of a radio not in force is no choice for this run, and the row keeps it as it is
        until the station is chosen for or forgotten."""
        try:
            kept = json.loads(text or "{}")
        except ValueError:
            return
        for call, value in (kept.items() if isinstance(kept, dict) else ()):
            station = self._book.get(str(call))
            id = radio_id_of(value) if isinstance(value, str) else value if isinstance(value, int) and not isinstance(value, bool) else None
            if station is not None and id is not None and self._known(id):
                station.message_radio, self._choices[station.call] = radio_word(id), id
            elif station is not None and id is not None and keep_unknown:
                self._unplaced[station.call] = id
