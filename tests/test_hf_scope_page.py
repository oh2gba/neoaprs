"""The scope and the transmit level as the page has them (neoaprs/web/scopefeed.py, tncwire.py): `hf_scope` makes a page one of those that are sent the pictures and tells the modem whether any page wants them, a page that leaves
or stops asking is forgotten, the pictures go to the pages that asked and to no other, the topic `hf` says whether the scope is there, the gain and the peak, the setting of the gain reaches the modem, and it restarts the modem
only where nothing could set it live."""
import asyncio
from dataclasses import replace
from pathlib import Path

from neoaprs.mercuryscope import SCOPE_BINS, ScopeFrame
from tests.support.env import Env, until
from tests.support.fakemercury import Air

FRAME = ScopeFrame(tuple(range(SCOPE_BINS)), -41)


async def test_a_page_asks_for_the_scope_gets_the_pictures_and_the_modem_is_told_whether_any_page_wants_them(tmp_path: Path) -> None:
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
    e.ctl.mercury.scope_frame.emit(FRAME, False)
    message = await watching.expect("hf_scope")
    assert message["bins"] == list(FRAME.bins) and message["level"] == -41 and message["tx"] is False
    assert other.of("hf_scope") == [], "a page that did not ask is sent no picture"
    await other.send({"cmd": "hf_scope", "on": True})
    await watching.send({"cmd": "hf_scope", "on": False})
    await until(lambda: wanted == [True, True, True])                                    # (the other page still wants it: the modem is told it is wanted, not that it is not)
    e.ctl.mercury.scope_frame.emit(FRAME, True)
    assert (await other.expect("hf_scope"))["tx"] is True
    await other.aclose()
    await until(lambda: wanted[-1] is False)
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
