"""A receive-only radio (type `tnc-text`, neoaprs/radiotypes/tnctext.py) on the real controller:
alone, every sending service refuses with `transmit.off`; beside a Dummy packet radio everything goes
there; nothing is written on it.
"""

import asyncio
from dataclasses import replace
from datetime import timedelta

from hypothesis import given, strategies as st
import pytest

from neoaprs import ax25, kiss
from neoaprs.claims import Claims
from neoaprs.beaconrule import beacon_radios
from neoaprs.direwolf import PROFILE as DIREWOLF, PROFILE_300 as DIREWOLF_300
from neoaprs.config import LISTENS_ONLY, RECEIVE_ONLY, can_transmit
from neoaprs.emailrule import email_radio
from neoaprs.messagerule import message_radio
from neoaprs.packet import GATEABLE, Packet
from neoaprs.radiodriver import RunOverrides
from neoaprs.radiospec import RadioHeard, RadioSpec, in_force_choice, in_force_set, senders, transmits, unheard_radio
from neoaprs.radiotypes import BY_KEY, type_of
from neoaprs.source import Source
from neoaprs.serialprobe import named_ports
from neoaprs.serialholders import port_key
from neoaprs.tncdriver import PROFILES, line_settings
from neoaprs.tncsearch import claimed
from neoaprs.tncprofile import TNC_TEXT
from neoaprs.web.radioview import radio_row
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR, Env, idle_for, until, until_started
from tests.support.ptyline import feed as feed_pty, heard as heard_pty, posix_only

ME = "OH2GBA"
HEARD = "OH2ABC-7"
SETTINGS = {
    "station/call": ME,
    "station/lat": "60.17",
    "station/lon": "24.94",
    "tnc/profile": TNC_TEXT.key,
    "digi/enabled": "true",
    "messages/alert": "false",
    "station/status": "QRV 145.500",
    "status/source": "text",
    "status/interval_min": "60",
    "beacon/interval_min": "20",
}
TO_US = f"{HEARD}>APRS,WIDE1-1::{ME:<9}:Hello{{12\r".encode()  # a message to us, with its id: an ack is due
# A directed query: our position is due as its answer
ASKS_US = f"{HEARD}>APRS,WIDE1-1::{ME:<9}:?APRSP\r".encode()
FILL_IN = b"OH2DIG-9>APRS,WIDE1-1,WIDE2-1:!6010.00N/02456.00E>wants a fill-in\r"
POSITION = f"{HEARD}>APRS,WIDE1-1:!6011.00N/02457.00E>heard on the text radio\r".encode()


async def started(tmp_path: object, beside: bool) -> tuple[Env, int | None]:
    e = Env(tmp_path, web=True, settings=SETTINGS)  # type: ignore[arg-type]
    await e.start()
    other = None
    if beside:
        other = await e.ctl.add_radio("dummy")
        assert other is not None
        await until_started(lambda: e.ctl.radios.get(other).state is Source.State.CONNECTED)  # type: ignore[union-attr]
    e.feed(POSITION)
    await until(lambda: (s := e.ctl.stationbook.get(HEARD)) is not None and s.heard_on(1).count > 0)
    return e, other


async def ours(e: Env) -> list[Packet]:
    return [p for p in await e.packets() if p.direction == "out"]


async def refused(page: object, command: dict[str, object]) -> str:
    await page.send(command)  # type: ignore[attr-defined]
    answer = await page.expect("error")  # type: ignore[attr-defined]
    assert answer["cmd"] == command["cmd"], answer
    return str(answer["code"])


