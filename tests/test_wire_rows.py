"""The rows of the topics as the daemon makes them (neoaprs/web/views.py): a world with a row of every kind (stations of every kind including our own, objects, items, weather and
telemetry stations; packets of every decoded kind; messages in every state with their attempts; bulletins; our objects and bulletins; station preferences; the TNC; the settings) is held
to a golden file, and every row is held to its model.

The golden file tests/fixtures/wire/rows.json is the JSON the page is told (keys sorted: the order of the keys of a row is the model's). A change of the wire is made on purpose: change the
model, then write the file again with `python -m tests.test_wire_rows`."""
import json
from typing import Any

import pytest
from pydantic import TypeAdapter

from neoaprs.web import views
from neoaprs.web.bulletinwire import BulletinRow
from neoaprs.web.gpswire import GpsState
from neoaprs.web.messagewire import MessageRow
from neoaprs.web.ownwire import OwnBulletinRow, OwnObjectRow
from neoaprs.web.packetwire import PacketRow
from neoaprs.web.prefwire import StationPref
from neoaprs.web.stationwire import StationRow, WeatherValues
from neoaprs.web.tncwire import TncState
from neoaprs.web.wirebase import _Model
from tests.support import wireworld
from tests.support.files import FIXTURES

GOLDEN = FIXTURES / "wire" / "rows.json"
MODELS = {
    "stations": StationRow, "packets": PacketRow, "messages": MessageRow, "bulletins": BulletinRow, "own_objects": OwnObjectRow, "own_bulletins": OwnBulletinRow, "station_prefs": StationPref, "tnc": TncState, "gps": GpsState,
}


PLATFORM_DEFAULTS = ("messages/alert_command",)          # (the default command is the system's own: PowerShell on Windows, a shell line elsewhere)


def as_json() -> Any:
    return without_platform(json.loads(json.dumps(wireworld.rows(views))))


def without_platform(rows: Any) -> Any:
    for config in rows.get("config", []):
        for part in ("values", "defaults"):
            for key in PLATFORM_DEFAULTS:
                config.get(part, {}).pop(key, None)
    return rows


def test_the_rows_are_the_rows_of_the_golden_file() -> None:
    made, golden = as_json(), without_platform(json.loads(GOLDEN.read_text(encoding="utf-8")))
    assert set(made) == set(golden)
    for topic in golden:
        assert made[topic] == golden[topic], topic


@pytest.mark.parametrize("topic", sorted(MODELS))
def test_every_row_of_the_world_is_a_row_of_its_model(topic: str) -> None:
    rows = as_json()[topic]
    adapter = TypeAdapter(MODELS[topic])
    for row in rows.values() if isinstance(rows, dict) else rows:
        adapter.validate_json(json.dumps(row))
        assert list(row) == list(MODELS[topic].model_fields), "a row has the fields of its model, in its order"


def test_the_world_has_a_row_of_every_kind() -> None:
    rows = as_json()
    stations = rows["stations"].values()
    assert {s["kind"] for s in stations} == {"station", "object", "item"} and any(s["own"] for s in stations) and any(s["is_me"] for s in stations)
    assert any(s["weather"] for s in stations) and any(s["telemetry"] for s in stations) and any(s["locator"] for s in stations) and any(s["extensions"] for s in stations)
    assert {p["decoded"]["type"] for p in rows["packets"].values()} >= {"position", "message", "object", "item", "status", "other", "undecoded"}
    assert {m["state"] for m in rows["messages"].values()} == {"acked", "failed", "sending", "received", "overheard"}
    assert {o["state"] for o in rows["own_objects"].values()} == {"live", "killing"}


def test_a_field_the_model_does_not_have_is_refused_and_a_field_the_object_does_not_have_fails() -> None:
    with pytest.raises(TypeError, match="no field nonsense"):
        WeatherValues.row(wireworld.book().get("N0WX-1").weather, nonsense=1)  # type: ignore[union-attr]

    class Short:
        wind_dir = 1
    with pytest.raises(AttributeError):
        WeatherValues.row(Short())


def test_the_helper_makes_times_text_and_tuples_lists() -> None:
    class Model(_Model):
        at: str
        path: list[str]

    class Thing:
        at = wireworld.T0
        path = ("A", "B*")
    assert Model.row(Thing()) == {"at": "2026-10-21T12:00:00Z", "path": ["A", "B*"]}


if __name__ == "__main__":
    GOLDEN.write_text(json.dumps(as_json(), sort_keys=True, indent=1) + "\n", encoding="utf-8")
