"""What every type of radio shares: the fields of the operator's choices on a radio (whether the beacon and the status go out on it, the path of our frames, the digipeater), each kept by a type only where it is allowed
(`fields_of`), the values of the kinds (`FM_LIMITS`, `HF_LIMITS`, `LORA_LIMITS`, `FM_ALLOWED`, `HF_ALLOWED`, `LORA_ALLOWED`), whose numbers and reasons are neoaprs/radiotype.py's, and what the types
share whatever their kind (`NOTHING_ALLOWED`, `TERMINAL_ONLY`, `LISTENS`)."""
from dataclasses import replace

from neoaprs.configtypes import boolean
from neoaprs.configvalues import digipeater_path
from neoaprs.radiotype import (FM_BEACON_MIN_MIN, HF_BEACON_JITTER_SEC, HF_BEACON_MIN_MIN, HF_MAX_FRAME, HF_RETRY_JITTER_SEC, LORA_BEACON_JITTER_SEC, LORA_BEACON_MIN_MIN, LORA_MAX_FRAME,
                               LORA_MAX_KISS, LORA_RETRY_JITTER_SEC, Allowed, Can, Field, Limits)
from neoaprs.tnc2line import MAX_TEXT

BEACON = Field("beacon", "bool", boolean, "true", text="radio.field.beacon")               # the beacon goes out on this radio (Send on)
STATUS = Field("status", "bool", boolean, "false", text="radio.field.status")              # the status report goes out on this radio (the status's Send on); no radio ticked: the main radio (beaconrule.status_radios)
PATH = Field("path", "path", digipeater_path, "", text="radio.field.path")                 # the digipeaters of our frames on it: empty the recommended path of the symbol, DIRECT none (today's beacon/path)
DIGIPEAT = Field("digipeat", "bool", boolean, "false", text="radio.field.digipeat")        # the fill-in digipeater repeats what this radio hears (today's digi/enabled)
COMMON_FIELDS: tuple[Field, ...] = (BEACON, STATUS, PATH, DIGIPEAT)

NOTHING_ALLOWED = Allowed(paths=False, digipeat=False, smart_beacon=False, gateway_heard=False, shared_channel=False)     # no path, digipeater, SmartBeaconing, gateway or shared channel of ours
TERMINAL_ONLY = Can(find=False, terminal=True, tune=False, key_test=False, scope=False, tx_gain=False, frequencies=False)    # a Terminal and nothing else to do on the radio
LISTENS = replace(TERMINAL_ONLY, transmit=False)          # a radio that only receives (`Can.transmit` False): no rule picks it to send on, and its line is never written to

FM_LIMITS = Limits(None, FM_BEACON_MIN_MIN, 0, 0)
HF_LIMITS = Limits(HF_MAX_FRAME, HF_BEACON_MIN_MIN, HF_BEACON_JITTER_SEC, HF_RETRY_JITTER_SEC)
FM_ALLOWED = Allowed(paths=True, digipeat=True, smart_beacon=True, gateway_heard=True, shared_channel=True)
HF_ALLOWED = NOTHING_ALLOWED            # (HF is allowed none of them: its own name, as the other kinds', for the rules that read a kind's)
LORA_LIMITS = Limits(LORA_MAX_FRAME, LORA_BEACON_MIN_MIN, LORA_BEACON_JITTER_SEC, LORA_RETRY_JITTER_SEC, MAX_TEXT, max_kiss=LORA_MAX_KISS)      # every type of the kind LoRa (radiotypes/dummylora.py says why)
LORA_ALLOWED = Allowed(paths=True, digipeat=False, smart_beacon=True, gateway_heard=True, shared_channel=False)
LORA_PATH = "WIDE1-1"                  # the path of the LoRa networks, which their iGates repeat (aprs-reference/lora-plan.md section 2.5)


def fields_of(own: tuple[Field, ...], allowed: Allowed, *, transmit: bool = True) -> tuple[Field, ...]:
    """A type's fields: its own, then the beacon and the status where it can send (`Can.transmit`), and the path and the digipeater where it is allowed them."""
    return (*own, *((BEACON, STATUS) if transmit else ()), *((PATH,) if allowed.paths else ()), *((DIGIPEAT,) if allowed.digipeat else ()))
