"""The scope by radio (`radio_scope`, neoaprs/web/scopefeed.py `RadioScopes`): a radio whose type
has a scope sends its rows in frames naming it, a page may watch several radios, and a radio without
a scope is refused.
"""
import asyncio
from dataclasses import replace
from pathlib import Path

from neoaprs.mercurymodem import Mercury
from neoaprs.mercuryscope import ROW_BINS, ScopeRow, parse_history, parse_row, scope_clock
from neoaprs.radiospec import HF_ID
from neoaprs.web.scopefeed import RADIO_KIND, parse_radio_frame
from tests.support.env import until
from tests.test_radios_wire import added, at_rest, refused, started

ROW = ScopeRow(bytes(i % 256 for i in range(ROW_BINS)), -41, False)


def made(modem: Mercury, row: ScopeRow) -> None:
    """A row as the modem part makes one: kept, then told."""
    modem.scope_row.emit(modem.scope_history.add(row, scope_clock()))


def named(frame: bytes) -> tuple[int, bytes]:
    found = parse_radio_frame(frame)
    assert found is not None, f"a frame of kind {frame[0]}, not one that names its radio"
    return found


async def test_each_radio_with_a_scope_sends_its_rows_named_radio_2_too(tmp_path: Path) -> None:
    e, page = await started(tmp_path, {"hf/enabled": "true", "hf/profile": "mercury"})
    await page.until(lambda: page.topics["radios"].get("2", {}).get("type") == "mercury")
    three = await added(page, "mercury")
    modem = e.ctl.radios.get(three).driver.modem                      # type: ignore[union-attr]
    assert modem is not None and modem is not e.mercury, "a radio of its own has a modem of its own"
    await at_rest(modem)
    await at_rest(e.mercury)
    made(modem, replace(ROW, level=-50))
    await page.send({"cmd": "radio_scope", "radio": three, "on": True})
    radio, history = named((await page.frames(1))[0])
    rows = parse_history(history)
    assert radio == three and rows is not None and [row for row, _ in rows] == [replace(ROW, level=-50)], "first the rows its modem kept, in a frame that names it"
    made(e.mercury, ROW)
    made(modem, ROW)
    radio, row = named((await page.frames(2))[1])
    assert (radio, parse_row(row)) == (three, ROW), "then its rows, and none of radio 2's"
    await page.quiet(0.2)
    assert len(page.binary) == 2

    alone, both = await e.ws(), await e.ws()
    await alone.send({"cmd": "radio_scope", "radio": HF_ID, "on": True})
    radio, history = named((await alone.frames(1))[0])
    assert radio == HF_ID and parse_history(history) is not None, "radio 2's in frames that name it, as every radio's"
    await both.send({"cmd": "radio_scope", "radio": HF_ID, "on": True})
    await both.send({"cmd": "radio_scope", "radio": three, "on": True})
    firsts = [named(frame) for frame in await both.frames(2)]
    assert sorted(radio for radio, _ in firsts) == [HF_ID, three] and all(frame[0] == 2 for _, frame in firsts), "each radio's rows kept, each named"
    made(e.mercury, replace(ROW, tx=True))
    made(modem, replace(ROW, level=-30))
    assert named((await alone.frames(2))[1]) == (HF_ID, (await alone.frames(2))[1][5:]) and parse_row(named(alone.binary[1])[1]) == replace(ROW, tx=True)
    rows_of = {radio: parse_row(frame) for radio, frame in map(named, (await both.frames(4))[2:])}
    assert rows_of == {HF_ID: replace(ROW, tx=True), three: replace(ROW, level=-30)}, "a page that looks at two radios has both, each by its radio"
    assert all(frame[0] == RADIO_KIND for frame in both.binary + alone.binary)
    assert len(page.binary) == 3 and parse_row(named(page.binary[2])[1]) == replace(ROW, level=-30)

    await both.send({"cmd": "radio_scope", "radio": three, "on": False})
    await until(lambda: e.server.api.topics.scopes.pages(three) == 1)
    made(modem, ROW)
    await page.frames(4)
    await asyncio.sleep(0.2)
    assert len(both.binary) == 4, "a radio stopped is sent no more"
    await page.aclose()
    await until(lambda: e.server.api.topics.scopes.pages(three) == 0)
    await e.stop()


async def test_a_radio_whose_type_has_no_scope_is_refused_with_its_name_and_a_stop_never_is(tmp_path: Path) -> None:
    e, page = await started(tmp_path)
    dummy = await added(page, "dummy-hf", "Attic")
    for command, code, params in (({"cmd": "radio_scope", "radio": dummy, "on": True}, "radio.no_scope", {"name": "Attic", "radio": dummy}),
                                  ({"cmd": "radio_scope", "radio": 1, "on": True}, "radio.no_scope", {"name": "FM", "radio": 1}),
                                  ({"cmd": "radio_scope", "radio": 9, "on": True}, "radio.unknown", {"radio": 9})):
        error = await refused(page, command)
        assert (error["code"], error["params"]) == (code, params), command
    assert error["text"] == "radio_scope: there is no radio 9"
    for radio in (dummy, 1, 9, HF_ID):
        await page.send({"cmd": "radio_scope", "radio": radio, "on": False})
    await page.quiet(0.3)
    assert len(page.of("error")) == 3 and page.binary == [], "a stop is never refused, and sends nothing"
    await e.stop()


async def test_the_scope_of_a_radio_removed_lets_go_of_its_modem(tmp_path: Path) -> None:
    """A page looked at a radio's scope and the radio is removed: its feed is disconnected from that
    modem's rows."""
    e, page = await started(tmp_path, {"hf/enabled": "true", "hf/profile": "mercury"})
    three = await added(page, "mercury")
    modem = e.ctl.radios.get(three).driver.modem                      # type: ignore[union-attr]
    assert modem is not None
    await at_rest(modem)
    await page.send({"cmd": "radio_scope", "radio": three, "on": True})
    await page.frames(1)
    followed = len(modem.scope_row)
    assert followed >= 1 and e.server is not None and e.server.api.topics.scopes.pages(three) == 1
    assert await e.ctl.remove_radio(three)
    assert e.server.api.topics.scopes.pages(three) == 0 and len(modem.scope_row) == followed - 1, "the feed let go of the removed radio's modem"
    made(modem, ROW)
    await page.quiet(0.2)
    assert len(page.binary) == 1, "and its rows reach no page"
    await e.stop()