async def test_alone_every_sending_service_refuses_with_rx_only_and_not_one_byte_leaves_on_its_line(
    tmp_path: object,
) -> None:
    e, _ = await started(tmp_path, beside=False)
    page = await e.ws()
    assert (
        e.ctl.config.listens_only
        and e.ctl.config.unheard_radio is None
        and e.ctl.radios.senders() == []
        and e.ctl.radios.beaconing() == []
    )
    assert can_transmit(e.ctl.config) == LISTENS_ONLY != RECEIVE_ONLY, (
        "the log and the support bundle say why: the radios cannot send, not that the operator switched transmitting off"
    )
    assert await refused(page, {"cmd": "beacon_now"}) == "transmit.off"
    assert await refused(page, {"cmd": "status_now"}) == "transmit.off"
    assert await refused(page, {"cmd": "send_message", "to": HEARD, "text": "Hello"}) == "transmit.off"
    assert (
        await refused(page, {"cmd": "send_message", "to": "EMAIL-2", "text": "oh2gba@example.org hello"})
        == "transmit.off"
    )
    assert (
        await refused(page, {"cmd": "general_query", "kind": "aprs", "path": None, "rf_only": True}) == "transmit.off"
    )
    assert await refused(page, {"cmd": "qru_ask", "text": "INFO"}) == "transmit.off"
    assert await refused(page, {"cmd": "query", "call": HEARD, "kind": "position"}) == "transmit.off"
    assert (
        await refused(page, {"cmd": "find_radio"})
        == await refused(page, {"cmd": "find_radio", "radio": 1})
        == "radio.receive_only"
    ), "Find my radio writes to the ports it tries: not to this one"
    await page.send(
        {
            "cmd": "object_set",
            "name": "FIELDDAY",
            "kind": "object",
            "lat": 60.2,
            "lon": 24.9,
            "symbol_table": "/",
            "symbol_code": "[",
            "comment": "",
            "course_deg": None,
            "speed_kmh": None,
            "path": None,
            "qru_group": "",
            "on_request": False,
            "radios": [1],
        }
    )
    await page.send({"cmd": "bulletin_post", "kind": "bulletin", "text": "Field day on Saturday"})
    e.feed(TO_US + ASKS_US + FILL_IN)
    await until(lambda: e.ctl.radios.get(1).stats.packets >= 4)  # type: ignore[union-attr]
    # An hour and a half of the station's clock: the beacons, the status, the object and the
    # bulletin are due
    for _ in range(30):
        e.now.advance(180)  # type: ignore[attr-defined]
        await idle_for(0.02)
    assert await e.heard(1, 0.3) == b"" and e.ctl.radios.get(1).stats.bytes_out == 0, (
        "not one byte left on the receive-only line"
    )  # type: ignore[union-attr]
    assert await ours(e) == [], "nothing is reported as sent"
    assert any(r.direction == "in" and r.text == "Hello" for r in e.ctl.messaging.records()), (
        "what it hears is taken in"
    )
    heard = [p for p in await e.packets() if p.direction == "in"]
    assert heard and all(p.radio_id == 1 and p.via in GATEABLE for p in heard), (
        "heard on the receive-only radio, and gated as anything heard on the air"
    )
    await e.stop()


