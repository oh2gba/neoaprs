"""What the operator says about a station, on the wire: the topic `station_prefs` (a table of entries by call), the commands that set and clear a station's path, the one that makes it RF only and the one that sets its alert, and
the message `station_alert` that tells every page an alert fired. Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import Iso, _Command, _Message, _Model

ALERT_KM_MIN, ALERT_KM_MAX = 1, 1000                # (neoaprs/pref.py has the same: the core does not import the wire)


class AlertWhen(_Model):
    """When the operator is told about a station: any of the three, each once for each time it happens (it is not told again for every packet), by the message `station_alert` to every page and by the alert command of
    the settings (`messages/alert`, `messages/alert_command`), as a message to us is."""
    on_air: bool = Field(description="a packet of the station is heard after it was silent for 30 minutes or more, or for the first time; a packet over the internet counts while `igate/enabled` is on")
    within_km: int | None = Field(ge=ALERT_KM_MIN, le=ALERT_KM_MAX, description="its position comes from farther to this many km from us or nearer (it is outside again only some way beyond: a tenth more, at least 0.5 km); "
                                                                          "null if the distance is not watched. A station that is that near already when the alert is set is not told until it has been outside")
    direct: bool = Field(description="a packet of it is heard direct (no digipeater) after none was for 30 minutes or more")


class StationPref(_Model):
    """What the operator has set for one station, apart from what its packets say. The entries are the values of the topic `station_prefs`, keyed by call: a station with no path of its
    own, and not RF only, has no entry. A command that sets or changes one part is a `set` of the whole entry, one that clears the last part a `del`."""
    path: str | None = Field(description="the digipeaters that a message to the station, and the ack of a message from it, go by way of: calls separated by commas, empty for direct (no digipeaters at all); "
                                         "null if none is set, and the setting `beacon/path` counts")
    rf_only: bool = Field(description="true if everything sent to the station (a message and each attempt of it, an ack, the answer to a query) has `RFONLY` as the last element of its path, which iGates that honour it do not put on the internet")
    alert: AlertWhen | None = Field(description="when the operator is told about the station; null if no alert is set")


class SetStationPath(_Command):
    """Gives a station a path of its own: the digipeaters that a message to it, and the ack of a message from it, go by way of. `path` is up to 8 digipeater calls separated by commas, checked as the setting
    `beacon/path` is, or `DIRECT` for a path of its own with no digipeaters at all; an empty `path` is no path of its own, as `clear_station_path` makes it. Answered by the `set` of the station's entry in the topic `station_prefs`
    (its `rf_only` is whatever it was), or by an `error` that names the reason."""
    cmd: Literal["set_station_path"]
    call: str = Field(min_length=1, max_length=64)
    path: str = Field(max_length=256)


class ClearStationPath(_Command):
    """Takes a station's own path away, so that it has the path of the setting `beacon/path` again (a station without one is no error). Answered by the `set` of its entry in `station_prefs` with a null `path`
    (or the `del` of the entry when it was not RF only either), or by an `error`."""
    cmd: Literal["clear_station_path"]
    call: str = Field(min_length=1, max_length=64)


class SetStationRfOnly(_Command):
    """Makes everything we send to a station RF only, or not: `RFONLY` is added as the last element of the path of each message and attempt, each ack and each answer to a query (a path that holds `RFONLY` or `NOGATE`
    already gets no second one). A path that would be more than 8 elements with it is refused when a message is sent ("path too long for RF only"). The email gateway `EMAIL-2` is on the internet and is refused. Answered by the `set`
    of the station's entry in the topic `station_prefs` (its other parts are whatever they were), or by the `del` of the entry when `on` is false and nothing else is set, or by an `error` that names the reason."""
    cmd: Literal["set_station_rf_only"]
    call: str = Field(min_length=1, max_length=64)
    on: bool


class SetStationAlert(_Command):
    """Sets when the operator is told about a station (see `AlertWhen`): `on_air`, `within_km` (1 to 1000, null for none) and `direct`, any of them at once; all off takes the alert away. Our own station and our own objects and items
    are refused. Answered by the `set` of the station's entry in the topic `station_prefs` (its path and RF only are whatever they were), or by its `del` when nothing else is set and the alert is taken away, or by an `error`."""
    cmd: Literal["set_station_alert"]
    call: str = Field(min_length=1, max_length=64)
    on_air: bool
    within_km: int | None = Field(ge=ALERT_KM_MIN, le=ALERT_KM_MAX)
    direct: bool


class StationAlertMsg(_Message):
    """An alert set on a station fired (`set_station_alert`): told to every page that is open, once. The page alerts as for a message to us (the sound, the pop-up, the browser tab, as its own choice says) and shows it in its toast."""
    type: Literal["station_alert"]
    call: str = Field(description="the station")
    kind: Literal["on_air", "within", "direct"] = Field(description="what happened: it came on the air, it came within the distance, it was heard direct")
    text: str = Field(description="the words of the alert command and the log, in English: `OH2XYZ is on the air`, `OH2XYZ is 8.2 km from you`, `OH2XYZ is heard direct`")
    at: Iso = Field(description="when the packet that fired it was heard (for `within`, when the station's position was, or when ours moved)")
    km: float | None = Field(description="for `within`, how far the station is, km with one decimal; else null")
