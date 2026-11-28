"""The COM names in Windows' registry map of serial ports (HKLM\\HARDWARE\\DEVICEMAP\\SERIALCOMM).

Every serial port driver writes its name there, also a virtual port filed under a device class other than
"Ports" (com0com without its Ports class option, hub4com, VSPE), which pyserial's list leaves out.
Read only; `winreg` is imported late so tests can stub it and other systems never load it.
"""

import importlib
import logging
from typing import Any

log = logging.getLogger("neoaprs.serialport")

SERIALCOMM_KEY = r"HARDWARE\DEVICEMAP\SERIALCOMM"


def _registry() -> Any:
    return importlib.import_module("winreg")


def names(registry: Any = None) -> list[str]:
    """Return the port names the map holds, each once whatever its case; none if the map cannot be read."""
    try:
        winreg = registry if registry is not None else _registry()
        found: dict[str, str] = {}
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, SERIALCOMM_KEY) as key:
            index = 0
            while True:
                try:
                    _device, data, _kind = winreg.EnumValue(key, index)
                except OSError:  # no more values
                    break
                index += 1
                if isinstance(data, str) and (name := data.strip().rstrip("\0").strip()):
                    found.setdefault(name.upper(), name)
    except (ImportError, OSError) as e:
        log.debug("the registry map of serial ports was not read: %s", e)
        return []
    return list(found.values())
