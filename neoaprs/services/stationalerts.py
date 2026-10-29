"""The alerts the operator set on stations (the station preferences, services/prefbook.py: `Pref.alert`), watched as the station book changes, so that they work with no page open. Three can be set for a station, any
of them at once, and each fires once for each crossing, not for every packet:

    on_air   a packet of the station is heard after it was silent for QUIET (half an hour) or more, or for the first time
    within   its position comes from farther than N km from us to N km or nearer (or we come that near it), or is first known to be that near (a station never heard, or we without a position of ours, when the alert was set); it is outside again only beyond N km and a margin (OUTSIDE_MARGIN), so that a station that stands
             on the edge and whose positions wander a little is not told again and again
    direct   a packet of it is heard direct (no digipeater: the station book's `last_direct_at`) after none was for QUIET or more

What counts is what the Stations table shows: a packet over the internet counts only while `igate/enabled` is on (else the station's radio side, Station.radio_view, is what is watched). When an alert is set, changed
or read at the start, the station as it is then is the starting point: an alert never fires for what was already true (a station already near does not fire until it has been outside and comes in again; what was not known then is not "true" yet). Our own station
and our own objects have none (`set` refuses them). A firing is `fired` (the page's topics tell every page with the message `station_alert`; the wiring runs the alert command for it, services/alerts.py) and a line in the log."""
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

QUIET = timedelta(minutes=30)               # how long a station must have been silent (or not heard direct) for its next packet to fire
OUTSIDE_MARGIN = 0.1                        # a station that is near is outside again only beyond N km and this part of N more ...
OUTSIDE_MARGIN_MIN_KM = 0.5                 # ... and at least this many km more

@dataclass(slots=True)
class _Seen:
    """What the watch last knew of an alerted station: when it was last heard and last heard direct (on the channels that count), and whether it was near (None: not known, for want of its position or ours)."""
    heard_at: datetime | None
    direct_at: datetime | None
    inside: bool | None


def outside_km(within_km: int) -> float:
    """How far a station that was near must go to be outside again."""
    return within_km + max(within_km * OUTSIDE_MARGIN, OUTSIDE_MARGIN_MIN_KM)


def km_text(km: float) -> str:
    """A distance as the alert says it: one decimal under 10 km, whole kilometres above."""
    return f"{km:.1f}" if km < 10 else f"{km:.0f}"


class StationAlerts:
    def __init__(self, book: StationBook, prefs: PrefBook, config: ConfigSource, clock: Clock = utcnow) -> None:
        self._book = book
        self._prefs = prefs
        self._config = config
        self.clock = clock
        self._alerts: dict[str, Alert] = {}
        self._seen: dict[str, _Seen] = {}
        self._internet = False                  # `igate/enabled` when the starting points were taken: a change of it takes them again
        self.fired: Signal[[Fired]] = Signal("stationalerts.fired")

    # ---- what is set
    def load(self) -> None:
        """The alerts the preferences hold, at the start (after they are read and the station book is filled): the stations as the book has them are the starting points."""
        self._internet = self._config().igate_enabled
        for call, pref in self._prefs.all().items():
            self.pref_changed(call, pref)

    def alerts(self) -> dict[str, Alert]:
        return dict(self._alerts)

    async def set(self, call: str, alert: Alert) -> None:
        """Sets the alert of a station (one that watches nothing takes it away). Raises MessagingError with the reason: our own station, or an object or item of ours, has none; the rest is the preferences' to refuse."""
        try:
            key = normal_name(call)
        except ValueError as e:
            raise MessagingError(str(e)) from None
        station = self._book.get(key)
        if key == self._own_call() or (station is not None and (station.is_me or station.own)):
            raise MessagingError(f"{key} is our own: an alert is for another station", "alert.own", call=key)
        await self._prefs.set_alert(key, alert)

    def _own_call(self) -> str:
        """Our call as the book names a station; empty while there is none (or it is no call)."""
        try:
            return normal_name(self._config().station_call)
        except ValueError:
            return ""

    def pref_changed(self, call: str, pref: Pref | None) -> None:
        """An entry of the preferences was set or changed (or is gone): an alert that is new or changed starts from the station as it is now."""
        self._follow_internet()
        alert = None if pref is None else pref.alert
        if alert is None:
            self._alerts.pop(call, None)
            self._seen.pop(call, None)
            return
        if self._alerts.get(call) != alert:
            self._alerts[call] = alert
            self._seen[call] = self._start(call, alert)

    # ---- what is heard
    def station_changed(self, station: Station) -> None:
        """The station book changed a station: our own one moving moves every distance; an alerted one is looked at."""
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
        """Our own position changed (the settings, or the GPS of a moving station): every station with a distance to watch is measured again, and one we came near fires."""
        for call, alert in self._alerts.items():
            station = self._book.get(call)
            view = None if station is None or station.own else self._view(station)
            if alert.within_km is not None and view is not None:
                self._place(call, view, alert.within_km, self._seen.setdefault(call, _Seen(None, None, None)), self.clock())

    def _place(self, call: str, view: Station, within_km: int, seen: _Seen, at: datetime) -> None:
        """Whether the station is near now; coming near from outside fires, `at` being when (the time of its position, or now when we moved)."""
        km = self._book.distance_km(view)
        if km is None:
            return
        if km <= within_km:
            if seen.inside is not True:
                self._fire(Fired(call, "within", f"{call} is {km_text(km)} km from you", at, round(km, 1)))
            seen.inside = True
        elif km > outside_km(within_km):
            seen.inside = False

    # ---- the starting points
    def _start(self, call: str, alert: Alert) -> _Seen:
        """The station as it is now, which nothing fires for."""
        station = self._book.get(call)
        view = None if station is None else self._view(station)
        if view is None:
            return _Seen(None, None, None)
        km = None if alert.within_km is None else self._book.distance_km(view)
        return _Seen(view.last_heard, view.last_direct_at, None if km is None or alert.within_km is None else km <= alert.within_km)

    def settings_changed(self, config: Config) -> None:
        """The settings were saved: `igate/enabled` may have been switched."""
        self._follow_internet()

    def _follow_internet(self) -> None:
        """`igate/enabled` was switched: what counts changed, and every alert starts again from the stations as they are now."""
        internet = self._config().igate_enabled
        if internet != self._internet:
            self._internet = internet
            self._seen = {call: self._start(call, alert) for call, alert in self._alerts.items()}

    def _view(self, station: Station) -> Station | None:
        """The station as the alerts see it: whole while the internet is shown, else its radio side (None for one known from the internet alone)."""
        return station if self._config().igate_enabled else station.radio_view()

    def _fire(self, fired: Fired) -> None:
        log.info("station alert: %s", fired.text)
        self.fired.emit(fired)

