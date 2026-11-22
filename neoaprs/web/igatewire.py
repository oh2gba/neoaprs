"""Wire model of the topic `igate`."""
from typing import Literal

from pydantic import Field

from .wirebase import Iso, _Model


class IgateState(_Model):
    """The iGate (neoaprs/services/igate.py): what the radio hears is put on APRS-IS, and nothing from APRS-IS is ever sent on the air. Whether it is connected, to which server, and what it has done since the daemon
    started. Told whole as it changes, at most once a second."""
    enabled: bool = Field(description="`igate/enabled` as in force")
    state: Literal["off", "connecting", "connected", "listening", "unverified"] = Field(
        description="`off`: the switch is off; `connecting`: not logged in (yet, or again after a loss, or waiting for what `reason` says is missing); `connected`: logged in and verified, packets are gated; "
                    "`listening`: logged in without a passcode, so that nothing is gated and the stations of the internet are read only; `unverified`: the server did not accept the passcode, nothing is gated "
                    "(the connection reads, as `listening` does) and the login is not tried again with another until the settings change")
    server: str = Field(description="the name the server gave at the login (`T2FINLAND`); empty until it has answered")
    reason: Literal["", "no_server", "no_call", "unreachable", "offline", "not_server", "lost", "unverified"] = Field(
        description="why it is not connected, as a code the page says in its words (the log has the connection's own): `no_server` no server is set; `no_call` our call is not set or is none; `unreachable` the server cannot be reached; "
                    "`offline` the server's name cannot be looked up (no connection); `not_server` it answered as no APRS-IS server, or not in time; `lost` the connection ended; `unverified` the server did not accept the password; "
                    "empty while `connected`, `listening` and `off`")
    gated: int = Field(ge=0, description="packets put on APRS-IS since the daemon started")
    dropped: dict[str, int] = Field(description="packets heard and not put on APRS-IS since the daemon started, by the reason: `tcpip` (TCPIP or TCPXX in the path), `nogate` (NOGATE or RFONLY), `query` (a generic query), "
                                                "`source` (the source is not a station), `own` (our own call), `duplicate` (gated in the last 30 seconds), `newline` (a CR or LF inside), `long` (more than 512 bytes), "
                                                "`frame` (not a UI frame, or a third-party header that is none), `offline` (heard while not connected), `not_air` (not heard on the radio: a packet from the internet or one the Dummy radio made up). A reason that has not happened is not a key")
    last_gated_at: Iso | None = Field(description="when the latest packet was gated; null before the first")
