"""Properties of the readers of what pactl says of a sound server: its sinks and sources, the clients
and the streams of a process, and the ids of the settings that name a server's device.
Any listing, a real one damaged above all, gives nodes with a name the ALSA names can carry, never an
exception; a stream target is a number; an id reads back as it was written.
"""

import json

from hypothesis import given
from hypothesis import strategies as st

from neoaprs import soundserver
from neoaprs.soundserver import ALSA_ORDER, clients_of, parse_id, parse_nodes, server_id, stream_targets
from tests.support.files import fixture_text
from tests.support.mutation import mutated_json, mutated_text

SINKS = json.loads(fixture_text("pactl/virtual-sinks.json"))
SOURCES = json.loads(fixture_text("pactl/pipewire-sources.json"))
STREAMS = json.loads(fixture_text("pactl/virtual-sink-inputs.json"))
CLIENTS = json.loads(fixture_text("pactl/pipewire-clients.json"))
NAME = st.from_regex(r"[A-Za-z0-9_.:@+-]{1,40}", fullmatch=True)


@given(st.sampled_from(["sink", "source"]), st.one_of(mutated_json(SINKS), mutated_json(SOURCES)))
def test_any_listing_gives_nodes_of_names_alsa_can_carry(kind: soundserver.Kind, entries: object) -> None:
    for node in parse_nodes(kind, json.dumps(entries)):
        assert soundserver._NAME.match(node.name) and node.description and node.kind == kind
        assert node.card is None or node.card >= 0


@given(st.one_of(st.text(max_size=200), mutated_text(json.dumps(SINKS))))
def test_any_text_is_a_listing_or_none_of_it(text: str) -> None:
    assert isinstance(parse_nodes("sink", text), list)


@given(st.one_of(mutated_json(STREAMS), mutated_json(CLIENTS)), st.integers(0, 2**22))
def test_any_streams_and_clients_give_numbers_or_nothing(entries: object, pid: int) -> None:
    text = json.dumps(entries)
    clients = clients_of(text, pid)
    assert all(isinstance(client, str) for client in clients)
    targets = stream_targets(text, pid, "sink", clients)
    assert targets is None or all(isinstance(target, int) for target in targets)


@given(NAME, st.sampled_from(("",) + ALSA_ORDER))
def test_an_id_reads_back_as_it_was_written(name: str, channel: str) -> None:
    assert parse_id(server_id(name, channel)) == (name, channel)


@given(st.text(max_size=80))
def test_any_id_is_a_name_and_a_channel_or_none(ident: str) -> None:
    found = parse_id(ident)
    assert found is None or (soundserver._NAME.match(found[0]) and found[1] in ("",) + ALSA_ORDER)
