"""The layers' service (neoaprs/services/layers.py, neoaprs/services/layerasked.py) with a fake fetch and the loop's time skipped (tests/support/virtualtime.py): a source is asked only while a page looks and never
more often than its feed allows however many look; a failure backs off, a refusal of the request stops the feed until the daemon starts again, a 429 is waited out; a service's answer is cut to the true circle and the
nearest, the own receiver's by nothing; the ages; the own receiver asked at the start and at a save, found in its places and its state told; the doors of NEOAPRS_UPDATE_CHECK and NEOAPRS_LAYERS_URL; nothing made
or stopped after the service's stop; and, with a fake server on the loopback, what a service's question carries and that a long answer does not hold the daemon's loop."""
import asyncio
import gzip
import json
import logging
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from neoaprs.config import DEFAULTS, Config
from neoaprs.layerthing import MAX_UNPACKED, LayerTable
from neoaprs.services.layers import Layers
from neoaprs.updatefetch import FeedAnswer
from tests.support.env import remember_stop, until
from tests.support.fakelayers import Answer, layers_server
from tests.support.virtualtime import virtual_time

T0 = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
HOME = (60.2231, 24.7152)
SERVICE = "https://opendata.adsb.fi/api/v3/lat/60.2/lon/24.7/dist/86"
RECEIVER_FIRST = "http://127.0.0.1/tar1090/data/aircraft.json"


def plane(id: str, lat: float = 60.3, lon: float = 24.9, **extra: Any) -> dict[str, Any]:
    return {"hex": id, "lat": lat, "lon": lon, "alt_baro": 8000, "gs": 220.0, "track": 90.0, "seen_pos": 0.0, **extra}


def sky(*planes: dict[str, Any]) -> bytes:
    return json.dumps({"now": 1794812336, "aircraft": list(planes)}).encode()


class Net:
    """The internet and the receivers as a fetch function: `answer(url)` says what each address answers (None: not there); every question is kept."""

    def __init__(self, answer: Callable[[str], FeedAnswer | None] | None = None) -> None:
        self.answer = answer or (lambda url: FeedAnswer(200, sky(plane("461f2a"))))
        self.asked: list[str] = []
        self.headers: list[dict[str, str]] = []

    async def __call__(self, url: str, version: str, platform: str, headers: dict[str, str], max_packed: int, max_unpacked: int, timeout_sec: float = 10.0) -> FeedAnswer | None:
        self.asked.append(url)
        self.headers.append(dict(headers))
        return self.answer(url)


class Settings:
    def __init__(self, **values: Any) -> None:
        self.config: Config = replace(DEFAULTS, radios=(), **values)

    def __call__(self) -> Config:
        return self.config


def clock() -> datetime:
    return T0 + timedelta(seconds=asyncio.get_running_loop().time())


async def layers(net: Net, settings: Settings, where: Callable[[], tuple[float, float] | None] = lambda: HOME, environ: dict[str, str] | None = None) -> Layers:
    made = Layers(settings, where, "0.21.0", "linux", fetch=net, clock=clock, environ={"NEOAPRS_UPDATE_CHECK": "1"} if environ is None else environ)
    remember_stop(made.stop)
    await made.start()
    return made


def tables(service: Layers) -> list[LayerTable]:
    told: list[LayerTable] = []
    service.told.connect(told.append)
    return told


# ---- asked only while a page looks, at most every interval

async def test_a_service_is_asked_only_while_a_page_looks_and_at_most_every_30_seconds() -> None:
    async with virtual_time():
        net = Net()
        service = await layers(net, Settings(map_aircraft="adsbfi"))
        told = tables(service)
        await asyncio.sleep(600)
        assert net.asked == [], "nobody looks: nothing is asked"
        service.watch("aircraft", True)
        await asyncio.sleep(1)
        assert net.asked == [SERVICE] and told[-1].source == "adsbfi" and [t.id for t in told[-1].things] == ["461f2a"]
        await asyncio.sleep(28)
        assert len(net.asked) == 1
        await asyncio.sleep(2)
        assert len(net.asked) == 2
        service.watch("aircraft", False)
        await asyncio.sleep(600)
        assert len(net.asked) == 2, "nobody looks any more"
        service.watch("aircraft", True)
        await asyncio.sleep(1)
        assert len(net.asked) == 3, "a look after a long while asks at once"
        service.watch("aircraft", False)
        service.watch("aircraft", True)
        await asyncio.sleep(1)
        assert len(net.asked) == 3, "but not when the last question is younger than the interval"


