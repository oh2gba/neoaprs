"""The serial ports of the machine on the wire: the command that asks for the list and the message that answers it. For the page that lets the operator pick the radio's port. Models like the rest of the
protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import _Command, _Message, _Model


class PortRow(_Model):
    """A serial port the system lists, or a Bluetooth device paired with it (Linux). Nothing was opened or connected to find it."""
    device: str = Field(description="the name to give as `serial/port`: `COM3`, `/dev/ttyUSB0`, `bt://AA:BB:CC:DD:EE:FF` for a paired Bluetooth device")
    description: str = Field(description="what the system calls it, such as `USB Serial Port (COM3)`; `n/a` where it does not say")
    hwid: str = Field(description="the hardware id the system gives, such as `USB VID:PID=0403:6001 SER=A1`; `n/a` where it does not say")
    vid: int | None = Field(description="the USB vendor id of an adapter; null for a port that is not USB")
    pid: int | None = Field(description="the USB product id of an adapter; null for a port that is not USB")


class ListPorts(_Command):
    """Asks for the serial ports of the machine the daemon runs on, and the Bluetooth devices paired with it. Answered with `ports` to the page that asked. A KISS TCP port (`socket://127.0.0.1:8001`, Direwolf) is not a port of the machine: it is typed."""
    cmd: Literal["list_ports"]


class PortsMsg(_Message):
    """The answer to `list_ports`."""
    type: Literal["ports"]
    ports: list[PortRow] = Field(description="the ports, in natural order (`COM2` before `COM10`), then the paired Bluetooth devices")
    search: bool = Field(description="whether the daemon looks for the radio among the ports by itself (Linux, the ports that match `serial/pattern`); where it is false (Windows, macOS) the radio is the port in `serial/port`, so the operator picks it from this list")


class FindRadio(_Command):
    """Find my radio: tries the serial ports and the paired Bluetooth devices that the search for the radio looks at (not a KISS TCP address), one after the other and each at the usual speeds, until a TNC answers in KISS or can be
    put into KISS the way a TNC profile does. The radio's own line is closed while it runs and opened again after it. It writes nothing but a carriage return and, to a TNC that answers with text, the steps of the TNC profiles that
    put it into KISS; nothing is sent to the air. Told to the page that asked with `radio_search` messages (`trying` before each try, then `found` or `cancelled`); the page puts the answer in the settings. An `error` when a search is running
    (`radio.busy`), when there is no port to try (`radio.no_ports`) and when none answered (`radio.not_found`)."""
    cmd: Literal["find_radio"]


class FindRadioCancel(_Command):
    """Ends the search of `find_radio`; the page that asked is told `cancelled`. An `error` (`radio.not_running`) when none is running."""
    cmd: Literal["find_radio_cancel"]


class RadioSearchMsg(_Message):
    """How `find_radio` goes, to the page that asked."""
    type: Literal["radio_search"]
    state: Literal["trying", "found", "cancelled"] = Field(description="`trying`: about to try `port` at `baud`; `found`: a TNC answered at `port` at `baud` and `profile` fits it, and the search is over; `cancelled`: `find_radio_cancel` ended it")
    port: str = Field(description="the port being tried or found; empty for `cancelled`")
    baud: int | None = Field(description="the speed; null for a port that has none (a Bluetooth device) and for `cancelled`")
    profile: str = Field(description="for `found`, the key of the TNC profile (`tnc/profile`); empty otherwise")
    number: int = Field(ge=0, description="the try that is under way, from 1; 0 for `found` and `cancelled`")
    total: int = Field(ge=0, description="how many tries there are if nothing answers; 0 for `found` and `cancelled`")
