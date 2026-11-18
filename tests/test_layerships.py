"""The ships of the map's layer (neoaprs/services/layerships.py): Fintraffic's whole feed asked at its two addresses with the program's header and nothing of the station, cut to the true circle and the 300 nearest,
ships older than 30 minutes left out, the names from the second address, a refusal that stops it; and the own AIS receiver, a connection the daemon opens and keeps while the source is in force (looked at or not),
its table told to the pages that look at most every five seconds, a lost connection tried again, nothing cut by distance, and no port listened to."""
import asyncio
import json
import os
import re
import socket
import sys
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

import pytest

from neoaprs import aisfeed
from neoaprs.aisdecode import AisPosition, AisStatic
from neoaprs.shiptable import ShipTable
from neoaprs.layerthing import FINTRAFFIC_HEADERS, FINTRAFFIC_LOCATIONS, FINTRAFFIC_VESSELS
from neoaprs.services import layerships
from neoaprs.services.layers import Layers
from neoaprs.updatefetch import FeedAnswer
from tests.support import aissentences as ais
from tests.support.env import remember_stop, until
from tests.support.fakeais import ais_receiver
from tests.support.fakelayers import layers_server
from tests.support.virtualtime import virtual_time
from tests.test_layers import HOME, T0, Net, Settings, tables

HELSINKI = (60.17, 24.94)


async def layers(net: Net, settings: Settings, where: Callable[[], tuple[float, float] | None] = lambda: HOME, environ: dict[str, str] | None = None) -> Layers:
    """The service started on the loop's skipped time, whose clock reads T0 when it is made (the ships' own times are relative to it)."""
    began = asyncio.get_running_loop().time()
    made = Layers(settings, where, "0.21.0", "linux", fetch=net, clock=lambda: T0 + timedelta(seconds=asyncio.get_running_loop().time() - began),
                  environ={"NEOAPRS_UPDATE_CHECK": "1"} if environ is None else environ)
    remember_stop(made.stop)
    await made.start()
    return made


def feature(mmsi: int, lat: float, lon: float, age_min: float = 1.0, sog: float = 10.0, cog: float = 90.0, heading: int = 90, now: datetime = T0) -> dict[str, Any]:
    stamp = int((now - timedelta(minutes=age_min)).timestamp() * 1000)
    return {"mmsi": mmsi, "type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": {"mmsi": mmsi, "sog": sog, "cog": cog, "heading": heading, "timestampExternal": stamp}}


def locations(*features: dict[str, Any]) -> bytes:
    return json.dumps({"type": "FeatureCollection", "features": list(features)}).encode()


def vessels(*named: tuple[int, str, int, str]) -> bytes:
    return json.dumps([{"mmsi": m, "name": n, "shipType": k, "destination": d} for m, n, k, d in named]).encode()


def fintraffic(*features: dict[str, Any], named: tuple[tuple[int, str, int, str], ...] = (), status: int = 200, vessel_status: int = 200) -> Net:
    def answer(url: str) -> FeedAnswer | None:
        if url.endswith("/vessels"):
            return FeedAnswer(vessel_status, vessels(*named) if vessel_status == 200 else b"")
        return FeedAnswer(status, locations(*features) if status == 200 else b"")
    return Net(answer)


# ---- Fintraffic

async def test_fintraffic_is_asked_at_both_its_addresses_with_its_header_and_nothing_of_the_station_and_the_names_arrive() -> None:
    async with virtual_time():
        net = fintraffic(feature(230111000, 60.1, 24.9), named=((230111000, "AURA", 60, "TALLINN"),))
        service = await layers(net, Settings(map_ships="fintraffic", map_radius_km=150, station_call="OH2GBA-7"), where=lambda: HELSINKI)
        told = tables(service)
        service.watch("ships", True)
        await asyncio.sleep(1)
        assert sorted(net.asked) == sorted([FINTRAFFIC_LOCATIONS, FINTRAFFIC_VESSELS]) and net.headers == [FINTRAFFIC_HEADERS] * 2
        assert "OH2GBA" not in " ".join(net.asked) + json.dumps(net.headers) and "?" not in "".join(net.asked), "the station is in no part of the question"
        [thing] = told[-1].things
        assert (told[-1].source, told[-1].away, thing.id, thing.name, thing.ship_type, thing.destination) == ("fintraffic", False, "230111000", "AURA", 60, "TALLINN")


