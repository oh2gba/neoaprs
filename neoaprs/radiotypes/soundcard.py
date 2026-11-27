"""The radio on a sound card with Direwolf as its modem (direwolf.py): 1200 baud, or 300 on HF.

The daemon starts Direwolf with the radio's sound card and keying and reaches it on its KISS port.
The "direwolf" driver; offered only where the installation carries Direwolf.
"""

from neoaprs.configtypes import int_in
from neoaprs.direwolf import PROFILE, PROFILE_300, TX_GAIN_MAX_DB, TX_GAIN_MIN_DB
from neoaprs.radiotype import Allowed, Band, Can, Field, Limits, RadioType
from neoaprs.radiotypes.common import FM_ALLOWED, FM_LIMITS, SLOW_PACKET_ALLOWED, SLOW_PACKET_LIMITS, fields_of
from neoaprs.radiotypes.mercury import KEYING, RX_CARD, SOUND_CARD, TX_CARD
from neoaprs.tncprofile import Profile

# The transmit level; 0 dB is the most Direwolf sends.
TX_GAIN = Field(
    "tx_gain_db",
    "int",
    int_in(TX_GAIN_MIN_DB, TX_GAIN_MAX_DB),
    "0",
    range=(TX_GAIN_MIN_DB, TX_GAIN_MAX_DB),
    text="radio.field.tx_gain_db",
)
SOUND_CARD_CAN = Can(
    find=False,
    terminal=True,
    tune=True,
    key_test=True,
    scope=False,
    tx_gain=True,
    frequencies=False,
    rx_level=True,
)


def _sound_card(profile: Profile, limits: Limits, allowed: Allowed, band: Band) -> RadioType:
    return RadioType(
        profile.key,
        "fm",
        profile.name,
        f"radio.type.{profile.key}",
        profile.transport,
        "direwolf",
        profile.key,
        fields_of((SOUND_CARD, KEYING, TX_GAIN, TX_CARD, RX_CARD), allowed),
        limits,
        allowed,
        SOUND_CARD_CAN,
        dummy=False,
        systems=frozenset({"linux", "win32"}),
        band=band,
    )


TYPES: tuple[RadioType, ...] = (
    _sound_card(PROFILE, FM_LIMITS, FM_ALLOWED, "vhf_uhf"),
    _sound_card(PROFILE_300, SLOW_PACKET_LIMITS, SLOW_PACKET_ALLOWED, "hf"),
)
