"""What the operator says about a station, apart from what its packets say: a path of its own, whether it is RF only, and when to be alerted about it (services/stationalerts.py fires the alert). Each is optional and
independent, and a station with none has no entry.

The path: the digipeaters a message (and its ack) to the station goes by way of; empty is direct (chosen as DIRECT), which is not the same as none set (then the first attempts of a message go by the path lately heard to reach the station, the rest and everything else by `beacon/path`). RF only: everything we send to the station (a message and each attempt of it, its acks, the answers to its queries) goes by its path with RFONLY
added at the end, which iGates that honour it do not put on the internet; the email gateway EMAIL-2 is on the internet and can never be RF only. They are operator data, kept in the table `station_pref` of the message log's database, read once at the start and written through; `changed` tells (call, pref) when a station's
entry is set or changes and (call, None) when its last part is cleared and the entry is gone.

A path is set on a radio: what a station is given is the path set on the radio the frame goes out on (`path_for(call, attempt, radio_id)`), else the path lately heard, else that radio's own path. A call that names no
radio means radio 1, and the path of the entry (`Pref.path`, what the page is told) is radio 1's. The paths set on the other radios are held beside the entries and kept through a `PathLog` (the table `station_path`);
without one there is nowhere to keep them, and setting one is refused. `path_changed` tells (call, radio id) when the path of a station on a radio is set, changes or is taken away, radio 1's too. Forgetting an
entry (its last part cleared) forgets radio 1's path with it, never the paths on the other radios."""
import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from typing import Protocol

from neoaprs.ax25 import MAX_PATH
from neoaprs.callsign import normal_name
from neoaprs.clock import Clock, utcnow
from neoaprs.config import Config
from neoaprs.message import EMAIL_GATEWAY, MessagingError, normal_path, path_choice
from neoaprs.messagelog import MessageLog
from neoaprs.pref import ALERT_KM_MAX, ALERT_KM_MIN, Alert, Pref
from neoaprs.radiospec import RadioSpec
from neoaprs.radiotype import FM_ID, RadioId, RadioTypeError
from neoaprs.radiotypes import kind_field, recommended_path
from neoaprs.route import Deliveries, automatic_path, rf_only_path
from neoaprs.signal import Signal


log = logging.getLogger("neoaprs.messaging")


def _has_path(spec: RadioSpec) -> bool:
    """Whether the radio's type has a "path" field (a type that is none: its kind's)."""
    try:
        return spec.rtype.field("path") is not None
    except RadioTypeError:
        return kind_field(spec.kind, "path") is not None


def _recommended(spec: RadioSpec) -> str:
    """The path its type recommends (a type that is none: its kind's)."""
    try:
        return spec.rtype.recommended_path
    except RadioTypeError:
        return recommended_path(spec.kind)


class PathLog(Protocol):
    """Where the paths set on the radios other than radio 1 are kept: the table `station_path` (stationsql.py), reached through the message log (MessageLog of package D2 has these three). Each write says
    whether it was kept."""
    async def paths(self) -> dict[str, dict[RadioId, str]]: ...       # call to (radio id to the path as it is kept: calls with commas between, empty for direct), radio 1's too
    async def save_path(self, call: str, radio: RadioId, path: str) -> bool: ...
    async def forget_path(self, call: str, radio: RadioId) -> bool: ...


