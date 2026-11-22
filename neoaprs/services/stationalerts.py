"""Station alerts the operator set (`Pref.alert`), watched as the station book changes.

Kinds: `on_air`, `within` (N km) and `direct`. Each fires once per crossing; the station as it
is when an alert is set is the starting point."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from neoaprs.callsign import normal_name
from neoaprs.clock import Clock, utcnow
from neoaprs.config import Config
from neoaprs.message import MessagingError
from neoaprs.pref import Alert, Fired, Pref
from neoaprs.services.common import ConfigSource
from neoaprs.services.prefbook import PrefBook
from neoaprs.signal import Signal
from neoaprs.station import Station
from neoaprs.stationbook import StationBook

log = logging.getLogger("neoaprs.stationalerts")

# how long a station must be silent (or not heard direct) for its next packet to fire
QUIET = timedelta(minutes=30)
# a near station is outside again beyond N km plus this fraction of N, and at least
OUTSIDE_MARGIN = 0.1
# this many km more
OUTSIDE_MARGIN_MIN_KM = 0.5


@dataclass(slots=True)
class _Seen:
    """What the watch last knew of an alerted station: last heard, last direct, whether near.

    `inside` is None when unknown for want of its position or ours."""

    heard_at: datetime | None
    direct_at: datetime | None
    inside: bool | None


def outside_km(within_km: int) -> float:
    return within_km + max(within_km * OUTSIDE_MARGIN, OUTSIDE_MARGIN_MIN_KM)


def km_text(km: float) -> str:
    """Return a distance for the alert text: one decimal under 10 km, else whole kilometres."""
    return f"{km:.1f}" if km < 10 else f"{km:.0f}"


class StationAlerts:
    def __init__(self, book: StationBook, prefs: PrefBook, config: ConfigSource, clock: Clock = utcnow) -> None:
        self._book = book
        self._prefs = prefs
        self._config = config
        self.clock = clock
        self._alerts: dict[str, Alert] = {}
        self._seen: dict[str, _Seen] = {}
        # `igate/enabled` when the starting points were taken; a change retakes them
        self._internet = False
        self.fired: Signal[[Fired]] = Signal("stationalerts.fired")

    def load(self) -> None:
        """Load the alerts at start; stations as they are then become the starting points."""
        self._internet = self._config().igate_enabled
        for call, pref in self._prefs.all().items():
            self.pref_changed(call, pref)

    def alerts(self) -> dict[str, Alert]:
        return dict(self._alerts)

    async def set(self, call: str, alert: Alert) -> None:
        """Set a station's alert; one watching nothing removes it.

        Raise MessagingError for our own station or object."""
        try:
            key = normal_name(call)
        except ValueError as e:
            raise MessagingError.of(e) from None
        station = self._book.get(key)
        if key == self._own_call() or (station is not None and (station.is_me or station.own)):
            raise MessagingError(f"{key} is our own: an alert is for another station", "alert.own", call=key)
        await self._prefs.set_alert(key, alert)

    def _own_call(self) -> str:
        try:
            return normal_name(self._config().station_call)
        except ValueError:
            return ""

    def pref_changed(self, call: str, pref: Pref | None) -> None:
        """React to a preference entry set, changed or gone; an alert starts from now."""
        self._follow_internet()
        alert = None if pref is None else pref.alert
        if alert is None:
            self._alerts.pop(call, None)
            self._seen.pop(call, None)
            return
        if self._alerts.get(call) != alert:
            self._alerts[call] = alert
            self._seen[call] = self._start(call, alert)

    def station_changed(self, station: Station) -> None:
        """React to a station change: our move alters all distances; alerted ones are checked."""
        self._follow_internet()
        if station.is_me:
            self._we_moved()
            return
        alert = self._alerts.get(station.call)
        if alert is not None and not station.own:
            self._look(station.call, station, alert)

    def _look(self, call: str, station: Station, alert: Alert) -> None:
        seen = self._seen.setdefault(call, _Seen(None, None, None))
        view = self._view(station)
        if view is None:
            return
        heard, direct = view.last_heard, view.last_direct_at
        if seen.heard_at is None or heard > seen.heard_at:
            if alert.on_air and (seen.heard_at is None or heard - seen.heard_at >= QUIET):
                self._fire(Fired(call, "on_air", f"{call} is on the air", heard))
            seen.heard_at = heard
        if direct is not None and (seen.direct_at is None or direct > seen.direct_at):
            if alert.direct and (seen.direct_at is None or direct - seen.direct_at >= QUIET):
                self._fire(Fired(call, "direct", f"{call} is heard direct", direct))
            seen.direct_at = direct
        if alert.within_km is not None:
            self._place(call, view, alert.within_km, seen, view.last_position_at or self.clock())

    def _we_moved(self) -> None:
        """Remeasure watched distances after our position changed; a station we came near fires."""
        for call, alert in self._alerts.items():
            station = self._book.get(call)
            view = None if station is None or station.own else self._view(station)
            if alert.within_km is not None and view is not None:
                self._place(
                    call, view, alert.within_km, self._seen.setdefault(call, _Seen(None, None, None)), self.clock()
                )

    def _place(self, call: str, view: Station, within_km: int, seen: _Seen, at: datetime) -> None:
        """Update whether the station is near; coming near from outside fires, stamped `at`."""
        km = self._book.distance_km(view)
        if km is None:
            return
        if km <= within_km:
            if seen.inside is not True:
                self._fire(Fired(call, "within", f"{call} is {km_text(km)} km from you", at, round(km, 1)))
            seen.inside = True
        elif km > outside_km(within_km):
            seen.inside = False

    def _start(self, call: str, alert: Alert) -> _Seen:
        station = self._book.get(call)
        view = None if station is None else self._view(station)
        if view is None:
            return _Seen(None, None, None)
        km = None if alert.within_km is None else self._book.distance_km(view)
        return _Seen(
            view.last_heard,
            view.last_direct_at,
            None if km is None or alert.within_km is None else km <= alert.within_km,
        )

    def settings_changed(self, config: Config) -> None:
        self._follow_internet()

    def _follow_internet(self) -> None:
        """When `igate/enabled` changed, restart every alert from the stations as they are now."""
        internet = self._config().igate_enabled
        if internet != self._internet:
            self._internet = internet
            self._seen = {call: self._start(call, alert) for call, alert in self._alerts.items()}

    def _view(self, station: Station) -> Station | None:
        """Return the station as alerts see it: whole with the internet shown, else radio side."""
        return station if self._config().igate_enabled else station.radio_view()

    def _fire(self, fired: Fired) -> None:
        log.info("station alert: %s", fired.text)
        self.fired.emit(fired)
