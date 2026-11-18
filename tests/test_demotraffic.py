"""The made-up traffic of the demo daemon (scripts/demotraffic.py, scripts/demo-daemon --traffic): sixteen aircraft round Espoo that move each second and that the daemon's readers take in all three forms (one on the
ground left out, one in an emergency, one without a track, one with a registration only); the server answers the receiver's file, the Radarcape's list and the services' paths and nothing else; a port in use is a refusal that says so;
and demo-daemon starts it, points the daemon's services at it and stops it with the daemon."""
import json
import socket
import threading
import urllib.error
import urllib.request
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from neoaprs.geo import distance_km
from neoaprs import radarcape
from neoaprs.airports import place
from neoaprs.clock import from_unix
from neoaprs.readsb import read_aircraft
from tests.test_scripts import load_script

traffic = load_script("demotraffic.py")
T = 1794812336.0
ESPOO = (60.2231, 24.7152)


def test_sixteen_aircraft_round_espoo_of_which_the_reader_shows_fifteen_with_an_emergency_a_diamond_and_a_registration_alone() -> None:
    assert len(traffic.aircraft(T)) == 16
    shown = read_aircraft(json.dumps(traffic.receiver_file(T)).encode()) or []
    assert len(shown) == 15 and "4601a9" not in {a.id for a in shown}, "the one on the ground is not shown"
    assert [a.id for a in shown if a.emergency] == ["461e1a"]
    assert [a.id for a in shown if a.heading_deg is None] == ["4608a3"]
    assert [(a.name, a.registration) for a in shown if a.id == "460f11"] == [("", "OH-CEX")]
    assert all(distance_km(*ESPOO, a.lat, a.lon) < 120 for a in shown) and all(a.speed_kmh for a in shown)


def test_they_move_each_second_and_the_service_answer_has_the_same_aircraft_in_the_services_form() -> None:
    now, later = traffic.aircraft(T), traffic.aircraft(T + 1)
    assert all((a["lat"], a["lon"]) != (b["lat"], b["lon"]) for a, b in zip(now, later, strict=True) if a["alt_baro"] != "ground")
    answer = traffic.service_answer(T)
    assert set(answer) == {"ac", "msg", "now", "total", "ctime", "ptime"} and answer["now"] == int(T * 1000)
    assert {a.id for a in read_aircraft(json.dumps(answer).encode()) or []} == {a.id for a in read_aircraft(json.dumps(traffic.receiver_file(T)).encode()) or []}


def test_every_aircraft_has_a_kind_and_every_kind_of_mark_is_there() -> None:
    shown = read_aircraft(json.dumps(traffic.receiver_file(T)).encode()) or []
    assert all(a.category and a.designator for a in shown)
    assert {"A1", "A2", "A3", "A5", "A7", "B1", "B2", "B6"} <= {a.category for a in shown}
    assert [a.designator for a in shown if a.category == "A7"] == ["EC35"] and "B748" in {a.designator for a in shown}


def test_the_radarcapes_list_has_the_same_aircraft_with_one_on_the_ground_one_in_emergency_one_without_a_flight_and_one_without_speed_and_track() -> None:
    listed = traffic.radarcape_list(T)
    assert isinstance(listed, list) and len(listed) == 16 and all(row["hex"] == row["hex"].upper() for row in listed)
    shown = radarcape.read_aircraft(json.dumps(listed).encode(), from_unix(T)) or []
    readsb_shown = read_aircraft(json.dumps(traffic.receiver_file(T)).encode()) or []
    assert {a.id for a in shown} == {a.id for a in readsb_shown} and "4601a9" not in {a.id for a in shown}, "the one on the ground is not shown"
    assert [a.id for a in shown if a.emergency] == ["461e1a"]
    assert [(a.speed_kmh, a.heading_deg) for a in shown if a.id == "4608a3"] == [(None, None)]
    assert {a.id for a in shown if not a.name} == {"460f11", "4690c2", "4690d3"}
    assert {(a.id, a.category, a.designator) for a in shown} == {(a.id, a.category, a.designator) for a in readsb_shown}