async def test_adsb_lol_is_asked_at_most_every_minute() -> None:
    async with virtual_time():
        net = Net()
        service = await layers(net, Settings(map_aircraft="adsblol"))
        service.watch("aircraft", True)
        await asyncio.sleep(1)
        await asyncio.sleep(58)
        assert net.asked == ["https://api.adsb.lol/v2/lat/60.2/lon/24.7/dist/86"]
        await asyncio.sleep(2)
        assert len(net.asked) == 2


async def test_a_failure_waits_twice_as_long_each_time_and_an_answer_puts_it_back() -> None:
    async with virtual_time() as time:
        answers: list[FeedAnswer | None] = [None, FeedAnswer(503, b""), FeedAnswer(200, b"<html>"), FeedAnswer(200, sky())]
        net = Net(lambda url: answers.pop(0) if answers else FeedAnswer(200, sky()))
        at: list[float] = []
        net.answer = (lambda inner: (lambda url: (at.append(time.time()), inner(url))[1]))(net.answer)
        service = await layers(net, Settings(map_aircraft="adsbfi"))
        told = tables(service)
        service.watch("aircraft", True)
        await asyncio.sleep(60 + 120 + 240 + 30 + 5)
        gaps = [round(b - a) for a, b in zip(at, at[1:], strict=False)]
        assert gaps[:4] == [60, 120, 240, 30], "after 1, 2 and 3 failures in a row (no answer, a 503, not readsb's JSON); the answer puts it back to 30 s"
        assert [t.away for t in told[:4]] == [True, True, True, False]


async def test_a_404_stops_the_service_until_the_daemon_starts_again_with_one_warning(caplog: pytest.LogCaptureFixture) -> None:
    async with virtual_time():
        net = Net(lambda url: FeedAnswer(404, b""))
        settings = Settings(map_aircraft="adsbfi")
        service = await layers(net, settings)
        with caplog.at_level(logging.WARNING, "neoaprs.layers"):
            service.watch("aircraft", True)
            await asyncio.sleep(3600)
            service.watch("aircraft", False)
            service.watch("aircraft", True)
            settings.config = replace(settings.config, map_aircraft="adsblol")
            service.config_changed(settings.config)
            await asyncio.sleep(1)
            settings.config = replace(settings.config, map_aircraft="adsbfi")
            service.config_changed(settings.config)
            await asyncio.sleep(3600)
        assert [url for url in net.asked if "adsb.fi" in url] == [SERVICE], "a second request is never made"
        assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 2, "one for adsb.fi, one for adsb.lol"
        assert service.table("aircraft").away


@pytest.mark.parametrize("status", [400, 401, 403])
async def test_every_refusal_of_the_request_itself_stops_the_service(status: int, caplog: pytest.LogCaptureFixture) -> None:
    async with virtual_time():
        net = Net(lambda url: FeedAnswer(status, b""))
        service = await layers(net, Settings(map_aircraft="adsbfi"))
        service.watch("aircraft", True)
        await asyncio.sleep(3600)
        assert len(net.asked) == 1


async def test_a_429_is_waited_out_for_as_long_as_its_retry_after_says() -> None:
    async with virtual_time():
        answers = [FeedAnswer(429, b"", 600.0)]
        net = Net(lambda url: answers.pop(0) if answers else FeedAnswer(200, sky()))
        service = await layers(net, Settings(map_aircraft="adsblol"))
        service.watch("aircraft", True)
        await asyncio.sleep(598)
        assert len(net.asked) == 1
        await asyncio.sleep(4)
        assert len(net.asked) == 2


# ---- the area and the number

