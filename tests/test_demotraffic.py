"""The made-up traffic of the demo daemon (scripts/demotraffic.py, scripts/demo-daemon --traffic): a dozen aircraft round Espoo that move each second and that the daemon's reader takes in both forms (one on the
ground left out, one in an emergency, one without a track, one with a registration only); the server answers the receiver's file and the services' paths and nothing else; a port in use is a refusal that says so;
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
from neoaprs.readsb import read_aircraft
from tests.test_scripts import load_script

traffic = load_script("demotraffic.py")
T = 1794812336.0
ESPOO = (60.2231, 24.7152)


def test_a_dozen_aircraft_round_espoo_of_which_the_reader_shows_eleven_with_an_emergency_a_diamond_and_a_registration_alone() -> None:
    assert len(traffic.aircraft(T)) == 12
    shown = read_aircraft(json.dumps(traffic.receiver_file(T)).encode()) or []
    assert len(shown) == 11 and "4601a9" not in {a.id for a in shown}, "the one on the ground is not shown"
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
            assert len(json.loads(response.read())["aircraft"]) == 12
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
    assert command[-1].endswith("scripts/demotraffic.py") and running == [True] and process.ended == ["terminate", "wait"], "the traffic runs while the daemon does, and ends with it"
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
