"""Two objects of ours at once, through the whole daemon and the page's socket: both are made, both stay on the map and in the table of our objects, both are sent, and both are found again after a restart and by a page that is loaded anew."""
from pathlib import Path

from neoaprs.web.protocol import TOPIC_NAMES
from tests.support.air import said
from tests.support.env import Env


def values(name: str, kind: str = "object", **changes: object) -> dict[str, object]:
    return {"cmd": "object_set", "name": name, "kind": kind, "lat": 60.17, "lon": 24.94, "symbol_table": "/", "symbol_code": ">", "comment": f"{name} here", "course_deg": None, "speed_kmh": None, "path": None, **changes}


async def page_of(e: Env):  # type: ignore[no-untyped-def]
    page = await e.ws()
    await page.expect("hello")
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    return page


def names(page: object, topic: str) -> set[str]:
    return set(page.topics[topic])                                              # type: ignore[attr-defined]


async def quick(e: Env) -> None:
    e.ctl.ownobjects.tick_sec = e.ctl.ownbulletins.tick_sec = 0.02
    e.ctl.sender.spacing_sec = 0.0
    await e.start()
    await e.until_usable()


async def test_two_objects_made_one_after_the_other_both_stay_both_are_sent_and_both_survive_a_restart_and_a_new_page(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await quick(e)
    page = await page_of(e)
    await page.send(values("ALPHA"))
    await page.until(lambda: "ALPHA" in names(page, "own_objects") and "ALPHA" in names(page, "stations"))
    await page.send(values("BRAVO", lon=25.0))
    await page.until(lambda: "BRAVO" in names(page, "own_objects") and "BRAVO" in names(page, "stations"))
    assert names(page, "own_objects") == {"ALPHA", "BRAVO"} and {"ALPHA", "BRAVO"} <= names(page, "stations")
    frames = await said(e, 2)
    assert sorted(f.info[:11] for f in frames) == [b";ALPHA    *", b";BRAVO    *"]
    await page.until(lambda: page.topics["own_objects"]["ALPHA"]["sent"] == 1 and page.topics["own_objects"]["BRAVO"]["sent"] == 1)
    assert names(page, "own_objects") == {"ALPHA", "BRAVO"}

    fresh = await page_of(e)                                                    # a page that is loaded anew
    assert names(fresh, "own_objects") == {"ALPHA", "BRAVO"} and {"ALPHA", "BRAVO"} <= names(fresh, "stations")

    await e.settled()
    clock = e.now
    await e.stop()
    again = Env(tmp_path, web=True, clock=clock)
    await quick(again)
    after = await page_of(again)
    assert names(after, "own_objects") == {"ALPHA", "BRAVO"} and {"ALPHA", "BRAVO"} <= names(after, "stations")
    assert [(o.name, o.sent) for o in again.ctl.ownobjects.records()] == [("ALPHA", 1), ("BRAVO", 1)]
    await again.stop()


async def test_changing_or_killing_one_of_two_leaves_the_other_and_an_object_and_an_item_of_different_names_live_together(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await quick(e)
    page = await page_of(e)
    await page.send(values("ALPHA"))
    await page.send(values("BRAVO", "item"))
    await page.until(lambda: names(page, "own_objects") == {"ALPHA", "BRAVO"})
    assert (page.topics["own_objects"]["ALPHA"]["kind"], page.topics["own_objects"]["BRAVO"]["kind"]) == ("object", "item")
    await said(e, 2)
    await page.send(values("ALPHA", comment="changed"))
    await page.until(lambda: page.topics["own_objects"]["ALPHA"]["comment"] == "changed")
    assert page.topics["own_objects"]["BRAVO"]["comment"] == "BRAVO here" and names(page, "own_objects") == {"ALPHA", "BRAVO"}
    await page.send({"cmd": "object_kill", "name": "ALPHA"})
    await page.until(lambda: page.topics["own_objects"]["ALPHA"]["state"] == "killing" and "ALPHA" not in names(page, "stations"))      # (its kill goes out over three minutes)
    assert page.topics["own_objects"]["BRAVO"]["state"] == "live" and "BRAVO" in names(page, "stations")
    assert [o.name for o in e.ctl.ownobjects.records() if o.alive] == ["BRAVO"]
    await e.stop()