async def test_a_services_answer_is_cut_to_the_true_circle_and_the_300_nearest_with_an_emergency_kept_beyond_them() -> None:
    near = [plane(f"a{n:05x}", 60.2231 + n * 0.0002, 24.7152) for n in range(400)]           # (within 10 km)
    far_in_circle = plane("e00001", 61.2, 24.7152, squawk="7700")                                # (109 km: in the circle, beyond the 300 nearest)
    outside = [plane("b00001", 61.7, 24.7152), plane("e00002", 61.8, 24.7152, emergency="general")]          # (165 and 176 km: the request asked for the circle and 8 km more)
    async with virtual_time():
        net = Net(lambda url: FeedAnswer(200, sky(*near, far_in_circle, *outside)))
        service = await layers(net, Settings(map_aircraft="adsbfi", map_radius_km=150))
        service.watch("aircraft", True)
        await asyncio.sleep(1)
        ids = [thing.id for thing in service.table("aircraft").things]
        assert len(ids) == 301 and ids[:300] == [f"a{n:05x}" for n in range(300)] and ids[300] == "e00001"


async def test_the_own_receiver_is_cut_by_nothing_but_the_guard_of_2000_newest() -> None:
    far = [plane("c00001", 30.0, -90.0), plane("c00002", -33.9, 151.2)]           # (thousands of km away: all shown)
    many = [plane(f"d{n:05x}", 60.0, 25.0, seen_pos=n / 100) for n in range(2500)]
    async with virtual_time():
        bodies = [sky(*far), sky(*many)]
        net = Net(lambda url: FeedAnswer(200, bodies.pop(0) if bodies else sky()))
        service = await layers(net, Settings(map_aircraft="receiver", map_radius_km=10))
        await asyncio.sleep(1)
        assert {thing.id for thing in service.table("aircraft").things} == {"c00001", "c00002"}
        service.watch("aircraft", True)
        await asyncio.sleep(5)
        kept = service.table("aircraft").things
        assert len(kept) == 2000 and {thing.id for thing in kept} == {f"d{n:05x}" for n in range(2000)}, "the newest positions"


async def test_an_aircraft_older_than_its_limit_is_dropped_60_s_from_the_receiver_and_90_s_from_a_service() -> None:
    async with virtual_time():
        net = Net(lambda url: FeedAnswer(200, sky(plane("aaaaaa", seen_pos=50), plane("bbbbbb", seen_pos=70), plane("cccccc", seen_pos=85), plane("dddddd", seen_pos=95))))
        settings = Settings(map_aircraft="receiver")
        service = await layers(net, settings)
        await asyncio.sleep(1)
        assert [t.id for t in service.table("aircraft").things] == ["aaaaaa"]
        settings.config = replace(settings.config, map_aircraft="adsbfi")
        service.config_changed(settings.config)
        service.watch("aircraft", True)
        await asyncio.sleep(1)
        assert [t.id for t in service.table("aircraft").things] == ["aaaaaa", "bbbbbb", "cccccc"]


async def test_the_pages_are_told_again_when_things_grow_too_old_and_a_failure_keeps_the_things_but_says_away() -> None:
    async with virtual_time():
        answers = [FeedAnswer(200, sky(plane("aaaaaa")))]
        net = Net(lambda url: answers.pop(0) if answers else None)
        service = await layers(net, Settings(map_aircraft="adsbfi"))
        told = tables(service)
        service.watch("aircraft", True)
        await asyncio.sleep(40)
        assert [len(t.things) for t in told] == [1, 1] and told[-1].away, "the second question failed: the aircraft stays, the table says away"
        await asyncio.sleep(90)
        assert told[-1].things == () and told[-1].away, "it aged out, and the pages were told"


# ---- the own receiver

async def test_the_own_receiver_is_asked_at_the_start_and_at_a_save_that_chooses_it_or_changes_its_address_and_nobody_looks() -> None:
    async with virtual_time():
        net = Net()
        settings = Settings(map_aircraft="receiver")
        service = await layers(net, settings)
        await asyncio.sleep(60)
        assert net.asked == [RECEIVER_FIRST], "once at the start, for its state in Settings"
        assert service.states()[0].receiver is not None and service.states()[0].receiver.state == "receiving"
        settings.config = replace(settings.config, map_radius_km=100)
        service.config_changed(settings.config)
        await asyncio.sleep(1)
        assert len(net.asked) == 1, "a save that changes nothing of it asks nothing"
        settings.config = replace(settings.config, map_aircraft_host="pi.local:8080")
        service.config_changed(settings.config)
        await asyncio.sleep(1)
        assert net.asked[1:] == ["http://pi.local:8080/tar1090/data/aircraft.json"]
        settings.config = replace(settings.config, map_aircraft="none")
        service.config_changed(settings.config)
        settings.config = replace(settings.config, map_aircraft="receiver")
        service.config_changed(settings.config)
        await asyncio.sleep(60)
        assert len(net.asked) == 3 and service.states()[0].receiver is not None


