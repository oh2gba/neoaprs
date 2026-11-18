"""The map's Radius (`map/radius_km`) sets the detailed map's download, the circle asked of APRS-IS and the objects' QRU box, and nothing else: a station heard on a radio is in the station book, in the database and
told to the page wherever it is, on an FM radio and on an HF radio alike, thousands of km outside the circle."""
from pathlib import Path

from neoaprs.geo import distance_km
from tests.support.air import on_air
from tests.support.env import Env, until
from tests.support.fakemercury import Air

FAR_OBJECT = ("FARBOX", ";FARBOX   *092345z3351.00S/15112.00Er")  # an object in Sydney, heard on FM
HOME = (60.17, 24.94)
FAR_FM = ("VK2FAR", "!3351.00S/15112.00E>far on FM")       # Sydney, about 15000 km away
FAR_HF = ("W6FAR", "!3746.00N/12225.00W>far on HF")        # San Francisco, about 8800 km away


async def test_a_station_heard_on_an_fm_radio_and_one_on_an_hf_radio_far_outside_the_radius_are_kept_and_told_to_the_page(tmp_path: Path) -> None:
    air = Air(frame_sec=0.2)
    e = Env(tmp_path, hf=air.station(), web=True, settings={"map/radius_km": "10"})
    await e.start()
    assert e.ctl.config.map_radius_km == 10
    page = await e.ws()
    await until(lambda: page.revs.get("stations") is not None)
    e.feed(on_air(FAR_FM[0], FAR_FM[1].encode()))
    e.feed(on_air(FAR_FM[0], FAR_OBJECT[1].encode()))
    assert e.hf_radio is not None
    e.hf_radio.feed(on_air(FAR_HF[0], FAR_HF[1].encode()))
    await until(lambda: {"VK2FAR", "W6FAR", "FARBOX"} <= set(page.topics["stations"]))
    for call in (FAR_FM[0], FAR_HF[0], FAR_OBJECT[0]):
        row = page.topics["stations"][call]
        assert row["distance_km"] > 8000 and distance_km(*HOME, row["lat"], row["lon"]) > 8000
        assert e.ctl.stationbook.get(call) is not None
    assert {s.call for s in await e.stations()} >= {"VK2FAR", "W6FAR", "FARBOX"}
    assert {p.source for p in await e.packets()} >= {"VK2FAR", "W6FAR"}
