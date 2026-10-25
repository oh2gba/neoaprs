"""The signals of the program connected, in the one place that does it (`Signal.connect` is for the composition root only): what the radio hears goes to the packet log, the station book, messaging (which hands bulletins to the board), the queries and our objects (one that another station
reports is theirs and is dropped), our objects go to the station book, what the book changes goes to the database, the port the search found is remembered, and the GPS fix moves our own row on the map and the ALOHA circle.

Also how the settings become the Tnc's: `tnc_settings`, and how the station book is filled from the database at the start: `seed_station_book`."""
import logging
from dataclasses import replace
from datetime import timedelta
from typing import NamedTuple

from .app import Services
from .config import Config
from .packet import Packet
from .packetcodec import tnc2
from .policy import LOG_KEEP_DAYS
from .serialprobe import search_pattern
from .source import Source
from .stationbook import DETAILS_SEEN
from .tnc import Tnc
from .tncprofile import Profile, names_tcp, tcp_url

log = logging.getLogger("neoaprs.wiring")
packets_log = logging.getLogger("neoaprs.packets")
start_log = logging.getLogger("neoaprs.controller")          # what the start of the daemon says is the controller's, whoever does it


class TncSettings(NamedTuple):
    port: str                   # where to open the radio, "" to listen to the ports for it
    baud: int
    profile: Profile            # what the TNC is: how to switch it to KISS, whether it may be asked if it is there
    fallback_probe: bool        # when the port cannot be opened, listen to the ports for the radio
    skip: tuple[str, ...]       # ports the search never opens (serial/skip)
    pattern: str                # the globs of the ports the search listens to (serial/pattern)


def tnc_settings(config: Config, port_override: str = "", pattern_override: str = "") -> TncSettings:
    """What the Tnc is started with. A port given for this run is the only one tried; otherwise the port of the settings, else the one the search found last time (and a port that cannot be
    opened is followed by the search). The search listens to the ports of `pattern_override` when the process was given one for this run, else of NEOAPRS_SERIAL_PATTERN when that is set, else of serial/pattern. A TCP profile connects to tcp/host and
    tcp/port (or to the `tcp://` address in serial/port) and never searches."""
    pattern = pattern_override or search_pattern(config.serial_pattern)
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
    tnc.packet.connect(parts.ownobjects.on_packet)
    tnc.packet.connect(parts.digipeater.on_packet)               # (after the rest: what was heard is logged and handled before the copy that is sent)
    parts.ownobjects.changed.connect(book.own_object)
    parts.ownobjects.removed.connect(book.forget_own)
    book.changed.connect(packetlog.save_station)
    book.removed.connect(packetlog.delete_station)
    tnc.state_changed.connect(lambda state: _remember_port(parts, state))
    parts.config_changed.connect(lambda config: parts.aloha.refresh())                  # (our position may have moved)
    parts.gps_feed.fixed.connect(parts.gps.take)                                         # the GPS fix, and where it is: the service keeps it, the book and the ALOHA circle follow it
    parts.gps_feed.changed.connect(parts.gps.feed_changed)
    parts.gps.moved.connect(lambda: place_me(parts))
    parts.gps.moved.connect(parts.aloha.refresh)


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


def place_me(parts: Services) -> None:
    """Our own station in the book: at the latest GPS fix, however old, while the beacon is a moving station's and the GPS has given one, else at the position of the settings (and none until there is a call and
    a position)."""
    c, fix = parts.config, parts.gps.mobile_fix()
    if c.station_call and fix is not None:
        parts.stationbook.set_me(c.station_call, fix.lat, fix.lon, c.station_symbol_table, c.station_symbol_code, c.station_comment,
                                 course_deg=fix.course_deg, speed_kmh=fix.speed_kmh, altitude_m=fix.altitude_m, at=fix.at)
    elif c.station_call and c.station_position is not None:
        parts.stationbook.set_me(c.station_call, *c.station_position, c.station_symbol_table, c.station_symbol_code, c.station_comment)
    else:
        parts.stationbook.clear_me()                                 # (no own station until there is a call and a position)


async def seed_station_book(parts: Services) -> None:
    """The station book made from the packets, the messages and the weather log kept in the database, at the start."""
    book, packetlog = parts.stationbook, parts.packetlog
    book.seed(await packetlog.stations())
    book.seed_deliveries(await packetlog.deliveries())
    place_me(parts)
    book.seed_tracks(await packetlog.positions(LOG_KEEP_DAYS))      # (after our own station is in the book: it gets no track)
    await _seed_weather(parts)
    book.seed_details(await packetlog.recent(DETAILS_SEEN))
    book.seed_messaging(await packetlog.messaging_evidence(LOG_KEEP_DAYS))
    book.seed_recent(await packetlog.since(parts.clock() - timedelta(hours=1)))


async def _seed_weather(parts: Services) -> None:
    """The weather log made from the packets kept when it is empty (once), then the newest observation of each station into the book."""
    if await parts.weatherlog.count() == 0:
        made = await parts.weatherlog.backfill(LOG_KEEP_DAYS)
        if made:
            start_log.info("the weather log was empty: %d observations were read from the packets already kept", made)
    parts.stationbook.seed_weather(await parts.weatherlog.latest_all())