@pytest.mark.slow("runs a daemon with its radios and services through its loop")
async def test_beside_a_dummy_fm_radio_everything_goes_on_that_one_an_ack_too_and_a_query_heard_on_the_text_radio_alone_is_not_answered(
    tmp_path: object,
) -> None:
    e, fm = await started(tmp_path, beside=True)
    assert fm is not None
    # Our frames one after the other: the pause between them is not what this is about
    e.ctl.sender.spacing_sec = 0.0
    page = await e.ws()
    assert (
        not e.ctl.config.listens_only
        and e.ctl.config.unheard_radio == fm
        and [r.id for r in e.ctl.radios.senders()] == [fm]
        and [r.id for r in e.ctl.radios.beaconing()] == [fm]
    )
    assert e.ctl.radios.for_station(HEARD).id == fm, (
        "a station heard on the text radio alone gets its messages on the radio that sends"
    )  # type: ignore[union-attr]
    await page.send({"cmd": "beacon_now"})
    await page.send({"cmd": "send_message", "to": HEARD, "text": "Hello"})
    assert await refused(page, {"cmd": "qru_ask", "text": "INFO", "radio": 1}) == "radio.receive_only", (
        "the text radio named: refused, by its name"
    )
    assert await refused(page, {"cmd": "station_radio", "call": HEARD, "radio": 1}) == "radio.receive_only", (
        "the text radio is no radio for a station's messages"
    )
    assert e.ctl.radios.choice(HEARD) is None and e.ctl.radios.for_station(HEARD).id == fm, "nothing was chosen"  # type: ignore[union-attr]
    await page.send(
        {
            "cmd": "object_set",
            "name": "FIELDDAY",
            "kind": "object",
            "lat": 60.2,
            "lon": 24.9,
            "symbol_table": "/",
            "symbol_code": "[",
            "comment": "",
            "course_deg": None,
            "speed_kmh": None,
            "path": None,
            "qru_group": "",
            "on_request": False,
            "radios": [1, fm],
        }
    )
    e.feed(TO_US + FILL_IN)
    for _ in range(20):
        e.now.advance(2)  # type: ignore[attr-defined]
        # Its ticker looks once a second of real time
        e.ctl.ownobjects.tick()
        await idle_for(0.03)
    out = await ours(e)
    assert out and all(p.radio_id == fm for p in out), "everything of ours went on the radio that sends"
    infos = [p.info for p in out]
    assert any(i.startswith(f":{HEARD:<9}:ack12".encode()) for i in infos), (
        "the ack of a message heard on the text radio alone went on the radio the message rule gives"
    )
    assert (
        any(i.startswith(f":{HEARD:<9}:Hello{{".encode()) for i in infos)
        and any(i.startswith(b";FIELDDAY ") for i in infos)
        and any(i[:1] in b"!=/@" for i in infos)
    ), infos
    assert not any(str(ax25.decode(p.raw).source) == "OH2DIG-9" for p in out), (
        "the text radio's fill-in is no one's: it may not repeat, and the Dummy did not hear it"
    )
    e.feed(ASKS_US)
    await until(lambda: e.ctl.radios.get(1).stats.packets >= 4)  # type: ignore[union-attr]
    await idle_for(0.5)
    after = [p.info for p in await ours(e) if p not in out and not p.info.startswith(b">")]
    assert all(i.startswith(f":{HEARD:<9}:Hello{{".encode()) for i in after), (
        "a query heard on the text radio alone is not answered (a retry of our message, or the timed status, may go meanwhile)",
        after,
    )
    assert await e.heard(1, 0.3) == b"" and e.ctl.radios.get(1).stats.bytes_out == 0, (
        "not one byte left on the receive-only line"
    )  # type: ignore[union-attr]
    await e.stop()


GENERAL = ax25.Frame(ax25.Address("APRS"), ax25.Address("OH2QRY"), (ax25.Address("WIDE1", 1),), info=b"?APRS?")
ASKS_HEARD = ax25.Frame(
    ax25.Address("APRS"),
    ax25.Address("OH2ABC", 7),
    (ax25.Address("WIDE1", 1),),
    info=f":{ME:<9}:?APRSH OH2DIG-9".encode(),
)
ASKS_QRU = ax25.Frame(
    ax25.Address("APRS"), ax25.Address("OH2ABC", 7), (ax25.Address("WIDE1", 1),), info=f":{'QRU':<9}:INFO{{7".encode()
)
# A radio that numbers its query waits for our ack
ASKS_NUMBERED = ax25.Frame(
    ax25.Address("APRS"), ax25.Address("OH2ABC", 7), (ax25.Address("WIDE1", 1),), info=f":{ME:<9}:?APRSP{{21".encode()
)


