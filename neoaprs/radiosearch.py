"""What Find my radio (services/radiofinder.py) reports while it goes and when it is done."""
from typing import NamedTuple


class Trying(NamedTuple):
    port: str
    baud: int | None                 # None for a port that has no speed (a Bluetooth device)
    number: int                      # 1 for the first try
    total: int                       # how many tries there are if nothing answers


class Found(NamedTuple):
    port: str
    baud: int | None                 # None for a port that has no speed
    profile: str                     # the key of the TNC profile that fits it (`tnc/profile`)
