"""The signals of the program connected, in the one place that does it (`Signal.connect` is for the composition root only): what the radio hears goes to the packet log, the station book, the weather log, messaging (which hands bulletins to the board and messages to
QRU to the QRU server), the queries and our objects (one that another station reports is theirs and is dropped), the receive-only iGate and, last, the digipeater. A packet received from APRS-IS (`Packet.via` is `is`; the connection `Services.aprsis` reads the lines and hands each packet to `Services.hear_internet`) is handed through a signal of its own, `Services.internet_packet`, and
goes only to the packet log, the station book and the weather log (and, from `neoaprs/web/topics.py`, to the page): the one gate for packets from the internet is the pair of lists `SEEN_BY_ALL` and `ON_AIR_ONLY` below. Our objects go to the station book, what the book changes goes to the database, the port the search found is remembered, and the GPS fix moves our own row on the map and the ALOHA circle.

Every radio's packets go to the one signal `Services.radio_packet`, and what changes of a radio (its state, its lines and counters, its modem) is told on `Services.radio_changed` with its id: `wire_radio`
connects a radio's line, its modem and its beacon when the registry makes it (neoaprs/radioregistry.py, which connects nothing itself), so that the handlers are connected once whatever the number of radios.

Also how the station book is filled from the database at the start: `seed_station_book`. How the settings become a radio's line's is its driver's (neoaprs/tncdriver.py, neoaprs/mercurydriver.py)."""
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta

from .app import Radio, Services
from .config import MESSAGE_RADIOS
from .mercury import DIAL_BAND, SUGGESTED
from .packet import IS, Packet
from .packetcodec import tnc2
from .policy import LOG_KEEP_DAYS
from .radiospec import FM_ID
from .source import Source
from .stationbook import DETAILS_SEEN, ROUTES_SEEN
from .tncdriver import TncDriver
from .versions import Frequency, suggested

log = logging.getLogger("neoaprs.wiring")
packets_log = logging.getLogger("neoaprs.packets")
# Who sees a packet, by its channel (Packet.via), as names of the parts in `Services`; no other part is handed a packet (tests/test_internet_gate.py walks the signals and holds them to these two lists).
SEEN_BY_ALL = ("packetlog", "stationbook", "weatherlog")                              # the log, the book of stations and the weather trends take a packet whatever the channel
ON_AIR_ONLY = ("messaging", "queries", "qruask", "generalask", "ownobjects", "igate", "digipeater")                  # what answers, acknowledges, repeats or sends: only what was on the radio
start_log = logging.getLogger("neoaprs.controller")          # what the start of the daemon says is the controller's, whoever does it


class AirOnly:
    """A handler of the packets of the radio that does not take a packet from the internet, though it were handed one: it is dropped, counted and said once in the log. The signal of the radio carries none, so this is the second
    lock on the door the first one keeps shut."""

    def __init__(self, handler: Callable[[Packet], object]) -> None:
        self.handler = handler
        self.refused = 0

    def __call__(self, packet: Packet) -> None:
        if packet.via == IS:
            self.refused += 1
            if self.refused == 1:
                log.warning("a packet from the internet was handed to %s, which takes packets from the air only: dropped", getattr(self.handler, "__qualname__", "a handler"))
            return
        self.handler(packet)


def wire(parts: Services) -> None:
    book, packetlog = parts.stationbook, parts.packetlog
    parts.internet_packet.connect(_log_packet)
    parts.radio_packet.connect(_log_packet)                      # (every radio: what any hears goes the same way, each packet stamped with its radio)
    for handler in (packetlog.append, book.take, parts.weatherlog.take):                       # SEEN_BY_ALL
        parts.radio_packet.connect(handler)
        parts.internet_packet.connect(handler)
    for on_air in (parts.messaging.on_packet, parts.queries.on_packet, parts.qruask.on_packet, parts.generalask.on_packet, parts.ownobjects.on_packet, parts.igate.on_packet, parts.digipeater.on_packet):          # ON_AIR_ONLY
        parts.radio_packet.connect(AirOnly(on_air))               # (the digipeater last: what was heard is logged and handled before the copy that is sent; the iGate puts what any radio hears on APRS-IS, nothing comes the other way)
    parts.aprsis.heard.connect(parts.hear_internet)               # what APRS-IS sends goes in by the one gate for packets from the internet
    parts.aprsis.changed.connect(parts.igate.link_changed)
    parts.ownobjects.changed.connect(book.own_object)
    parts.ownobjects.removed.connect(book.forget_own)
    book.changed.connect(packetlog.save_station)
    book.removed.connect(packetlog.delete_station)
    book.changed.connect(parts.stationalerts.station_changed)                         # the alerts set on stations: what the book changes, what the operator sets, and the settings (whether the internet counts)
    parts.prefbook.changed.connect(parts.stationalerts.pref_changed)
    parts.config_changed.connect(parts.stationalerts.settings_changed)
    parts.stationalerts.fired.connect(parts.alerts.station)                             # (one that fires runs the alert command, as a message to us does; the page is told by its topics)
    wired: list[object] = []                                                             # the lines, modems and beacons connected so far (a radio given another driver may keep its line)
    parts.radios.wire = lambda radio: wire_radio(parts, radio, wired)                   # (a radio made later, or given another driver, is connected the same way)
    for radio in parts.radios.all():
        wire_radio(parts, radio, wired)
    parts.stationbook.removed.connect(parts.radios.forget)                              # (a station let go takes the operator's radio for it along: neoaprs/radioregistry.py)
    parts.stationbook.cleared.connect(parts.radios.forget_all)
    parts.updatecheck.dial_changed.connect(lambda dial: _show_frequencies(parts))        # (the frequencies the HF box suggests come from the project's file or the version page: a move needs no release)
    parts.frequencies.changed.connect(lambda: _show_frequencies(parts))
    parts.config_changed.connect(lambda config: parts.aloha.refresh())                  # (our position may have moved)
    parts.gps_feed.fixed.connect(parts.gps.take)                                         # the GPS fix, and where it is: the service keeps it, the book and the ALOHA circle follow it
    parts.gps_feed.changed.connect(parts.gps.feed_changed)
    parts.gps.moved.connect(lambda: place_me(parts))
    parts.gps.moved.connect(parts.aloha.refresh)
    parts.mapfetch.changed.connect(parts.mapauto.fetch_changed)                         # (a job it began has ended: done, or to be tried again at the next start)


