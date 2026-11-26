"""The radios the operator adds, renames, retypes, enables, moves and removes (Controller methods,
checks in neoaprs/radioedits.py): each stored before it is put in force, only that radio restarted,
and every refusal a RadioError naming the radio.
"""

import asyncio
import json
import logging
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs.claims import Claim
from neoaprs.radioregistry import driver_key
from neoaprs.radiospec import FM_ID, HF_ID, RadioError
from neoaprs.radiotype import RadioTypeError
from neoaprs.services.beacon import memory_key_of
from neoaprs.source import Source
from neoaprs.store import DB_NAME
from tests.support.air import on_air
from tests.support.env import Env, idle_for, until, until_async


async def test_a_radio_is_added_off_given_its_port_switched_on_and_then_heard_and_the_others_are_not_touched(
    tmp_path: Path,
) -> None:
    e = Env(tmp_path)
    await e.start()
    # A KISS server on the loopback: the new radio's
    other = await e.new_radio()
    line = e.tnc._generation
    id = await e.ctl.add_radio("kiss-tcp", "Shack", enabled=False)
    assert id == 2 and e.ctl.radios.get(id) is not None and e.ctl.radios.get(id).state is Source.State.STOPPED  # type: ignore[union-attr]
    assert await e.ctl.save_radio_settings(id, {"port": other.url})
    assert await e.ctl.change_radio(id, enabled=True)
    added = e.ctl.radios.get(id)
    assert added is not None
    await until(lambda: added.state is Source.State.CONNECTED and added.beacon.running)
    assert (added.name, added.spec.position, added.kind) == ("Shack", 2, "fm") and [
        r.id for r in e.ctl.radios.enabled()
    ] == [FM_ID, id]
    other.feed(on_air("OH2TRD", b"!6010.00N/02456.00E>on the added radio"))
    await until(lambda: e.ctl.stationbook.get("OH2TRD") is not None)
    assert [p.radio_id for p in await e.packets()] == [id]
    assert e.tnc._generation == line and e.tnc.state is Source.State.CONNECTED, "radio 1 kept its line"
    [stored] = [s for s in await e.ctl.store.radios() if s.id == id]
    assert (stored.type, stored.name, stored.enabled, dict(stored.settings)) == (
        "kiss-tcp",
        "Shack",
        True,
        {"port": other.url},
    ) and stored == e.ctl.config.radio(id)
    await e.stop()


async def test_a_radio_is_renamed_given_a_type_of_its_kind_and_moved_and_what_it_cannot_be_is_refused(
    tmp_path: Path,
) -> None:
    e = Env(tmp_path, radio=False)
    await e.start(connected=False)
    id = await e.ctl.add_radio("dummy", "Shack", enabled=False)
    assert id is not None
    assert await e.ctl.change_radio(id, name="  Mobile ") and e.ctl.config.radio(id).name == "Mobile"  # type: ignore[union-attr]
    assert await e.ctl.change_radio(id, type="kiss") and e.ctl.config.radio(id).type == "kiss"  # type: ignore[union-attr]
    assert id == 2 and await e.ctl.change_radio(id, position=1) and [r.id for r in e.ctl.radios.all()] == [FM_ID, id], (
        "the same place: by position, then by id"
    )
    assert await e.ctl.change_radio(FM_ID, position=5) and [r.id for r in e.ctl.radios.all()] == [id, FM_ID], "moved"
    with pytest.raises(RadioError, match="radio 2's already"):
        await e.ctl.change_radio(FM_ID, name="MOBILE")
    assert await e.ctl.change_radio(id, name="MOBILE") and await e.ctl.change_radio(id, name="Mobile"), (
        "its own name in other letters"
    )
    for columns, words in (
        ({"name": "a name too long"}, "at most 8"),
        ({"name": "Mö"}, "printable ASCII"),
        ({"type": "mercury"}, "radio/2/type"),
        ({"position": 0}, "radio/2/position"),
        ({"enabled": "yes"}, "radio/2/enabled"),
        ({"kind": "hf"}, "cannot be changed"),
    ):
        with pytest.raises(RadioError, match=words):
            await e.ctl.change_radio(id, **columns)
    with pytest.raises(RadioTypeError):
        await e.ctl.change_radio(id, type="tin-can")
    with pytest.raises(RadioError, match="no such radio"):
        await e.ctl.change_radio(9, name="Gone")
    with pytest.raises(RadioTypeError):
        await e.ctl.add_radio("tin-can")
    [stored] = [s for s in await e.ctl.store.radios() if s.id == id]
    assert (stored.name, stored.type, stored.position) == ("Mobile", "kiss", 1), "what was refused changed nothing"
    await e.stop()


