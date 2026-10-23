"""The beacon and the status on the wire: the commands to send our position packet and our status report now. The interval and the times of the beacon are fields of `status` (neoaprs/web/hostwire.py). Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from .wirebase import _Command


class BeaconNow(_Command):
    """Sends our position packet now, with the settings as they are (the same packet as the timer's), and the next one is an interval later. It goes out through the TNC, so it is not answered:
    it arrives as the new `packets` row with direction `out`, and `status` follows with the time of the beacon. Answered with an `error` when it could not be sent: the TNC is not connected, or
    the settings make no frame."""
    cmd: Literal["beacon_now"]


class StatusNow(_Command):
    """Sends our status report now, with the settings as they are (from the text or from the radio, as `status/source` says), whether it changed and inside the interval; the next one of the timer
    is an interval later. It goes out through the TNC, so it is not answered: it arrives as the new `packets` row with direction `out`, and `status` follows with the text. Answered with an `error` when
    it could not be sent: the status is off or has no text, the radio is away, the call is not set, the TNC is not connected or the settings make no frame."""
    cmd: Literal["status_now"]
