"""The sound server's devices as pactl lists them, the ALSA names a modem opens them by, and where a
modem's streams sit. The inputs are pactl's own JSON (tests/fixtures/pactl)."""

import json
import os
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from neoaprs import direwolf, mercury, soundserver
from neoaprs.mercury import SoundCard
from neoaprs.soundserver import Node
from tests.support.files import fixture_text

CARDS = {0: "CODEC", 2: "Generic"}


def pactl_of(*names: str) -> soundserver.Run:
    """A pactl that answers the listings from fixtures `<name>-sinks.json` and so on."""
    files = {
        ("list", "sinks"): "sinks",
        ("list", "sources"): "sources",
        ("list", "sink-inputs"): "sink-inputs",
        ("list", "source-outputs"): "source-outputs",
        ("list", "clients"): "clients",
    }

    def run(args: Sequence[str]) -> str | None:
        part = files[tuple(args)]
        for name in names:
            try:
                return fixture_text(f"pactl/{name}-{part}.json")
            except FileNotFoundError:
                continue
        return "[]"

    return run


def nodes_of(name: str) -> list[Node]:
    found = soundserver.list_nodes(pactl_of(name))
    assert found is not None
    return found


def test_the_devices_a_user_made_are_listed_and_the_monitors_are_not() -> None:
    names = [(n.kind, n.name, n.description) for n in nodes_of("virtual")]
    assert ("sink", "Radio_remap", "Radio") in names
    assert ("sink", "Radio_null", "Radio_null") in names
    assert ("source", "quad_in", "Rubix44") in names
    assert not [n for n in names if n[1].endswith(".monitor")]


def test_a_card_s_devices_carry_its_alsa_card_and_a_made_one_none() -> None:
    station = {n.name: n for n in nodes_of("station")}
    sink = station["alsa_output.usb-BurrBrown_from_Texas_Instruments_USB_AUDIO_CODEC-00.analog-stereo"]
    assert (sink.description, sink.card, sink.device) == ("FTDX101", 0, 0)
    assert len([n for n in station.values() if n.kind == "source"]) == 1  # two monitors left out
    assert all(n.card is None for n in nodes_of("virtual"))


def test_the_rows_show_the_description_and_name_no_technical_word() -> None:
    rows = soundserver.cards(nodes_of("station"), CARDS)
    assert [(r.name, r.playback, r.capture, r.alsa) for r in rows] == [
        ("FTDX101", True, False, "plughw:CARD=CODEC,DEV=0"),
        ("Soundcard", True, False, "plughw:CARD=Generic,DEV=0"),
        ("FTDX101", False, True, "plughw:CARD=CODEC,DEV=0"),
    ]
    assert (
        rows[0].id == "pulse:DEVICE=alsa_output.usb-BurrBrown_from_Texas_Instruments_USB_AUDIO_CODEC-00.analog-stereo"
    )


def test_a_source_of_four_channels_is_offered_whole_and_by_each_channel() -> None:
    rows = [r for r in soundserver.cards(nodes_of("virtual"), {}) if r.id.startswith("pulse:DEVICE=quad_in")]
    assert [(r.id, r.channel) for r in rows] == [
        ("pulse:DEVICE=quad_in", 0),
        ("pulse:DEVICE=quad_in,CHANNEL=front-left", 1),
        ("pulse:DEVICE=quad_in,CHANNEL=front-right", 2),
        ("pulse:DEVICE=quad_in,CHANNEL=rear-left", 3),
        ("pulse:DEVICE=quad_in,CHANNEL=rear-right", 4),
    ]


def test_a_pro_audio_source_is_offered_whole_only() -> None:
    # the plug-ins read AUX positions by order and lose the rest (measured): no channel of it alone
    rows = [r for r in soundserver.cards(nodes_of("virtual"), {}) if "pro_in" in r.id]
    assert [r.id for r in rows] == ["pulse:DEVICE=pro_in"]


def test_a_listing_that_is_no_json_or_a_name_that_needs_quotes_gives_no_row() -> None:
    assert soundserver.parse_nodes("sink", "Connection failure: Connection refused") == []
    entry = json.loads(fixture_text("pactl/virtual-sinks.json"))[0]
    assert soundserver.parse_nodes("sink", json.dumps([entry | {"name": "a b"}, entry | {"name": 'x"y'}])) == []


