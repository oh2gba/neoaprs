"""What the operator says about a station, apart from what its packets say: a path, a timeout of its own and whether it is RF only. Each is optional and independent, and a station with none has no entry.

The path: the digipeaters a message (and its ack) to the station goes by way of; empty is direct, which is not the same as none set (then it has `beacon/path`). The timeout: the minutes after its last
position that the station leaves the map; 0 is never, none set means the fixed 180 minutes (`HIDE_AFTER_MIN` of config.py) (the page does the hiding, the daemon only keeps and tells the number; the daily prune never removes a
station with a timeout of 0). RF only: everything we send to the station (a message and each attempt of it, its acks, the answers to its queries) goes by its path with RFONLY
added at the end, which iGates that honour it do not put on the internet; the email gateway EMAIL-2 is on the internet and can never be RF only. They are operator data, kept in the table `station_pref` of the message log's database, read once at the start and written through; `changed` tells (call, pref) when a station's
entry is set or changes and (call, None) when its last part is cleared and the entry is gone."""
import asyncio
from collections.abc import Callable
from dataclasses import replace

from neoaprs.ax25 import MAX_PATH
from neoaprs.callsign import CallsignError
from neoaprs.config import MAX_HIDE_AFTER_MIN, Config
from neoaprs.message import EMAIL_GATEWAY, MessagingError, normal_call, normal_path
from neoaprs.messagelog import MessageLog
from neoaprs.pref import Pref
from neoaprs.route import rf_only_path
from neoaprs.signal import Signal

MAX_NAME = 9                          # the longest name that is not a call: an object's


def _key(name: str) -> str:
    """The station the entry is for: a call in its normal form, else (an object or an item has a name that is no call) the name as it is."""
    try:
        return normal_call(name)
    except CallsignError:
        text = name.strip()
        if not text or len(text) > MAX_NAME or not text.isprintable():
            raise MessagingError(f"{name!r} is not a call or the name of an object (1 to {MAX_NAME} printable characters)") from None
        return text


class PrefBook:
    def __init__(self, messagelog: MessageLog, config: Callable[[], Config]) -> None:
        self._log = messagelog
        self._config = config
        self._own: dict[str, Pref] = {}
        self._lock = asyncio.Lock()                    # a change reads the entry and writes it back: two at once for one station must not lose one
        self.changed: Signal[[str, Pref | None]] = Signal("prefs_changed")

    async def load(self) -> None:
        self._own = {call: Pref(None if path is None else normal_path(path), hide, rf_only) for call, (path, hide, rf_only) in (await self._log.prefs()).items()}

    # ---- what there is
    def all(self) -> dict[str, Pref]:
        """The stations that have an entry, by call."""
        return dict(self._own)

    def paths(self) -> dict[str, tuple[str, ...]]:
        """The stations that have a path of their own, by call."""
        return {call: pref.path for call, pref in self._own.items() if pref.path is not None}

    def path_for(self, call: str) -> tuple[str, ...]:
        """The path everything we send to the station goes by: its own when it has one, else `beacon/path`; with RFONLY at the end when the station is RF only. Raises MessagingError when that would be more than
        8 digipeaters ("path too long for RF only"): nothing is sent then."""
        try:
            own = self._own.get(normal_call(call))
        except ValueError:
            own = None
        path = self._config().beacon_path_calls if own is None or own.path is None else own.path
        if own is None or not own.rf_only:
            return path
        added = rf_only_path(path)
        if len(added) > MAX_PATH:
            raise MessagingError(f"path too long for RF only: {len(path)} digipeaters and RFONLY make more than the {MAX_PATH} a path may have")
        return added

    def never_hidden(self) -> frozenset[str]:
        """The stations whose own timeout is 0, which the daily prune keeps in the station book."""
        return frozenset(call for call, pref in self._own.items() if pref.hide_after_min == 0)

    # ---- the path
    async def set_path(self, call: str, path: str) -> tuple[str, ...]:
        """Gives the station a path of its own: 0 to 8 digipeater calls separated by commas, checked as beacon/path is; empty is direct. Raises MessagingError with the reason; the path as it is kept."""
        try:
            key, calls = normal_call(call), normal_path(path)
        except ValueError as e:
            raise MessagingError(str(e)) from None
        await self._change(key, lambda pref: replace(pref, path=calls), "the path could not be kept", quiet=False)
        return calls

    async def clear_path(self, call: str) -> None:
        """Takes the station's own path away: it has `beacon/path` again. A station without one is not an error."""
        try:
            key = normal_call(call)
        except ValueError as e:
            raise MessagingError(str(e)) from None
        await self._change(key, lambda pref: replace(pref, path=None), "the path could not be removed", quiet=True)

    # ---- the timeout
    async def set_timeout(self, call: str, minutes: int) -> int:
        """Gives the station a timeout of its own: minutes (0 to 10080, 0 is never). Raises MessagingError with the reason."""
        key = _key(call)
        if not 0 <= minutes <= MAX_HIDE_AFTER_MIN:
            raise MessagingError(f"{minutes} is not between 0 and {MAX_HIDE_AFTER_MIN} minutes")
        await self._change(key, lambda pref: replace(pref, hide_after_min=minutes), "the timeout could not be kept", quiet=False)
        return minutes

    async def clear_timeout(self, call: str) -> None:
        """Takes the station's own timeout away: it has the fixed 180 minutes again. A station without one is not an error."""
        await self._change(_key(call), lambda pref: replace(pref, hide_after_min=None), "the timeout could not be removed", quiet=True)

    # ---- RF only
    async def set_rf_only(self, call: str, on: bool) -> None:
        """Makes everything we send to the station RF only, or not. Raises MessagingError with the reason: the call is none, or it is the email gateway, which is on the internet."""
        try:
            key = normal_call(call)
        except ValueError as e:
            raise MessagingError(str(e)) from None
        if on and key == EMAIL_GATEWAY:
            raise MessagingError(f"{EMAIL_GATEWAY} cannot be RF only: the email gateway is on the internet")
        await self._change(key, lambda pref: replace(pref, rf_only=on), "RF only could not be kept", quiet=not on)

    async def _change(self, key: str, make: Callable[[Pref], Pref], failure: str, quiet: bool) -> None:
        """The entry of the station as `make` says, kept first and then held; an entry with nothing in it is removed. A setting is always told (the page waits for it); a clearing is `quiet` when
        there was nothing to clear."""
        async with self._lock:
            before = self._own.get(key)
            after = make(before or Pref())
            if quiet and after == (before or Pref()):
                return
            empty = after == Pref()
            saved = await (self._log.forget_pref(key) if empty else self._log.save_pref(key, None if after.path is None else ",".join(after.path), after.hide_after_min, after.rf_only))
            if not saved:
                raise MessagingError(f"{failure}: the database is not open")
            if empty:
                del self._own[key]
            else:
                self._own[key] = after
            self.changed.emit(key, None if empty else after)
