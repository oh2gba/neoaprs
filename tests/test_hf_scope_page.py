"""The scope and the transmit level as the page has them (neoaprs/web/scopefeed.py, tncwire.py): `hf_scope` makes a page one of those that are sent the rows of the waterfall and tells the modem whether any page wants them, a page that leaves
or stops asking is forgotten, the rows go to the pages that asked and to no other, the topic `hf` says whether the scope is there, the gain and the peak, the setting of the gain reaches the modem, and it restarts the modem
only where nothing could set it live."""
import asyncio
from dataclasses import replace
from pathlib import Path

from neoaprs.mercuryscope import ROW_BINS, ScopeRow, parse_row
from tests.support.env import Env, until
from tests.support.fakemercury import Air

ROW = ScopeRow(bytes(i % 256 for i in range(ROW_BINS)), -41, False)


async def test_a_page_asks_for_the_scope_gets_the_rows_and_the_modem_is_told_whether_any_page_wants_them(tmp_path: Path) -> None:
    air = Air(frame_sec=0.2)
    station = air.station()
    e = Env(tmp_path, radio=station, web=True)
    await e.start()
    wanted: list[bool] = []
    original = e.ctl.mercury.want_scope
    e.ctl.mercury.want_scope = lambda on: (wanted.append(on), original(on))[1]          # type: ignore[method-assign]
    watching, other = await e.ws(), await e.ws()
    await watching.send({"cmd": "subscribe", "topics": ["hf"]})
    await watching.until(lambda: watching.topics["hf"]["modem"]["state"] == "running")
    modem = watching.topics["hf"]["modem"]
    assert modem["scope"] is False and modem["tx_gain_db"] == 0 and modem["tx_peak_dbfs"] is None, "a Mercury something else runs: no scope of ours"
    await watching.send({"cmd": "hf_scope", "on": True})
    await until(lambda: wanted == [True])
    e.ctl.mercury.scope_row.emit(ROW)
    assert [parse_row(frame) for frame in await watching.frames(1)] == [ROW]
    assert other.binary == [], "a page that did not ask is sent no row"
    await other.send({"cmd": "hf_scope", "on": True})
    await watching.send({"cmd": "hf_scope", "on": False})
    await until(lambda: wanted == [True, True, True])                                    # (the other page still wants it: the modem is told it is wanted, not that it is not)
    e.ctl.mercury.scope_row.emit(replace(ROW, tx=True))
    assert [row.tx for row in map(parse_row, await other.frames(1)) if row is not None] == [True]
    assert len(watching.binary) == 1, "a page that stopped asking is sent no more"
    await other.aclose()
    await until(lambda: wanted[-1] is False)
    await e.stop()
    await air.aclose()


async def test_the_rows_of_the_waterfall_are_binary_frames_to_the_pages_that_asked_and_not_to_a_page_that_is_behind(tmp_path: Path) -> None:
    air = Air(frame_sec=0.2)
    e = Env(tmp_path, radio=air.station(), web=True)
    await e.start()
    watching, other = await e.ws(), await e.ws()
    await watching.send({"cmd": "hf_scope", "on": True})
    await until(lambda: e.server.api.topics.scope.pages == 1)
    e.ctl.mercury.scope_row.emit(ROW)
    frames = await watching.frames(1)
    assert parse_row(frames[0]) == ROW and len(frames[0]) == 310 and watching.of("hf_scope") == [], "the row is a frame of its own, not a message"
    assert other.binary == [], "a page that did not ask is sent no row"
    link = next(c for c in e.server.api.topics.scope._pages)
    link.client.buffered = lambda: 10 ** 9                                      # type: ignore[method-assign]
    e.ctl.mercury.scope_row.emit(ScopeRow(bytes(ROW_BINS), -90, True))
    await asyncio.sleep(0.2)
    assert len(watching.binary) == 1, "a page whose socket holds what it has not read is sent no more rows"
    del link.client.buffered
    e.ctl.mercury.scope_row.emit(ScopeRow(bytes(ROW_BINS), -90, True))
    assert parse_row((await watching.frames(2))[1]) == ScopeRow(bytes(ROW_BINS), -90, True)
    await e.stop()
    await air.aclose()


async def test_the_setting_of_the_gain_reaches_the_modem_and_the_topic_and_a_modem_without_the_ui_is_started_again(tmp_path: Path) -> None:
    air = Air(frame_sec=0.2)
    station = air.station()
    e = Env(tmp_path, radio=station, web=True)
    await e.start()
    page = await e.ws()
    await page.send({"cmd": "subscribe", "topics": ["hf"]})
    await page.until(lambda: page.topics["hf"]["modem"]["state"] == "running")
    await page.send({"cmd": "set_config", "values": {"mercury/tx_gain_db": "-3"}})
    await page.until(lambda: page.topics["hf"]["modem"]["tx_gain_db"] == -3)
    assert e.ctl.mercury.tx_gain_db == -3
    await page.send({"cmd": "set_config", "values": {"mercury/tx_gain_db": "21"}})
    error = await page.expect("error")
    assert error["key"] == "mercury/tx_gain_db" and error["code"] == "setting.range" and error["params"]["min"] == -20 and error["params"]["max"] == 20
    config = e.ctl.config
    assert e.ctl.mercury.live_gain is False
    assert e.ctl._hf_settings(config) != e.ctl._hf_settings(replace(config, mercury_tx_gain_db=5)), "nothing could set it live: the modem is started again, and has it in its ini"
    e.ctl.mercury._ui = type("Up", (), {"connected": True})()                             # type: ignore[assignment]
    assert e.ctl.mercury.live_gain is True
    assert e.ctl._hf_settings(config) == e.ctl._hf_settings(replace(config, mercury_tx_gain_db=5)), "with the link open the gain is sent and nothing restarts"
    e.ctl.mercury._ui = None
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
        api.on_command(page, '{"cmd": "hf_scope", "on": true}')
        api.detach(page)                    # (the command and the close came in one read: the command runs after)
        await asyncio.sleep(0.1)            # (the command's task has run)
        assert api.topics.scope.pages == 0 and not e.ctl.mercury._wanted, "no pictures are made for a page that has left"
    finally:
        await e.stop()
        await air.aclose()
