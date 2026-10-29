"""Asking around on the wire: the command that sends a general query (?APRS?, ?IGATE?, ?WX?) and the topic `general`, the last query of each kind and the stations heard after it. Models like the rest of the protocol,
listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import Iso, PathText, _Command, _Model


class GeneralQuery(_Command):
    """Asks the stations in radio range a general query of APRS 1.0.1 (the services/generalask.py of the daemon): one frame from our call to our tocall whose information field is exactly `?APRS?` (`kind`
    `aprs`: who is around? the stations answer with their positions), `?IGATE?` (`igate`: the iGates answer with their capabilities) or `?WX?` (`wx`: the weather stations answer with their weather). It goes
    once, by `path` (digipeater calls or aliases separated by commas, `OH2RDK-7,OH2RCH-2` or `WIDE1-1,WIDE2-1`, checked as the setting `beacon/path` is, or `DIRECT` for none; null or empty is `beacon/path`)
    with `RFONLY` after it when `rf_only`. The answers are ordinary packets (rows of `stations` and `packets`); the topic `general` tells the query and the stations heard after it. Answered with an `error`
    when RX only is ticked or no call is set (`transmit.off`, or the interlock's reason), the radio is away, the path is no path (`path.*`, `call.*`) or is too long with RFONLY (`path.too_long_rf_only`),
    or the query of that kind was sent less than 60 seconds ago (`general.too_soon`, with the `seconds` that are left)."""
    cmd: Literal["general_query"]
    kind: Literal["aprs", "igate", "wx"]
    path: PathText | None
    rf_only: bool


class GeneralAsked(_Model):
    """A general query sent from here."""
    kind: Literal["aprs", "igate", "wx"] = Field(description="which query: `aprs` (?APRS?), `igate` (?IGATE?) or `wx` (?WX?)")
    query: str = Field(description="the information field it went with, `?APRS?`, `?IGATE?` or `?WX?`")
    at: Iso = Field(description="when it was sent")
    path: list[str] = Field(description="the path it went by, `RFONLY` last when it was RF only; empty for no digipeaters")
    until: Iso = Field(description="when the counting of `new` ends, two minutes after it was sent")
    new: list[str] = Field(description="the calls of the stations heard on the radio (not as a third-party packet, not from the internet) between the query and `until` that had not been heard on the radio "
                                       "in the ten minutes before it, in the order they were heard: most are answers, but a station cannot be told to answer, so this is no more than who spoke after a quiet spell")


class GeneralState(_Model):
    """The general queries sent from here: the last one of each kind. Forgotten when the daemon stops. Told whole as it changes."""
    asked: list[GeneralAsked] = Field(description="the last query of each kind, the oldest first; empty before one")
