"""Rhizomatica's Mercury HF modem (neoaprs/mercury.py), reached on its KISS broadcast port.

The daemon starts and stops the program with the radio's sound card and keying. The "mercury"
driver.
"""

from neoaprs.configtypes import boolean, int_in, optional_int, text_of
from neoaprs.configvalues import dial_or_empty, mercury_keying
from neoaprs.mercuryscope import TX_GAIN_MAX_DB, TX_GAIN_MIN_DB
from neoaprs.radiotype import Can, Field, RadioType
from neoaprs.radiotypes.common import HF_ALLOWED, HF_LIMITS, fields_of
from neoaprs.tncprofile import MERCURY

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
)
