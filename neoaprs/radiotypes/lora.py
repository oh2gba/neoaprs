"""The LoRa APRS boards: firmware that hands the computer KISS or TNC2 text from LoRa packets.

Types `lora-tcp`, `lora-serial` and `lora-console`, all on the "tnc" driver (loraboard.py reads the
line); limits are in common.py. No frequency field and no Find: the board's own settings stay.
"""

from dataclasses import replace

from neoaprs.configvalues import host_name
from neoaprs.radiotype import Allowed, Can, Field, RadioType
from neoaprs.radiotypes.common import (
    LISTENS,
    LORA_ALLOWED,
    LORA_LIMITS,
    LORA_PATH,
    NOTHING_ALLOWED,
    TERMINAL_ONLY,
    fields_of,
)
from neoaprs.radiotypes.kisstcp import TCP_HOST, TCP_PORT
from neoaprs.radiotypes.serialtnc import BAUD, PORT
from neoaprs.tncprofile import LORA_CONSOLE, LORA_SERIAL, LORA_TCP, Profile


def host_or_empty(text: str) -> str:
    """Return the board's address, or "" while none is typed; the radio then opens nothing."""
    return host_name(text) if text.strip() else ""


# A board on the network is never on this computer, so there is no default address.
BOARD_HOST = replace(TCP_HOST, parse=host_or_empty, default="")


def _board(
    profile: Profile, fields: tuple[Field, ...], allowed: Allowed = LORA_ALLOWED, can: Can = TERMINAL_ONLY
) -> RadioType:
    return RadioType(
        profile.key,
        "lora",
        profile.name,
        f"radio.type.{profile.key}",
        profile.transport,
        "tnc",
        profile.key,
        fields,
        LORA_LIMITS,
        allowed,
        can,
        dummy=False,
        recommended_path=LORA_PATH,
    )


TYPES: tuple[RadioType, ...] = (
    _board(LORA_TCP, fields_of((BOARD_HOST, TCP_PORT), LORA_ALLOWED)),
    _board(LORA_SERIAL, fields_of((PORT, BAUD), LORA_ALLOWED)),
    # Only where it is reached; nothing goes out.
    _board(LORA_CONSOLE, fields_of((PORT, BAUD), NOTHING_ALLOWED, transmit=False), NOTHING_ALLOWED, LISTENS),
)