async def test_a_service_is_not_asked_at_the_start_or_at_a_save() -> None:
    async with virtual_time():
        net = Net()
        settings = Settings(map_aircraft="adsbfi")
        service = await layers(net, settings)
        settings.config = replace(settings.config, map_aircraft="adsblol")
        service.config_changed(settings.config)
        await asyncio.sleep(60)
        assert net.asked == [] and service.states()[0].receiver is None


async def test_the_receiver_is_looked_for_in_its_places_the_one_that_answers_is_kept_and_the_search_begins_again_after_a_failure() -> None:
    async with virtual_time():
        up = {"on": True}
        net = Net(lambda url: FeedAnswer(200, sky(plane("aaaaaa"))) if url.endswith(":8080/data/aircraft.json") and up["on"] else FeedAnswer(404, b"") if up["on"] else None)
        service = await layers(net, Settings(map_aircraft="receiver", map_aircraft_host="pi.local"))
        await asyncio.sleep(1)
        assert net.asked == [*(f"http://pi.local{p}" for p in ("/tar1090/data/aircraft.json", "/data/aircraft.json", "/skyaware/data/aircraft.json", "/dump1090/data/aircraft.json")),
                             "http://pi.local:8080/tar1090/data/aircraft.json", "http://pi.local:8080/data/aircraft.json"]
        service.watch("aircraft", True)
        await asyncio.sleep(5)
        assert net.asked[6:] == ["http://pi.local:8080/data/aircraft.json"], "the place that answered is asked from then on"
        up["on"] = False
        await asyncio.sleep(5)
        await asyncio.sleep(10)
        assert net.asked[7] == "http://pi.local:8080/data/aircraft.json" and net.asked[8] == "http://pi.local/tar1090/data/aircraft.json", "after the failure the search begins again"


async def test_the_receivers_state_is_looking_then_receiving_then_no_answer_with_one_line_in_the_log_each(caplog: pytest.LogCaptureFixture) -> None:
    async with virtual_time():
        up = {"on": True}
        net = Net(lambda url: FeedAnswer(200, sky(plane("aaaaaa"), plane("bbbbbb"))) if up["on"] else None)
        service = Layers(Settings(map_aircraft="receiver", map_aircraft_host="pi.local:8080"), lambda: HOME, "0.21.0", "linux", fetch=net, clock=clock, environ={})
        remember_stop(service.stop)
        changed: list[int] = []
        service.changed.connect(lambda: changed.append(1))
        service.config_changed(service._config())
        assert service.states()[0].receiver is not None and service.states()[0].receiver.state == "looking"
        with caplog.at_level(logging.INFO, "neoaprs.layers"):
            await service.start()
            await asyncio.sleep(1)
            state = service.states()[0].receiver
            assert state is not None and (state.state, state.things) == ("receiving", 2) and state.heard_at is not None
            service.watch("aircraft", True)
            await asyncio.sleep(12)
            up["on"] = False
            await asyncio.sleep(30)
        state = service.states()[0].receiver
        assert state is not None and (state.state, state.things) == ("no_answer", 2)
        lines = [r.getMessage() for r in caplog.records if r.name == "neoaprs.layers"]
        assert lines == ["the aircraft receiver at pi.local: receiving", "the aircraft receiver at pi.local: no answer"]
        assert changed, "the topic `map` is told"


async def test_the_receivers_address_is_never_in_the_log_as_typed(caplog: pytest.LogCaptureFixture) -> None:
    async with virtual_time():
        await layers(Net(lambda url: None), Settings(map_aircraft="receiver", map_aircraft_host="https://pi.local:8443/secret/aircraft.json?token=abc"))
        with caplog.at_level(logging.DEBUG):
            await asyncio.sleep(1)
        assert "secret" not in caplog.text and "token" not in caplog.text and "pi.local" in caplog.text


