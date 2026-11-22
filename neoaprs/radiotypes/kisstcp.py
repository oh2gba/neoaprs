"""KISS over TCP: a program or bridge reached by host and port (Direwolf, the sound-card modems).

The port may also be a tcp:// address. The "tnc" driver.
"""
from dataclasses import replace

from neoaprs.configtypes import int_in
from neoaprs.configvalues import host_name
from neoaprs.radiotype import Field, RadioType
from neoaprs.radiotypes.common import FM_ALLOWED, FM_LIMITS, TERMINAL_ONLY, fields_of
from neoaprs.radiotypes.serialtnc import PORT as SERIAL_PORT
from neoaprs.tncprofile import KISS_TCP

# a tcp:// or socket:// address, or empty (then tcp_host and tcp_port): no serial device to claim
PORT = replace(SERIAL_PORT, claims=None)
TCP_PORT_RANGE = (1, 65535)  # the range of tcp/port (config.RANGES)
TCP_HOST = Field("tcp_host", "text", host_name, "127.0.0.1", together="tcp", text="radio.field.tcp_host")
# 8001 is Direwolf, 8100 the sound-card modems
TCP_PORT = Field("tcp_port", "int", int_in(*TCP_PORT_RANGE), "8001", range=TCP_PORT_RANGE, together="tcp", text="radio.field.tcp_port")

TYPES: tuple[RadioType, ...] = (
    RadioType(KISS_TCP.key, "fm", KISS_TCP.name, f"radio.type.{KISS_TCP.key}", KISS_TCP.transport, "tnc", KISS_TCP.key, fields_of((PORT, TCP_HOST, TCP_PORT), FM_ALLOWED), FM_LIMITS, FM_ALLOWED,
              TERMINAL_ONLY, dummy=False),
)