def wire_radio(parts: Services, radio: Radio, wired: list[object]) -> None:
    """One radio's signals, each part of it connected once: what its line hears goes to `radio_packet`, and what changes of it to `radio_changed` with its id; the port its search found is remembered; its
    beacon is also put on APRS-IS (a moving station's); its modem, when it has one, is followed to other ports and takes the transmit gain of the settings live."""
    def first_time(part: object) -> bool:
        if any(part is known for known in wired):
            return False
        wired.append(part)
        return True

    line, modem, beacon, id = radio.line, radio.driver.modem, radio.beacon, radio.id
    if first_time(line):
        line.packet.connect(parts.radio_packet.emit)
        line.state_changed.connect(lambda state: _remember_port(parts, radio, state))
        line.state_changed.connect(lambda state: parts.radio_changed.emit(id))
        line.changed.connect(lambda: parts.radio_changed.emit(id))
    if modem is not None and first_time(modem):
        modem.ports_changed.connect(lambda: parts.repoint(id))                           # (a modem started again on other ports, the old pair taken meanwhile: the radio's line follows it)
        modem.changed.connect(lambda: parts.radio_changed.emit(id))
        parts.config_changed.connect(lambda config: modem.set_tx_gain(radio.spec.value("tx_gain_db")))       # (the transmit gain is set live in the modem, and the tune tone follows it)
    if first_time(beacon):
        beacon.sent.connect(parts.igate.beacon_sent)                                     # (a moving station's beacon is also put on APRS-IS)


def _show_frequencies(parts: Services) -> None:
    """The frequencies the HF box suggests, on the modem it reads them from: the project's list, else the dial the version page names, else the built-in ones; the page's radio topic is told again."""
    built_in = [Frequency(band, dial) for band, dial in SUGGESTED]
    now = suggested(parts.frequencies.listed, parts.updatecheck.hf_dial, built_in, f"{DIAL_BAND} m")
    parts.mercury.frequencies = now
    parts.skeds.changed.emit()                              # (the Skeds tab offers the same dials)
    parts.mercury.changed.emit()


def _log_packet(packet: Packet) -> None:
    """One line for each packet of the radio at INFO; the packets of the internet, many more of them, at DEBUG (`--debug`), so that they do not fill the log."""
    level = logging.DEBUG if packet.via == IS else logging.INFO
    if packets_log.isEnabledFor(level):                  # (the line of a packet of the internet is made only when the log asks for it: they are many)
        packets_log.log(level, "%s%s -> %s", "sent " if packet.direction == "out" else "internet " if packet.via == IS else "", tnc2(packet), packet.summary)


def _remember_port(parts: Services, radio: Radio, state: Source.State) -> None:
    """A port the search found is stored as serial/last_port and tried first next time. Not a port that was named (the settings or --port) and opened. The one row is radio 1's until the radios are stored
    (package D1a), and only a TNC's line is searched for."""
    driver = radio.driver
    if state is not Source.State.CONNECTED or radio.id != FM_ID or not isinstance(driver, TncDriver):
        return
    path = driver.found_port(radio.spec, parts.config, parts.run)
    if path:
        parts.tasks.spawn(_store_last_port(parts, path), "remember-port")


async def _store_last_port(parts: Services, path: str) -> None:
    """The port the search found, as `serial/last_port`: stored and put in force under the lock of the settings (not through save_config, which would restart the Tnc that was just found), and told to the page."""
    async with parts.config_lock:
        if await parts.store.put_setting("serial/last_port", path):
            parts.config = replace(parts.config, serial_last_port=path)
            log.info("the radio was found on %s; it is tried first next time", path)
            parts.config_changed.emit(parts.config)


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
    book.seed_radio(await packetlog.radio_positions(LOG_KEEP_DAYS))     # (the radio's side of the stations that were heard from the internet too)
    await _seed_weather(parts)
    book.seed_details(await packetlog.recent(DETAILS_SEEN))
    book.seed_routes(reversed(await packetlog.window(ROUTES_SEEN)))      # (the newest first, as the window gives them: the routes are read oldest first)
    book.seed_messaging(await packetlog.messaging_evidence(LOG_KEEP_DAYS))
    book.seed_recent(await packetlog.since(parts.clock() - timedelta(hours=1)))
    parts.radios.restore(await parts.store.setting(MESSAGE_RADIOS))     # (the operator's radio by station, on the stations just seeded)


async def _seed_weather(parts: Services) -> None:
    """The weather log made from the packets kept when it is empty (once), then the newest observation of each station into the book."""
    if await parts.weatherlog.count() == 0:
        made = await parts.weatherlog.backfill(LOG_KEEP_DAYS)
        if made:
            start_log.info("the weather log was empty: %d observations were read from the packets already kept", made)
    parts.stationbook.seed_weather(await parts.weatherlog.latest_all())
