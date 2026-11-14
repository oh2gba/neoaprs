"""What every type of radio shares: the fields of the operator's choices on a radio (whether the beacon goes out on it, the path of our frames, the digipeater), each kept by a type only where it is allowed
(`fields_of`), and the values of the two kinds of today (`FM_LIMITS`, `HF_LIMITS`, `FM_ALLOWED`, `HF_ALLOWED`), whose numbers and reasons are neoaprs/radiorules.py's."""
from neoaprs.configtypes import boolean
from neoaprs.configvalues import digipeater_path
from neoaprs.radiorules import FM_BEACON_MIN_MIN, HF_BEACON_JITTER_SEC, HF_BEACON_MIN_MIN, HF_MAX_FRAME, HF_RETRY_JITTER_SEC
from neoaprs.radiotype import Allowed, Field, Limits

BEACON = Field("beacon", "bool", boolean, "true", text="radio.field.beacon")               # the beacon goes out on this radio (Send on)
PATH = Field("path", "path", digipeater_path, "", text="radio.field.path")                 # the digipeaters of our frames on it: empty the recommended path of the symbol, DIRECT none (today's beacon/path)
DIGIPEAT = Field("digipeat", "bool", boolean, "false", text="radio.field.digipeat")        # the fill-in digipeater repeats what this radio hears (today's digi/enabled)
COMMON_FIELDS: tuple[Field, ...] = (BEACON, PATH, DIGIPEAT)

FM_LIMITS = Limits(None, FM_BEACON_MIN_MIN, 0, 0)
HF_LIMITS = Limits(HF_MAX_FRAME, HF_BEACON_MIN_MIN, HF_BEACON_JITTER_SEC, HF_RETRY_JITTER_SEC)
FM_ALLOWED = Allowed(paths=True, digipeat=True, smart_beacon=True, gateway_heard=True, shared_channel=True)
HF_ALLOWED = Allowed(paths=False, digipeat=False, smart_beacon=False, gateway_heard=False, shared_channel=False)


def fields_of(own: tuple[Field, ...], allowed: Allowed) -> tuple[Field, ...]:
    """A type's fields: its own, then the beacon, and the path and the digipeater where it is allowed them."""
    return (*own, BEACON, *((PATH,) if allowed.paths else ()), *((DIGIPEAT,) if allowed.digipeat else ()))
