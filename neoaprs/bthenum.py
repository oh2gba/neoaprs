"""What the hardware id of a Windows Bluetooth COM port says: the device it reaches, or none.

Windows makes two COM ports for a paired device with a serial port: the device's own, whose BTHENUM
id ends in the device's address, and the computer's incoming one, whose address is twelve zeros.
"""

import re

INCOMING = "000000000000"
# `BTHENUM\{00001101-...}_VID&0001009E_PID&4082\7&1A2B3C4D&0&E458BCC0B53D_C00000000`
_ADDRESS = re.compile(r"&([0-9A-F]{12})_[0-9A-F]+$")


def address_in(hwid: str) -> str | None:
    """Return the twelve hex digits of the device's address, INCOMING for the incoming port, None if no BTHENUM id."""
    upper = hwid.strip().upper()
    found = _ADDRESS.search(upper) if upper.startswith("BTHENUM") else None
    return found.group(1) if found else None


def reaches_device(hwid: str) -> bool:
    """Return whether the id is a Bluetooth COM port of a device (not the incoming one)."""
    address = address_in(hwid)
    return address is not None and address != INCOMING


def plain(address: str) -> str:
    """Return a device address as the ids write it: `AA:BB:CC:DD:EE:FF` becomes `AABBCCDDEEFF`."""
    return address.replace(":", "").replace("-", "").upper()
