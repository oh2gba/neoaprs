"""The radio a message to a station goes out on while both radios are on (neoaprs/radios.py: `for_station`, `choose`, the state row MESSAGE_RADIOS), the pause before a retry on HF (message.retry_pause:
two stations that collided must not retry at the same moment again), and a station whose position takes no messages can still be written to (`may_not_message`). John and OH2GAX, 4 Nov 2026."""
import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

from neoaprs.clock import utc
from neoaprs.config import DEFAULTS, MESSAGE_RADIOS
from neoaprs.message import FIRST_WAIT_SEC, MessageRecord, due_at, retry_pause
from neoaprs.radiorules import FM, HF
from neoaprs.radios import Radios
from neoaprs.station import Station
from neoaprs.stationbook import StationBook
from tests.support.air import on_air
from tests.test_web import with_page

T0 = utc(2026, 11, 4, 7, 30)
BOTH = replace(DEFAULTS, fm_enabled=True, hf_enabled=True)


class Kept:
    """A Memory: the rows written."""
    def __init__(self) -> None:
        self.rows: dict[str, str] = {}

    async def setting(self, key: str) -> str | None:
        return self.rows.get(key)

    async def put_settings(self, data: dict[str, str]) -> bool:
        self.rows.update(data)
        return True


def station(call: str, fm: int = 0, hf: int = 0, **values: Any) -> Station:
    return Station(call, first_heard=T0, last_heard=T0, heard_fm=fm, heard_hf=hf, **values)


def radios(memory: Kept | None = None, config: Any = BOTH) -> tuple[Radios, StationBook, object, object]:
    book, fm, hf = StationBook(), object(), object()
    book.seed([station("OH2GAX-2", fm=40, hf=21), station("OH2FAR", hf=3), station("OH2NEAR", fm=5)])
    remember = (lambda text: memory.rows.update({MESSAGE_RADIOS: text})) if memory is not None else (lambda text: None)
    return Radios(fm, hf, lambda: config, book, remember), book, fm, hf          # type: ignore[arg-type]  (what is chosen is all that is asked of a radio here)


async def test_a_station_heard_on_both_radios_goes_on_fm_until_the_operator_chooses_hf_and_the_choice_is_kept() -> None:
    kept = Kept()
    r, book, fm, hf = radios(kept)
    changed: list[str] = []
    book.changed.connect(lambda s: changed.append(f"{s.call}:{s.message_radio}"))
    assert r.for_station("OH2GAX-2") is fm and r.for_station("OH2FAR") is hf and r.for_station("OH2NEAR") is fm, "the daemon's choice: FM unless heard on HF alone"
    assert r.choose("OH2GAX-2", "hf") and r.for_station("OH2GAX-2") is hf and changed == ["OH2GAX-2:hf"], "the page hears of it with the station"
    assert r.choose("OH2NEAR", "hf") and r.choose("OH2FAR", "fm") and r.for_station("OH2FAR") is fm
    await r.flush()
    assert json.loads(kept.rows[MESSAGE_RADIOS]) == {"OH2FAR": "fm", "OH2GAX-2": "hf", "OH2NEAR": "hf"}
    assert r.choose("OH2NEAR", "") and r.for_station("OH2NEAR") is fm, "an empty choice gives it back to the daemon"
    assert not r.choose("OH2NOBODY", "hf") and not r.choose("OH2GAX-2", "lora"), "an unknown station or radio is no choice"

    again, book2, fm2, hf2 = radios()
    again.restore(kept.rows[MESSAGE_RADIOS])
    assert again.for_station("OH2GAX-2") is hf2 and again.for_station("OH2FAR") is fm2, "after a restart"
    again.restore("not json") or again.restore('{"OH2GAX-2": "lora"}')
    assert book2.get("OH2GAX-2").message_radio == "hf"                     # type: ignore[union-attr]


def test_with_one_radio_on_the_choice_is_not_asked() -> None:
    r, _, fm, _ = radios(config=replace(DEFAULTS, fm_enabled=True, hf_enabled=False))
    assert r.choose("OH2GAX-2", "hf") and r.for_station("OH2GAX-2") is fm, "the choice waits for both radios to be on"


def message(attempts: int, to: str = "OH2GAX-2", number: int = 556) -> MessageRecord:
    return MessageRecord(number, T0, "out", "OH2GBA", to, "going down 5W", "DN", "sending", attempts=attempts, last_attempt_at=T0 if attempts else None)


def test_a_retry_on_hf_waits_a_pause_of_its_own_and_one_on_fm_none() -> None:
    assert retry_pause(message(0), HF.retry_jitter_sec) == timedelta(0), "the first attempt goes at once"
    assert retry_pause(message(4), HF.retry_jitter_sec) == timedelta(0), "after the last attempt only the answer is waited for"
    assert retry_pause(message(1), FM.retry_jitter_sec) == timedelta(0) and FM.retry_jitter_sec == 0
    pause = retry_pause(message(1), HF.retry_jitter_sec)
    assert timedelta(0) <= pause <= timedelta(seconds=HF.retry_jitter_sec) and retry_pause(message(1), HF.retry_jitter_sec) == pause, "the same every time it is asked"
    assert due_at(message(1)) == T0 + timedelta(seconds=FIRST_WAIT_SEC)
    ours = [retry_pause(message(n), HF.retry_jitter_sec) for n in (1, 2, 3)]
    theirs = [retry_pause(message(n, to="OH2GBA", number=36), HF.retry_jitter_sec) for n in (1, 2, 3)]
    assert ours != theirs, "the two stations of a collision pause differently"
    spread = {round(retry_pause(message(1, number=n), HF.retry_jitter_sec).total_seconds()) for n in range(200)}
    assert len(spread) > 15, "the pauses cover the range"


def test_a_station_whose_position_takes_no_messages_can_be_written_to_and_is_marked() -> None:
    plain = station("OH2PLN", fm=1, position_messaging=False)
    assert plain.can_message and plain.may_not_message
    talker = station("OH2TLK", fm=1, position_messaging=False, sent_message=True)
    assert talker.can_message and not talker.may_not_message, "a station that sent a message does messages"
    assert not station("OH2ANY", fm=1).may_not_message and not station("FIRE", fm=1, kind="object").can_message


async def test_the_page_chooses_the_radio_of_a_station_and_its_row_says_it(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    e.feed(on_air("OH2GAX-2", b"=6015.42N/02447.93E-Otso"))
    await page.until(lambda: "OH2GAX-2" in page.topics["stations"])
    assert page.topics["stations"]["OH2GAX-2"]["message_radio"] == ""
    await page.send({"cmd": "message_radio", "call": "OH2GAX-2", "radio": "hf"})
    await page.until(lambda: page.topics["stations"]["OH2GAX-2"]["message_radio"] == "hf")
    await page.send({"cmd": "message_radio", "call": "OH2NOBODY", "radio": "hf"})
    error = await page.expect("error")
    assert error["code"] == "station.unknown"