async def test_the_whole_feed_is_cut_to_the_true_circle_and_ships_older_than_30_minutes_are_not_told() -> None:
    async with virtual_time():
        net = fintraffic(feature(1, 60.1, 24.9), feature(2, 60.1, 24.9, age_min=29), feature(3, 60.1, 24.9, age_min=31), feature(4, 65.0, 25.5), feature(5, 59.44, 24.75))
        service = await layers(net, Settings(map_ships="fintraffic", map_radius_km=100), where=lambda: HELSINKI)
        service.watch("ships", True)
        await asyncio.sleep(1)
        assert sorted(t.id for t in service.table("ships").things) == ["1", "2", "5"], "Oulu is outside the circle, the 31 minute old ship is left out, Tallinn (80 km) is in"
        await asyncio.sleep(2 * 60)
        assert sorted(t.id for t in service.table("ships").things) == ["1", "5"], "the 29 minute old one grew too old"


async def test_the_300_nearest_ships_are_told() -> None:
    async with virtual_time():
        many = [feature(1000 + n, 60.17 + n / 5000, 24.94) for n in range(400)]
        service = await layers(fintraffic(*many), Settings(map_ships="fintraffic", map_radius_km=300), where=lambda: HELSINKI)
        service.watch("ships", True)
        await asyncio.sleep(1)
        ids = [t.id for t in service.table("ships").things]
        assert len(ids) == 300 and ids[0] == "1000" and "1299" in ids and "1300" not in ids


async def test_the_positions_are_asked_every_minute_and_the_names_every_quarter_of_an_hour() -> None:
    async with virtual_time():
        net = fintraffic(feature(1, 60.1, 24.9))
        service = await layers(net, Settings(map_ships="fintraffic", map_radius_km=150), where=lambda: HELSINKI)
        service.watch("ships", True)
        await asyncio.sleep(1000)
        assert net.asked.count(FINTRAFFIC_VESSELS) == 2 and 16 <= net.asked.count(FINTRAFFIC_LOCATIONS) <= 17
        service.watch("ships", False)
        await asyncio.sleep(3600)
        assert len(net.asked) <= 19, "nobody looks: nothing is asked"


async def test_a_refusal_of_the_positions_stops_fintraffic_and_a_refusal_of_the_names_only_leaves_the_ships_unnamed() -> None:
    async with virtual_time():
        net = fintraffic(feature(1, 60.1, 24.9), status=404)
        service = await layers(net, Settings(map_ships="fintraffic", map_radius_km=150), where=lambda: HELSINKI)
        service.watch("ships", True)
        await asyncio.sleep(3600 * 2)
        assert net.asked.count(FINTRAFFIC_LOCATIONS) == 1 and service.table("ships").away is True
    async with virtual_time():
        net = fintraffic(feature(1, 60.1, 24.9), vessel_status=404)
        service = await layers(net, Settings(map_ships="fintraffic", map_radius_km=150), where=lambda: HELSINKI)
        service.watch("ships", True)
        await asyncio.sleep(1200)
        assert net.asked.count(FINTRAFFIC_VESSELS) == 1 and net.asked.count(FINTRAFFIC_LOCATIONS) >= 15
        [thing] = service.table("ships").things
        assert thing.name == "" and service.table("ships").away is False


async def test_fintraffic_that_is_not_offered_where_the_circle_misses_its_waters_is_never_asked() -> None:
    async with virtual_time():
        net = fintraffic(feature(1, 50.1, 8.7))
        service = await layers(net, Settings(map_ships="fintraffic", map_radius_km=300), where=lambda: (50.11, 8.68))
        service.watch("ships", True)
        await asyncio.sleep(600)
        assert net.asked == [] and service.states()[1].source == "none" and "fintraffic" not in service.states()[1].offered


async def test_with_the_update_check_off_fintraffic_is_not_asked_and_its_table_says_away() -> None:
    async with virtual_time():
        net = fintraffic(feature(1, 60.1, 24.9))
        service = await layers(net, Settings(map_ships="fintraffic", map_radius_km=150), where=lambda: HELSINKI, environ={"NEOAPRS_UPDATE_CHECK": "0"})
        service.watch("ships", True)
        await asyncio.sleep(600)
        assert net.asked == [] and service.table("ships").away is True


