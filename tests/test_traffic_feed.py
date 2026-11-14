"""The feeds of the map's ships and aircraft (neoaprs/services/ais.py, neoaprs/services/adsb.py, neoaprs/services/trafficfeed.py) and their topics (`ships`, `aircraft`, `traffic`): off until the switch is
on, asked round our position, a ship named by the voyage data that is read whole first and then from the newest it had, an item that goes is told, a failure says why and keeps what was heard until it is old,
no position waits, the switch off forgets everything at once, and a page sees it all. What they read reaches no part that sends: not the radio, not APRS-IS, not the station book, not the packet log."""
import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from neoaprs.clock import utc
from neoaprs.config import Config
from neoaprs.services.adsb import AircraftFeed
from neoaprs.services.ais import VESSELS_EVERY_SEC, ShipFeed
from neoaprs.services.trafficfeed import Feed
from neoaprs.trafficfetch import FetchError
from neoaprs.web.protocol import TOPIC_NAMES
from tests.support.clock import FixedClock
from tests.support.env import Env, remember_stop, until
from tests.support.files import fixture_text

HOME = (60.17, 24.94)


class Server:
    """The open data as a fetch function: an answer for each address that begins with a key (a FetchError is a failure), and what it was asked."""

    def __init__(self, answers: Mapping[str, Any]) -> None:
        self.answers = dict(answers)
        self.asked: list[str] = []

    async def __call__(self, url: str, user: str, max_bytes: int) -> Any:
        self.asked.append(url)
        for start, answer in self.answers.items():
            if url.startswith(start):
                if isinstance(answer, FetchError):
                    raise answer
                return answer
        raise FetchError("HTTP 404")


def digitraffic() -> Server:
    return Server({"https://meri.digitraffic.fi/api/ais/v1/locations": json.loads(fixture_text("traffic/locations.json")),
                   "https://meri.digitraffic.fi/api/ais/v1/vessels": json.loads(fixture_text("traffic/vessels.json"))})


class Settings:
    def __init__(self, **values: Any) -> None:
        self.config = replace(Config(), **values)

    def __call__(self) -> Config:
        return self.config


def ships(server: Server, settings: Settings, centre: Any = lambda: HOME, clock: FixedClock | None = None) -> ShipFeed:
    feed = ShipFeed(settings, centre, "NeoAPRS/test", fetch=server, clock=clock or FixedClock(utc(2026, 11, 13, 19, 10)))
    remember_stop(feed.stop)
    return feed


async def test_the_ships_are_off_until_the_switch_is_on_and_go_at_once_when_it_is_turned_off() -> None:
    server, settings = digitraffic(), Settings()
    feed = ships(server, settings)
    told: list[str] = []
    feed.changed.connect(told.append)
    await feed.start()
    assert feed.state is Feed.State.OFF and server.asked == []
    settings.config = replace(settings.config, ais_enabled=True)
    feed.settings_changed()
    await until(lambda: feed.state is Feed.State.RECEIVING)
    assert sorted(feed.items) == ["230145760", "244854000", "636015526"] and sorted(told) == sorted(feed.items)
    assert feed.items["636015526"].voyage.name == "SAKURA PRINCESS"
    assert server.asked[0] == "https://meri.digitraffic.fi/api/ais/v1/vessels"
    assert server.asked[1] == "https://meri.digitraffic.fi/api/ais/v1/locations?latitude=60.1700&longitude=24.9400&radius=450"
    cleared: list[bool] = []
    feed.cleared.connect(lambda: cleared.append(True))
    settings.config = replace(settings.config, ais_enabled=False)
    feed.settings_changed()
    assert feed.items == {} and feed.state is Feed.State.OFF and cleared == [True] and feed.voyages == {}


