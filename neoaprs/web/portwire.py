"""The serial ports of the machine on the wire: the command that asks for the list and the message that answers it. For the page that lets the operator pick the radio's port. Models like the rest of the
protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import _Command, _Message, _Model


class PortRow(_Model):
    """A serial port the system lists. Nothing was opened to find it."""
    device: str = Field(description="the name to give as `serial/port`: `COM3`, `/dev/ttyUSB0`")
    description: str = Field(description="what the system calls it, such as `USB Serial Port (COM3)`; `n/a` where it does not say")
    hwid: str = Field(description="the hardware id the system gives, such as `USB VID:PID=0403:6001 SER=A1`; `n/a` where it does not say")
    vid: int | None = Field(description="the USB vendor id of an adapter; null for a port that is not USB")
    pid: int | None = Field(description="the USB product id of an adapter; null for a port that is not USB")


class ListPorts(_Command):
    """Asks for the serial ports of the machine the daemon runs on. Answered with `ports` to the page that asked. A KISS TCP port (`socket://127.0.0.1:8001`, Direwolf) is not a port of the machine: it is typed."""
    cmd: Literal["list_ports"]


class PortsMsg(_Message):
    """The answer to `list_ports`."""
    type: Literal["ports"]
    ports: list[PortRow] = Field(description="the ports, in natural order (`COM2` before `COM10`)")
    search: bool = Field(description="whether the daemon looks for the radio among the ports by itself (Linux, the ports that match `serial/pattern`); where it is false (Windows, macOS) the radio is the port in `serial/port`, so the operator picks it from this list")