def test_a_null_description_falls_back_to_the_nick_then_the_name() -> None:
    entry = json.loads(fixture_text("pactl/virtual-sinks.json"))[0]
    (node,) = soundserver.parse_nodes("sink", json.dumps([entry | {"description": "(null)"}]))
    assert node.description == entry["properties"].get("node.nick", entry["name"])


def test_no_server_means_no_list() -> None:
    assert soundserver.list_nodes(lambda args: None) is None
    assert soundserver.server_cards({}, lambda args: None) == []


def test_the_devices_are_listed_only_where_the_alsa_plugin_of_the_server_is_there(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(soundserver.sys, "platform", "linux")
    monkeypatch.setattr(soundserver, "system_alsa", lambda: None)
    assert soundserver.server_cards({}, pactl_of("virtual")) == [], "the modem could not open them"
    monkeypatch.setattr(soundserver, "system_alsa", lambda: soundserver.SystemAlsa(tmp_path, tmp_path / "alsa.conf"))
    assert soundserver.server_cards({}, pactl_of("virtual"))


def test_pactl_missing_gives_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(soundserver.shutil, "which", lambda name: None)
    assert soundserver.pactl(["list", "sinks"]) is None


# ---- a start


def test_a_device_that_is_gone_stops_the_start() -> None:
    nodes = nodes_of("virtual")
    assert soundserver.missing("pulse:DEVICE=quad_in|pulse:DEVICE=Radio_remap", nodes) == ""
    assert "no sink" in soundserver.missing("pulse:DEVICE=quad_in|pulse:DEVICE=Radio_unplugged", nodes)
    assert "no source" in soundserver.missing("pulse:DEVICE=Radio_remap|pulse:DEVICE=Radio_remap", nodes)
    assert soundserver.missing("pulse:DEVICE=quad_in|pulse:DEVICE=Radio_remap", None) != ""


def test_a_half_left_empty_stops_the_start() -> None:
    # an empty half would be the system's default device: the loudspeakers
    assert soundserver.missing("pulse:DEVICE=quad_in|", nodes_of("virtual")) != ""


def test_a_channel_the_source_does_not_have_stops_the_start() -> None:
    nodes = nodes_of("virtual")
    assert soundserver.missing("pulse:DEVICE=quad_in,CHANNEL=rear-right|pulse:DEVICE=Radio_remap", nodes) == ""
    assert soundserver.missing("pulse:DEVICE=quad_in,CHANNEL=side-left|pulse:DEVICE=Radio_remap", nodes) != ""
    assert soundserver.missing("pulse:DEVICE=pro_in,CHANNEL=front-left|pulse:DEVICE=Radio_remap", nodes) != ""


def test_the_modem_is_given_our_alsa_names_by_the_devices_index() -> None:
    nodes = nodes_of("virtual")
    assert (
        soundserver.alsa_setting("pulse:DEVICE=quad_in,CHANNEL=rear-right|pulse:DEVICE=Radio_remap", nodes, "pulse")
        == "neoaprs_pa_ch3:82,4|neoaprs_pa:60"
    )
    assert (
        soundserver.alsa_setting("plughw:CARD=CODEC,DEV=0|pulse:DEVICE=Radio_remap", nodes, "pipewire")
        == "plughw:CARD=CODEC,DEV=0|neoaprs_pw:60"
    )
    assert soundserver.alsa_setting("plughw:CARD=CODEC,DEV=0", nodes, "pulse") == "plughw:CARD=CODEC,DEV=0"


def test_an_alsa_name_given_is_short_enough_for_direwolf() -> None:
    # Direwolf opens no more than the first 29 characters of a name (audio.c, audio_in_name[30]); a
    # cut name is one the server does not know, and that plays on the default device
    long = Node(
        "source", 999999, "alsa_input.usb-Roland_Rubix44-00.analog-surround-71", "Rubix", soundserver.ALSA_ORDER
    )
    for via in soundserver.PLUGINS:
        for channel in ("", *soundserver.ALSA_ORDER):
            assert len(soundserver.alsa_name(soundserver.server_id(long.name, channel), "source", [long], via)) <= 29


def test_every_alsa_name_given_is_defined_in_the_configuration_which_takes_in_the_systems_first() -> None:
    conf = soundserver.CONF.read_text(encoding="utf-8")
    assert [line for line in conf.splitlines() if line and not line.startswith("#")][
        0
    ] == f"<{soundserver.SYSTEM_CONF.as_posix()}>"
    for via in soundserver.PLUGINS.values():
        assert f"pcm.{via.prefix} {{" in conf
        for n in range(len(soundserver.ALSA_ORDER)):
            assert f"pcm.{via.prefix}_ch{n} {{" in conf and f"ttable.0.{n} 1" in conf


def test_the_card_behind_gives_the_levels_and_the_claims() -> None:
    nodes = nodes_of("station")
    sink, source = (
        f"pulse:DEVICE=alsa_{d}.usb-BurrBrown_from_Texas_Instruments_USB_AUDIO_CODEC-00.analog-stereo"
        for d in ("output", "input")
    )
    assert soundserver.behind(f"{source}|{sink}", nodes, CARDS) == "plughw:CARD=CODEC,DEV=0"
    assert soundserver.claims(f"{source}|{sink}", nodes, CARDS) == ["plughw:CARD=CODEC,DEV=0"]
    other = "pulse:DEVICE=alsa_output.pci-0000_0b_00.4.analog-stereo"
    assert soundserver.behind(f"{source}|{other}", nodes, CARDS) == ""
    virtual = nodes_of("virtual")
    assert soundserver.behind("pulse:DEVICE=quad_in|pulse:DEVICE=Radio_remap", virtual, {}) == ""
    assert soundserver.claims("pulse:DEVICE=quad_in,CHANNEL=front-left|pulse:DEVICE=Radio_remap", virtual, {}) == [
        "pulse:DEVICE=quad_in,CHANNEL=front-left",
        "pulse:DEVICE=Radio_remap",
    ]
    assert soundserver.claims("plughw:CARD=CODEC,DEV=0", [], {}) == ["plughw:CARD=CODEC,DEV=0"]


# ---- the streams of a running modem


def _pids() -> tuple[int, int]:
    """The players of the fixture: pacat on Radio_remap, parec on quad_in."""
    sinks = json.loads(fixture_text("pactl/virtual-sink-inputs.json"))
    sources = json.loads(fixture_text("pactl/virtual-source-outputs.json"))
    play = next(
        int(e["properties"]["application.process.id"]) for e in sinks if "application.process.id" in e["properties"]
    )
    rec = next(
        int(e["properties"]["application.process.id"]) for e in sources if "application.process.id" in e["properties"]
    )
    return play, rec


def test_streams_on_the_named_devices_are_in_place() -> None:
    play, rec = _pids()
    run = pactl_of("virtual")
    assert soundserver.misplaced("plughw:CARD=X,DEV=0|pulse:DEVICE=Radio_remap", play, run) == ""
    assert soundserver.misplaced("pulse:DEVICE=quad_in|plughw:CARD=X,DEV=0", rec, run) == ""


def test_a_stream_on_another_device_is_found() -> None:
    play, rec = _pids()
    run = pactl_of("virtual")
    assert "not on Radio_null" in soundserver.misplaced("plughw:CARD=X,DEV=0|pulse:DEVICE=Radio_null", play, run)
    assert "not on codec_in" in soundserver.misplaced("pulse:DEVICE=codec_in|plughw:CARD=X,DEV=0", rec, run)


def test_a_device_gone_while_running_is_found() -> None:
    play, _ = _pids()
    assert soundserver.misplaced("plughw:CARD=X,DEV=0|pulse:DEVICE=Radio_gone", play, pactl_of("virtual")) != ""


def test_a_stream_of_pipewires_own_alsa_plugin_is_found_by_its_client() -> None:
    # that plug-in's stream has no process id of its own: its client has (pipewire-clients.json)
    run = pactl_of("pipewire")
    play, rec = 46, 47  # the aplay and arecord of the fixture
    assert soundserver.misplaced("plughw:CARD=X,DEV=0|pulse:DEVICE=Radio_remap", play, run) == ""
    assert soundserver.misplaced("pulse:DEVICE=quad_in|plughw:CARD=X,DEV=0", rec, run) == ""
    assert "not on Radio_null" in soundserver.misplaced("plughw:CARD=X,DEV=0|pulse:DEVICE=Radio_null", play, run)


def test_no_stream_of_the_process_seen_or_no_answer_cannot_be_told_and_is_no_fault_yet() -> None:
    setting = "pulse:DEVICE=quad_in|pulse:DEVICE=Radio_remap"
    assert soundserver.misplaced(setting, 999999, pactl_of("virtual")) is None
    assert soundserver.misplaced(setting, 999999, lambda args: None) is None, "no server answers"
    play, _ = _pids()
    run = pactl_of("virtual")
    assert soundserver.misplaced(setting, play, lambda a: None if a[1] == "sink-inputs" else run(a)) is None


def test_a_server_device_the_listing_lacks_is_never_handed_to_a_modem_by_its_name() -> None:
    nodes = nodes_of("virtual")
    assert soundserver.alsa_name("pulse:DEVICE=Radio_gone", "sink", nodes, "pulse") == ""
    assert soundserver.alsa_setting("pulse:DEVICE=quad_in|pulse:DEVICE=Radio_gone", nodes, "pulse") == "neoaprs_pa:82|"
    assert soundserver.parse_id("pulse:DEVICE=quad_in\n") is None, "a stored name with a line end is no name"


# ---- the plug-ins


def test_the_plugin_folder_is_found_where_the_system_keeps_it(tmp_path: Path) -> None:
    debian, fedora, arch = (tmp_path / d for d in ("x86_64-linux-gnu", "lib64", "lib"))
    for folder in (debian, fedora, arch):
        folder.mkdir()
    (fedora / soundserver.PLUGINS["pipewire"].file).write_bytes(b"")
    assert soundserver.plugin_dir({}, [debian, fedora, arch]) == fedora
    assert soundserver.plugin(fedora) == "pipewire"
    (arch / soundserver.PLUGINS["pulse"].file).write_bytes(b"")
    assert soundserver.plugin_dir({}, [debian, arch]) == arch
    assert soundserver.plugin(arch) == "pulse"
    assert soundserver.plugin_dir({}, [debian]) is None
    assert soundserver.plugin_dir({"ALSA_PLUGIN_DIR": str(debian)}, [fedora]) == debian


def test_the_systems_alsa_library_is_the_one_beside_its_plugins(tmp_path: Path) -> None:
    plugins = tmp_path / "lib64" / "alsa-lib"
    plugins.mkdir(parents=True)
    (plugins / soundserver.PLUGINS["pulse"].file).write_bytes(b"")
    conf = tmp_path / "alsa.conf"
    assert soundserver.system_alsa(plugins, conf) is None, "no library, no configuration"
    (tmp_path / "lib64" / "libasound.so.2").write_bytes(b"")
    conf.write_text("")
    assert soundserver.system_alsa(plugins, conf) == soundserver.SystemAlsa(tmp_path / "lib64", conf)


def test_a_device_of_the_server_is_never_proposed_nor_chosen() -> None:
    # the server's default is the desktop's own sound; the operator picks such a device himself
    rows = soundserver.cards(nodes_of("virtual"), {})
    codec = SoundCard("plughw:CARD=CODEC,DEV=0", "USB AUDIO CODEC", True, True)
    assert mercury.propose_sound_card(rows) == ""
    assert mercury.propose_sound_card([*rows, codec]) == codec.id
    assert direwolf.own_card(rows) == "" and mercury.choose_sound_card(rows) == ""


def test_a_stream_not_yet_on_any_device_is_no_fault() -> None:
    # PipeWire 1.6 lists a stream as on sink 4294967295 (PA_INVALID_INDEX) until it is linked (openSUSE, measured)
    play, _ = _pids()
    entries = json.loads(fixture_text("pactl/virtual-sink-inputs.json"))
    for e in entries:
        e["sink"] = 4294967295
    text = json.dumps(entries)
    assert soundserver.stream_targets(text, play, "sink") == []


def test_no_test_reaches_this_computers_sound_server() -> None:
    """The suite points the clients of the sound server at a socket that is not there (tests/conftest.py):
    pactl answers nothing, in this process and in every process a test starts."""
    assert os.environ["PULSE_SERVER"].startswith("unix:/nonexistent/")
    assert soundserver.child_environment()["PULSE_SERVER"] == os.environ["PULSE_SERVER"]
    if shutil.which("pactl") is not None and sys.platform.startswith("linux"):
        assert soundserver.pactl(["list", "sinks"]) is None