async def test_the_voyage_data_is_asked_again_after_ten_minutes_from_the_newest_it_had() -> None:
    server, settings, clock = digitraffic(), Settings(ais_enabled=True), FixedClock(utc(2026, 11, 13, 19, 10))
    feed = ships(server, settings, clock=clock)
    await feed.read(HOME)
    await feed.read(HOME)
    assert [url.split("?")[0].rsplit("/", 1)[1] for url in server.asked] == ["vessels", "locations", "locations"]
    clock.advance(VESSELS_EVERY_SEC)
    await feed.read(HOME)
    assert server.asked[3] == "https://meri.digitraffic.fi/api/ais/v1/vessels?from=1794596826871"


async def test_a_failure_says_why_and_keeps_the_ships_until_they_are_old_and_a_ship_that_goes_is_told() -> None:
    server, settings, clock = digitraffic(), Settings(ais_enabled=True), FixedClock(utc(2026, 11, 13, 19, 10))
    feed = ships(server, settings, clock=clock)
    await feed._round()
    assert len(feed) == 3
    server.answers["https://meri.digitraffic.fi/api/ais/v1/locations"] = FetchError("HTTP 503")
    assert await feed._round() >= feed.every_sec
    assert (feed.state, feed.problem, len(feed)) == (Feed.State.FAILING, "HTTP 503", 3)
    told: list[str] = []
    feed.changed.connect(told.append)
    clock.advance(3600)
    await feed._round()
    assert feed.items == {} and sorted(told) == ["230145760", "244854000", "636015526"]


async def test_without_a_position_the_feed_waits_and_shows_nothing() -> None:
    server = digitraffic()
    feed = ships(server, Settings(ais_enabled=True), centre=lambda: None)
    await feed._round()
    assert feed.state is Feed.State.WAITING and feed.problem.startswith("no position") and server.asked == []


async def test_the_aircraft_are_asked_round_us_and_an_old_answer_shows_none() -> None:
    answer = json.loads(fixture_text("traffic/aircraft.json"))
    server = Server({"https://opendata.adsb.fi/api/v2/": answer})
    clock = FixedClock(utc(2026, 11, 13, 19, 10, 52))
    feed = AircraftFeed(Settings(adsb_enabled=True), lambda: (59.5, 18.0), "NeoAPRS/test", fetch=server, clock=clock)
    remember_stop(feed.stop)
    await feed._round()
    assert server.asked == ["https://opendata.adsb.fi/api/v2/lat/59.5000/lon/18.0000/dist/243"]
    assert sorted(feed.items) == ["4ac9ec", "4aca04"] and feed.state is Feed.State.RECEIVING
    clock.advance(120)
    answer["now"] = 0                                 # (an answer without its time is taken as of now, less how long ago each was heard)
    for one in answer["aircraft"]:
        one["seen_pos"] = 300.0
    await feed._round()
    assert feed.items == {}


async def test_a_page_is_told_the_ships_and_the_state_and_nothing_reaches_a_part_that_sends(tmp_path: Path) -> None:
    e = Env(tmp_path, FixedClock(utc(2026, 11, 13, 19, 10)), web=True, settings={"station/lat": "60.17", "station/lon": "24.94"})
    await e.start()
    await e.until_usable()
    server = digitraffic()
    e.ctl.ships._fetch = server
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    assert page.topics["ships"] == {} and page.topics["aircraft"] == {}
    assert page.topics["traffic"]["ais"] == {"enabled": False, "state": "off", "problem": "", "count": 0, "radius_km": 450.0, "updated_at": None}
    await page.send({"cmd": "set_config", "values": {"ais/enabled": "true"}})
    await page.until(lambda: len(page.topics["ships"]) == 3 and page.topics["traffic"]["ais"]["state"] == "receiving")
    assert page.topics["ships"]["230145760"]["name"] == "DUNKER" and page.topics["traffic"]["ais"]["count"] == 3
    assert e.ctl.stationbook.get("DUNKER") is None and all(s.call.isdigit() is False for s in e.ctl.stationbook.stations())
    assert await e.packets() == [] and e.ctl.igate.gated == 0
    await page.send({"cmd": "set_config", "values": {"ais/enabled": "false"}})
    await page.until(lambda: page.topics["ships"] == {} and page.topics["traffic"]["ais"]["state"] == "off")
    await e.stop()
