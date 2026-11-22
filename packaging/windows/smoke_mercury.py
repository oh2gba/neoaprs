"""Start the mercury.exe NeoAPRS ships and check that it listens on this computer only.

`smoke_mercury.py PATH\\mercury.exe` runs it with the `null` audio backend and waits until its four
TCP ports (KISS, control, ARQ data, UI websocket) appear in `netstat -ano`. It fails when any
is bound to an address other than 127.0.0.1: those ports have no password. The Windows half of the
check in scripts/build-mercury."""
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

LOOPBACK = "127.0.0.1"
WAIT_SEC = 40.0
FIRST_PORT = 18100
PORT_TRIES = 100
CONTROL_OFFSET = 200
# As in neoaprs/mercury.py: the UI port is the broadcast port plus this.
UI_OFFSET = 2000


def listening(netstat: str, pid: int) -> dict[int, set[str]]:
    """Return the addresses process `pid` listens on, by port, from `netstat -ano` text.

    The state word is localised, so a listener is recognised by its all-zero foreign address."""
    found: dict[int, set[str]] = {}
    for line in netstat.splitlines():
        fields = line.split()
        if len(fields) != 5 or fields[0].upper() != "TCP" or fields[-1] != str(pid) or fields[2] not in ("0.0.0.0:0", "[::]:0", "*:*"):
            continue
        address, _, port = fields[1].rpartition(":")
        if port.isdigit():
            found.setdefault(int(port), set()).add(address.strip("[]"))
    return found


def verdict(found: dict[int, set[str]], ports: set[int]) -> str:
    """Return "" if every port listens on 127.0.0.1 alone, else what is wrong."""
    missing = sorted(ports - found.keys())
    if missing:
        return f"not listening yet on {missing}"
    elsewhere = {port: sorted(addresses) for port, addresses in sorted(found.items()) if port in ports and addresses != {LOOPBACK}}
    if elsewhere:
        return f"listens on an address that is not 127.0.0.1: {elsewhere}"
    return ""


def free(port: int) -> bool:
    with socket.socket() as probe:
        try:
            probe.bind((LOOPBACK, port))
        except OSError:
            return False
    return True


def free_ports() -> tuple[int, int, int, int]:
    """Return the first free set of broadcast, control, data and UI ports on the loopback."""
    for broadcast in range(FIRST_PORT, FIRST_PORT + PORT_TRIES):
        four = (broadcast, broadcast + CONTROL_OFFSET, broadcast + CONTROL_OFFSET + 1, broadcast + UI_OFFSET)
        if all(free(port) for port in four):
            return four
    raise SystemExit(f"smoke_mercury: no free set of ports from {FIRST_PORT}")


def table() -> str:
    return subprocess.run(["netstat", "-ano"], check=False, capture_output=True, text=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout


def watch(child: "subprocess.Popen[bytes]", ports: set[int], read_table: Callable[[], str] = table, wait_sec: float = WAIT_SEC, pause_sec: float = 0.5) -> tuple[str, dict[int, set[str]]]:
    """Wait for every port to listen, the program to end or `wait_sec`; return verdict,
    listeners."""
    deadline = time.monotonic() + wait_sec
    while True:
        found = listening(read_table(), child.pid)
        if ports <= found.keys():
            return verdict(found, ports), found
        if child.poll() is not None:
            return f"the program ended with {child.returncode}", found
        if time.monotonic() > deadline:
            return verdict(found, ports), found
        time.sleep(pause_sec)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0 if len(sys.argv) == 2 else 2
    program = Path(sys.argv[1])
    if not program.is_file():
        print(f"smoke_mercury: {program} is not there", file=sys.stderr)
        return 1
    broadcast, control, data, ui = free_ports()
    with tempfile.TemporaryDirectory(prefix="mercury-smoke-", ignore_cleanup_errors=True) as folder:
        ini = Path(folder) / "mercury.ini"
        ini.write_text(f"[store]\nenabled = false\n[main]\nui_enabled = true\nui_port = {ui}\nwaterfall_enabled = false\n", encoding="utf-8")
        argv = [str(program), "-C", str(ini), "-m", "1", "-x", "null", "-b", str(broadcast), "-p", str(control), "-P", "none"]
        # A pipe nobody reads would fill and stop the program, so the output goes to a file.
        out = open(Path(folder) / "mercury.out", "wb")
        child = subprocess.Popen(argv, cwd=folder, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            problem, found = watch(child, {broadcast, control, data, ui})
        finally:
            child.terminate()
            try:
                child.wait(20)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            out.close()
            log = (Path(folder) / "mercury.out").read_text(encoding="utf-8", errors="replace")
    shown = {port: sorted(addresses) for port, addresses in sorted(found.items())}
    if problem:
        print(f"smoke_mercury: {problem} (sockets of process {child.pid}: {shown})\n" + "\n".join(log.splitlines()[-20:]), file=sys.stderr)
        return 1
    print(f"smoke_mercury: {program.name} listens on 127.0.0.1 only: ports {broadcast}, {control}, {data} and {ui} ({shown})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
