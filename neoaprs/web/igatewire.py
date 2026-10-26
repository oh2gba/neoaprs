"""The receive-only iGate on the wire: the topic `igate`. Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`. The settings (`igate/enabled`, `igate/server`, `igate/password`) are in the topic `config` like the others."""
from typing import Literal

from pydantic import Field

from .wirebase import Iso, _Model


class IgateState(_Model):
    """The receive-only iGate (neoaprs/services/igate.py): what the radio hears is put on APRS-IS, and nothing from APRS-IS is ever sent on the air. Whether it is connected, to which server, and what it has done since the daemon
    started. Told whole as it changes, at most once a second."""
    enabled: bool = Field(description="`igate/enabled` as in force")
    state: Literal["off", "connecting", "connected", "unverified"] = Field(
        description="`off`: the switch is off; `connecting`: not logged in (yet, or again after a loss, or waiting for what `problem` says is missing); `connected`: logged in and verified, packets are gated; "
                    "`unverified`: the server did not accept the password, nothing is sent and the login is not tried again until the settings change")
    server: str = Field(description="the name the server gave at the login (`T2FINLAND`); empty until it has answered")
    problem: str = Field(description="why it is not connected: what is missing (the call, the password, the server) or the connection's own words (`Connection refused`, `the server did not accept the password`); empty while `connected` and `off`")
    gated: int = Field(ge=0, description="packets put on APRS-IS since the daemon started")
    dropped: dict[str, int] = Field(description="packets heard and not put on APRS-IS since the daemon started, by the reason: `tcpip` (TCPIP or TCPXX in the path), `nogate` (NOGATE or RFONLY), `query` (a generic query), "
                                                "`source` (the source is not a station), `own` (our own call), `duplicate` (gated in the last 30 seconds), `newline` (a CR or LF inside), `long` (more than 512 bytes), "
                                                "`frame` (not a UI frame, or a third-party header that is none), `offline` (heard while not connected), `not_air` (not heard on the radio: a packet from the internet or one the Dummy radio made up). A reason that has not happened is not a key")
    last_gated_at: Iso | None = Field(description="when the latest packet was gated; null before the first")