def test_the_radarcapes_list_gives_the_airports_of_some_aircraft_one_with_both_known_one_with_an_unknown_code_one_with_a_destination_only_and_most_with_neither() -> None:
    shown = {a.id: a for a in radarcape.read_aircraft(json.dumps(traffic.radarcape_list(T)).encode(), from_unix(T)) or []}
    assert [(place(shown[i].origin), place(shown[i].destination)) for i in ("461f2a", "4ab822", "3c4b2f")] == [("Stockholm", "Helsinki (Vantaa)"), ("", "Helsinki (Vantaa)"), ("", "London")]
    assert (shown["4ab822"].origin, shown["3c4b2f"].origin) == ("ESXX", "")
    assert sum(1 for a in shown.values() if a.origin or a.destination) == 3


def test_three_aircraft_tell_a_vertical_rate_in_both_forms_one_climbing_one_descending_one_level_and_the_rest_tell_none() -> None:
    from_readsb = {a.id: a.vertical_ms for a in read_aircraft(json.dumps(traffic.receiver_file(T)).encode()) or []}
    from_radarcape = {a.id: a.vertical_ms for a in radarcape.read_aircraft(json.dumps(traffic.radarcape_list(T)).encode(), from_unix(T)) or []}
    assert from_readsb == from_radarcape
    assert {i: v for i, v in from_readsb.items() if v is not None} == {"461f2a": 9.1, "4ab822": 0.0, "3c4b2f": -10.7}


@pytest.mark.parametrize(("path", "form"), [("/tar1090/data/aircraft.json", "aircraft"), ("/api/v3/lat/60.2/lon/24.7/dist/86", "ac"), ("/v2/lat/60.2/lon/24.7/dist/86", "ac"), ("/v2/lat/-0.5/lon/-120.0/dist/250", "ac"),
                                           ("/data/aircraft.json", None), ("/api/v3/lat/x/lon/24.7/dist/86", None), ("/", None)])
def test_each_path_answers_its_form_and_any_other_is_not_found(path: str, form: str | None) -> None:
    found = traffic.answer(path, T)
    assert (None if found is None else next(key for key in ("aircraft", "ac") if key in found)) == form


def test_the_server_answers_over_http_on_this_computer() -> None:
    server = traffic.serve(0)
    assert server is not None
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/tar1090/data/aircraft.json", timeout=5) as response:  # noqa: S310  (the test's own server)
            assert len(json.loads(response.read())["aircraft"]) == 16
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/aircraftlist.json?knownposonly=1", timeout=5) as response:  # noqa: S310
            assert len(json.loads(response.read())) == 16
        with pytest.raises(urllib.error.HTTPError) as gone:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/nothing", timeout=5)  # noqa: S310
        assert gone.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def test_a_port_in_use_is_a_refusal_that_says_so(capsys: pytest.CaptureFixture[str]) -> None:
    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        held.listen()
        port = held.getsockname()[1]
        assert traffic.main(["--port", str(port)]) == 2
    assert f"the port {port} of this computer is in use" in capsys.readouterr().err


class Started:
    def __init__(self, line: str) -> None:
        self.stdout = StringIO(line)
        self.ended: list[str] = []

    def terminate(self) -> None:
        self.ended.append("terminate")

    def wait(self) -> int:
        self.ended.append("wait")
        return 0


def test_demo_daemon_with_traffic_starts_it_points_the_daemons_services_at_it_and_stops_it_with_the_daemon(tmp_path: Path) -> None:
    demo = load_script("demo-daemon")
    ran: list[dict[str, str]] = []
    made: list[tuple[list[str], Started]] = []
    running: list[bool] = []

    def start(command: list[str], **options: Any) -> Started:
        made.append((command, Started("listening on 127.0.0.1:7391\n")))
        return made[-1][1]

    def run(command: list[str], cwd: Path, env: dict[str, str]) -> int:
        ran.append(env)
        running.append(bool(made) and made[-1][1].ended == [])
        return 0

    assert demo.main(["--data", str(tmp_path / "demo"), "--traffic"], run, start) == 0
    ((command, process),) = made
    assert Path(command[-1]).parts[-2:] == ("scripts", "demotraffic.py") and running == [True] and process.ended == ["terminate", "wait"], "the traffic runs while the daemon does, and ends with it"
    assert ran[0]["NEOAPRS_LAYERS_URL"] == "http://127.0.0.1:7391" and ran[0]["NEOAPRS_UPDATE_CHECK"] == "0" and ran[0]["NEOAPRS_NO_DEVICES"] == "1"
    assert demo.main(["--data", str(tmp_path / "demo")], run, start) == 0 and len(made) == 1 and "NEOAPRS_LAYERS_URL" not in ran[1], "without --traffic: nothing of it"


