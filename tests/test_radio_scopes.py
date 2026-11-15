"""The scope by radio (`radio_scope`, neoaprs/web/scopefeed.py `RadioScopes`): a radio whose type has a scope sends its rows in frames that name it, radio 2's in today's frames unless the page asks for named ones, a
page may look at several radios at once and each is sent only what it asked for; a radio whose type has none is refused with its name and id, one that is none with `radio.unknown`, and a stop is never refused. Over the
page's socket of a real daemon, the rows made on each radio's own modem as the modem part makes them."""
import asyncio
from dataclasses import replace
from pathlib import Path

from neoaprs.mercurymodem import Mercury
from neoaprs.mercuryscope import ROW_BINS, ScopeRow, parse_history, parse_row, scope_clock
from neoaprs.radiospec import HF_ID
from neoaprs.web.scopefeed import RADIO_KIND, parse_radio_frame
from tests.support.env import until
from tests.test_radios_wire import added, refused, started

ROW = ScopeRow(bytes(i % 256 for i in range(ROW_BINS)), -41, False)


def made(modem: Mercury, row: ScopeRow) -> None:
    """A row as the modem part makes one: kept, then told."""
    modem.scope_row.emit(modem.scope_history.add(row, scope_clock()))


def named(frame: bytes) -> tuple[int, bytes]:
    found = parse_radio_frame(frame)
    assert found is not None, f"a frame of kind {frame[0]}, not one that names its radio"
    return found


async def test_each_radio_with_a_scope_sends_its_rows_named_and_radio_2_as_before_unless_asked_for_by_name(tmp_path: Path) -> None:
    e, page = await started(tmp_path, {"hf/enabled": "true", "hf/profile": "mercury"})
    await page.until(lambda: page.topics["radios"].get("2", {}).get("type") == "mercury")
    three = await added(page, "mercury")
    modem = e.ctl.radios.get(three).driver.modem                      # type: ignore[union-attr]
    assert modem is not None and modem is not e.ctl.mercury, "a radio of its own has a modem of its own"
    made(modem, replace(ROW, level=-50))
    await page.send({"cmd": "radio_scope", "radio": three, "on": True})
    radio, history = named((await page.frames(1))[0])
    rows = parse_history(history)
    assert radio == three and rows is not None and [row for row, _ in rows] == [replace(ROW, level=-50)], "first the rows its modem kept, in a frame that names it"
    made(e.ctl.mercury, ROW)
    made(modem, ROW)
    radio, row = named((await page.frames(2))[1])
    assert (radio, parse_row(row)) == (three, ROW), "then its rows, and none of radio 2's"
    await page.quiet(0.2)
    assert len(page.binary) == 2

    old, both = await e.ws(), await e.ws()
    await old.send({"cmd": "radio_scope", "radio": HF_ID, "on": True})
    assert parse_history((await old.frames(1))[0]) is not None, "radio 2's in the frames of before, which name no radio"
    await both.send({"cmd": "radio_scope", "radio": HF_ID, "on": True, "named": True})
    await both.send({"cmd": "radio_scope", "radio": three, "on": True})
    firsts = [named(frame) for frame in await both.frames(2)]
    assert sorted(radio for radio, _ in firsts) == [HF_ID, three] and all(frame[0] == 2 for _, frame in firsts), "each radio's rows kept, each named"
    made(e.ctl.mercury, replace(ROW, tx=True))
    made(modem, replace(ROW, level=-30))
    assert parse_row((await old.frames(2))[1]) == replace(ROW, tx=True)
    rows_of = {radio: parse_row(frame) for radio, frame in map(named, (await both.frames(4))[2:])}
    assert rows_of == {HF_ID: replace(ROW, tx=True), three: replace(ROW, level=-30)}, "a page that looks at two radios has both, each by its radio"
    assert all(frame[0] == RADIO_KIND for frame in both.binary) and all(frame[0] != RADIO_KIND for frame in old.binary)
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
        for name in (False, True):
            await page.send({"cmd": "radio_scope", "radio": radio, "on": False, "named": name})
    await page.quiet(0.3)
    assert len(page.of("error")) == 3 and page.binary == [], "a stop is never refused, and sends nothing"
    await e.stop()