@pytest.mark.slow("runs a daemon with its radios and services through its loop")
@pytest.mark.parametrize(
    "query", [GENERAL, ASKS_HEARD, ASKS_QRU, ASKS_NUMBERED], ids=["general", "heard", "qru", "numbered"]
)
@pytest.mark.parametrize("text_first", [True, False], ids=["text-first", "kiss-first"])
async def test_a_query_heard_on_the_text_radio_and_on_a_kiss_radio_beside_it_is_answered_on_the_kiss_radio(
    tmp_path: object, query: ax25.Frame, text_first: bool
) -> None:
    e = Env(
        tmp_path,
        web=True,
        settings=SETTINGS | {"beacon/interval_min": "0", "status/interval_min": "0", "digi/enabled": "false"},
    )  # type: ignore[arg-type]
    await e.start()
    beside = await e.new_radio()
    kiss_id = await e.ctl.add_radio("kiss")
    assert kiss_id is not None
    page = await e.ws()
    await page.send({"cmd": "set_config", "values": {f"radio/{kiss_id}/port": beside.url}})
    await until_started(
        lambda: (r := e.ctl.radios.get(kiss_id)) is not None and r.state is Source.State.CONNECTED and r.usable
    )
    await beside.connected()
    # OH2DIG-9 is in the packet log, for ?APRSH
    e.feed(FILL_IN)
    await until(lambda: e.tnc.stats.packets >= 1)
    # The general query's random wait, made short
    e.ctl.queries._delay = lambda: 0.1
    e.ctl.qru.first_wait_sec = 0.1
    e.ctl.ownobjects.set("PUB", "object", 60.17, 24.94, "/", "r", "Pub", qru_group="FOOD", on_request=True)
    as_text, as_kiss = query.tnc2().encode() + b"\r", kiss.encode(ax25.encode(query))
    # Two receivers on one channel hear every frame; which copy comes first is chance
    if text_first:
        e.feed(as_text)
        await until(lambda: e.tnc.stats.packets >= 2)
        beside.feed(as_kiss)
    else:
        beside.feed(as_kiss)
        await idle_for(0.2)
        e.feed(as_text)
    await until(lambda: e.tnc.stats.packets >= 2)
    await idle_for(1.5)
    answers = [p for p in await ours(e) if p.radio_id == kiss_id]
    assert answers, "the KISS radio heard the query too: it is answered there"
    acks = [p for p in await ours(e) if p.info.startswith(f":{'OH2ABC-7':<9}:ack".encode())]
    assert len(acks) == (1 if query is ASKS_NUMBERED else 0), (
        "one transmission heard on two radios is acked once",
        [p.info for p in acks],
    )
    assert await e.heard(1, 0.3) == b"" and e.tnc.stats.bytes_out == 0, "not one byte left on the receive-only line"
    await e.stop()


