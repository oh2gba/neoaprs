"""What the operator says about a station, on the wire: the topic `station_prefs` (a table of entries by call) and the commands that set and clear a station's path, its timeout and its attempts, and the one that makes it RF only. Models like the rest of
the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from neoaprs.config import MAX_HIDE_AFTER_MIN
from neoaprs.message import MAX_ATTEMPTS

from .wirebase import _Command, _Model


class StationPref(_Model):
    """What the operator has set for one station, apart from what its packets say. The entries are the values of the topic `station_prefs`, keyed by call: a station with no path, no timeout and no attempts of its
    own, and not RF only, has no entry. A command that sets or changes one part is a `set` of the whole entry, one that clears the last part a `del`."""
    path: str | None = Field(description="the digipeaters that a message to the station, and the ack of a message from it, go by way of: calls separated by commas, empty for direct (no digipeaters at all); "
                                         "null if none is set, and the setting `beacon/path` counts")
    hide_after_min: int | None = Field(ge=0, le=MAX_HIDE_AFTER_MIN, description="the minutes after the station's last position that it leaves the map (the page does the hiding); 0 is never; "
                                                                               "null if none is set, and the setting `map/hide_after_min` counts")
    attempts: int | None = Field(ge=1, le=MAX_ATTEMPTS, description="how many times a message to the station is transmitted before it has failed (taken when the message is sent); 1 or 2 attempts without an ack leave "
                                                                      "the message `unconfirmed`, not `failed`; null if none is set, and the setting `messages/attempts` counts")
    rf_only: bool = Field(description="true if everything sent to the station (a message and each attempt of it, an ack, the answer to a query) has `RFONLY` as the last element of its path, which iGates that honour it do not put on the internet")


class SetStationPath(_Command):
    """Gives a station a path of its own: the digipeaters that a message to it, and the ack of a message from it, go by way of. `path` is up to 8 digipeater calls separated by commas, checked as the setting
    `beacon/path` is; an empty `path` is a valid path of its own, direct with no digipeaters at all, which is not the same as none set. Answered by the `set` of the station's entry in the topic `station_prefs`
    (its `hide_after_min` is whatever it was), or by an `error` that names the reason."""
    cmd: Literal["set_station_path"]
    call: str = Field(min_length=1, max_length=64)
    path: str = Field(max_length=256)


class ClearStationPath(_Command):
    """Takes a station's own path away, so that it has the path of the setting `beacon/path` again (a station without one is no error). Answered by the `set` of its entry in `station_prefs` with a null `path`
    (or the `del` of the entry when it had no timeout either), or by an `error`."""
    cmd: Literal["clear_station_path"]
    call: str = Field(min_length=1, max_length=64)


class SetStationTimeout(_Command):
    """Gives a station a timeout of its own: how long after its last position it stays on the map, in minutes; 0 is never. The page hides a station whose last position is older than that (a station
    without one of its own uses the setting `map/hide_after_min`), and the daily prune does not remove a station with a timeout of 0 from the station book. `call` is a station's call as it is in the
    topic `stations` (the name of an object or an item too). Answered by the `set` of the station's entry in the topic `station_prefs` (its `path` is whatever it was), or by an `error` that names the reason."""
    cmd: Literal["set_station_timeout"]
    call: str = Field(min_length=1, max_length=64)
    minutes: int = Field(ge=0, le=MAX_HIDE_AFTER_MIN)


class ClearStationTimeout(_Command):
    """Takes a station's own timeout away, so that it has the setting `map/hide_after_min` again (a station without one is no error). Answered by the `set` of its entry in `station_prefs` with a null
    `hide_after_min` (or the `del` of the entry when it had no path either), or by an `error`."""
    cmd: Literal["clear_station_timeout"]
    call: str = Field(min_length=1, max_length=64)


class SetStationAttempts(_Command):
    """Gives a station a count of attempts of its own, 1 to 10: the number of times a message sent to it from now on is transmitted before it has failed (a message already being sent keeps its own). With 1 or 2 a
    message that gets no ack is `unconfirmed`, not `failed`. Answered by the `set` of the station's entry in the topic `station_prefs` (its `path` and `hide_after_min` are whatever they were), or by an `error` that names the reason."""
    cmd: Literal["set_station_attempts"]
    call: str = Field(min_length=1, max_length=64)
    attempts: int = Field(ge=1, le=MAX_ATTEMPTS)


class ClearStationAttempts(_Command):
    """Takes a station's own attempts away, so that the setting `messages/attempts` counts again (a station without them is no error). Answered by the `set` of its entry in `station_prefs` with a null `attempts`
    (or the `del` of the entry when it had no path and no timeout either), or by an `error`."""
    cmd: Literal["clear_station_attempts"]
    call: str = Field(min_length=1, max_length=64)


class SetStationRfOnly(_Command):
    """Makes everything we send to a station RF only, or not: `RFONLY` is added as the last element of the path of each message and attempt, each ack and each answer to a query (a path that holds `RFONLY` or `NOGATE`
    already gets no second one). A path that would be more than 8 elements with it is refused when a message is sent ("path too long for RF only"). The email gateway `EMAIL-2` is on the internet and is refused. Answered by the `set`
    of the station's entry in the topic `station_prefs` (its other parts are whatever they were), or by the `del` of the entry when `on` is false and nothing else is set, or by an `error` that names the reason."""
    cmd: Literal["set_station_rf_only"]
    call: str = Field(min_length=1, max_length=64)
    on: bool