def test_demo_daemon_refuses_when_the_traffic_could_not_start_and_runs_no_daemon(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    demo = load_script("demo-daemon")
    ran: list[object] = []
    assert demo.main(["--data", str(tmp_path / "demo"), "--traffic"], lambda *a, **k: ran.append(a) or 0, lambda command, **options: Started("")) == 2
    assert ran == [] and "could not be started" in capsys.readouterr().err


# ---- the ships

ships = load_script("demoships.py")


def test_eight_made_up_ships_off_helsinki_in_fintraffics_two_forms_of_which_one_lies_at_anchor() -> None:
    from neoaprs.clock import from_unix
    from neoaprs.digitraffic import read_locations, read_vessels
    from neoaprs.shiptable import ShipTable
    found = read_locations(json.dumps(traffic.ships("/api/ais/v1/locations", T)).encode()) or []
    named = read_vessels(json.dumps(traffic.ships("/api/ais/v1/vessels", T)).encode()) or []
    assert len(found) == 8 and len(named) == 8
    assert all(distance_km(60.12, 24.97, p.lat, p.lon) < 60 for p in found), "off Helsinki"
    table = ShipTable(lambda: from_unix(T))
    for p in found:
        table.position(p)
    for n in named:
        table.static(n)
    things = {t.id: t for t in table.things(from_unix(T), 1800)}
    assert len(things) == 8 and things["230111000"].name == "FINLANDIA" and things["230111000"].ship_type == 60 and things["230111000"].destination == "TALLINN"
    assert [t.id for t in things.values() if t.heading_deg is None] == ["230666000", "230777000"], "the ones at anchor say no heading (the diamond)"


def test_the_ships_move_between_two_answers_and_the_paths_are_fintraffics_only() -> None:
    now, later = ships.locations(T)["features"], ships.locations(T + 60)["features"]
    moving = [a for a, b in zip(now, later, strict=True) if a["geometry"] != b["geometry"]]
    assert len(moving) == 6
    assert traffic.ships("/api/ais/v1/locations", T) is not None and traffic.ships("/api/ais/v1/vessels", T) is not None and traffic.ships("/api/ais/v1/other", T) is None


def test_the_receivers_lines_decode_to_six_ships_with_their_names_and_kinds_in_all_four_message_types() -> None:
    from neoaprs.aisdecode import AisDecoder, AisPosition, AisStatic
    from neoaprs.clock import from_unix
    decoder = AisDecoder()
    at = from_unix(T)
    lines = [line for n, ship in enumerate(ships.AT_SEA) for line in ships.static_lines(ship, n)] + [line for ship in ships.AT_SEA for line in ships.position_lines(ship, T)]
    found = [x for line in lines if (x := decoder.feed(line, at)) is not None]
    positions = {p.mmsi: p for p in found if isinstance(p, AisPosition)}
    statics = [s for s in found if isinstance(s, AisStatic)]
    assert len(positions) == 6 and all(distance_km(60.12, 24.97, p.lat, p.lon) < 60 for p in positions.values())
    assert {s.name for s in statics} - {""} == {"FINLANDIA", "AURA", "BOTNIA", "SEA LARK", "ULLA", "WAVE RIDER"}
    assert positions[230666000].heading_deg is None and positions[230666000].sog_kn == 0.0, "one at anchor"
    assert {s.ship_type for s in statics if s.ship_type} == {60, 70, 80, 37, 30, 36}


def test_the_made_up_receiver_sends_its_lines_over_tcp_and_a_port_in_use_is_a_refusal_that_says_so(capsys: pytest.CaptureFixture[str]) -> None:
    server = ships.serve(0)
    assert server is not None
    try:
        with socket.create_connection(("127.0.0.1", server.server_address[1]), timeout=5) as connection:
            got = b""
            while got.count(b"\n") < 20:
                got += connection.recv(4096)
        assert got.startswith(b"!AIVDM,") and b"\r\n" in got
        port = server.server_address[1]
        assert ships.serve(port) is None
        assert f"the port {port} of this computer is in use" in capsys.readouterr().err
    finally:
        server.shutdown()
        server.server_close()
