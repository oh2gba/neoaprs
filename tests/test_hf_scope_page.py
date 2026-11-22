"""Tests for the HF radio scope and transmit level on the page (neoaprs/web/scopefeed.py,
radiowire.py): `radio_scope` subscriptions, waterfall rows, the radio's row, and the gain setting
(`radio/2/tx_gain_db`) reaching the modem.
"""
import asyncio
from dataclasses import replace
from pathlib import Path

from neoaprs.config import Config
from neoaprs.mercuryscope import ROW_BINS, ScopeRow, parse_history, parse_row, scope_clock
from neoaprs.radiospec import HF_ID
from neoaprs.web.scopefeed import parse_radio_frame
from tests.support.env import Env, until
from tests.support.fakemercury import Air

ROW = ScopeRow(bytes(i % 256 for i in range(ROW_BINS)), -41, False)
ON = {"cmd": "radio_scope", "radio": HF_ID, "on": True}
OFF = {"cmd": "radio_scope", "radio": HF_ID, "on": False}


def inner(frame: bytes) -> bytes:
    """The frame of the modem part inside a frame that names radio 2."""
    found = parse_radio_frame(frame)
    assert found is not None and found[0] == HF_ID, "every frame names its radio"
    return found[1]


def history_of(frame: bytes) -> list[tuple[ScopeRow, int]] | None:
    return parse_history(inner(frame))


def row_of(frame: bytes) -> ScopeRow | None:
    return parse_row(inner(frame))


def with_gain(config: Config, gain: int) -> Config:
    """The settings with radio 2's transmit gain."""
    return replace(config, radios=tuple(replace(s, settings={**s.settings, "tx_gain_db": str(gain)}) if s.id == HF_ID else s for s in config.radios))


def made(e: Env, row: ScopeRow) -> None:
    """A row as the modem part makes one: kept, then told."""
    m = e.mercury
    m.scope_row.emit(m.scope_history.add(row, scope_clock()))


async def test_a_page_asks_for_the_scope_gets_the_rows_kept_and_then_the_rows_and_another_page_that_did_not_ask_gets_none(tmp_path: Path) -> None:
    air = Air(frame_sec=0.2)
    station = air.station()
    e = Env(tmp_path, radio=station, web=True)
    await e.start()
    watching, other = await e.ws(), await e.ws()
    await watching.until(lambda: (watching.topics.get("radios", {}).get("2", {}).get("modem") or {}).get("state") == "running")
    modem = watching.topics["radios"]["2"]["modem"]
    assert modem["scope"] is False and modem["tx_gain_db"] == 0 and modem["tx_peak_dbfs"] is None, "a Mercury something else runs: no scope of ours"
    made(e, replace(ROW, level=-50))
    await watching.send(ON)
    history = history_of((await watching.frames(1))[0])
    assert history is not None and [row for row, _ in history] == [replace(ROW, level=-50)] and 0 <= history[0][1] < 60_000, "first the row made before it looked, with its age"
    made(e, ROW)
    assert [row_of(frame) for frame in (await watching.frames(2))[1:]] == [ROW]
    assert other.binary == [], "a page that did not ask is sent no row"
    await other.send(ON)
    other_history = history_of((await other.frames(1))[0])
    assert other_history is not None and [row for row, _ in other_history] == [replace(ROW, level=-50), ROW], "a second page has its own history"
    await watching.send(OFF)
    await until(lambda: e.server.api.topics.scopes.pages(HF_ID) == 1)
    made(e, replace(ROW, tx=True))
    assert [row.tx for row in map(row_of, (await other.frames(2))[1:]) if row is not None] == [True], "the other page still looks"
    assert len(watching.binary) == 2, "a page that stopped asking is sent no more"
    await other.aclose()
    await until(lambda: e.server.api.topics.scopes.pages(HF_ID) == 0)
    await e.stop()
    await air.aclose()


