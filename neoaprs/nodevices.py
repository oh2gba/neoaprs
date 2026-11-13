"""The switch NEOAPRS_NO_DEVICES=1: a daemon that opens no real device and talks to no real service, whatever its settings say.

A bench daemon (a test's, the smoke test's, the one of the screenshots, a proof on a copy of a real data folder) runs on a machine whose radios are on the desk, and the settings it is given may name the radio's
serial port, the sound card and the keying line of the HF radio, and the APRS-IS login of the operator. Under the switch every door that leads out of the program is shut, each by one call into this module at
the place that would open it:

* no serial device is opened, listed or searched for (the radio's port, the GPS receiver's, a keying line), and no Bluetooth port: `check_port` in the one place a port is opened, `refused` where the ports are listed;
* the Mercury modem program is not started and its sound cards are not listed (`refused`);
* no connection leaves this computer: to APRS-IS, a KISS TCP server, a gpsd, a rigctld or a Mercury on another host (`check_host`), for the update check, the suggested frequencies, Send logs, Update now and the
  map (`check_url`, `url_refused`);
* the default alert command, which shows a notification on the desktop and plays a sound, is not run, and the Dummy HF radio's audio is not played (`refused`).

What stays: the Dummy radios, whatever is on the loopback (a KISS TCP radio, a gpsd, a version page: the fakes of the tests and the benches) and the page's own server.

A door that is shut behaves as it does when its device is not there: the checks raise the system's own error for a file that is missing or a connection that is refused, so the part that asked waits and says what
it says of a radio that is unplugged or a server that is down. The page is told nothing else. The log says it: one line when the daemon starts (`announce`), and one line for each door the first time it is
refused, at the level its part tells a device that is away at.

The variable is read here and nowhere else (`on`), each time it is asked, so that nothing has to be set up before the first door is tried. The switch is on for every value that is not empty and not `0`
(`sets`): `1` is what the benches write, and `true`, `yes`, `on` or a slip of the keyboard keep the doors shut as well. A value that was mistyped must not be the reason a bench daemon keys the radio; the
line at the start names the value it found."""
import errno
import ipaddress
import logging
import os
import urllib.request
from urllib.parse import urlsplit

log = logging.getLogger("neoaprs.nodevices")

ENV = "NEOAPRS_NO_DEVICES"
OFF_VALUES = frozenset({"", "0"})                # the values that leave the switch off (a variable that is not set counts as the empty one); every other value sets it
LOCAL_NAMES = frozenset({"", "localhost"})        # the names that are this computer without a lookup (no host at all is this computer too); any other name is refused unasked
TCP_PORTS = ("socket://", "tcp://")              # the ports that are a TCP connection (KISS over TCP), which may be one to the loopback
TOLD_MAX = 500                                   # the doors remembered as told; the memory starts over beyond that

_told: set[str] = set()


def sets(value: str | None) -> bool:
    """Whether this value of the variable sets the switch: every one but none, the empty one and `0`, the spaces around it aside."""
    return (value or "").strip() not in OFF_VALUES


def on() -> bool:
    """Whether the switch is on."""
    return sets(os.environ.get(ENV))


def announce() -> None:
    """The line at the start of the daemon that says the switch is on, and for which value: one that was meant to leave it off (`false`, `no`) is seen here."""
    if on():
        log.info("%s is set: no serial port, Bluetooth device or sound card is opened, the Mercury modem is not started, nothing but this computer is connected to, and the default alert command is not run "
                 "(the variable is %r: every value but an empty one and 0 sets it)", ENV, os.environ.get(ENV, ""))


def refused(door: str, level: int = logging.WARNING) -> bool:
    """Whether the switch shuts this door; `door` says what does not happen ("the serial port /dev/ttyUSB0 is not opened") and is told in the log the first time, at `level`."""
    if not on():
        return False
    if door not in _told:
        if len(_told) >= TOLD_MAX:
            _told.clear()
        _told.add(door)
        log.log(level, "%s is set: %s", ENV, door)
    return True


def this_computer(host: str) -> bool:
    """Whether `host` is this computer itself: localhost, or an address of the loopback (127.0.0.0/8, ::1, the IPv4 ones in their IPv6 form). A name is not looked up: any other name is somewhere else."""
    name = host.strip().strip("[]").lower().rstrip(".")
    if name in LOCAL_NAMES:
        return True
    try:
        address = ipaddress.ip_address(name.split("%", 1)[0])
    except ValueError:
        return False
    mapped = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) else None
    return (mapped or address).is_loopback


def host_refused(host: str, what: str = "", level: int = logging.WARNING) -> bool:
    """Whether a connection to `host` is refused: the switch is on and the host is not this computer. `what` says what is there ("APRS-IS"), for the log."""
    return on() and not this_computer(host) and refused(f"no connection to {host}" + (f" ({what})" if what else ""), level)


def check_host(host: str, what: str = "", level: int = logging.WARNING) -> None:
    """Raises the error of a server that is not there (ConnectionRefusedError) for a host that is refused."""
    if host_refused(host, what, level):
        raise ConnectionRefusedError(errno.ECONNREFUSED, os.strerror(errno.ECONNREFUSED))


def url_refused(url: str, what: str = "", level: int = logging.INFO) -> bool:
    """Whether the address is refused: it names a host that is not this computer. A path of a file, which names no host, never is."""
    if not on():
        return False
    try:
        host = urlsplit(url.strip()).hostname
    except ValueError:
        return refused(f"no connection to {url!r}", level)             # (an address that cannot be read is not shown to be this computer)
    return host is not None and host_refused(host, what, level)


def check_url(url: str, what: str = "", level: int = logging.INFO) -> None:
    """Raises the error of a server that is not there (ConnectionRefusedError) for an address that is refused."""
    if url_refused(url, what, level):
        raise ConnectionRefusedError(errno.ECONNREFUSED, os.strerror(errno.ECONNREFUSED))


def direct() -> list[urllib.request.BaseHandler]:
    """What an opener of urllib is built with besides its own handlers: under the switch a handler that knows no proxy, nothing otherwise. An address of this computer, which the switch lets through, is then asked
    of this computer itself. With urllib's own handler it would go to the proxy that `http_proxy` or the system's settings name, on another computer (on Linux only `no_proxy` keeps the loopback from it)."""
    return [urllib.request.ProxyHandler({})] if on() else []


def check_port(path: str, level: int = logging.WARNING) -> None:
    """Raises, for a port that is refused, the error it gives when it is not there: FileNotFoundError for a device (`/dev/ttyUSB0`, `COM3`), ConnectionRefusedError for a Bluetooth port (`bt://`, `ble://`), a TCP port
    on another host and any other address pyserial would open. The one port that is let through is a TCP one on this computer (`socket://127.0.0.1:8001`, `tcp://localhost:8001`)."""
    if not on():
        return
    port = path.strip()
    if port.lower().startswith(TCP_PORTS):
        check_url(port, "a KISS TCP port", level)
    elif "://" in port:
        if refused(f"the port {port} is not opened", level):
            raise ConnectionRefusedError(errno.ECONNREFUSED, os.strerror(errno.ECONNREFUSED))
    elif refused(f"the serial port {port} is not opened", level):
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT))
