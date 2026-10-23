"""The Bluetooth devices that are paired with this computer (Linux), for the list of ports. BlueZ keeps them and tells anyone who asks over the system's D-Bus, no root needed; `busctl` (systemd) asks, and where it is not
there `bluetoothctl` does. Nothing is connected to, scanned for or changed: a device that is paired is listed whether it is near or not. A device is left out that says it has no serial port (a phone's headset, a
Bluetooth LE sensor): classic serial ports are all that `bt://` opens."""
import json
import logging
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass

log = logging.getLogger("neoaprs.btpaired")

SERIAL_PORT_UUID = "00001101-0000-1000-8000-00805f9b34fb"
ASK_SEC = 4.0
BUSCTL = ["busctl", "--system", "--json=short", "call", "org.bluez", "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects"]
BLUETOOTHCTL = ["bluetoothctl", "devices", "Paired"]


@dataclass(frozen=True)
class PairedDevice:
    address: str
    name: str


def _run(command: list[str]) -> str:
    """What the command printed, or nothing when it is not installed, fails or does not answer in time."""
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=ASK_SEC, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as e:
        log.debug("%s: %s", command[0], e)
        return ""
    return done.stdout if done.returncode == 0 else ""


def _value(prop: object) -> object:
    return prop.get("data") if isinstance(prop, dict) else None


def from_busctl(output: str) -> list[PairedDevice]:
    """The paired devices in the JSON `busctl` gives for BlueZ's GetManagedObjects (an object path to its interfaces to their properties, each property {"type", "data"})."""
    try:
        objects = json.loads(output)["data"][0]
    except (ValueError, KeyError, IndexError, TypeError):
        return []
    found: dict[str, PairedDevice] = {}
    for interfaces in objects.values() if isinstance(objects, dict) else []:
        device = interfaces.get("org.bluez.Device1") if isinstance(interfaces, dict) else None
        if not isinstance(device, dict):
            continue
        address = _value(device.get("Address"))
        uuids = _value(device.get("UUIDs"))
        if not isinstance(address, str) or _value(device.get("Paired")) is not True:
            continue
        if isinstance(uuids, list) and uuids and SERIAL_PORT_UUID not in [str(u).lower() for u in uuids]:
            continue
        name = str(_value(device.get("Alias")) or _value(device.get("Name")) or "")
        if name == address.replace(":", "-"):                      # (the alias of a device that never gave a name)
            name = ""
        found.setdefault(address.upper(), PairedDevice(address.upper(), name))
    return list(found.values())


def from_bluetoothctl(output: str) -> list[PairedDevice]:
    """The devices in the lines `Device AA:BB:CC:DD:EE:FF Name` of `bluetoothctl devices Paired` (it does not say which have a serial port)."""
    found: list[PairedDevice] = []
    for line in output.splitlines():
        parts = line.strip().split(maxsplit=2)
        if len(parts) >= 2 and parts[0] == "Device" and len(parts[1]) == 17 and parts[1].count(":") == 5:
            found.append(PairedDevice(parts[1].upper(), parts[2] if len(parts) > 2 else ""))
    return found


def paired_devices(run: Callable[[list[str]], str] | None = None) -> list[PairedDevice]:
    """The paired devices that may have a serial port, by name. Empty on a system without BlueZ, without D-Bus, or when the question is not answered."""
    if not sys.platform.startswith("linux"):
        return []
    ask = run or _run
    answer = ask(BUSCTL)
    devices = from_busctl(answer) if answer else from_bluetoothctl(ask(BLUETOOTHCTL))
    return sorted(devices, key=lambda d: (d.name.lower(), d.address))
