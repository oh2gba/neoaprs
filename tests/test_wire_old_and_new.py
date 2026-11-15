"""Until the removals (package W3, which deletes this file) every field of the wire of before is still there beside the new one that names a radio by its id, and says the same: the page of before keeps
working on the old fields while the page is moved to the new (breakdown 1.11: nothing of the old wire is removed in wave 4).

The words of before name radios 1 and 2 only: `fm` is radio 1, `hf` radio 2, "" none (or another radio). The rows of the world of tests/support/wireworld.py, and a daemon's topics over its socket."""
from pathlib import Path
from typing import Any

from neoaprs.web import views
from neoaprs.web.protocol import TOPIC_NAMES
from tests.support import wireworld
from tests.support.env import Env

WORD = {1: "fm", 2: "hf"}


def word(id: int | None) -> str:
    return "" if id is None else WORD.get(id, "")


def test_every_row_says_its_radio_in_the_word_of_before_and_by_its_id_alike() -> None:
    rows = wireworld.rows(views)
    assert {p["radio_id"] for p in rows["packets"].values()} >= {2, None} and {m["radio_id"] for m in rows["messages"].values()} >= {2, None}
    for packet in rows["packets"].values():
        assert packet["radio"] == word(packet["radio_id"]), packet
    for message in rows["messages"].values():
        assert message["radio"] == word(message["radio_id"]), message
        for attempt in message["attempts_detail"]:
            assert attempt["radio"] == word(attempt["radio_id"]), attempt
    for station in rows["stations"].values():
        fm, hf = station["heard"].get("1"), station["heard"].get("2")
        assert (station["heard_fm"], station["last_fm_at"]) == ((0, None) if fm is None else (fm["count"], fm["last_at"])), station["call"]
        assert (station["heard_hf"], station["last_hf_at"]) == ((0, None) if hf is None else (hf["count"], hf["last_at"])), station["call"]
    for obj in rows["own_objects"].values():
        assert obj["radio"] == {(1,): "fm", (2,): "hf", (1, 2): "both"}[tuple(obj["radios"])], obj


async def test_the_topics_of_before_say_of_radios_1_and_2_what_the_topic_radios_says(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True, settings={"hf/enabled": "true", "hf/profile": "dummy-hf"})
    page = None
    try:
        await e.start()
        page = await e.ws()
        await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
        await page.until(lambda: page.topics["radios"]["2"]["state"] == "connected" and page.topics["tnc"]["state"] == "connected")
        await page.quiet(0.4)
        radios, tnc, hf = page.topics["radios"], page.topics["tnc"], page.topics["hf"]
        for old, new in ((tnc, radios["1"]), (hf, radios["2"])):
            assert (old["state"], old["stats"], old["lines"], old["modem"], old["dummy"]) == (new["state"], new["stats"], new["lines"], new["modem"], new["dummy"])
            assert (old["rules"]["kind"], old["rules"]["paths"], old["rules"]["digipeat"], old["rules"]["smart_beacon"], old["rules"]["beacon_min_min"]) == \
                (new["kind"], new["allowed"]["paths"], new["allowed"]["digipeat"], new["allowed"]["smart_beacon"], new["limits"]["beacon_min_min"])
        config = page.topics["config"]
        flat = {"serial/port": "radio/1/port", "serial/baud": "radio/1/baud", "tcp/host": "radio/1/tcp_host", "tcp/port": "radio/1/tcp_port", "beacon/path": "radio/1/path", "digi/enabled": "radio/1/digipeat",
                "mercury/sound_card": "radio/2/sound_card", "mercury/keying": "radio/2/keying", "mercury/tx_gain_db": "radio/2/tx_gain_db"}
        assert {old: config["values"][old] for old in flat} == {old: config["radio_values"][new] for old, new in flat.items()}
        assert (config["values"]["fm/enabled"], config["values"]["hf/enabled"]) == ("true" if radios["1"]["enabled"] else "false", "true" if radios["2"]["enabled"] else "false")
        assert (config["values"]["tnc/profile"], config["values"]["hf/profile"]) == (radios["1"]["type"], radios["2"]["type"])
        await page.send({"cmd": "status"})
        status: dict[str, Any] = await page.expect("status")
        assert (status["beacon_last_sent"], status["beacon_next_due"]) == (radios["1"]["beacon"]["last_sent"], radios["1"]["beacon"]["next_due"])
        assert (status["hf_beacon_last_sent"], status["hf_beacon_next_due"]) == (radios["2"]["beacon"]["last_sent"], radios["2"]["beacon"]["next_due"])
    finally:
        if page is not None:
            await page.aclose()
        await e.stop()