async def test_the_last_enabled_radio_is_neither_switched_off_nor_removed(tmp_path: Path) -> None:
    e = Env(tmp_path, radio=False)
    await e.start(connected=False)
    with pytest.raises(RadioError, match="last one that is enabled"):
        await e.ctl.change_radio(FM_ID, enabled=False)
    with pytest.raises(RadioError, match="last one that is enabled"):
        await e.ctl.remove_radio(FM_ID)
    id = await e.ctl.add_radio("dummy", enabled=False)
    assert id is not None and await e.ctl.change_radio(id, enabled=True)
    assert await e.ctl.change_radio(FM_ID, enabled=False), "with another one on, it may be"
    with pytest.raises(RadioError, match="last one that is enabled"):
        await e.ctl.change_radio(id, enabled=False)
    await until(lambda: e.tnc.state is Source.State.STOPPED)
    assert [s.id for s in e.ctl.config.enabled_radios] == [id] and e.ctl.radios.senders() == [e.ctl.radios.get(id)], (
        "radio 1 is stopped, the other sends"
    )
    await e.stop()


@pytest.mark.expects_errors
async def test_a_save_that_leaves_out_a_radio_in_force_is_refused_and_the_radio_runs_on(tmp_path: Path) -> None:
    """Only Remove takes a radio away (its transaction clears what names it): settings saved without
    a radio in force, or with it marked removed, are not stored, and the radio stays as it was, in
    force and in the database."""
    e = Env(tmp_path, radio=False)
    await e.start(connected=False)
    id = await e.ctl.add_radio("dummy", "Shack")
    added = e.ctl.radios.get(id) if id is not None else None
    assert added is not None
    await until(lambda: added.state is Source.State.CONNECTED)
    before = await e.ctl.store.radios()
    without = tuple(s for s in e.ctl.config.radios if s.id != id)
    marked = tuple(replace(s, removed_at=e.ctl.clock()) if s.id == id else s for s in e.ctl.config.radios)
    for radios in (without, marked):
        assert not await e.ctl.save_config(replace(e.ctl.config, station_comment="two radios less one", radios=radios))
    assert (
        e.ctl.radios.get(id) is added
        and added.state is Source.State.CONNECTED
        and e.ctl.config.radio(id) == before[-1]
        and e.ctl.config.station_comment != "two radios less one"
    )
    assert await e.ctl.store.radios() == before
    await e.stop()


async def test_a_radios_own_settings_are_checked_stored_and_restart_that_radio_alone(tmp_path: Path) -> None:
    e = Env(tmp_path)
    await e.start()
    first, second = await e.new_radio(), await e.new_radio()
    id = await e.ctl.add_radio("kiss-tcp", enabled=False)
    assert (
        id is not None
        and await e.ctl.save_radio_settings(id, {"port": first.url})
        and await e.ctl.change_radio(id, enabled=True)
    )
    added = e.ctl.radios.get(id)
    assert added is not None
    await until(lambda: added.state is Source.State.CONNECTED and added.line.path == first.url)
    line = e.tnc._generation
    assert await e.ctl.save_radio_settings(id, {"port": second.url})
    await until(lambda: added.state is Source.State.CONNECTED and added.line.path == second.url)
    assert e.tnc._generation == line and e.tnc.state is Source.State.CONNECTED, "the other radio is not restarted"
    assert (
        await e.ctl.save_radio_settings(id, {"beacon": "false"})
        and added.choice("beacon") is False
        and added.line.path == second.url
    )
    for values, key in (({"baud": "fast"}, "radio/2/baud"), ({"scope": "on"}, "radio/2/scope")):
        with pytest.raises(RadioError, match=key):
            await e.ctl.save_radio_settings(id, values)
    [stored] = [s for s in await e.ctl.store.radios() if s.id == id]
    assert dict(stored.settings) == {"port": second.url, "beacon": "false"}
    await e.stop()


