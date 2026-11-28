"""The sound server's devices as pactl lists them, the ALSA names a modem opens them by, and where a
modem's streams sit. The inputs are pactl's own JSON (tests/fixtures/pactl)."""

import json
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


def test_the_modem_is_given_our_alsa_names() -> None:
    nodes = nodes_of("virtual")
    assert (
        soundserver.alsa_setting("pulse:DEVICE=quad_in,CHANNEL=rear-right|pulse:DEVICE=Radio_remap", nodes, "pulse")
        == "neoaprs_pulse_ch3:DEVICE=quad_in,CHANNELS=4|neoaprs_pulse:DEVICE=Radio_remap"
    )
    assert (
        soundserver.alsa_setting("plughw:CARD=CODEC,DEV=0|pulse:DEVICE=Radio_remap", nodes, "pipewire")
        == "plughw:CARD=CODEC,DEV=0|neoaprs_pipewire:DEVICE=Radio_remap"
    )
    assert soundserver.alsa_setting("plughw:CARD=CODEC,DEV=0", nodes, "pulse") == "plughw:CARD=CODEC,DEV=0"


def test_every_alsa_name_given_is_defined_in_the_configuration() -> None:
    conf = soundserver.CONF.read_text(encoding="utf-8")
    for via in soundserver.PLUGINS:
        assert f"pcm.neoaprs_{via} {{" in conf
        for n in range(len(soundserver.ALSA_ORDER)):
            assert f"pcm.neoaprs_{via}_ch{n} {{" in conf and f"ttable.0.{n} 1" in conf


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
        "pulse:DEVICE=quad_in",
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


def test_no_stream_yet_is_no_fault() -> None:
    assert soundserver.misplaced("pulse:DEVICE=quad_in|pulse:DEVICE=Radio_remap", 999999, pactl_of("virtual")) == ""


# ---- the plug-ins


def test_the_plugin_folder_is_found_where_the_system_keeps_it(tmp_path: Path) -> None:
    debian, fedora, arch = (tmp_path / d for d in ("x86_64-linux-gnu", "lib64", "lib"))
    for folder in (debian, fedora, arch):
        folder.mkdir()
    (fedora / soundserver.PLUGINS["pipewire"]).write_bytes(b"")
    assert soundserver.plugin_dir({}, [debian, fedora, arch]) == fedora
    assert soundserver.plugin(fedora) == "pipewire"
    (arch / soundserver.PLUGINS["pulse"]).write_bytes(b"")
    assert soundserver.plugin_dir({}, [debian, arch]) == arch
    assert soundserver.plugin(arch) == "pulse"
    assert soundserver.plugin_dir({}, [debian]) is None
    assert soundserver.plugin_dir({"ALSA_PLUGIN_DIR": str(debian)}, [fedora]) == debian


def test_a_device_of_the_server_is_never_proposed_nor_chosen() -> None:
    # the server's default is the desktop's own sound; the operator picks such a device himself
    rows = soundserver.cards(nodes_of("virtual"), {})
    codec = SoundCard("plughw:CARD=CODEC,DEV=0", "USB AUDIO CODEC", True, True)
    assert mercury.propose_sound_card(rows) == ""
    assert mercury.propose_sound_card([*rows, codec]) == codec.id
    assert direwolf.own_card(rows) == "" and mercury.choose_sound_card(rows) == ""