class PrefBook:
    def __init__(self, messagelog: MessageLog, config: Callable[[], Config], heard: Callable[[str], Deliveries | None] = lambda call: None, clock: Clock = utcnow, *, paths: PathLog | None = None) -> None:
        self._log = messagelog
        self._path_log = paths                         # where the paths of the radios other than radio 1 are kept; None: nowhere (they cannot be set)
        self._on: dict[RadioId, dict[str, tuple[str, ...]]] = {}       # the paths set on the radios other than radio 1, by radio and call (radio 1's is the entry's own, `Pref.path`)
        self._config = config
        self._heard = heard                            # how the packets of a station reached us (the station book's Deliveries), None for a station not heard
        self._clock = clock
        self._own: dict[str, Pref] = {}
        self._lock = asyncio.Lock()                    # a change reads the entry and writes it back: two at once for one station must not lose one
        self.changed: Signal[[str, Pref | None]] = Signal("prefs_changed")
        self.path_changed: Signal[[str, RadioId]] = Signal("prefs_path_changed")      # (call, radio id): the path set on that radio is another now (`path_on` says which); nothing listens before W1

    async def load(self) -> None:
        self._own = {call: Pref(None if path is None else normal_path(path), rf_only, alert) for call, (path, rf_only, alert) in (await self._log.prefs()).items()}
        self._on = {}
        for call, by_radio in (await self._path_log.paths() if self._path_log is not None else {}).items():
            for radio_id, path in by_radio.items():
                if radio_id != FM_ID:                  # (radio 1's is the entry's own: `prefs` gave it)
                    self._on.setdefault(radio_id, {})[call] = normal_path(path)

    # ---- what there is
    def all(self) -> dict[str, Pref]:
        """The stations that have an entry, by call (the path of an entry is the one set on radio 1)."""
        return dict(self._own)

    def paths(self, radio_id: RadioId = FM_ID) -> dict[str, tuple[str, ...]]:
        """The stations that have a path of their own on the radio (radio 1 when none is named), by call."""
        if radio_id != FM_ID:
            return dict(self._on.get(radio_id, {}))
        return {call: pref.path for call, pref in self._own.items() if pref.path is not None}

    def path_on(self, call: str, radio_id: RadioId) -> tuple[str, ...] | None:
        """The path set for the station (its call as `normal_name` gives it) on the radio; None when none is set there."""
        if radio_id != FM_ID:
            return self._on.get(radio_id, {}).get(call)
        own = self._own.get(call)
        return None if own is None else own.path

    def path_for(self, call: str, attempt: int | None = None, radio_id: RadioId = FM_ID) -> tuple[str, ...]:
        """The path everything we send to the station on the radio `radio_id` goes by (radio 1 when none is named): the station's own when one is set on that radio, else (for attempt number `attempt` of a
        message, 1 for the first, when it is given) the path that has lately been heard to reach the station for the first attempts (route.automatic_path), else the radio's own path (`beacon/path` for radio 1); with
        RFONLY at the end when the station is RF only. Raises MessagingError when that would be more than 8 digipeaters ("path too long for RF only"): nothing is sent then."""
        try:
            key = normal_name(call)
            own, path = self._own.get(key), self.path_on(key, radio_id)
        except ValueError:
            key, own, path = "", None, None
        if path is None and attempt is not None and key != EMAIL_GATEWAY:
            path = automatic_path(self._heard(key), self._clock(), attempt)
        if path is None:
            path = self._radio_path(radio_id)
        if own is None or not own.rf_only:
            return path
        added = rf_only_path(path)
        if len(added) > MAX_PATH:
            raise MessagingError(f"path too long for RF only: {len(path)} digipeaters and RFONLY make more than the {MAX_PATH} a path may have")
        return added

    def _radio_path(self, radio_id: RadioId) -> tuple[str, ...]:
        """The radio's own path, for a station with none set on it: radio 1's (`Config.path_calls`) for radio 1, for a radio the settings do not have and for one of a kind that has no path setting (whether a
        frame may carry a path on a radio is the fit's to say, services/radioset.py); else the radio's "path", which empty is the path its type recommends (LoRa WIDE1-1), else the recommended path of the
        station's symbol, and DIRECT none."""
        config = self._config()
        spec = None if radio_id == FM_ID else config.radio(radio_id)
        if spec is None or not _has_path(spec):
            return config.path_calls(FM_ID)
        chosen = path_choice(str(spec.value("path")))
        return tuple(c for c in (_recommended(spec) or config.recommended_path).split(",") if c) if chosen is None else chosen

    # ---- the path
    async def set_path(self, call: str, path: str, radio_id: RadioId = FM_ID) -> tuple[str, ...]:
        """Gives the station a path of its own on the radio (radio 1 when none is named): 1 to 8 digipeater calls separated by commas, checked as beacon/path is, or DIRECT for no digipeaters at all; an empty
        path takes the station's own away (it is automatic again), as clear_path does. Raises MessagingError with the reason; the path as it is kept (empty for direct)."""
        try:
            key, calls = normal_name(call), path_choice(path)
        except ValueError as e:
            raise MessagingError(str(e)) from None
        if calls is None:
            await self.clear_path(call, radio_id)
            return ()
        if radio_id != FM_ID:
            await self._keep_on(radio_id, key, calls)
        else:
            await self._change(key, lambda pref: replace(pref, path=calls), "the path could not be kept", quiet=False)
        return calls

    async def clear_path(self, call: str, radio_id: RadioId = FM_ID) -> None:
        """Takes the station's own path on the radio away (radio 1 when none is named): it has the radio's own path again. A station without one is not an error."""
        try:
            key = normal_name(call)
        except ValueError as e:
            raise MessagingError(str(e)) from None
        if radio_id != FM_ID:
            await self._keep_on(radio_id, key, None)
        else:
            await self._change(key, lambda pref: replace(pref, path=None), "the path could not be removed", quiet=True)

    async def _keep_on(self, radio_id: RadioId, key: str, calls: tuple[str, ...] | None) -> None:
        """The path of the station on a radio other than radio 1 as `calls` says (None: none), kept first and then held."""
        async with self._lock:
            if calls is None and key not in self._on.get(radio_id, {}):
                return
            if self._path_log is None:
                raise MessagingError(f"the path on radio {radio_id} could not be kept: there is nowhere to keep a path but radio 1's")
            if not await (self._path_log.forget_path(key, radio_id) if calls is None else self._path_log.save_path(key, radio_id, ",".join(calls))):
                raise MessagingError(f"the path could not be {'removed' if calls is None else 'kept'}: the database is not open")
            if calls is None:
                del self._on[radio_id][key]
            else:
                self._on.setdefault(radio_id, {})[key] = calls
            self.path_changed.emit(key, radio_id)

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
                await self._keep_others(key)
            else:
                self._own[key] = after
            self.changed.emit(key, None if empty else after)
            if (before or Pref()).path != after.path:
                self.path_changed.emit(key, FM_ID)

    async def _keep_others(self, key: str) -> None:
        """The entry of the station was forgotten, and radio 1's path with it: its paths on the other radios stay. A message log that forgot them too (D2's first `forget_pref` forgets every path of the
        station) has each one kept again; one it would not keep is said in the log and no longer held."""
        held = [(radio_id, on[key]) for radio_id, on in self._on.items() if key in on]
        if not held or self._path_log is None:
            return
        kept = (await self._path_log.paths()).get(key, {})
        for radio_id, calls in held:
            if radio_id not in kept and not await self._path_log.save_path(key, radio_id, ",".join(calls)):
                log.warning("the path of %s on radio %s was lost with its other preferences: it could not be kept again", key, radio_id)
                del self._on[radio_id][key]
                self.path_changed.emit(key, radio_id)
