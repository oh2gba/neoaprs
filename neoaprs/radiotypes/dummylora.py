"""The Dummy LoRa radio: made-up LoRa APRS stations round the station, with no board or port.

Packets are heard in TNC2 text with the SNR and strength a board measures (dummylorascene.py); the
"tnc" driver with its own line (dummyworlds.py). Its box has only Enable, name, beacon and Terminal.
"""

from neoaprs.radiotype import RadioType
from neoaprs.radiotypes.common import LORA_ALLOWED, LORA_LIMITS, LORA_PATH, fields_of
from neoaprs.radiotypes.dummy import DUMMY_CAN
from neoaprs.tncprofile import DUMMY_LORA

TYPES: tuple[RadioType, ...] = (
    RadioType(
        DUMMY_LORA.key,
        "lora",
        DUMMY_LORA.name,
        f"radio.type.{DUMMY_LORA.key}",
        DUMMY_LORA.transport,
        "tnc",
        DUMMY_LORA.key,
        fields_of((), LORA_ALLOWED),
        LORA_LIMITS,
        LORA_ALLOWED,
        DUMMY_CAN,
        dummy=True,
        recommended_path=LORA_PATH,
    ),
)