async def test_remove_takes_the_radio_out_of_the_sets_the_choices_the_paths_and_its_rows_and_stops_it_for_good(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    e = Env(tmp_path, settings={"hf/enabled": "true", "hf/profile": "dummy-hf"})
    # No program: the Dummy HF radio works without its speaker
    e.mercury._finder = lambda: None
    await e.start()
    await until(lambda: e.hf.usable)
    e.feed(on_air("OH2GAX-2", b"!6010.00N/02456.00E>a station"))
    await until(lambda: e.ctl.stationbook.get("OH2GAX-2") is not None)
    assert e.ctl.radios.choose("OH2GAX-2", HF_ID) and e.ctl.radios.choose("OH2GBA", FM_ID)
    await e.ctl.radios.flush()
    await e.ctl.prefbook.set_path("OH2GAX-2", "WIDE2-1", radio_id=HF_ID)
    await e.ctl.prefbook.set_path("OH2GAX-2", "WIDE1-1", radio_id=FM_ID)
    e.ctl.ownobjects.set("SKED", "object", 60.2, 24.9, "/", "E", radios=(FM_ID, HF_ID))
    assert e.beacon_2.send_now()

    async def hf_sent_kept() -> bool:
        return await e.ctl.store.setting(memory_key_of(HF_ID)) is not None

    await until_async(hf_sent_kept)
    beacon_2, hf = e.beacon_2, e.ctl.radios.get(HF_ID)
    with caplog.at_level(logging.INFO, "neoaprs.controller"):
        assert await e.ctl.remove_radio(HF_ID)
    told = [r.getMessage() for r in caplog.records if "removed" in r.getMessage() or "restarted" in r.getMessage()]
    assert told == ["the Mercury radio (radio 2) is removed"], "once, with the name it had"
    assert e.ctl.ownobjects.get("SKED").radios == (FM_ID,), "and out of the object in memory"  # type: ignore[union-attr]
    assert e.ctl.radios.get(HF_ID) is None and e.ctl.config.radio(HF_ID).removed and not e.ctl.config.hf_enabled  # type: ignore[union-attr]
    assert (e.ctl.radios.choice("OH2GAX-2"), e.ctl.radios.choice("OH2GBA")) == (None, FM_ID)
    assert e.ctl.prefbook.path_on("OH2GAX-2", HF_ID) is None and e.ctl.prefbook.path_on("OH2GAX-2", FM_ID) == (
        "WIDE1-1",
    )
    await until(lambda: hf is not None and hf.state is Source.State.STOPPED and not beacon_2.running)
    assert all(claim.holder != HF_ID for claim in e.ctl.radios.claims.all()), "what it held is let go"
    with pytest.raises(RadioError, match="removed"):
        await e.ctl.change_radio(HF_ID, name="Back")
    with pytest.raises(RadioError, match="removed"):
        await e.ctl.save_radio_settings(HF_ID, {"keying": "vox"})
    with pytest.raises(RadioError, match="removed"):
        await e.ctl.remove_radio(HF_ID)
    await e.stop()
    db = sqlite3.connect(tmp_path / DB_NAME)
    try:
        assert db.execute("SELECT id, removed_at IS NOT NULL FROM radio ORDER BY id").fetchall() == [(1, 0), (2, 1)], (
            "its row stays, marked"
        )
        assert db.execute("SELECT radios FROM own_object WHERE name = 'SKED'").fetchall() == [("1",)], (
            "out of the object's set"
        )
        assert db.execute("SELECT call, radio_id FROM station_path ORDER BY radio_id").fetchall() == [
            ("OH2GAX-2", 1)
        ], "its paths gone, the other radio's kept"
        [(choices,)] = db.execute("SELECT value FROM settings WHERE key = 'messages/radio_by_station'").fetchall()
        assert json.loads(choices) == {"OH2GBA": FM_ID}
        assert db.execute("SELECT key FROM settings WHERE key GLOB 'radio/2/*'").fetchall() == [], (
            "its own state rows gone"
        )
    finally:
        db.close()
    again = Env(tmp_path, radio=False)
    await again.start(connected=False)
    assert (
        again.ctl.radios.get(HF_ID) is None
        and again.ctl.config.radio(HF_ID).removed
        and [r.id for r in again.ctl.radios.all()] == [FM_ID]
    )  # type: ignore[union-attr]
    assert not again.ctl.config.hf_enabled and again.ctl.radios.choice("OH2GAX-2") is None
    await again.stop()


async def test_a_daemon_stopped_while_a_removed_radio_is_still_being_stopped_stops_it_and_its_beacon_for_good(
    tmp_path: Path,
) -> None:
    e = Env(tmp_path, settings={"hf/enabled": "true", "hf/profile": "dummy-hf"})
    # No program: the Dummy HF radio works without its speaker
    e.mercury._finder = lambda: None
    await e.start()
    hf = e.ctl.radios.get(HF_ID)
    assert hf is not None
    await until(lambda: e.hf.usable and hf.beacon.running)
    stopping, stops, stop = asyncio.Event(), [], hf.driver.stop

    async def slow_stop() -> None:
        stops.append(len(stops))
        if len(stops) == 1:
            stopping.set()
            # The removal's stop of the radio is still on its way when the daemon stops: it is
            # cancelled there
            await asyncio.Event().wait()
        await stop()

    hf.driver.stop = slow_stop  # type: ignore[method-assign]
    assert await e.ctl.remove_radio(HF_ID)
    await asyncio.wait_for(stopping.wait(), 5)
    await e.stop()
    assert stops == [0, 1] and not hf.beacon.running and hf.state is Source.State.STOPPED, (
        "stopped for good by the daemon's stop, its beacon with it"
    )


async def test_a_radio_wanted_again_while_its_line_is_being_stopped_keeps_its_beacon_and_its_claims(
    tmp_path: Path,
) -> None:
    """Nothing of the program takes a removed radio back today; the registry's `sync` does take back
    one it dropped, and the stop that was under way then leaves the radio as `sync` has it."""
    e = Env(tmp_path, settings={"hf/enabled": "true", "hf/profile": "dummy-hf"})
    # No program: the Dummy HF radio works without its speaker
    e.mercury._finder = lambda: None
    await e.start()
    hf, before = e.ctl.radios.get(HF_ID), e.ctl.config
    assert hf is not None
    await until(lambda: e.hf.usable and hf.beacon.running)
    stopping, go, stopped, stop = asyncio.Event(), asyncio.Event(), asyncio.Event(), hf.driver.stop

    async def held_stop() -> None:
        stopping.set()
        await go.wait()
        await stop()
        stopped.set()

    hf.driver.stop = held_stop  # type: ignore[method-assign]
    assert e.ctl.radios.claims.hold(Claim("gps", "/dev/ttyACM9", HF_ID)) is None
    assert await e.ctl.remove_radio(HF_ID)
    await asyncio.wait_for(stopping.wait(), 5)
    # Radio 2 wanted again while its line is still being stopped
    e.ctl.radios.sync(before)
    go.set()
    await asyncio.wait_for(stopped.wait(), 5)
    await idle_for(0.1)
    assert e.ctl.radios.get(HF_ID) is hf and hf.beacon.running, "the radio taken back keeps its beacon"
    assert e.ctl.radios.claims.holder_of("gps", "/dev/ttyACM9") == HF_ID, (
        "and what it holds that its line does not let go of"
    )
    hf.driver.stop = stop  # type: ignore[method-assign]
    await e.stop()


async def test_a_radio_the_settings_name_by_todays_flat_keys_is_changed_in_its_own_rows(tmp_path: Path) -> None:
    """A save of the flat keys changes the radio they are a view of, in its rows (radio 1's port and
    type, radio 2's tickbox and keying); nothing goes to a settings row."""
    e = Env(tmp_path, radio=False, settings={"hf/enabled": "false"})
    await e.start(connected=False)
    # A port that is not there: radio 1 starts again on it at the save, and a real device's name
    # would be opened
    port = str(tmp_path / "ttyUSB7")
    assert await e.ctl.save_config(
        replace(e.ctl.config, serial_port=port, tnc_profile="kiss", mercury_keying="vox", hf_profile="dummy-hf")
    )
    settings = await e.ctl.store.settings()
    assert not {"serial/port", "tnc/profile", "mercury/keying", "hf/profile", "hf/enabled"} & settings.keys()
    radios = {s.id: (s.type, s.enabled, dict(s.settings)) for s in await e.ctl.store.radios()}
    assert radios == {
        FM_ID: ("kiss", True, {"path": "WIDE1-1,WIDE2-1", "port": port}),
        HF_ID: ("dummy-hf", False, {"keying": "vox"}),
    }
    await e.stop()


def _radio_rows(path: Path, id: int) -> tuple[object, ...]:
    with sqlite3.connect(path / DB_NAME) as db:
        return (
            db.execute(
                "SELECT kind, type, name, enabled, position, removed_at FROM radio WHERE id = ?", (id,)
            ).fetchall(),
            db.execute("SELECT key, value, rev FROM radio_setting WHERE radio_id = ? ORDER BY key", (id,)).fetchall(),
        )


@pytest.mark.parametrize("on", [False, True])
async def test_a_stored_radio_of_a_type_this_build_does_not_know_is_left_off_and_its_row_kept(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, on: bool
) -> None:
    """A row a newer build wrote (its type, `carrier-pigeon`, is none here) neither stops the start
    nor runs: the radio is not made, nothing is sent on it, the page's topic leaves it out, a save
    of another radio puts the settings in force with it there, and its row and its own settings stay
    as they were for the build that knows the type."""
    from neoaprs.controller import Controller
    from neoaprs.web.radioview import radio_row

    first = Controller(tmp_path, check_sec=0)
    await first.open_database()
    await first.store.add_radio("fm", "kiss", "", True, 1)
    await first.store.add_radio(
        "fm", "carrier-pigeon", "Wolf", on, 2, settings={"port": "/dev/ttyUSB9", "sound_card": "plughw:1,0"}
    )
    assert first.db is not None
    await first.db.close()
    stored = _radio_rows(tmp_path, 2)
    ctl = Controller(tmp_path, check_sec=0)
    try:
        await ctl.start()
        assert [r.id for r in ctl.radios.all()] == [FM_ID] and ctl.radios.get(2) is None
        assert (
            [r.id for r in ctl.radios.senders()] == [FM_ID]
            and ctl.radios.senders()[0] is ctl.radios.get(FM_ID)
            and [r.id for r in ctl.radios.beaconing()] == [FM_ID]
        )
        assert "radio 2 is of the type carrier-pigeon, which this NeoAPRS does not have: it is left off" in caplog.text
        assert await ctl.change_radio(FM_ID, name="Base"), (
            "a save with the radio of the unknown type among the settings"
        )
        assert ctl.radios.get(2) is None and caplog.text.count("which this NeoAPRS does not have") == 1, "told once"
        with pytest.raises(RadioError, match="the last one that is enabled"):
            # The radio of the unknown type, on or off, runs nothing
            await ctl.change_radio(FM_ID, enabled=False)
        rows = {
            spec.id: radio_row(spec, ctl.config.radios, ctl.radios.get(spec.id), ctl.radios.claims)
            for spec in ctl.config.radios
        }
        assert rows[2] is None and rows[FM_ID] is not None, "the page's topic `radios` leaves it out"
        assert [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR] == [], (
            "nothing fails on the way (the transmit gain of a modem that is no radio's among it)"
        )
    finally:
        await ctl.stop()
    assert (
        _radio_rows(tmp_path, 2)
        == stored
        == (
            [("fm", "carrier-pigeon", "Wolf", int(on), 2, None)],
            [("port", "/dev/ttyUSB9", 1), ("sound_card", "plughw:1,0", 1)],
        )
    )


async def test_a_stored_radio_2_of_another_kind_than_the_start_up_hf_radio_is_made_of_its_own_type_before_the_start(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A stored radio 2 of another kind than the HF radio radio 2 was before the round (an FM Dummy:
    nothing makes radio 2 an HF radio any more) runs with the driver of its own type before any part
    asks it anything, so the start does not fail on the HF radio's settings."""
    from neoaprs.controller import Controller

    first = Controller(tmp_path, check_sec=0)
    await first.open_database()
    await first.store.add_radio("fm", "kiss", "", True, 1)
    await first.store.add_radio("fm", "dummy", "Bench", True, 2)
    assert first.db is not None
    await first.db.close()
    ctl = Controller(tmp_path, check_sec=0)
    try:
        await ctl.start()
        radio = ctl.radios.get(2)
        assert radio is not None and radio.spec.type == "dummy" and radio.driver_key == driver_key(radio.spec)
        assert [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR] == []
    finally:
        await ctl.stop()
