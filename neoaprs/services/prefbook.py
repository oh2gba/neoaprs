"""What the operator says about a station, apart from what its packets say: a path of its own, whether it is RF only, and when to be alerted about it (services/stationalerts.py fires the alert). Each is optional and
independent, and a station with none has no entry.

The path: the digipeaters a message (and its ack) to the station goes by way of; empty is direct (chosen as DIRECT), which is not the same as none set (then the first attempts of a message go by the path lately heard to reach the station, the rest and everything else by `beacon/path`). RF only: everything we send to the station (a message and each attempt of it, its acks, the answers to its queries) goes by its path with RFONLY
added at the end, which iGates that honour it do not put on the internet; the email gateway EMAIL-2 is on the internet and can never be RF only. They are operator data, kept in the table `station_pref` of the message log's database, read once at the start and written through; `changed` tells (call, pref) when a station's
entry is set or changes and (call, None) when its last part is cleared and the entry is gone."""
import asyncio
from collections.abc import Callable
from dataclasses import replace

from neoaprs.ax25 import MAX_PATH
from neoaprs.callsign import normal_name
from neoaprs.clock import Clock, utcnow
from neoaprs.config import Config
from neoaprs.message import EMAIL_GATEWAY, MessagingError, normal_path, path_choice
from neoaprs.messagelog import MessageLog
from neoaprs.pref import ALERT_KM_MAX, ALERT_KM_MIN, Alert, Pref
from neoaprs.route import Deliveries, automatic_path, rf_only_path
from neoaprs.signal import Signal

class PrefBook:
    def __init__(self, messagelog: MessageLog, config: Callable[[], Config], heard: Callable[[str], Deliveries | None] = lambda call: None, clock: Clock = utcnow) -> None:
        self._log = messagelog
        self._config = config
        self._heard = heard                            # how the packets of a station reached us (the station book's Deliveries), None for a station not heard
        self._clock = clock
        self._own: dict[str, Pref] = {}
        self._lock = asyncio.Lock()                    # a change reads the entry and writes it back: two at once for one station must not lose one
        self.changed: Signal[[str, Pref | None]] = Signal("prefs_changed")

    async def load(self) -> None:
        self._own = {call: Pref(None if path is None else normal_path(path), rf_only, alert) for call, (path, rf_only, alert) in (await self._log.prefs()).items()}

    # ---- what there is
    def all(self) -> dict[str, Pref]:
        """The stations that have an entry, by call."""
        return dict(self._own)

    def paths(self) -> dict[str, tuple[str, ...]]:
        """The stations that have a path of their own, by call."""
        return {call: pref.path for call, pref in self._own.items() if pref.path is not None}

    def path_for(self, call: str, attempt: int | None = None) -> tuple[str, ...]:
        """The path everything we send to the station goes by: its own when it has one, else (for attempt number `attempt` of a message, 1 for the first, when it is given) the path that has lately been heard to
        reach the station for the first attempts (route.automatic_path), else `beacon/path`; with RFONLY at the end when the station is RF only. Raises MessagingError when that would be more than
        8 digipeaters ("path too long for RF only"): nothing is sent then."""
        try:
            key = normal_name(call)
            own = self._own.get(key)
        except ValueError:
            key, own = "", None
        heard = None
        if own is None or own.path is None:
            if attempt is not None and key != EMAIL_GATEWAY:
                heard = automatic_path(self._heard(key), self._clock(), attempt)
        path = (self._config().beacon_path_calls if heard is None else heard) if own is None or own.path is None else own.path
        if own is None or not own.rf_only:
            return path
        added = rf_only_path(path)
        if len(added) > MAX_PATH:
            raise MessagingError(f"path too long for RF only: {len(path)} digipeaters and RFONLY make more than the {MAX_PATH} a path may have")
        return added

    # ---- the path
    async def set_path(self, call: str, path: str) -> tuple[str, ...]:
        """Gives the station a path of its own: 1 to 8 digipeater calls separated by commas, checked as beacon/path is, or DIRECT for no digipeaters at all; an empty path takes the station's own away (it is
        automatic again), as clear_path does. Raises MessagingError with the reason; the path as it is kept (empty for direct)."""
        try:
            key, calls = normal_name(call), path_choice(path)
        except ValueError as e:
            raise MessagingError(str(e)) from None
        if calls is None:
            await self.clear_path(call)
            return ()
        await self._change(key, lambda pref: replace(pref, path=calls), "the path could not be kept", quiet=False)
        return calls

    async def clear_path(self, call: str) -> None:
        """Takes the station's own path away: it has `beacon/path` again. A station without one is not an error."""
        try:
            key = normal_name(call)
        except ValueError as e:
            raise MessagingError(str(e)) from None
        await self._change(key, lambda pref: replace(pref, path=None), "the path could not be removed", quiet=True)

    # ---- RF only
    async def set_rf_only(self, call: str, on: bool) -> None:
        """Makes everything we send to the station RF only, or not. Raises MessagingError with the reason: the call is none, or it is the email gateway, which is on the internet."""
        try:
            key = normal_name(call)
        except ValueError as e:
            raise MessagingError(str(e)) from None
        if on and key == EMAIL_GATEWAY:
            raise MessagingError(f"{EMAIL_GATEWAY} cannot be RF only: the email gateway is on the internet")
        await self._change(key, lambda pref: replace(pref, rf_only=on), "RF only could not be kept", quiet=not on)

    # ---- the alert
    async def set_alert(self, call: str, alert: Alert) -> None:
        """When to tell the operator about the station (services/stationalerts.py watches it); an alert that watches nothing takes the station's away. Raises MessagingError with the reason: the call is none, or the
        distance is not a whole number of kilometres from ALERT_KM_MIN to ALERT_KM_MAX."""
        try:
            key = normal_name(call)
        except ValueError as e:
            raise MessagingError(str(e)) from None
        if alert.within_km is not None and not ALERT_KM_MIN <= alert.within_km <= ALERT_KM_MAX:
            raise MessagingError(f"the distance of an alert is {ALERT_KM_MIN} to {ALERT_KM_MAX} km, not {alert.within_km}", "alert.km_range", km=alert.within_km, min=ALERT_KM_MIN, max=ALERT_KM_MAX)
        await self._change(key, lambda pref: replace(pref, alert=alert if alert.any else None), "the alert could not be kept", quiet=not alert.any)

    async def _change(self, key: str, make: Callable[[Pref], Pref], failure: str, quiet: bool) -> None:
        """The entry of the station as `make` says, kept first and then held; an entry with nothing in it is removed. A setting is always told (the page waits for it); a clearing is `quiet` when
        there was nothing to clear."""
        async with self._lock:
            before = self._own.get(key)
            after = make(before or Pref())
            if quiet and after == (before or Pref()):
                return
            empty = after == Pref()
            saved = await (self._log.forget_pref(key) if empty else self._log.save_pref(key, None if after.path is None else ",".join(after.path), after.rf_only, after.alert))
            if not saved:
                raise MessagingError(f"{failure}: the database is not open")
            if empty:
                del self._own[key]
            else:
                self._own[key] = after
            self.changed.emit(key, None if empty else after)
