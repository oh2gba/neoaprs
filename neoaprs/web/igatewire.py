"""Wire model of the topic `igate`."""

from typing import Literal

from pydantic import Field

from .wirebase import Iso, _Command, _Message, _Model


class IgateState(_Model):
    """The login to APRS-IS (neoaprs/services/igate.py): it shows the internet's stations (`igate/enabled`), puts what the radios hear on APRS-IS (`igate/gate`, the iGate), or both, and nothing from APRS-IS is
    ever sent on the air. Whether it is connected, to which server, and what it has done since the daemon started. Told whole as it changes, at most once a second."""

    enabled: bool = Field(description="`igate/enabled` (Show Internet stations) as in force")
    gate: bool = Field(
        description="`igate/gate` (Send what I hear) as in force: what the radios hear is put on APRS-IS while `state` is `connected`"
    )
    state: Literal["off", "connecting", "connected", "listening", "unverified"] = Field(
        description="`off`: both ticks are off; `connecting`: not logged in (yet, or again after a loss, or waiting for what `reason` says is missing); `connected`: logged in and verified, packets are gated; "
        "`listening`: logged in without a passcode (`gate` is off), so that nothing is gated and the stations of the internet are read only; `unverified`: the server did not accept the passcode, nothing is gated "
        "(the connection reads, as `listening` does) and the login is not tried again with another until the settings change"
    )
    server: str = Field(description="the name the server gave at the login (`T2FINLAND`); empty until it has answered")
    reason: Literal["", "no_server", "no_call", "unreachable", "offline", "not_server", "lost", "unverified"] = Field(
        description="why it is not connected, as a code the page says in its words (the log has the connection's own): `no_server` no server is set; `no_call` our call is not set or is none; `unreachable` the server cannot be reached; "
        "`offline` the server's name cannot be looked up (no connection); `not_server` it answered as no APRS-IS server, or not in time; `lost` the connection ended; `unverified` the server did not accept the password; "
        "empty while `connected`, `listening` and `off`"
    )
    gated: int = Field(ge=0, description="packets put on APRS-IS since the daemon started")
    dropped: dict[str, int] = Field(
        description="packets heard and not put on APRS-IS since the daemon started, by the reason: `tcpip` (TCPIP or TCPXX in the path), `nogate` (NOGATE or RFONLY), `query` (a generic query), "
        "`source` (the source is not a station), `own` (our own call), `duplicate` (gated in the last 30 seconds), `newline` (a CR or LF inside), `long` (more than 512 bytes), "
        "`frame` (not a UI frame, or a third-party header that is none), `offline` (heard while not connected), `not_air` (not heard on the radio: a packet from the internet or one the Dummy radio made up). A reason that has not happened is not a key"
    )
    last_gated_at: Iso | None = Field(description="when the latest packet was gated; null before the first")


class IgateSentLine(_Model):
    """A line that was put on APRS-IS."""

    at: Iso = Field(description="when it was sent")
    radio: int | None = Field(ge=1, description="the radio that heard the packet; null for our own position")
    line: str = Field(
        description="the line as it went to the server, after the gating rules (the TNC2 text): other stations' data, shown as text only"
    )


class IgateLook(_Command):
    """With `on`, this page shows the lines that Send what I hear has put on APRS-IS (the Internet box of the settings is open, `igate/gate` is on and the page is in front): it is sent `igate_sent` with the kept lines at once and then each line as it is
    sent. With `on` false, or when the page closes, no more. Never refused."""

    cmd: Literal["igate_look"]
    on: bool


class IgateSentMsg(_Message):
    """The lines put on APRS-IS, to a page that looks (`igate_look`): `whole` true replaces the page's list with `lines` (the newest 200 since the daemon started, oldest first, as the page opened the box), false adds `lines` (one line as it is sent) to its end."""

    type: Literal["igate_sent"]
    whole: bool
    lines: list[IgateSentLine] = Field(max_length=200)