# ---- the doors

async def test_with_the_update_check_off_no_service_is_asked_and_its_table_says_away_but_the_own_receiver_is() -> None:
    async with virtual_time():
        net = Net()
        settings = Settings(map_aircraft="adsbfi")
        service = await layers(net, settings, environ={"NEOAPRS_UPDATE_CHECK": "0"})
        service.watch("aircraft", True)
        await asyncio.sleep(600)
        assert net.asked == [] and service.table("aircraft").away
        settings.config = replace(settings.config, map_aircraft="receiver")
        service.config_changed(settings.config)
        await asyncio.sleep(1)
        assert net.asked and net.asked[0] == RECEIVER_FIRST


@pytest.mark.parametrize(("given", "asked"), [("http://127.0.0.1:7391", "http://127.0.0.1:7391/api/v3/lat/60.2/lon/24.7/dist/86"), ("http://localhost:7391/other", "http://localhost:7391/api/v3/lat/60.2/lon/24.7/dist/86"),
                                              ("http://example.org:7391", None), ("http://user@127.0.0.1:7391", None), ("ftp://127.0.0.1", None)])
async def test_neoaprs_layers_url_takes_the_place_of_the_services_only_when_it_is_a_server_on_this_computer_even_with_the_update_check_off(given: str, asked: str | None) -> None:
    async with virtual_time():
        net = Net()
        service = await layers(net, Settings(map_aircraft="adsbfi"), environ={"NEOAPRS_UPDATE_CHECK": "0", "NEOAPRS_LAYERS_URL": given})
        service.watch("aircraft", True)
        await asyncio.sleep(1)
        assert net.asked == ([asked] if asked else [])


async def test_without_a_position_a_service_is_not_asked_and_it_is_once_there_is_one() -> None:
    async with virtual_time():
        net = Net()
        where: dict[str, tuple[float, float] | None] = {"at": None}
        service = await layers(net, Settings(map_aircraft="adsbfi"), where=lambda: where["at"])
        service.watch("aircraft", True)
        await asyncio.sleep(60)
        assert net.asked == [] and service.table("aircraft").away
        where["at"] = HOME
        service.moved()
        await asyncio.sleep(1)
        assert net.asked == [SERVICE]


# ---- the source in force

async def test_a_change_of_source_tells_the_pages_the_new_source_with_no_things() -> None:
    async with virtual_time():
        net = Net()
        settings = Settings(map_aircraft="adsbfi")
        service = await layers(net, settings)
        told = tables(service)
        service.watch("aircraft", True)
        await asyncio.sleep(1)
        settings.config = replace(settings.config, map_aircraft="none")
        service.config_changed(settings.config)
        assert told[-1] == LayerTable("aircraft", "none", False, ())
        await asyncio.sleep(600)
        assert len(net.asked) == 1
        settings.config = replace(settings.config, map_aircraft="adsblol")
        service.config_changed(settings.config)
        assert (told[-1].source, told[-1].things) == ("adsblol", ())
        await asyncio.sleep(1)
        assert net.asked[-1].startswith("https://api.adsb.lol/"), "the look stands, and is served once a source is chosen"


async def test_the_states_say_the_source_in_force_and_what_is_offered_and_a_stored_source_not_offered_counts_as_none() -> None:
    async with virtual_time():
        settings = Settings(map_ships="fintraffic", map_radius_km=150)
        where: dict[str, tuple[float, float] | None] = {"at": (60.17, 24.94)}
        service = await layers(Net(), settings, where=lambda: where["at"])
        aircraft, ships = service.states()
        assert (aircraft.layer, aircraft.source, aircraft.offered, aircraft.receiver) == ("aircraft", "none", ("none", "adsbfi", "adsblol", "receiver"), None)
        assert (ships.layer, ships.source, ships.offered) == ("ships", "fintraffic", ("none", "fintraffic", "receiver"))
        changed: list[int] = []
        service.changed.connect(lambda: changed.append(1))
        where["at"] = (50.11, 8.68)
        service.moved()
        assert service.states()[1].source == "none" and service.states()[1].offered == ("none", "receiver") and changed == [1]
        assert service._config().map_ships == "fintraffic", "it stays stored"


