"""A station's track asked for by itself (`station_track`): the answer is the station row's `track`,
oldest first; a call with no row is refused with `station.unknown`. Over the page socket of a real
daemon."""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from neoaprs.radiospec import FM_ID
from tests.support.wireworld import heard
from tests.test_radios_wire import refused, started


async def test_a_station_track_is_what_its_row_has_and_a_station_not_in_the_topic_is_refused(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    now = e.ctl.clock()
    for minutes, lat in ((20, "6010.00N"), (10, "6011.00N"), (0, "6012.00N")):
        e.ctl.stationbook.take(
            replace(heard(f"!{lat}/02456.00E>moving", "OH2XYZ-9", at=now - timedelta(minutes=minutes)), radio_id=FM_ID)
        )
    await page.until(lambda: len(page.topics["stations"].get("OH2XYZ-9", {}).get("track", [])) == 3)
    await page.send({"cmd": "station_track", "call": "OH2XYZ-9"})
    answer = await page.expect("station_track")
    assert answer == {
        "type": "station_track",
        "call": "OH2XYZ-9",
        "points": page.topics["stations"]["OH2XYZ-9"]["track"],
    }
    assert [round(lat, 3) for _, lat, _ in answer["points"]] == [60.167, 60.183, 60.2], "oldest first"
    for call in ("OH2NONE", "N0CALL-15"):
        error = await refused(page, {"cmd": "station_track", "call": call})
        assert (error["code"], error["params"]) == ("station.unknown", {"call": call})
    await e.stop()
