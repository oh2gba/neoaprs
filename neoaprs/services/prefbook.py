"""Operator preferences per station: a path of its own, RF only, and an alert.

A station with no part set has no entry. `Pref.path` is radio 1's path; other radios' paths
are kept through a `PathLog`. An empty path means DIRECT, which differs from none set."""

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
    """Return whether the radio's type, or its kind for an unknown type, has a "path" field."""
    try:
        return spec.rtype.field("path") is not None
    except RadioTypeError:
        return kind_field(spec.kind, "path") is not None


def _recommended(spec: RadioSpec) -> str:
    """Return the path the radio's type, or its kind for an unknown type, recommends."""
    try:
        return spec.rtype.recommended_path
    except RadioTypeError:
        return recommended_path(spec.kind)


class PathLog(Protocol):
    """Storage for per-radio paths; a write returns whether it was kept."""

    # call -> radio id -> comma-separated path, empty for direct
    async def paths(self) -> dict[str, dict[RadioId, str]]: ...
    async def save_path(self, call: str, radio: RadioId, path: str) -> bool: ...
    async def forget_path(self, call: str, radio: RadioId) -> bool: ...


class PrefBook:
    def __init__(
        self,
        messagelog: MessageLog,
        config: Callable[[], Config],
        heard: Callable[[str], Deliveries | None] = lambda call: None,
        clock: Clock = utcnow,
        *,
        paths: PathLog | None = None,
        gateway: Callable[[str, RadioId], tuple[str, ...]] = lambda call, radio: (),
    ) -> None:
        self._log = messagelog
        self._path_log = paths
        # paths of radios other than radio 1, by radio and call
        self._on: dict[RadioId, dict[str, tuple[str, ...]]] = {}
        self._config = config
        self._heard = heard
        self._clock = clock
        self._gateway = gateway
        self._own: dict[str, Pref] = {}
        # a change reads the entry and writes it back; two at once must not lose one
        self._lock = asyncio.Lock()
        self.changed: Signal[[str, Pref | None]] = Signal("prefs_changed")
        self.path_changed: Signal[[str, RadioId]] = Signal("prefs_path_changed")

    async def load(self) -> None:
        self._own = {
            call: Pref(None if path is None else normal_path(path), rf_only, alert)
            for call, (path, rf_only, alert) in (await self._log.prefs()).items()
        }
        self._on = {}
        for call, by_radio in (await self._path_log.paths() if self._path_log is not None else {}).items():
            for radio_id, path in by_radio.items():
                # radio 1's path is already in the entry
                if radio_id != FM_ID:
                    self._on.setdefault(radio_id, {})[call] = normal_path(path)

    # ---- what there is
    def all(self) -> dict[str, Pref]:
        """Return the entries by call; an entry's path is radio 1's."""
        return dict(self._own)

    def paths(self, radio_id: RadioId = FM_ID) -> dict[str, tuple[str, ...]]:
        """Return the paths set on the radio, by call."""
        if radio_id != FM_ID:
            return dict(self._on.get(radio_id, {}))
        return {call: pref.path for call, pref in self._own.items() if pref.path is not None}

    def path_on(self, call: str, radio_id: RadioId) -> tuple[str, ...] | None:
        """Return the path set for the normalised call on the radio, or None."""
        if radio_id != FM_ID:
            return self._on.get(radio_id, {}).get(call)
        own = self._own.get(call)
        return None if own is None else own.path

    def path_for(self, call: str, attempt: int | None = None, radio_id: RadioId = FM_ID) -> tuple[str, ...]:
        """Return the path for what is sent to the station on the radio.

        Order: own, lately heard (early attempts), radio's. Raise MessagingError if too long."""
        try:
            key = normal_name(call)
            own, path = self._own.get(key), self.path_on(key, radio_id)
        except ValueError:
            key, own, path = "", None, None
        if (spec := self._config().radio(radio_id)) is not None and not _has_path(spec):
            reply = self._gateway(key, radio_id)
            return rf_only_path(reply) if reply and own is not None and own.rf_only else reply
        if path is None and attempt is not None and key != EMAIL_GATEWAY:
            path = automatic_path(self._heard(key), self._clock(), attempt)
        if path is None:
            path = self._radio_path(radio_id)
        if own is None or not own.rf_only:
            return path
        added = rf_only_path(path)
        if len(added) > MAX_PATH:
            raise MessagingError(
                f"path too long for RF only: {len(path)} digipeaters and RFONLY make more than the {MAX_PATH} a path may have",
                "path.too_long_rf_only",
                count=len(path),
                max=MAX_PATH,
            )
        return added

    def _radio_path(self, radio_id: RadioId) -> tuple[str, ...]:
        """Return the radio's own path for a station with none set (recommended one if empty)."""
        config = self._config()
        spec = None if radio_id == FM_ID else config.radio(radio_id)
        if spec is None:
            return config.path_calls(FM_ID)
        chosen = path_choice(str(spec.value("path")))
        return (
            tuple(c for c in (_recommended(spec) or config.recommended_path).split(",") if c)
            if chosen is None
            else chosen
        )

    # ---- the path
    async def set_path(self, call: str, path: str, radio_id: RadioId = FM_ID) -> tuple[str, ...]:
        """Set the station's path (1 to 8 calls, or DIRECT) on the radio; an empty path clears it.

        Raise MessagingError if the path is invalid or cannot be kept."""
        try:
            key, calls = normal_name(call), path_choice(path)
        except ValueError as e:
            raise MessagingError.of(e) from None
        if calls is None:
            await self.clear_path(call, radio_id)
            return ()
        if radio_id != FM_ID:
            await self._keep_on(radio_id, key, calls)
        else:
            await self._change(key, lambda pref: replace(pref, path=calls), "the path could not be kept", quiet=False)
        return calls

    async def clear_path(self, call: str, radio_id: RadioId = FM_ID) -> None:
        """Remove the station's own path on the radio; a station without one is not an error."""
        try:
            key = normal_name(call)
        except ValueError as e:
            raise MessagingError.of(e) from None
        if radio_id != FM_ID:
            await self._keep_on(radio_id, key, None)
        else:
            await self._change(key, lambda pref: replace(pref, path=None), "the path could not be removed", quiet=True)

    async def _keep_on(self, radio_id: RadioId, key: str, calls: tuple[str, ...] | None) -> None:
        """Store, then hold, the path on a radio other than radio 1; None removes it."""
        async with self._lock:
            if calls is None and key not in self._on.get(radio_id, {}):
                return
            if self._path_log is None:
                raise MessagingError(
                    f"the path on radio {radio_id} could not be kept: there is nowhere to keep a path but radio 1's",
                    "failed",
                )
            if not await (
                self._path_log.forget_path(key, radio_id)
                if calls is None
                else self._path_log.save_path(key, radio_id, ",".join(calls))
            ):
                raise MessagingError(
                    f"the path could not be {'removed' if calls is None else 'kept'}: the database is not open",
                    "failed",
                )
            if calls is None:
                del self._on[radio_id][key]
            else:
                self._on.setdefault(radio_id, {})[key] = calls
            self.path_changed.emit(key, radio_id)

    # ---- RF only
    async def set_rf_only(self, call: str, on: bool) -> None:
        """Make what is sent to the station RF only, or not.

        Raise MessagingError for an invalid call or the email gateway."""
        try:
            key = normal_name(call)
        except ValueError as e:
            raise MessagingError.of(e) from None
        if on and key == EMAIL_GATEWAY:
            raise MessagingError(
                f"{EMAIL_GATEWAY} cannot be RF only: the email gateway is on the internet",
                "station.email_rf_only",
                call=EMAIL_GATEWAY,
            )
        await self._change(key, lambda pref: replace(pref, rf_only=on), "RF only could not be kept", quiet=not on)

    # ---- the alert
    async def set_alert(self, call: str, alert: Alert) -> None:
        """Set when to alert the operator about the station; an alert watching nothing removes it.

        Raise MessagingError for an invalid call or a distance outside ALERT_KM_MIN..MAX."""
        try:
            key = normal_name(call)
        except ValueError as e:
            raise MessagingError.of(e) from None
        if alert.within_km is not None and not ALERT_KM_MIN <= alert.within_km <= ALERT_KM_MAX:
            raise MessagingError(
                f"the distance of an alert is {ALERT_KM_MIN} to {ALERT_KM_MAX} km, not {alert.within_km}",
                "alert.km_range",
                km=alert.within_km,
                min=ALERT_KM_MIN,
                max=ALERT_KM_MAX,
            )
        await self._change(
            key,
            lambda pref: replace(pref, alert=alert if alert.any else None),
            "the alert could not be kept",
            quiet=not alert.any,
        )

    async def _change(self, key: str, make: Callable[[Pref], Pref], failure: str, quiet: bool) -> None:
        """Store, then hold, the entry `make` returns; an empty entry is removed.

        With `quiet`, clearing what is not set emits nothing."""
        async with self._lock:
            before = self._own.get(key)
            after = make(before or Pref())
            if quiet and after == (before or Pref()):
                return
            empty = after == Pref()
            saved = await (
                self._log.forget_pref(key)
                if empty
                else self._log.save_pref(
                    key, None if after.path is None else ",".join(after.path), after.rf_only, after.alert
                )
            )
            if not saved:
                raise MessagingError(f"{failure}: the database is not open", "failed")
            if empty:
                del self._own[key]
                await self._keep_others(key)
            else:
                self._own[key] = after
            self.changed.emit(key, None if empty else after)
            if (before or Pref()).path != after.path:
                self.path_changed.emit(key, FM_ID)

    async def _keep_others(self, key: str) -> None:
        """Save the paths on other radios again if forgetting the entry dropped them."""
        held = [(radio_id, on[key]) for radio_id, on in self._on.items() if key in on]
        if not held or self._path_log is None:
            return
        kept = (await self._path_log.paths()).get(key, {})
        for radio_id, calls in held:
            if radio_id not in kept and not await self._path_log.save_path(key, radio_id, ",".join(calls)):
                log.warning(
                    "the path of %s on radio %s was lost with its other preferences: it could not be kept again",
                    key,
                    radio_id,
                )
                del self._on[radio_id][key]
                self.path_changed.emit(key, radio_id)