async def test_the_real_question_on_the_loopback_is_packed_has_the_header_and_two_bare_addresses() -> None:
    internet = await layers_server()
    now = datetime.now(tz=T0.tzinfo)
    internet.route("/api/ais/v1/locations", body=locations(feature(230111000, 60.1, 24.9, now=now)), packed=True)
    internet.route("/api/ais/v1/vessels", body=vessels((230111000, "AURA", 60, "TALLINN")), packed=True)
    service = Layers(Settings(map_ships="fintraffic", map_radius_km=150, station_call="OH2GBA-7"), lambda: HELSINKI, "0.21.0", "linux", environ={"NEOAPRS_UPDATE_CHECK": "0", "NEOAPRS_LAYERS_URL": internet.url})
    remember_stop(service.stop)
    await service.start()
    service.watch("ships", True)
    await until(lambda: [t.name for t in service.table("ships").things] == ["AURA"])
    assert sorted(internet.paths()) == ["/api/ais/v1/locations", "/api/ais/v1/vessels"]
    for _, headers in internet.requests:
        assert headers["digitraffic-user"] == "NeoAPRS" and headers["accept-encoding"] == "gzip" and headers["user-agent"] == "NeoAPRS/0.21.0 (linux)"
        assert "OH2GBA" not in json.dumps(headers)


# ---- the own AIS receiver

@pytest.fixture
def no_receiver(monkeypatch: pytest.MonkeyPatch) -> None:
    """The connection to the receiver is refused (a test that is not about the connection): this computer's own port 10110 is never tried."""
    async def refused(host: str, port: int, timeout_sec: float = 10.0) -> Any:
        raise ConnectionRefusedError
    monkeypatch.setattr(aisfeed, "connect", refused)


def position_lines(mmsi: int, lat: float, lon: float, **extra: Any) -> list[str]:
    return ais.sentences(ais.class_a(mmsi, lat, lon, **extra))


async def own(receiver_address: str, settings: Settings | None = None, where: Any = lambda: HOME) -> Layers:
    """The service on real time with the fake receiver's address in force."""
    service = Layers(settings or Settings(map_ships="receiver", map_ships_host=receiver_address), where, "0.21.0", "linux", environ={"NEOAPRS_UPDATE_CHECK": "0"})
    remember_stop(service.stop)
    await service.start()
    return service


def ships_state(service: Layers) -> Any:
    return service.states()[1].receiver


async def test_the_connection_is_there_with_no_page_open_and_the_pages_are_told_nothing_then() -> None:
    receiver = await ais_receiver()
    service = await own(receiver.address)
    told = tables(service)
    await receiver.until_connected()
    await until(lambda: ships_state(service).state == "receiving")
    receiver.send(*position_lines(230111000, 60.1, 24.9), *position_lines(230222000, 60.2, 25.0))
    await until(lambda: ships_state(service).things == 2)
    assert told == [] and ships_state(service).heard_at is not None, "nobody looks: the table is told to nobody"
    service.watch("ships", True)
    assert sorted(t.id for t in service.table("ships").things) == ["230111000", "230222000"], "the first look is served the table as it is"


async def test_a_page_that_looks_is_told_the_table_with_the_names_of_both_classes() -> None:
    receiver = await ais_receiver()
    service = await own(receiver.address)
    service.watch("ships", True)
    told = tables(service)
    await receiver.until_connected()
    receiver.send(*position_lines(230111000, 60.1, 24.9, sog=12.0, cog=45.0, heading=44), *ais.sentences(ais.static_a(230111000, "AURA", 60, "TALLINN")),
                  *ais.sentences(ais.class_b(230333000, 60.3, 24.7, sog=0.0)), *ais.sentences(ais.static_b(230333000, 0, "SEA LARK")), *ais.sentences(ais.static_b(230333000, 1, ship_type=37)))
    await until(lambda: told and len(told[-1].things) == 2 and {t.name for t in told[-1].things} == {"AURA", "SEA LARK"}, 10.0)
    by_id = {t.id: t for t in told[-1].things}
    assert (told[-1].source, told[-1].away) == ("receiver", False)
    assert (by_id["230111000"].ship_type, by_id["230111000"].destination, by_id["230111000"].heading_deg) == (60, "TALLINN", 44)
    assert (by_id["230333000"].ship_type, by_id["230333000"].heading_deg) == (37, None), "at anchor: the diamond"


async def test_the_table_is_told_at_most_every_five_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(layerships, "TELL_EVERY_SEC", 0.3)
    receiver = await ais_receiver()
    service = await own(receiver.address)
    service.watch("ships", True)
    told = tables(service)
    await receiver.until_connected()
    for n in range(30):
        receiver.send(*position_lines(230000000 + n, 60.1 + n / 1000, 24.9))
        await asyncio.sleep(0.02)
    await until(lambda: told and len(told[-1].things) == 30)
    assert 1 <= len(told) <= 6, f"{len(told)} tables for 30 ships in 0.6 s"


