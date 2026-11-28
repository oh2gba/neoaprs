"""Connect the program's signals in one place (`Signal.connect` is for the composition root only).

Radio and APRS-IS packets reach different parts; `SEEN_BY_ALL` and `ON_AIR_ONLY` are the one
gate. `seed_station_book` fills the station book from the database at the start.
"""

import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta

from .app import Radio, Services
from .cardlevels import wanted
from .config import LAST_PORT, MESSAGE_RADIOS
from .mercury import DIAL_BAND, SUGGESTED
from .mercurymodem import Mercury
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
# Who sees a packet, by channel (Packet.via), as names of parts in `Services`; a test holds the
# signals to these two lists. The log, station book and weather trends take any channel.
SEEN_BY_ALL = ("packetlog", "stationbook", "weatherlog")
# What answers, acknowledges, repeats or sends: only what was on the radio.
ON_AIR_ONLY = ("messaging", "queries", "qruask", "generalask", "ownobjects", "igate", "pskreporter", "digipeater")
start_log = logging.getLogger("neoaprs.controller")


class AirOnly:
    """Wrap a handler of radio packets: an internet packet is dropped, counted and logged once."""

    def __init__(self, handler: Callable[[Packet], object]) -> None:
        self.handler = handler
        self.refused = 0

    def __call__(self, packet: Packet) -> None:
        if packet.via == IS:
            self.refused += 1
            if self.refused == 1:
                log.warning(
                    "a packet from the internet was handed to %s, which takes packets from the air only: dropped",
                    getattr(self.handler, "__qualname__", "a handler"),
                )
            return
        self.handler(packet)


def wire(parts: Services) -> None:
    book, packetlog = parts.stationbook, parts.packetlog
    parts.internet_packet.connect(_log_packet)
    parts.radio_packet.connect(_log_packet)
    for handler in (packetlog.append, book.take, parts.weatherlog.take):  # SEEN_BY_ALL
        parts.radio_packet.connect(handler)
        parts.internet_packet.connect(handler)
    for on_air in (
        parts.messaging.on_packet,
        parts.queries.on_packet,
        parts.qruask.on_packet,
        parts.generalask.on_packet,
        parts.ownobjects.on_packet,
        parts.igate.on_packet,
        parts.pskreporter.on_packet,
        parts.digipeater.on_packet,
    ):
        # The digipeater is last: what was heard is logged and handled before the copy is sent.
        parts.radio_packet.connect(AirOnly(on_air))
    parts.digipeater.counted.connect(parts.radio_changed.emit)
    parts.aprsis.heard.connect(parts.hear_internet)
    parts.aprsis.changed.connect(parts.igate.link_changed)
    parts.ownobjects.changed.connect(book.own_object)
    parts.ownobjects.removed.connect(book.forget_own)
    book.changed.connect(packetlog.save_station)
    book.removed.connect(packetlog.delete_station)
    # Alerts follow the book, the operator's settings and the iGate setting.
    book.changed.connect(parts.stationalerts.station_changed)
    parts.prefbook.changed.connect(parts.stationalerts.pref_changed)
    parts.config_changed.connect(parts.stationalerts.settings_changed)
    parts.stationalerts.fired.connect(parts.alerts.station)
    wired: list[object] = []
    parts.radios.wire = lambda radio: wire_radio(parts, radio, wired)
    # Each radio's modem and card take the transmit gain and levels live.
    parts.config_changed.connect(lambda config: _tx_gains(parts))
    for radio in parts.radios.all():
        wire_radio(parts, radio, wired)
    parts.stationbook.removed.connect(parts.radios.forget)
    parts.stationbook.cleared.connect(parts.radios.forget_all)
    # Suggested HF frequencies come from the project's file or the version page.
    parts.updatecheck.dial_changed.connect(lambda dial: _show_frequencies(parts))
    parts.frequencies.changed.connect(lambda: _show_frequencies(parts))
    parts.config_changed.connect(lambda config: parts.aloha.refresh())
    parts.gps_feed.fixed.connect(parts.gps.take)
    parts.gps_feed.changed.connect(parts.gps.feed_changed)
    parts.gps.moved.connect(lambda: place_me(parts))
    parts.gps.moved.connect(parts.aloha.refresh)
    parts.mapfetch.changed.connect(parts.mapauto.fetch_changed)
    parts.config_changed.connect(parts.layers.config_changed)
    parts.config_changed.connect(parts.pskreporter.settings_changed)
    parts.gps.moved.connect(parts.layers.moved)


def wire_radio(parts: Services, radio: Radio, wired: list[object]) -> None:
    """Connect one radio's line, modem, card and beacon signals, each part once."""

    def first_time(part: object) -> bool:
        if any(part is known for known in wired):
            return False
        wired.append(part)
        return True

    line, modem, card, beacon, id = radio.line, radio.driver.modem, radio.driver.card, radio.beacon, radio.id
    if first_time(line):
        line.packet.connect(parts.radio_packet.emit)
        line.state_changed.connect(lambda state: _remember_port(parts, radio, state))
        line.state_changed.connect(lambda state: parts.radio_changed.emit(id))
        line.changed.connect(lambda: parts.radio_changed.emit(id))
    if modem is not None and first_time(modem):
        if isinstance(modem, Mercury):
            modem.frequencies = parts.suggested_frequencies
            # the line is open only while the modem on its port runs and is the radio's own
            modem.changed.connect(line.modem_changed)
        # A modem restarted on other ports: the radio's line follows it.
        modem.ports_changed.connect(lambda: parts.repoint(id))
        modem.changed.connect(lambda: parts.radio_changed.emit(id))
    if card is not None and first_time(card):
        card.changed.connect(lambda: parts.radio_changed.emit(id))
    if first_time(beacon):
        beacon.sent.connect(parts.igate.beacon_sent)


