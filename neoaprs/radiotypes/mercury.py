"""Rhizomatica's Mercury HF modem (neoaprs/mercury.py), reached on its KISS broadcast port.

The daemon starts and stops the program with the radio's sound card and keying, or reaches one the
operator runs himself at an address and port. The "mercury" driver.
"""

from dataclasses import replace

from neoaprs.configtypes import boolean, int_in, optional_int, text_of
from neoaprs.configvalues import dial_or_empty, mercury_keying
from neoaprs.mercury import BROADCAST_PORT
from neoaprs.mercuryscope import TX_GAIN_MAX_DB, TX_GAIN_MIN_DB
from neoaprs.radiotype import Can, Field, RadioType
from neoaprs.radiotypes.common import HF_ALLOWED, HF_LIMITS, fields_of
from neoaprs.radiotypes.kisstcp import TCP_HOST, TCP_PORT
from neoaprs.tncprofile import MERCURY, MERCURY_OWN

# as `mercury -z` names it; empty: the daemon's own choice
SOUND_CARD = Field("sound_card", "text", text_of(200), "", text="radio.field.sound_card", claims="sound_card")
# vox, cm108, rts:PORT, dtr:PORT; empty: the daemon's own choice
KEYING = Field("keying", "text", mercury_keying, "", text="radio.field.keying", claims="keying")
TX_GAIN = Field(
    "tx_gain_db",
    "int",
    int_in(TX_GAIN_MIN_DB, TX_GAIN_MAX_DB),
    "0",
    range=(TX_GAIN_MIN_DB, TX_GAIN_MAX_DB),
    text="radio.field.tx_gain_db",
)
# the card's own playback level in percent (cardlevels.py); empty: never set
TX_CARD = Field("tx_card", "int", optional_int(0, 100), "", range=(0, 100), text="radio.field.tx_card")
RX_CARD = Field("rx_card", "int", optional_int(0, 100), "", range=(0, 100), text="radio.field.rx_card")
# the stations this radio hears directly go to PSK Reporter (services/pskreporter.py)
PSK_REPORT = Field("psk_report", "bool", boolean, "false", text="radio.field.psk_report")
# the dial the radio is tuned to, as the sked board writes it; empty: nothing is reported
PSK_DIAL = Field("psk_dial", "text", dial_or_empty, "", text="radio.field.psk_dial")
# the KISS port of the operator's own Mercury; its control port is 200 above (mercury.CONTROL_OFFSET)
OWN_PORT = replace(TCP_PORT, default=str(BROADCAST_PORT))

TYPES: tuple[RadioType, ...] = (
    RadioType(
        MERCURY.key,
        "hf",
        MERCURY.name,
        f"radio.type.{MERCURY.key}",
        MERCURY.transport,
        "mercury",
        MERCURY.key,
        fields_of((SOUND_CARD, KEYING, TX_GAIN, TX_CARD, RX_CARD, PSK_REPORT, PSK_DIAL), HF_ALLOWED),
        HF_LIMITS,
        HF_ALLOWED,
        Can(find=False, terminal=True, tune=True, key_test=True, scope=True, tx_gain=True, frequencies=True),
        dummy=False,
    ),
    RadioType(
        MERCURY_OWN.key,
        "hf",
        MERCURY_OWN.name,
        f"radio.type.{MERCURY_OWN.key}",
        MERCURY_OWN.transport,
        "mercury",
        MERCURY_OWN.key,
        fields_of((TCP_HOST, OWN_PORT, PSK_REPORT, PSK_DIAL), HF_ALLOWED),
        HF_LIMITS,
        HF_ALLOWED,
        Can(find=False, terminal=True, tune=False, key_test=False, scope=False, tx_gain=False, frequencies=True),
        dummy=False,
    ),
)