async def test_a_lost_connection_is_no_answer_with_the_ships_kept_and_it_is_opened_again(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(layerships, "AIS_RETRY_SEC", (0.05, 0.2))
    receiver = await ais_receiver()
    service = await own(receiver.address)
    service.watch("ships", True)
    told = tables(service)
    await receiver.until_connected()
    receiver.send(*position_lines(230111000, 60.1, 24.9))
    await until(lambda: ships_state(service).things == 1)
    with caplog.at_level("INFO", "neoaprs.layers"):
        receiver.drop()
        await until(lambda: ships_state(service).state == "no_answer" or receiver.connections >= 2)
        await until(lambda: receiver.connections >= 2 and ships_state(service).state == "receiving")
    assert any(t.away and len(t.things) == 1 for t in told), "while it was lost the table said away and kept its ship"
    words = [r.getMessage().rsplit(": ", 1)[1] for r in caplog.records if "the AIS receiver at 127.0.0.1" in r.getMessage()]
    assert words[:2] == ["no answer", "receiving"], "one line when the state changes, no more"
    assert receiver.connections >= 2


async def test_a_receiver_that_is_not_there_is_no_answer_tried_again_after_5_seconds_doubling_to_300(monkeypatch: pytest.MonkeyPatch) -> None:
    async with virtual_time():
        waits: list[float] = []
        tries: list[float] = []

        async def refused(host: str, port: int, timeout_sec: float = 10.0) -> Any:
            tries.append(asyncio.get_running_loop().time())
            raise ConnectionRefusedError

        monkeypatch.setattr(aisfeed, "connect", refused)
        service = await layers(Net(), Settings(map_ships="receiver"))
        await asyncio.sleep(1200)
        waits = [round(b - a) for a, b in zip(tries, tries[1:], strict=False)]
        assert waits[:7] == [5, 10, 20, 40, 80, 160, 300] and set(waits[6:]) == {300}
        assert ships_state(service).state == "no_answer"


async def test_the_address_is_this_computers_port_10110_when_empty_and_the_port_10110_when_it_names_none(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, int]] = []

    async def refused(host: str, port: int, timeout_sec: float = 10.0) -> Any:
        seen.append((host, port))
        raise ConnectionRefusedError

    monkeypatch.setattr(aisfeed, "connect", refused)
    before = 0
    for typed in ("", "ais.local", "[fe80::1]", "pi.local:4001"):
        service = await own("", Settings(map_ships="receiver", map_ships_host=typed))
        await until(lambda n=before: len(seen) > n)
        before = len(seen)
        await service.stop()
    assert seen == [("127.0.0.1", 10110), ("ais.local", 10110), ("fe80::1", 10110), ("pi.local", 4001)]


