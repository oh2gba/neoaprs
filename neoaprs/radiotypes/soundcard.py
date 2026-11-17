"""The radio on a sound card, with Direwolf as its modem (neoaprs/direwolf.py): an FM radio behind a Digirig, an AIOC or a USB sound card, which works with nothing else installed. The daemon starts Direwolf
for it with the radio's sound card and the way the radio is keyed, as it starts the Mercury modem for an HF radio, and reaches it on its KISS port. The sound card and the keying are the same settings as the
Mercury modem's, so one card is one resource whichever type uses it. The "direwolf" driver; offered on the systems whose installations carry Direwolf."""
from neoaprs.configtypes import int_in
from neoaprs.direwolf import PROFILE, TX_GAIN_MAX_DB, TX_GAIN_MIN_DB
from neoaprs.radiotype import Can, Field, RadioType
from neoaprs.radiotypes.common import FM_ALLOWED, FM_LIMITS, fields_of
from neoaprs.radiotypes.mercury import KEYING, RX_CARD, SOUND_CARD, TX_CARD

TX_GAIN = Field("tx_gain_db", "int", int_in(TX_GAIN_MIN_DB, TX_GAIN_MAX_DB), "0", range=(TX_GAIN_MIN_DB, TX_GAIN_MAX_DB), text="radio.field.tx_gain_db")      # the transmit level, 0 dB the most Direwolf sends

TYPES: tuple[RadioType, ...] = (
    RadioType("direwolf", "fm", PROFILE.name, "radio.type.direwolf", PROFILE.transport, "direwolf", PROFILE.key, fields_of((SOUND_CARD, KEYING, TX_GAIN, TX_CARD, RX_CARD), FM_ALLOWED), FM_LIMITS, FM_ALLOWED,
              Can(find=False, terminal=True, tune=True, key_test=True, scope=False, tx_gain=True, frequencies=False, rx_level=True), dummy=False, systems=frozenset({"linux", "win32"})),
)
