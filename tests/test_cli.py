"""The `neoaprs` command: which command a line is, that no command (or `run`) is the daemon with the flags of `python -m neoaprs`, the parser of each command, and the commands that run as processes (`map`,
`db`, `doctor`, `--version`) the way a user starts them: `python -m neoaprs ...`, as the unit and the scripts do. The workings of `service`, `replay` and `doctor` are in their own files."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from neoaprs import PROGRAM, VERSION, cli
from neoaprs.cli import capturecmd, dbcmd, servicecmd
from tests.conftest import ROOT
from tests.support.fakepmtiles import FakePmtiles, install_fake


def process(*args: str, home: Path, extra: dict[str, str] | None = None, path: str | None = None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in ("NEOAPRS_DATA_DIR", "NEOAPRS_DEBUG")}
    env.update({"HOME": str(home), "PYTHONPATH": str(ROOT), **(extra or {})})
    if path is not None:
        env["PATH"] = path
    return subprocess.run([sys.executable, "-m", "neoaprs", *args], cwd=home, env=env, capture_output=True, text=True, timeout=120)


@pytest.fixture
def daemon_calls(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """`run_daemon` is not run: what it is given is written down."""
    calls: list[list[str]] = []
    import neoaprs.daemon
    monkeypatch.setattr(neoaprs.daemon, "main", lambda argv=None, prog="neoaprs": calls.append(list(argv or [])) or 0)
    return calls


def test_no_command_and_run_are_the_daemon_with_its_flags(daemon_calls: list[list[str]]) -> None:
    assert cli.main([]) == 0 and cli.main(["--data", "x", "--port", "socket://127.0.0.1:8001", "--web-port", "0", "--debug"]) == 0
    assert cli.main(["run"]) == 0 and cli.main(["run", "--data", "y", "--debug"]) == 0
    assert daemon_calls == [[], ["--data", "x", "--port", "socket://127.0.0.1:8001", "--web-port", "0", "--debug"], [], ["--data", "y", "--debug"]]


def test_the_daemons_own_parser_is_what_decides_its_flags() -> None:
    import neoaprs.daemon as daemon
    args = daemon.build_parser().parse_args(["--data", "d", "--port", "COM3", "--web-port", "7400", "--debug"])
    assert (args.data, args.port, args.web_port, args.debug) == ("d", "COM3", 7400, True)
    with pytest.raises(SystemExit):
        daemon.build_parser().parse_args(["--web-port", "70000"])
    with pytest.raises(SystemExit):
        daemon.build_parser().parse_args(["--colour"])


def test_a_command_is_dispatched_with_the_rest_of_the_line(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, list[str]] = {}
    for name in cli.COMMANDS:
        monkeypatch.setitem(cli.HANDLERS, name, lambda argv, name=name: seen.setdefault(name, argv) and 0)
    for name in cli.COMMANDS:
        assert cli.main([name, "--flag", "x"]) == 0
    assert seen == {name: ["--flag", "x"] for name in cli.COMMANDS}
    assert set(cli.COMMANDS) == set(cli.HANDLERS) == {"run", "service", "map", "db", "replay", "gps-replay", "capture", "doctor", "support", "open", "stop", "app"}


def test_an_unknown_command_is_refused_and_help_lists_the_commands(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["servce", "install"]) == 2
    assert "servce: no such command" in capsys.readouterr().err
    assert cli.main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "--data" in out and "--web-port" in out and all(f"  {name} " in out for name in cli.COMMANDS)


def test_version_is_the_one_version_of_the_package(tmp_path: Path) -> None:
    done = process("--version", home=tmp_path)
    assert done.returncode == 0 and done.stdout.strip() == f"{PROGRAM} {VERSION}"
    import tomllib
    meta = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "version" not in meta["project"] and meta["project"]["dynamic"] == ["version"] and meta["tool"]["hatch"]["version"]["path"] == "neoaprs/__init__.py"
    assert meta["project"]["scripts"] == {"neoaprs": "neoaprs.cli:main"} and meta["project"]["gui-scripts"] == {"neoaprsw": "neoaprs.cli:gui_main", "neoaprs-app": "neoaprs.desktop.cmd:gui_main"}


def test_the_windowless_entry_replaces_the_streams_it_does_not_have(monkeypatch: pytest.MonkeyPatch, daemon_calls: list[list[str]]) -> None:
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(sys, "argv", ["neoaprsw", "run", "--data", "z"])
    assert cli.gui_main() == 0 and daemon_calls == [["--data", "z"]]
    assert sys.stdout is not None and sys.stderr is not None
    print("no console to print to")
    sys.stdout.close()
    sys.stderr.close()


# ---- the parsers ----

def test_the_service_parser_takes_an_action_and_its_options() -> None:
    parser = servicecmd.parser()
    args = parser.parse_args(["install", "--data", "d", "--linger", "--clone", "c"])
    assert (args.action, args.data, args.linger, args.clone) == ("install", "d", True, "c")
    assert parser.parse_args(["logs", "-n", "5"]).lines == 5 and parser.parse_args(["status"]).linger is False
    with pytest.raises(SystemExit):
        parser.parse_args(["restart"])
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_the_db_parser_has_the_commands_of_the_old_script() -> None:
    args = dbcmd.parse(["--data", "d", "set", "station/call", "OH2GBA"])
    assert (args.data, args.command, args.key, args.value) == ("d", "set", "station/call", "OH2GBA")
    assert dbcmd.parse(["packets", "-n", "7"]).n == 7 and dbcmd.parse(["get", "web/port"]).key == "web/port"
    assert {dbcmd.parse([c]).command for c in ("list", "stations", "packets")} == {"list", "stations", "packets"}
    with pytest.raises(SystemExit):
        dbcmd.parse(["drop"])


def test_the_capture_parser_and_its_refusal_to_overwrite(tmp_path: Path) -> None:
    args = capturecmd.parse(["out.bin", "--port", "COM3", "--baud", "1200", "--seconds", "5", "--force"])
    assert (args.out, args.port, args.baud, args.seconds, args.force) == ("out.bin", "COM3", 1200, 5.0, True)
    (tmp_path / "there.bin").write_bytes(b"x")
    assert capturecmd.main([str(tmp_path / "there.bin")]) == 2 and (tmp_path / "there.bin").read_bytes() == b"x"


def test_capture_records_a_tcp_tnc_into_a_file(tmp_path: Path) -> None:
    """`neoaprs capture --port socket://...` on a TCP TNC that plays the capture of the live radio: the file is the bytes, and the frames are counted."""
    from tests.test_replay import CAPTURE
    from neoaprs.cli.replaycmd import frames_of
    server = subprocess.Popen([sys.executable, "-m", "neoaprs", "replay", str(CAPTURE), "--interval", "0.05"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert server.stdout is not None
        address = server.stdout.readline().strip()
        out = tmp_path / "recorded.bin"
        done = process("capture", "--port", address, "--seconds", "3", str(out), home=tmp_path, extra={"PYTHONPATH": str(ROOT)})
        assert done.returncode == 0, done.stderr
        assert b"".join(frames_of(out.read_bytes())) == b"".join(frames_of(CAPTURE.read_bytes())) and "4 KISS frames" in done.stderr
    finally:
        server.terminate()
        server.communicate(timeout=10)


# ---- as processes ----

def test_map_is_the_map_command_line_under_the_main_command(tmp_path: Path) -> None:
    fake: FakePmtiles = install_fake(tmp_path / "tools")
    done = process("map", "--data", str(tmp_path / "data"), "--source", "https://build.example/20261020.pmtiles", "--lat", "60.17", "--lon", "24.94", "--radius", "40", "--maxzoom", "14", "--dry-run",
                   home=tmp_path, path=str(fake.path.parent))
    assert done.returncode == 0, done.stderr
    assert "493 MB for 40 km round us to zoom 14 (41233 tiles)" in done.stdout
    helped = process("map", "--help", home=tmp_path)
    assert helped.returncode == 0 and "usage: neoaprs map" in helped.stdout and "--dry-run" in helped.stdout


def test_db_through_the_main_command_sets_and_reads_a_setting(tmp_path: Path) -> None:
    data = str(tmp_path / "data")
    assert process("db", "--data", data, "set", "station/call", "oh2gba-9", home=tmp_path).stdout.strip() == "station/call = OH2GBA-9"
    assert process("db", "--data", data, "get", "station/call", home=tmp_path).stdout.strip() == "OH2GBA-9"
    done = process("db", "--data", data, "get", "web/colour", home=tmp_path)
    assert done.returncode == 2 and "no such setting" in done.stderr and done.stderr.startswith("neoaprs db:")


def test_doctor_through_the_main_command_prints_the_checklist(tmp_path: Path) -> None:
    done = process("doctor", "--data", str(tmp_path / "data"), home=tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.startswith(f"NeoAPRS {VERSION} on ") and "ok    Python 3." in done.stdout
    assert not (tmp_path / "data").exists(), "the doctor makes nothing"


def test_the_default_data_folder_is_the_same_for_every_command(tmp_path: Path) -> None:
    """With NEOAPRS_DATA_DIR set, the daemon's default, `db`, `doctor` and `service` look in the same place."""
    place = tmp_path / "place"
    for parser_default in (dbcmd.parse(["list"]).data, servicecmd.parser().parse_args(["status"]).data):
        assert parser_default == str(servicecmd.default_data_dir())
    done = process("doctor", home=tmp_path, extra={"NEOAPRS_DATA_DIR": str(place)})
    assert f"data folder {place}" in done.stdout