async def test_a_receiver_that_sends_a_thousand_lines_a_second_does_not_hold_the_loop() -> None:
    receiver = await ais_receiver()
    service = await own(receiver.address)
    service.watch("ships", True)
    await receiver.until_connected()
    lines = [line for n in range(2000) for line in position_lines(230000000 + n, 60.0 + (n % 100) / 100, 24.0 + (n // 100) / 10)]
    worst = 0.0

    async def ping() -> None:
        nonlocal worst
        while True:
            sent = time.perf_counter()
            await asyncio.sleep(0.005)
            worst = max(worst, time.perf_counter() - sent - 0.005)

    async def flood() -> None:
        for at in range(0, len(lines), 10):
            receiver.send(*lines[at:at + 10])
            await asyncio.sleep(0.01)
    pinging = asyncio.create_task(ping())
    try:
        await flood()
        await asyncio.sleep(0.3)
    finally:
        pinging.cancel()
    assert 0 < len(service.table("ships").things) <= 2000 and worst < 0.05, f"the loop was held {worst * 1000:.0f} ms"


async def test_nothing_the_own_receiver_gives_is_cut_by_distance_and_the_guard_is_2000_newest(no_receiver: None) -> None:
    async with virtual_time():
        service = await layers(Net(), Settings(map_ships="receiver", map_radius_km=10))
        receiver = service._held["ships"][1]
        receiver._handle([*position_lines(1001, 65.0, 25.5), *position_lines(1002, -33.9, 151.2), *position_lines(1003, 60.2, 24.7)])
        assert sorted(t.id for t in service.table("ships").things) == ["1001", "1002", "1003"], "Oulu and Sydney, with the radius at 10 km"
        for n in range(2100):
            receiver._handle(position_lines(2000 + n, 60.0, 24.0))
            await asyncio.sleep(0.01)
        ids = {t.id for t in service.table("ships").things}
        assert len(ids) == 2000 and "4099" in ids and "1001" not in ids, "the newest are kept"


async def test_a_ship_older_than_30_minutes_is_dropped_from_the_receivers_table(no_receiver: None) -> None:
    async with virtual_time():
        service = await layers(Net(), Settings(map_ships="receiver"))
        service.watch("ships", True)
        service._held["ships"][1]._handle(position_lines(1001, 60.1, 24.9))
        await asyncio.sleep(1700)
        assert [t.id for t in service.table("ships").things] == ["1001"]
        await asyncio.sleep(200)
        assert service.table("ships").things == ()


async def test_when_the_source_is_another_the_connection_is_closed_and_the_table_is_the_new_sources() -> None:
    receiver = await ais_receiver()
    settings = Settings(map_ships="receiver", map_ships_host=receiver.address)
    service = await own(receiver.address, settings)
    await receiver.until_connected()
    settings.config = replace(settings.config, map_ships="none")
    service.config_changed(settings.config)
    await until(lambda: not receiver.writers)
    assert service.states()[1].source == "none" and service.states()[1].receiver is None and service.table("ships").things == ()


async def test_a_save_that_replaces_the_receiver_just_before_the_daemons_stop_still_closes_its_connection() -> None:
    receiver = await ais_receiver()
    settings = Settings(map_ships="receiver", map_ships_host=receiver.address)
    service = await own(receiver.address, settings)
    await receiver.until_connected()
    settings.config = replace(settings.config, map_ships="none")
    service.config_changed(settings.config)
    await service.stop()                                      # (before the old source's own stop has had its turn)
    await until(lambda: not receiver.writers)
    assert not [task for task in asyncio.all_tasks() if task.get_name() == "layers-ais" and not task.done()]


async def test_a_flooding_receiver_is_held_to_the_bound_in_the_table_itself_positions_and_words() -> None:
    now = datetime(2026, 11, 18, 12, 0, 0)
    table = ShipTable(lambda: now, 100)
    for mmsi in range(1, 1001):
        table.position(AisPosition(mmsi, 60.0, 25.0, now + timedelta(seconds=mmsi), None, None, None))
        table.static(AisStatic(mmsi, f"S{mmsi}", 60, ""))
    assert len(table._positions) <= 200 and len(table._statics) <= 200
    kept = {int(thing.id) for thing in table.things(now + timedelta(seconds=1000), 1800)}
    assert 1000 in kept and 900 in kept and 1 not in kept, "the newest are the ones kept"


async def test_the_connection_asks_the_system_to_probe_it_when_it_goes_quiet() -> None:
    receiver = await ais_receiver()
    _, writer = await aisfeed.connect("127.0.0.1", receiver.port)
    try:
        assert writer.get_extra_info("socket").getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE) == 1
    finally:
        writer.close()


async def test_a_half_line_of_a_lost_connection_does_not_cost_the_first_line_of_the_next(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(layerships, "AIS_RETRY_SEC", (0.05, 0.2))
    receiver = await ais_receiver()
    service = await own(receiver.address)
    await receiver.until_connected()
    receiver.send_raw(b"!AIVDM,1,1,,A,garbage")              # (no line end: the connection is lost in the middle of a line)
    receiver.drop()
    await until(lambda: receiver.connections >= 2 and bool(receiver.writers))
    receiver.send(*position_lines(230111000, 60.1, 24.9))
    await until(lambda: ships_state(service).things == 1)


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the process's sockets are read from /proc")
async def test_the_daemon_opens_no_listening_socket_for_the_receiver() -> None:
    def listening() -> set[str]:
        inodes = {m.group(1) for name in os.listdir("/proc/self/fd") if (m := re.fullmatch(r"socket:\[(\d+)\]", os.readlink(f"/proc/self/fd/{name}") if os.path.exists(f"/proc/self/fd/{name}") else ""))}
        found = set()
        for table in ("/proc/net/tcp", "/proc/net/tcp6"):
            with open(table) as f:
                for row in list(f)[1:]:
                    fields = row.split()
                    if fields[3] == "0A" and fields[9] in inodes:
                        found.add(fields[1])
        return found
    receiver = await ais_receiver()
    before = listening()
    assert before, "the fake receiver itself listens (so the reading of the table works)"
    service = await own(receiver.address)
    service.watch("ships", True)
    await receiver.until_connected()
    receiver.send(*position_lines(1001, 60.1, 24.9))
    await until(lambda: ships_state(service).things == 1)
    assert listening() == before