async def test_find_my_radio_tries_no_port_a_radio_that_only_listens_is_set_to(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    e, _ = await started(tmp_path, beside=False)
    text = await e.ctl.add_radio(TNC_TEXT.key)
    assert text is not None
    page = await e.ws()
    # A port the search pattern matches; nothing is behind it, so the radio never opens it
    port = str(e.ports / "probe_text")
    await page.send({"cmd": "set_config", "values": {f"radio/{text}/port": port}})
    await until(lambda: (spec := e.ctl.config.radio(text)) is not None and spec.value("port") == port)
    assert all(c.holder != text for c in e.ctl.radios.claims.all()), "the radio has not opened its port"
    assert e.ctl.radiofinder._unclaimed([port], 1) == [], (
        "a TNC that is written nothing gets no carriage return and no KISS entries, even while its port is not held"
    )
    await e.stop()


# ---- the rules

KEYS = sorted(BY_KEY)


@st.composite
def stations(draw: st.DrawFn) -> tuple[RadioSpec, ...]:
    count = draw(st.integers(0, 6))
    specs = []
    for id in range(1, count + 1):
        key = draw(st.sampled_from(KEYS))
        specs.append(
            RadioSpec(
                id,
                type_of(key).kind,
                key,
                "",
                draw(st.booleans()),
                draw(st.integers(1, 6)),
                FixedClock()() if draw(st.booleans()) and draw(st.booleans()) else None,
            )
        )
    return tuple(specs)


@given(
    stations(),
    st.one_of(st.none(), st.integers(1, 6)),
    st.lists(st.integers(1, 6), max_size=6),
    st.dictionaries(st.integers(1, 6), st.integers(0, 600), max_size=6),
)
def test_every_radio_a_rule_picks_can_send(
    specs: tuple[RadioSpec, ...], choice: int | None, ticks: list[int], heard_minutes: dict[int, int]
) -> None:
    now = FixedClock()()
    can = {s.id for s in senders(specs)}
    assert all(transmits(s) and s.enabled and not s.removed for s in senders(specs))
    heard = {id: RadioHeard(1, now - timedelta(minutes=m)) for id, m in heard_minutes.items()}
    picked = [
        in_force_choice(choice, specs),
        message_radio(choice, heard, specs, now),
        unheard_radio(specs),
        email_radio(specs, choice),
        email_radio(specs, None),
        *beacon_radios(specs),
        *in_force_set(ticks, specs),
    ]
    assert all(id is None or id in can for id in picked), (specs, picked)
    assert (email_radio(specs, choice) is None) == (unheard_radio(specs) is None) == (not can), (
        "a radio for email and for a call no radio heard while some radio can send, and only then"
    )


def test_a_type_whose_profile_reads_text_or_writes_nothing_cannot_send_and_every_other_can() -> None:
    # The Sound card type's line is told Direwolf's profile by its own driver
    profiles = {**PROFILES, DIREWOLF.key: DIREWOLF, DIREWOLF_300.key: DIREWOLF_300}
    for t in BY_KEY.values():
        assert (
            profiles[t.profile].writes_nothing
            == (profiles[t.profile].framing == "text" or profiles[t.profile].receive_only)
            == (not t.can.transmit)
        ), t.key
    assert [t.key for t in BY_KEY.values() if not t.can.transmit] == [TNC_TEXT.key, "lora-console"]


def test_the_row_of_a_radio_that_only_receives_has_no_path_and_no_digipeat_choice_its_type_has_no_such_field() -> None:
    for key in (TNC_TEXT.key, "lora-console"):
        spec = RadioSpec(3, type_of(key).kind, key, "", True, 3, settings={"port": "/dev/ttyUSB7"})
        row = radio_row(spec, (spec,), None, Claims())
        assert row is not None and row["choices"] == {
            "beacon": True,
            "status": False,
            "ask": False,
            "local_info": False,
            "path": None,
            "digipeat": None,
        }, (key, row and row["choices"])
    tnc = RadioSpec(5, "fm", "kiss", "", True, 5)
    row = radio_row(tnc, (tnc,), None, Claims())
    assert row is not None and row["choices"] == {
        "beacon": True,
        "status": False,
        "ask": False,
        "local_info": False,
        "path": "",
        "digipeat": False,
    }


def test_a_search_leaves_out_the_ports_the_radios_that_only_listen_are_set_to() -> None:
    text = RadioSpec(3, "fm", TNC_TEXT.key, "", True, 3, settings={"port": "/dev/ttyUSB7"})
    off = replace(text, id=4, enabled=False, settings={"port": "/dev/ttyUSB8"})
    kiss = RadioSpec(5, "fm", "kiss", "", True, 5, settings={"port": "/dev/ttyUSB9"})
    config = replace(ON_AIR, radios=(*ON_AIR.radios, text, off, kiss))
    first = config.radio(1)
    assert first is not None and first.type == "kenwood-tnc2" and first.value("port") == "", (
        "radio 1 searches, and a TNC-2 is nudged with a carriage return"
    )
    claims = Claims()
    # As the radio registry has it: the settings in force
    claims.named = lambda: named_ports(config)
    assert claimed(claims, 1) == {
        port_key("/dev/ttyUSB7"): "held by radio 3",
        port_key("/dev/ttyUSB9"): "held by radio 5",
    }, "the receive-only radio's port is never searched, nor one a radio that sends is set to; a radio that is off is"
    assert line_settings(first, config, RunOverrides()).skip == ON_AIR.serial_skip_paths, (
        "read from the table at every listing: no restart of radio 1 when another radio's port changes"
    )
    assert (
        line_settings(text, config, RunOverrides()).skip == ON_AIR.serial_skip_paths
        and line_settings(first, ON_AIR, RunOverrides()).skip == ON_AIR.serial_skip_paths
    )
    assert line_settings(kiss, config, RunOverrides()).skip == ON_AIR.serial_skip_paths, (
        "a radio with its own port does not search: another radio's port is not in its settings, and restarts it not"
    )
    remembered = replace(config, serial_last_port="/dev/ttyUSB0")
    assert (
        line_settings(first, remembered, RunOverrides()).skip == ON_AIR.serial_skip_paths
        and line_settings(first, config, RunOverrides(port="/dev/ttyUSB0")).skip == ON_AIR.serial_skip_paths
    )


@pytest.mark.slow("runs a daemon with its radios and services through its loop")
async def test_a_save_of_the_text_radio_restarts_no_radio_that_has_its_own_port(tmp_path: object) -> None:
    e = Env(
        tmp_path,
        web=True,
        settings={"station/call": ME, "station/lat": "60.17", "station/lon": "24.94", "tnc/profile": "kiss"},
    )  # type: ignore[arg-type]
    await e.start()
    beside = await e.new_radio()
    page = await e.ws()
    kiss_id = await e.ctl.add_radio("kiss")
    assert kiss_id is not None
    await page.send({"cmd": "set_config", "values": {f"radio/{kiss_id}/port": beside.url}})
    await until_started(lambda: (r := e.ctl.radios.get(kiss_id)) is not None and r.state is Source.State.CONNECTED)
    text = await e.ctl.add_radio(TNC_TEXT.key)
    assert text is not None
    await idle_for(0.5)

    def opens() -> dict[int, int]:
        return {id: e.ctl.radios.get(id).stats.opens for id in (1, kiss_id)}  # type: ignore[union-attr]

    before = opens()
    await page.send({"cmd": "set_config", "values": {f"radio/{text}/port": "socket://127.0.0.1:9"}})
    await idle_for(1.0)
    assert opens() == before, "the text radio's port restarts no other radio"
    await page.send({"cmd": "radio_change", "radio": text, "enabled": False})
    await idle_for(1.0)
    assert opens() == before, "nor does its tickbox"
    await e.stop()


@pytest.mark.slow("runs a daemon with its radios and services through its loop")
@posix_only
async def test_the_search_of_a_radio_whose_own_port_is_gone_never_opens_the_port_a_text_radio_is_set_to(
    tmp_path: object,
) -> None:
    """The D710's cable is pulled while the Yaesu is switched on: radio 1, with a port of its own
    that cannot be opened, searches the ports as its fallback; the text monitor's port, which
    appears after the start and is not held yet, is left out of that search, so that not a carriage
    return reaches it, and the monitor opens its own port. The port is a pseudo-terminal behind a
    device path, as the search lists a serial device (a KISS TCP address is no device, and no search
    lists one): POSIX only, and the search is made on Linux alone."""
    e = Env(
        tmp_path,
        radio=False,
        settings={"station/call": ME, "station/lat": "60.17", "station/lon": "24.94", "tnc/profile": "kenwood-tnc2"},
        probe_nudge_sec=0.1,
    )  # type: ignore[arg-type]
    # Radio 1's own port: not there, and not in the search's pattern probe_*
    e.settings["serial/port"] = str(e.ports / "fm_gone")
    await e.start(connected=False)
    text = await e.ctl.add_radio(TNC_TEXT.key)
    assert text is not None
    # In the pattern: the search would listen to it
    monitor = e.ports / "probe_monitor"
    await e.ctl.save_radio_settings(text, {"port": str(monitor)})
    await idle_for(0.5)
    # The Yaesu is switched on: its port appears, and it prints what it hears
    master, _ = e.new_pty("probe_monitor")
    written = b""
    # The monitor's next try comes after its own wait
    for _ in range(16):
        feed_pty(master, POSITION)
        written += await asyncio.to_thread(heard_pty, master, 1, 0.5)
        if e.ctl.radios.get(text).state is Source.State.CONNECTED:  # type: ignore[union-attr]
            break
    written += await asyncio.to_thread(heard_pty, master, 1, 0.5)
    assert written == b"", "not a carriage return reached the text monitor's line"
    assert e.ctl.radios.get(text).state is Source.State.CONNECTED, "the monitor has its own port"  # type: ignore[union-attr]
    assert e.ctl.radios.get(1).state is not Source.State.CONNECTED, "radio 1 found no TNC"  # type: ignore[union-attr]
    await e.stop()