# ---- what a fake server sees (the real question, on the loopback)

@pytest.mark.parametrize(("where", "path"), [(HOME, "/api/v3/lat/60.2/lon/24.7/dist/86"), ((60.25789, 24.81234), "/api/v3/lat/60.3/lon/24.8/dist/86"), ((-0.04, -0.04), "/api/v3/lat/0.0/lon/0.0/dist/86")])
async def test_the_question_a_service_sees_carries_the_position_to_one_decimal_and_the_circle_and_nothing_of_the_station(where: tuple[float, float], path: str) -> None:
    internet = await layers_server()
    internet.answer = lambda asked: Answer(body=sky(plane("aaaaaa", *where)), packed=True)
    service = Layers(Settings(map_aircraft="adsbfi", map_radius_km=150, station_call="OH2GBA-7"), lambda: where, "0.21.0", "linux", environ={"NEOAPRS_UPDATE_CHECK": "0", "NEOAPRS_LAYERS_URL": internet.url})
    remember_stop(service.stop)
    await service.start()
    service.watch("aircraft", True)
    await until(lambda: service.table("aircraft").things)
    ((seen, headers),) = internet.requests
    assert seen == path, "for a home station and a moving one alike"
    assert "OH2GBA" not in seen + json.dumps(headers) and set(headers) == {"accept-encoding", "user-agent", "host", "connection"} and headers["user-agent"] == "NeoAPRS/0.21.0 (linux)"


async def test_with_the_own_receiver_set_the_internet_is_never_asked() -> None:
    internet, receiver = await layers_server(), await layers_server()
    receiver.route("/tar1090/data/aircraft.json", body=sky(plane("aaaaaa")))
    service = Layers(Settings(map_aircraft="receiver", map_aircraft_host=receiver.address), lambda: HOME, "0.21.0", "linux", environ={"NEOAPRS_UPDATE_CHECK": "1", "NEOAPRS_LAYERS_URL": internet.url})
    remember_stop(service.stop)
    await service.start()
    service.watch("aircraft", True)
    await until(lambda: len(receiver.requests) >= 2, 15.0)
    assert internet.requests == [] and [t.id for t in service.table("aircraft").things] == ["aaaaaa"]


async def test_after_the_stop_a_save_starts_and_stops_nothing() -> None:
    async with virtual_time():
        settings = Settings(map_aircraft="receiver")
        service = await layers(Net(), settings)
        await asyncio.sleep(1)
        await service.stop()
        settings.config = replace(settings.config, map_aircraft="adsbfi")
        service.config_changed(settings.config)
        service.watch("aircraft", True)
        assert len(service._tasks) == 0, "no task that nobody awaits"


async def test_the_loop_answers_within_50_ms_while_a_receiver_answers_some_16_megabytes() -> None:
    receiver = await layers_server()
    many = [plane(f"{n:06x}", lat=60 + (n % 1000) / 1000, lon=24 + (n // 1000) / 100, flight="FIN123  ", r="OH-ABC", t="A320", squawk="1234", category="A3") for n in range(75000)]
    body = sky(*many)
    assert 12_000_000 < len(body) <= MAX_UNPACKED
    receiver.route("/tar1090/data/aircraft.json", body=gzip.compress(body), headers={"Content-Encoding": "gzip"})       # (packed here, not by the fake server on the loop)
    service = Layers(Settings(map_aircraft="receiver", map_aircraft_host=receiver.address), lambda: HOME, "0.21.0", "linux", environ={})
    remember_stop(service.stop)
    worst = 0.0

    async def ping() -> None:
        nonlocal worst
        while True:
            sent = time.perf_counter()
            await asyncio.sleep(0.005)
            worst = max(worst, time.perf_counter() - sent - 0.005)
    pinging = asyncio.create_task(ping())
    try:
        await service.start()
        await until(lambda: (state := service.states()[0].receiver) is not None and state.state == "receiving", 30.0)
    finally:
        pinging.cancel()
    state = service.states()[0].receiver
    assert state is not None and state.things == 75000
    assert worst < 0.05, f"the loop was held {worst * 1000:.0f} ms"
