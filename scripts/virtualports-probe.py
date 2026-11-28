"""Prove on a real Windows how NeoAPRS lists and opens virtual COM ports; run there by scripts/check-windows-virtualports.

  python scripts/virtualports-probe.py registry NAME      a value NAME only in the registry map (needs administrator
                                                          rights; removed again): listed by name, cannot be opened
  python scripts/virtualports-probe.py pairs A B C D      com0com pairs A-B (Ports class) and C-D (another class):
                                                          listed, opened, data, held, DTR and RTS

Each check prints `ok` or `FAIL` and a line; the exit code is 1 when one failed.
"""

import asyncio
import importlib
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Any

import serial  # type: ignore[import-untyped]
import serial.tools.list_ports  # type: ignore[import-untyped]

from neoaprs import kiss, serialprobe
from neoaprs.coded import code_of
from neoaprs.serialport import SerialError, SerialPort

failed = 0
TEST_VALUE = "\\Device\\NeoAPRSTest0"


def check(ok: bool, what: str) -> None:
    global failed
    failed += not ok
    print(f"{'ok  ' if ok else 'FAIL'}  {what}", flush=True)


def listing() -> tuple[list[str], list[str], list[serialprobe.PortInfo]]:
    pyserial = [p.device for p in serial.tools.list_ports.comports()]
    ports = serialprobe.offered_ports()
    print(f"      pyserial lists {pyserial}; the registry map {serialprobe.serialcomm_names()}")
    print("      NeoAPRS offers " + ", ".join(f"{p.device}{' (name only)' if p.name_only else ''}" for p in ports))
    return pyserial, serialprobe.serialcomm_names(), ports


async def open_reason(name: str) -> str | None:
    port = SerialPort(name)
    try:
        await port.open()
    except SerialError as e:
        reason: str = e.args[0]  # a Reason, which keeps its code
        return reason
    port.close()
    return None


def registry(name: str) -> None:
    winreg: Any = importlib.import_module("winreg")

    try:  # a machine with no serial port has no map
        winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, serialprobe.SERIALCOMM_KEY).Close()
        made = False
    except FileNotFoundError:
        made = True
    print(f"      the registry map {'is made for the test' if made else 'is there'}")
    with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, serialprobe.SERIALCOMM_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, TEST_VALUE, 0, winreg.REG_SZ, name)
    try:
        pyserial, names, ports = listing()
        check(name in names and name not in pyserial, f"{name} is in the registry map and not in pyserial's list")
        port = next((p for p in ports if p.device == name), None)
        check(port is not None and port.name_only, f"NeoAPRS offers {name} by its name alone")
        check(all(p in [q.device for q in ports] for p in pyserial), "every port pyserial lists is offered too")
        check(name not in [p.device for p in serialprobe.system_ports()], "Find my radio does not try it")
        why = asyncio.run(open_reason(name))
        print(f"      opening {name}: {why}")
        check(why is not None and code_of(why)[0] not in ("radio.port_in_use",), "it cannot be opened, and says so")
    finally:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, serialprobe.SERIALCOMM_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, TEST_VALUE)
        if made:
            winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, serialprobe.SERIALCOMM_KEY)
    check(name not in serialprobe.serialcomm_names(), "the value is removed again")


def until(condition: Callable[[], bool], seconds: float = 5.0) -> bool:
    end = time.monotonic() + seconds
    while not condition():
        if time.monotonic() > end:
            return False
        time.sleep(0.02)
    return True


async def through(near: str, far: str) -> None:
    """Send a KISS frame from `far` (pyserial) to `near` (NeoAPRS's own port) and back."""
    heard = bytearray()
    port = SerialPort(near)
    port.data.connect(heard.extend)
    try:
        await port.open()
    except SerialError as e:
        check(False, f"NeoAPRS's port opens {near}: {e.args[0]}")
        return
    try:
        with serial.Serial(far, 9600, timeout=1) as other:
            frame = kiss.encode(b"\x82\xa0\xb4\x9c\x8a\x82\x60" + b"\x9e\x90\x64\x8e\x84\x82\x61\x03\xf0>test")
            other.write(frame)
            loop_end = asyncio.get_running_loop().time() + 5
            while bytes(heard) != frame and asyncio.get_running_loop().time() < loop_end:
                await asyncio.sleep(0.02)
            check(bytes(heard) == frame, f"a KISS frame written on {far} is read whole on {near} by NeoAPRS's port")
            port.write(frame)
            back = other.read(len(frame))
            check(back == frame, f"one written by NeoAPRS on {near} is read on {far}")
    finally:
        port.close()


def held(name: str) -> None:
    """Another process holds `name`: NeoAPRS says it is in use by another program."""
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            f"import serial,sys; s=serial.Serial({name!r}); print('held', flush=True); sys.stdin.read()",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        check(holder.stdout.readline().strip() == "held", f"another process holds {name}")
        why = asyncio.run(open_reason(name))
        print(f"      opening {name}: {why}")
        check(why is not None and code_of(why)[0] == "radio.port_in_use", "NeoAPRS says: in use by another program")
    finally:
        holder.communicate("")


def lines(near: str, far: str) -> None:
    """Report what com0com passes of DTR and RTS set on `near`, as seen on `far`."""
    with serial.Serial(near) as a, serial.Serial(far) as b:
        for dtr, rts in ((False, False), (True, False), (False, True), (True, True)):
            a.dtr, a.rts = dtr, rts
            time.sleep(0.2)
            print(
                f"      {near} DTR={int(dtr)} RTS={int(rts)}: {far} sees CTS={int(b.cts)} DSR={int(b.dsr)} CD={int(b.cd)}"
            )
        a.rts = True
        check(until(lambda: b.cts), f"RTS on {near} is seen on {far} (as CTS)")
        a.rts = False
        check(until(lambda: not b.cts), f"RTS off on {near} is seen on {far}")
        a.dtr = True
        check(until(lambda: b.dsr), f"DTR on {near} is seen on {far} (as DSR)")


def pairs(classed: list[str], unclassed: list[str]) -> None:
    pyserial, names, ports = listing()
    offered = {p.device: p for p in ports}
    check(all(n in pyserial for n in classed), f"pyserial lists the Ports-class pair {classed}")
    check(not any(n in pyserial for n in unclassed), f"pyserial does not list the other pair {unclassed}")
    check(all(n in names for n in classed + unclassed), "the registry map holds all four")
    check(all(n in offered for n in classed + unclassed), "NeoAPRS offers all four")
    check(all(n in offered and offered[n].name_only for n in unclassed), f"{unclassed} by name alone")
    check(
        not any(n in [p.device for p in serialprobe.system_ports()] for n in unclassed),
        "Find my radio does not try them",
    )
    asyncio.run(through(unclassed[0], unclassed[1]))
    held(unclassed[0])
    lines(unclassed[0], unclassed[1])
    asyncio.run(through(classed[0], classed[1]))


def main(argv: list[str]) -> int:
    if argv[:1] == ["registry"] and len(argv) == 2:
        registry(argv[1])
    elif argv[:1] == ["pairs"] and len(argv) == 5:
        pairs(argv[1:3], argv[3:5])
    else:
        print(__doc__)
        return 0 if argv[:1] in (["-h"], ["--help"]) else 2
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
