"""Wire models of the general query command and the topic `general`."""

from typing import Literal

from pydantic import Field

from .wirebase import Iso, PathText, _Command, _Model


class GeneralQuery(_Command):
    """Asks the stations in radio range a general query of APRS 1.0.1 (the services/generalask.py of the daemon): one frame from our call to our tocall whose information field is exactly `?APRS?` (`kind`
    `aprs`: who is around? the stations answer with their positions), `?IGATE?` (`igate`: the iGates answer with their capabilities) or `?WX?` (`wx`: the weather stations answer with their weather). It goes
    once on each radio of asking around's Send on (the radios whose `radio/<id>/ask` is ticked; with one radio that can send, that one) that takes
    frames now, by `path` (digipeater calls or aliases separated by commas, `OH2RDK-7,OH2RCH-2` or `WIDE1-1,WIDE2-1`, checked as a radio's path is, or `DIRECT` for none; null or empty is each radio's own
    path, and a radio that carries no path goes without one) with `RFONLY` after it when `rf_only`. The answers are ordinary packets (rows of `stations` and `packets`); the topic `general` tells the query and the
    stations heard after it. All or nothing: answered with an `error`, and nothing is sent on any radio, when the station is RX only or no call is set (`transmit.off`, or the interlock's reason), there is no
    radio (`radio.none`) or none of them takes frames now, the path is no path (`path.*`, `call.*`) or is too long with RFONLY (`path.too_long_rf_only`), or the query of that kind went on one of those
    radios less than 60 seconds ago (`general.too_soon`, with the `seconds` that are left, the longest)."""

    cmd: Literal["general_query"]
    kind: Literal["aprs", "igate", "wx"]
    path: PathText | None
    rf_only: bool = Field(
        default=True,
        description="RFONLY after the path; left out it is true. The page no longer sends it (the request always goes with RFONLY); a page of an older build may",
    )


class GeneralAsked(_Model):
    """A general query sent from here: one press, on one or more radios."""

    kind: Literal["aprs", "igate", "wx"] = Field(
        description="which query: `aprs` (?APRS?), `igate` (?IGATE?) or `wx` (?WX?)"
    )
    query: str = Field(description="the information field it went with, `?APRS?`, `?IGATE?` or `?WX?`")
    radios: list[int] = Field(
        description="the radios it went on, their ids, in the order of their boxes; what any of them heard is counted in `new`"
    )
    at: Iso = Field(description="when it was sent")
    path: list[str] | None = Field(
        description="the path it went by on the radios that carry one, `RFONLY` last when it was RF only; empty for no digipeaters; null when none was given and those radios' own paths differ"
    )
    until: Iso = Field(description="when the counting of `new` ends, two minutes after it was sent")
    new: list[str] = Field(
        description="the calls of the stations heard on one of its radios (not as a third-party packet, not from the internet) between the query and `until` that this radio had not heard "
        "in the ten minutes before it, in the order they were heard, each once whatever number of radios heard it: most are answers, but a station cannot be told to answer, "
        "so this is no more than who spoke after a quiet spell"
    )


class GeneralSent(_Model):
    """The last query of a kind on one radio."""

    kind: Literal["aprs", "igate", "wx"]
    radio: int = Field(description="the radio, its id")
    at: Iso = Field(description="when it went on that radio")


class GeneralState(_Model):
    """The general queries sent from here: the last one of each kind. Forgotten when the daemon stops. Told whole as it changes."""

    asked: list[GeneralAsked] = Field(description="the last query of each kind, the oldest first; empty before one")
    by_radio: list[GeneralSent] = Field(
        description="when the last query of each kind went on each radio, the oldest first: the wait before the next of a kind is each radio's, and a query waits for every radio it would go on (`general.too_soon`)"
    )