def _tx_gains(parts: Services) -> None:
    """Give every radio's modem the transmit gain and its sound card the radio's levels."""
    for radio in parts.radios.all():
        if (modem := radio.driver.modem) is not None:
            modem.set_tx_gain(radio.spec.value("tx_gain_db"))
        if (card := radio.driver.card) is not None:
            card.want(*wanted(radio.spec))


def _show_frequencies(parts: Services) -> None:
    """Set the suggested HF frequencies: the project's list, else the version page's, else built in."""
    built_in = [Frequency(band, dial) for band, dial in SUGGESTED]
    parts.suggested_frequencies = suggested(
        parts.frequencies.listed, parts.updatecheck.hf_dial, built_in, f"{DIAL_BAND} m"
    )
    parts.skeds.changed.emit()  # the Skeds tab offers the same dials
    for radio in parts.radios.all():
        if isinstance(modem := radio.driver.modem, Mercury):
            modem.frequencies = parts.suggested_frequencies
            modem.changed.emit()


def _log_packet(packet: Packet) -> None:
    """Log one line per radio packet at INFO; internet packets at DEBUG."""
    level = logging.DEBUG if packet.via == IS else logging.INFO
    if packets_log.isEnabledFor(level):
        packets_log.log(
            level,
            "%s%s -> %s",
            "sent " if packet.direction == "out" else "internet " if packet.via == IS else "",
            tnc2(packet),
            packet.summary,
        )


def _remember_port(parts: Services, radio: Radio, state: Source.State) -> None:
    """Store a found port as radio 1's `last_port`, tried first next time; a named port is not stored.

    A radio the registry has let go remembers nothing (its id may belong to another radio now).
    """
    driver = radio.driver
    if (
        state is not Source.State.CONNECTED
        or radio.id != FM_ID
        or not isinstance(driver, TncDriver)
        or parts.radios.get(radio.id) is not radio
    ):
        return
    path = driver.found_port(radio.spec, parts.config, parts.run)
    if path:
        parts.tasks.spawn(_store_last_port(parts, path), "remember-port")


async def _store_last_port(parts: Services, path: str) -> None:
    """Store the found port as `LAST_PORT` under the settings lock, without save_config.

    save_config would restart the Tnc that was just found.
    """
    async with parts.config_lock:
        if await parts.store.put_setting(LAST_PORT, path):
            parts.config = replace(parts.config, serial_last_port=path)
            log.info("the radio was found on %s; it is tried first next time", path)
            parts.config_changed.emit(parts.config)


def place_me(parts: Services) -> None:
    """Put our own station in the book at the latest GPS fix, else the settings' position, else none."""
    c, fix = parts.config, parts.gps.mobile_fix()
    if c.station_call and fix is not None:
        parts.stationbook.set_me(
            c.station_call,
            fix.lat,
            fix.lon,
            c.station_symbol_table,
            c.station_symbol_code,
            c.station_comment,
            course_deg=fix.course_deg,
            speed_kmh=fix.speed_kmh,
            altitude_m=fix.altitude_m,
            at=fix.at,
        )
    elif c.station_call and c.station_position is not None:
        parts.stationbook.set_me(
            c.station_call, *c.station_position, c.station_symbol_table, c.station_symbol_code, c.station_comment
        )
    else:
        parts.stationbook.clear_me()


async def seed_station_book(parts: Services) -> None:
    """Fill the station book at the start from the database's packets, messages and weather log."""
    book, packetlog = parts.stationbook, parts.packetlog
    book.seed(await packetlog.stations())
    book.seed_deliveries(await packetlog.deliveries())
    place_me(parts)
    # After our own station is in the book: it gets no track.
    book.seed_tracks(await packetlog.positions(LOG_KEEP_DAYS))
    book.seed_radio(await packetlog.radio_positions(LOG_KEEP_DAYS))
    await _seed_weather(parts)
    book.seed_details(await packetlog.recent(DETAILS_SEEN))
    book.seed_routes(reversed(await packetlog.window(ROUTES_SEEN)))
    book.seed_messaging(await packetlog.messaging_evidence(LOG_KEEP_DAYS))
    book.seed_recent(await packetlog.since(parts.clock() - timedelta(hours=1)))
    parts.radios.restore(await parts.store.setting(MESSAGE_RADIOS))


async def _seed_weather(parts: Services) -> None:
    """Backfill an empty weather log from the kept packets, then seed the book's newest observations."""
    if await parts.weatherlog.count() == 0:
        made = await parts.weatherlog.backfill(LOG_KEEP_DAYS)
        if made:
            start_log.info("the weather log was empty: %d observations were read from the packets already kept", made)
    parts.stationbook.seed_weather(await parts.weatherlog.latest_all())
