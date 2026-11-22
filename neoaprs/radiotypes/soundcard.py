"""The radio on a sound card with Direwolf as its modem (direwolf.py).

The daemon starts Direwolf with the radio's sound card and keying and reaches it on its KISS port.
The "direwolf" driver; offered only where the installation carries Direwolf.
"""
from neoaprs.configtypes import int_in
from neoaprs.direwolf import PROFILE, TX_GAIN_MAX_DB, TX_GAIN_MIN_DB
from neoaprs.radiotype import Can, Field, RadioType
from neoaprs.radiotypes.common import FM_ALLOWED, FM_LIMITS, fields_of
from neoaprs.radiotypes.mercury import KEYING, RX_CARD, SOUND_CARD, TX_CARD

# The transmit level; 0 dB is the most Direwolf sends.
TX_GAIN = Field("tx_gain_db", "int", int_in(TX_GAIN_MIN_DB, TX_GAIN_MAX_DB), "0", range=(TX_GAIN_MIN_DB, TX_GAIN_MAX_DB), text="radio.field.tx_gain_db")

TYPES: tuple[RadioType, ...] = (
    RadioType("direwolf", "fm", PROFILE.name, "radio.type.direwolf", PROFILE.transport, "direwolf", PROFILE.key, fields_of((SOUND_CARD, KEYING, TX_GAIN, TX_CARD, RX_CARD), FM_ALLOWED), FM_LIMITS, FM_ALLOWED,
              Can(find=False, terminal=True, tune=True, key_test=True, scope=False, tx_gain=True, frequencies=False, rx_level=True), dummy=False, systems=frozenset({"linux", "win32"})),
)
