"""The TNCs on a serial line (a device, or a socket://, ble:// or bt:// address as today): the KISS TNC and the three that are put into KISS by text (tncprofile.py says what each one is sent). One driver, "tnc"."""
from neoaprs.configtypes import optional_int
from neoaprs.configvalues import port_address
from neoaprs.radiotype import Can, Field, RadioType
from neoaprs.radiotypes.common import FM_ALLOWED, FM_LIMITS, fields_of
from neoaprs.tncprofile import KANTRONICS, KENWOOD_D710, KENWOOD_TNC2, KISS, Profile

BAUD_RANGE = (300, 921600)           # the range of today's serial/baud (config.RANGES)
PORT = Field("port", "port", port_address, "", text="radio.field.port", claims="serial")          # empty: found by listening to the ports of serial/pattern (today's serial/port)
BAUD = Field("baud", "int", optional_int(*BAUD_RANGE), "", range=BAUD_RANGE, text="radio.field.baud")   # empty: the speed of the profile (today's serial/baud)
SERIAL_CAN = Can(find=True, terminal=True, tune=False, key_test=False, scope=False, tx_gain=False, frequencies=False)


def _serial(profile: Profile) -> RadioType:
    return RadioType(profile.key, "fm", profile.name, f"radio.type.{profile.key}", profile.transport, "tnc", profile.key, fields_of((PORT, BAUD), FM_ALLOWED), FM_LIMITS, FM_ALLOWED, SERIAL_CAN, dummy=False)


TYPES: tuple[RadioType, ...] = tuple(_serial(p) for p in (KENWOOD_TNC2, KENWOOD_D710, KANTRONICS, KISS))     # in the order of today's list (tncprofile.PROFILES)
