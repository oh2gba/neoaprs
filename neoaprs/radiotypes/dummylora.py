"""The Dummy LoRa radio: no board, no port, a LoRa APRS network of made-up stations round the station (dummylorascene.py), heard in TNC2 text as a board hears it, each packet with the signal-to-noise
ratio and the strength a board measures. The first type of the kind `lora`: a description here, the "tnc" driver with its own line (dummyworlds.py), its texts in the page's catalogues. It is last of its kind
in the page's list, as every Dummy is.

What the kind LoRa may do and cannot do, which every type of the kind shares (`LORA_LIMITS`, `LORA_ALLOWED`; the numbers and their reasons are neoaprs/radiorules.py's): frames up to 250 bytes, and 252 bytes
of text on the air; the beacon timed no more often than on HF, with HF's pauses; paths, WIDE1-1 when the radio's own is empty, and SmartBeaconing, as the LoRa networks use them; no digipeating by us (the
network's iGates repeat WIDE1-1 already, and a second repeat of each frame takes the one shared channel twice as long); internet gateways hear the kind (the LoRa iGates); the ALOHA circle is not worked out
for it, as it is for a shared channel of 1200 baud only. A box of it has nothing but its Enable, its name and its beacon's choices: no port to find, no terminal,
no tuning and no dials."""
from neoaprs.radiorules import LORA_BEACON_JITTER_SEC, LORA_BEACON_MIN_MIN, LORA_MAX_FRAME, LORA_RETRY_JITTER_SEC
from neoaprs.radiotype import Allowed, Limits, RadioType
from neoaprs.radiotypes.common import fields_of
from neoaprs.radiotypes.dummy import NOTHING
from neoaprs.tnc2line import MAX_TEXT
from neoaprs.tncprofile import DUMMY_LORA

LORA_LIMITS = Limits(LORA_MAX_FRAME, LORA_BEACON_MIN_MIN, LORA_BEACON_JITTER_SEC, LORA_RETRY_JITTER_SEC, MAX_TEXT)
LORA_PATH = "WIDE1-1"                  # the path of the LoRa networks, which their iGates repeat (aprs-reference/lora-plan.md section 2.5)
LORA_ALLOWED = Allowed(paths=True, digipeat=False, smart_beacon=True, gateway_heard=True, shared_channel=False)

TYPES: tuple[RadioType, ...] = (
    RadioType(DUMMY_LORA.key, "lora", DUMMY_LORA.name, f"radio.type.{DUMMY_LORA.key}", DUMMY_LORA.transport, "tnc", DUMMY_LORA.key, fields_of((), LORA_ALLOWED), LORA_LIMITS, LORA_ALLOWED, NOTHING, dummy=True,
              recommended_path=LORA_PATH),
)
