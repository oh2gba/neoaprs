"""KISS over TCP: a program or a bridge reached by host and port (Direwolf, the sound-card modems), or a tcp:// address in the port. The "tnc" driver."""
from dataclasses import replace

from neoaprs.configtypes import int_in
from neoaprs.configvalues import host_name
from neoaprs.radiotype import Can, Field, RadioType
from neoaprs.radiotypes.common import FM_ALLOWED, FM_LIMITS, fields_of
from neoaprs.radiotypes.serialtnc import PORT as SERIAL_PORT
from neoaprs.tncprofile import KISS_TCP

PORT = replace(SERIAL_PORT, claims=None)      # today's serial/port, here a tcp:// or socket:// address or empty (then tcp/host and tcp/port): no serial device to claim
TCP_PORT_RANGE = (1, 65535)          # the range of today's tcp/port (config.RANGES)
TCP_HOST = Field("tcp_host", "text", host_name, "127.0.0.1", together="tcp", text="radio.field.tcp_host")                                          # today's tcp/host
TCP_PORT = Field("tcp_port", "int", int_in(*TCP_PORT_RANGE), "8001", range=TCP_PORT_RANGE, together="tcp", text="radio.field.tcp_port")           # today's tcp/port: 8001 Direwolf, 8100 the sound-card modems

TYPES: tuple[RadioType, ...] = (
    RadioType(KISS_TCP.key, "fm", KISS_TCP.name, f"radio.type.{KISS_TCP.key}", KISS_TCP.transport, "tnc", KISS_TCP.key, fields_of((PORT, TCP_HOST, TCP_PORT), FM_ALLOWED), FM_LIMITS, FM_ALLOWED,
              Can(find=False, terminal=True, tune=False, key_test=False, scope=False, tx_gain=False, frequencies=False), dummy=False),
)
