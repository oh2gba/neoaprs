"""Rhizomatica's Mercury HF modem (neoaprs/mercury.py): a program the daemon starts and stops with the radio's sound card and the way the radio is keyed, reached on its KISS broadcast port. The "mercury" driver."""
from neoaprs.configtypes import int_in, text_of
from neoaprs.configvalues import mercury_keying
from neoaprs.mercuryscope import TX_GAIN_MAX_DB, TX_GAIN_MIN_DB
from neoaprs.radiotype import Can, Field, RadioType
from neoaprs.radiotypes.common import HF_ALLOWED, HF_LIMITS, fields_of
from neoaprs.tncprofile import MERCURY

SOUND_CARD = Field("sound_card", "text", text_of(200), "", text="radio.field.sound_card", claims="sound_card")      # as `mercury -z` names it; empty: the daemon's own choice (today's mercury/sound_card)
KEYING = Field("keying", "text", mercury_keying, "", text="radio.field.keying", claims="keying")                     # vox, cm108, rts:PORT, dtr:PORT; empty: the daemon's own choice (today's mercury/keying)
TX_GAIN = Field("tx_gain_db", "int", int_in(TX_GAIN_MIN_DB, TX_GAIN_MAX_DB), "0", range=(TX_GAIN_MIN_DB, TX_GAIN_MAX_DB), text="radio.field.tx_gain_db")    # today's mercury/tx_gain_db

TYPES: tuple[RadioType, ...] = (
    RadioType(MERCURY.key, "hf", MERCURY.name, f"radio.type.{MERCURY.key}", MERCURY.transport, "mercury", MERCURY.key, fields_of((SOUND_CARD, KEYING, TX_GAIN), HF_ALLOWED), HF_LIMITS, HF_ALLOWED,
              Can(find=False, terminal=True, tune=True, key_test=True, scope=True, tx_gain=True, frequencies=True), dummy=False),
)
