"""The signals of the program connected, in the one place that does it (`Signal.connect` is for the composition root only): what the radio hears goes to the packet log, the station book, messaging (which hands bulletins to the board) and the queries, what
the book changes goes to the database, and the port the search found is remembered.

Also how the settings become the Tnc's: `tnc_settings`."""
import logging
from dataclasses import replace
from typing import NamedTuple

from .app import Services
from .config import Config
from .packet import Packet
from .packetcodec import tnc2
from .source import Source
from .tnc import Tnc
from .tncprofile import Profile, names_tcp, tcp_url

log = logging.getLogger("neoaprs.wiring")
packets_log = logging.getLogger("neoaprs.packets")


class TncSettings(NamedTuple):
    port: str                   # where to open the radio, "" to listen to the ports for it
    baud: int
    profile: Profile            # what the TNC is: how to switch it to KISS, whether it may be asked if it is there
    fallback_probe: bool        # when the port cannot be opened, listen to the ports for the radio
    skip: tuple[str, ...]       # ports the search never opens (serial/skip)
    pattern: str                # the globs of the ports the search listens to (serial/pattern)


def tnc_settings(config: Config, port_override: str = "", pattern_override: str = "") -> TncSettings:
    """What the Tnc is started with. A port given for this run is the only one tried; otherwise the port of the settings, else the one the search found last time (and a port that cannot be
    opened is followed by the search). The search listens to the ports of serial/pattern, or of `pattern_override` when the process was given one for this run. A TCP profile connects to tcp/host and
    tcp/port (or to the `tcp://` address in serial/port) and never searches."""
    pattern = pattern_override or config.serial_pattern
    profile, baud = config.profile, config.tnc_baud
    if port_override:
        return TncSettings(port_override, baud, profile, False, config.serial_skip_paths, pattern)
    if profile.transport == "tcp":
        return TncSettings(config.serial_port if names_tcp(config.serial_port) else tcp_url(config.tcp_host, config.tcp_port), baud, profile, False, config.serial_skip_paths, pattern)
    return TncSettings(config.serial_port or config.serial_last_port, baud, profile, True, config.serial_skip_paths, pattern)


def apply_tnc_settings(tnc: Tnc, settings: TncSettings) -> None:
    """For a Tnc that is stopped."""
    tnc.port, tnc.baud, tnc.profile, tnc.fallback_probe, tnc.skip, tnc.pattern = settings


def wire(parts: Services) -> None:
    tnc, book, packetlog = parts.tnc, parts.stationbook, parts.packetlog
    tnc.packet.connect(_log_packet)
    tnc.packet.connect(packetlog.append)
    tnc.packet.connect(book.take)
    tnc.packet.connect(parts.weatherlog.take)
    tnc.packet.connect(parts.messaging.on_packet)
    tnc.packet.connect(parts.queries.on_packet)
    book.changed.connect(packetlog.save_station)
    book.removed.connect(packetlog.delete_station)
    tnc.state_changed.connect(lambda state: _remember_port(parts, state))


def _log_packet(packet: Packet) -> None:
    packets_log.info("%s%s -> %s", "sent " if packet.direction == "out" else "", tnc2(packet), packet.summary)


def _remember_port(parts: Services, state: Source.State) -> None:
    """A port the search found is stored as serial/last_port and tried first next time. Not a port that was named (the settings or --port) and opened."""
    if state is not Source.State.CONNECTED or parts.port_override or parts.config.profile.transport == "tcp":
        return
    path, config = parts.tnc.path, parts.config
    if path and path not in (config.serial_port, config.serial_last_port):
        parts.tasks.spawn(_store_last_port(parts, path), "remember-port")


async def _store_last_port(parts: Services, path: str) -> None:
    if await parts.store.put_setting("serial/last_port", path):
        parts.config = replace(parts.config, serial_last_port=path)
        log.info("the radio was found on %s; it is tried first next time", path)