async def test_the_rows_of_the_waterfall_are_binary_frames_to_the_pages_that_asked_and_not_to_a_page_that_is_behind(tmp_path: Path) -> None:
    air = Air(frame_sec=0.2)
    e = Env(tmp_path, radio=air.station(), web=True)
    await e.start()
    watching, other = await e.ws(), await e.ws()
    await watching.send(ON)
    await until(lambda: e.server.api.topics.scopes.pages(HF_ID) == 1)
    assert history_of((await watching.frames(1))[0]) == [], "nothing kept yet"
    made(e, ROW)
    frames = (await watching.frames(2))[1:]
    assert row_of(frames[0]) == ROW and len(frames[0]) == 5 + 310 and watching.of("radio_scope") == [], "the row is a frame of its own, the radio's id before it, not a message"
    assert other.binary == [], "a page that did not ask is sent no row"
    link = next(c for c in e.server.api.topics.scopes._feeds[HF_ID][0]._pages)
    link.client.buffered = lambda: 10 ** 9                                      # type: ignore[method-assign]
    made(e, ScopeRow(bytes(ROW_BINS), -90, True))
    await asyncio.sleep(0.2)
    assert len(watching.binary) == 2, "a page whose socket holds what it has not read is sent no more rows"
    await watching.send(ON)
    await asyncio.sleep(0.2)
    assert len(watching.binary) == 2, "nor the rows kept"
    del link.client.buffered
    made(e, ScopeRow(bytes(ROW_BINS), -80, True))
    assert row_of((await watching.frames(3))[2]) == ScopeRow(bytes(ROW_BINS), -80, True), "once it has read, the rows that come, and not those it was not sent"
    await e.stop()
    await air.aclose()


async def test_the_setting_of_the_gain_reaches_the_modem_and_the_topic_and_a_modem_without_the_ui_is_started_again(tmp_path: Path) -> None:
    air = Air(frame_sec=0.2)
    station = air.station()
    e = Env(tmp_path, radio=station, web=True)
    await e.start()
    page = await e.ws()
    modem = lambda: page.topics.get("radios", {}).get("2", {}).get("modem") or {}        # noqa: E731
    await page.until(lambda: modem().get("state") == "running")
    await page.send({"cmd": "set_config", "values": {"radio/2/tx_gain_db": "-3"}})
    await page.until(lambda: modem().get("tx_gain_db") == -3)
    assert e.mercury.tx_gain_db == -3
    await page.send({"cmd": "set_config", "values": {"radio/2/tx_gain_db": "21"}})
    error = await page.expect("error")
    assert error["key"] == "radio/2/tx_gain_db" and error["code"] == "setting.range" and error["params"]["min"] == -20 and error["params"]["max"] == 20
    config, restart = e.ctl.config, e.ctl.radios.restart_key
    assert e.mercury.live_gain is False
    assert restart(HF_ID, config) != restart(HF_ID, with_gain(config, 5)), "nothing could set it live: the modem is started again, and has it in its ini"
    e.mercury._ui = type("Up", (), {"connected": True})()                             # type: ignore[assignment]
    assert e.mercury.live_gain is True
    assert restart(HF_ID, config) == restart(HF_ID, with_gain(config, 5)), "with the link open the gain is sent and nothing restarts"
    e.mercury._ui = None
    await e.stop()
    await air.aclose()


async def test_a_page_that_asks_for_the_scope_and_leaves_in_the_same_moment_is_not_kept(tmp_path: Path) -> None:
    air = Air(frame_sec=0.2)
    e = Env(tmp_path, radio=air.station(), web=True)
    await e.start()
    try:
        api = e.server.api

        class Page:
            def send_json(self, text: str) -> None: ...
            def send_binary(self, data: bytes) -> None: ...
            def buffered(self) -> int:
                return 0
        page = Page()
        api.attach(page)
        api.on_command(page, '{"cmd": "radio_scope", "radio": 2, "on": true}')
        # (the command and the close came in one read: the command runs after)
        api.detach(page)
        await asyncio.sleep(0.1)            # (the command's task has run)
        assert api.topics.scopes.pages(HF_ID) == 0, "a page that has left is sent nothing"
    finally:
        await e.stop()
        await air.aclose()
