"""The topic `call_routes`: how messages go to a call the page is shown no station row of.

A call has an entry while it has a radio chosen or a path set on a radio and no row is shown of
it (never heard, or heard only in what a tick leaves out); once its row is shown, it says the same."""

from collections.abc import Callable, Iterable
from typing import Any

from neoaprs.radiotype import RadioId

from .views import StationRadios


class CallRoutes:
    def __init__(
        self,
        held: Callable[[str], bool],
        chosen: Callable[[], Iterable[str]],
        paths: Callable[[RadioId], Iterable[str]],
        radio_ids: Callable[[], Iterable[RadioId]],
        radios: StationRadios,
    ) -> None:
        self._held, self._chosen, self._paths, self._radio_ids, self._radios = held, chosen, paths, radio_ids, radios
        # the calls the pages were last told an entry of
        self.told: set[str] = set()

    def _calls(self) -> set[str]:
        calls = set(self._chosen())
        for radio in self._radio_ids():
            calls.update(self._paths(radio))
        return {call for call in calls if not self._held(call)}

    def whole(self) -> dict[str, Any]:
        self.told = self._calls()
        return {call: self._entry(call) for call in sorted(self.told)}

    def item(self, call: str) -> dict[str, Any] | None:
        if call not in self._calls():
            self.told.discard(call)
            return None
        self.told.add(call)
        return self._entry(call)

    def _entry(self, call: str) -> dict[str, Any]:
        return {
            "radio_choice": self._radios.choice(call),
            "radio_now": self._radios.now(call),
            "paths": {str(id): ",".join(path) for id, path in sorted(self._radios.paths(call).items())},
        }
