"""What the operator says about a station, on the wire: the topic `station_prefs` (a table of entries by call) and the commands that set and clear a station's path, and the one that makes it RF only. Models like the rest of
the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import _Command, _Model


class StationPref(_Model):
    """What the operator has set for one station, apart from what its packets say. The entries are the values of the topic `station_prefs`, keyed by call: a station with no path of its
    own, and not RF only, has no entry. A command that sets or changes one part is a `set` of the whole entry, one that clears the last part a `del`."""
    path: str | None = Field(description="the digipeaters that a message to the station, and the ack of a message from it, go by way of: calls separated by commas, empty for direct (no digipeaters at all); "
                                         "null if none is set, and the setting `beacon/path` counts")
    rf_only: bool = Field(description="true if everything sent to the station (a message and each attempt of it, an ack, the answer to a query) has `RFONLY` as the last element of its path, which iGates that honour it do not put on the internet")


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
