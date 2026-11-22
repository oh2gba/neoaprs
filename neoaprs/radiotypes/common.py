"""What every type of radio shares: the fields of the operator's choices (Send on, path ...).

The limits and allowed controls of each kind and the shared sets (`NOTHING_ALLOWED`,
`TERMINAL_ONLY`, `LISTENS`) are here; the numbers are explained in the developer notes.
"""
from dataclasses import replace

from neoaprs.configtypes import boolean
from neoaprs.configvalues import digipeater_path
from neoaprs.radiotype import (FM_BEACON_MIN_MIN, HF_BEACON_JITTER_SEC, HF_BEACON_MIN_MIN, HF_MAX_FRAME, HF_RETRY_JITTER_SEC, LORA_BEACON_JITTER_SEC, LORA_BEACON_MIN_MIN, LORA_MAX_FRAME,
                               LORA_MAX_KISS, LORA_RETRY_JITTER_SEC, Allowed, Can, Field, Limits)
from neoaprs.tnc2line import MAX_TEXT

# the beacon goes out on this radio (Send on)
BEACON = Field("beacon", "bool", boolean, "true", text="radio.field.beacon")
# the status report goes out on this radio (beaconrule.send_on_radios)
STATUS = Field("status", "bool", boolean, "false", text="radio.field.status")
ASK = Field("ask", "bool", boolean, "false", text="radio.field.ask")  # Ask around's query goes out on this radio
# Local info's request goes out on this radio
LOCAL_INFO = Field("local_info", "bool", boolean, "false", text="radio.field.local_info")
# the Send on of each thing that goes to no station in particular
SEND_ON = (BEACON, STATUS, ASK, LOCAL_INFO)
# the digipeaters of our frames: empty is the symbol's recommended path, DIRECT none
PATH = Field("path", "path", digipeater_path, "", text="radio.field.path")
# the fill-in digipeater repeats what this radio hears
DIGIPEAT = Field("digipeat", "bool", boolean, "false", text="radio.field.digipeat")
COMMON_FIELDS: tuple[Field, ...] = (*SEND_ON, PATH, DIGIPEAT)

# no path, digipeater, SmartBeaconing, gateway or shared channel of ours
NOTHING_ALLOWED = Allowed(paths=False, digipeat=False, smart_beacon=False, gateway_heard=False, shared_channel=False)
# a Terminal and nothing else to do on the radio
TERMINAL_ONLY = Can(find=False, terminal=True, tune=False, key_test=False, scope=False, tx_gain=False, frequencies=False)
# a radio that only receives: no rule picks it to send on, its line is never written to
LISTENS = replace(TERMINAL_ONLY, transmit=False)

FM_LIMITS = Limits(None, FM_BEACON_MIN_MIN, 0, 0)
HF_LIMITS = Limits(HF_MAX_FRAME, HF_BEACON_MIN_MIN, HF_BEACON_JITTER_SEC, HF_RETRY_JITTER_SEC)
FM_ALLOWED = Allowed(paths=True, digipeat=True, smart_beacon=True, gateway_heard=True, shared_channel=True)
HF_ALLOWED = NOTHING_ALLOWED  # HF is allowed none of them
# every LoRa type shares these (radiotypes/dummylora.py)
LORA_LIMITS = Limits(LORA_MAX_FRAME, LORA_BEACON_MIN_MIN, LORA_BEACON_JITTER_SEC, LORA_RETRY_JITTER_SEC, MAX_TEXT, max_kiss=LORA_MAX_KISS)
LORA_ALLOWED = Allowed(paths=True, digipeat=False, smart_beacon=True, gateway_heard=True, shared_channel=False)
# the LoRa networks' path, which their iGates repeat (aprs-reference/lora-plan.md 2.5)
LORA_PATH = "WIDE1-1"


def fields_of(own: tuple[Field, ...], allowed: Allowed, *, transmit: bool = True) -> tuple[Field, ...]:
    """Return a type's fields: its own, Send on if it can send, path and digipeater if allowed."""
    return (*own, *(SEND_ON if transmit else ()), *((PATH,) if allowed.paths else ()), *((DIGIPEAT,) if allowed.digipeat else ()))
