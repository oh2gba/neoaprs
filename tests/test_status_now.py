"""Where the status comes from (`status/source`) and "Send status now" (`RigStatus.send_now`,
command `status_now`): off and text send nothing from the radio, and an asked status goes out inside
the interval.
"""

import logging
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs.config import DEFAULTS, Config
from neoaprs.source import Source
from tests.support.air import said
from tests.support.env import Env
from neoaprs.coded import code_of
from tests.support.fakes import rigctld
from tests.test_rigstatus import FIRST, Rig

TEXT = "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:>211200zQRV 145.500"


# ---- the setting ---------------------------------------------------------------------------------


def test_while_the_source_is_empty_it_follows_the_radio_then_the_text_then_nothing() -> None:
    assert DEFAULTS.status_source == "" and DEFAULTS.status_choice == "off"
    assert replace(DEFAULTS, station_status="QRV").status_choice == "text"
    assert replace(DEFAULTS, station_status="QRV", status_rigctld="127.0.0.1:4532").status_choice == "rig"
    assert (
        Config.from_data({"status/rigctld": "127.0.0.1:4532", "status/template": "QRV {freq}"}).status_choice == "rig"
    ), "an installation from before the choice does what it did"


def test_a_source_that_is_set_wins_and_the_radio_is_only_used_for_rig() -> None:
    both = replace(DEFAULTS, station_status="QRV", status_rigctld="127.0.0.1:4532")
    assert (
        replace(both, status_source="text").status_rig_address is None
        and replace(both, status_source="off").status_choice == "off"
    )
    assert replace(both, status_source="rig").status_rig_address == ("127.0.0.1", 4532)
    assert replace(DEFAULTS, status_source="rig").status_rig_address is None


def test_the_source_is_off_text_rig_or_empty() -> None:
    assert [Config.check("status/source", t) for t in ("", " Rig ", "text", "off")] == ["", "rig", "text", "off"]
    with pytest.raises(ValueError, match=r"status/source: 'radio' is not off, text or rig"):
        Config.check("status/source", "radio")


def test_a_save_that_chooses_the_radio_without_an_address_is_refused_with_the_reason() -> None:
    with pytest.raises(ValueError, match=r"status/source: the radio needs status/rigctld"):
        Config.checked(DEFAULTS, {"status/source": "rig"})
    assert Config.checked(DEFAULTS, {"status/source": "rig", "status/rigctld": "127.0.0.1:4532"}).status_choice == "rig"
    with pytest.raises(ValueError, match=r"status/source"):
        Config.checked(replace(DEFAULTS, status_source="rig", status_rigctld="127.0.0.1:4532"), {"status/rigctld": ""})


# ---- the timer follows the choice ----------------------------------------------------------------


async def test_the_timer_sends_the_text_while_the_radio_is_set_but_not_chosen_and_nothing_while_off() -> None:
    rig = Rig(await rigctld(), station_status="QRV 145.500", status_source="text")
    await rig.status.poll()
    assert rig.status.rig_state == "unused" and rig.tnc.lines() == [TEXT]
    off = Rig(await rigctld(), station_status="QRV 145.500", status_source="off")
    await off.status.poll()
    assert off.tnc.sent == [] and off.status.rig_state == "unused"


# ---- send now ------------------------------------------------------------------------------------


async def test_send_now_sends_the_text_inside_the_interval_and_again_although_it_did_not_change() -> None:
    rig = Rig(None, station_status="QRV 145.500")
    await rig.status.poll()
    rig.clock.advance(60)
    assert await rig.status.send_now() == ""
    assert await rig.status.send_now() == ""
    assert rig.tnc.lines() == [TEXT, TEXT.replace("211200z", "211201z"), TEXT.replace("211200z", "211201z")]
    assert rig.status.last_sent_at == rig.clock() and rig.status.last_text == "QRV 145.500"


async def test_send_now_counts_the_interval_from_itself() -> None:
    rigd = await rigctld()
    rig = Rig(rigd)
    assert await rig.status.send_now() == "" and rig.tnc.lines() == [FIRST]
    rigd.hz = 7074000
    rig.clock.advance(29 * 60)
    await rig.status.poll()
    assert len(rig.tnc.sent) == 1, "the timer waits the whole interval after a status that was asked for"
    rig.clock.advance(60)
    await rig.status.poll()
    assert rig.tnc.sent[-1].info.endswith(b"QRV 7.074 MHz USB")


async def test_send_now_reads_the_radio_and_says_when_it_is_away() -> None:
    rigd = await rigctld()
    rig = Rig(rigd)
    rigd.radio_on = False
    away = await rig.status.send_now()
    assert (
        (away, code_of(away)[0]) == ("the radio does not answer", "status.rig_away")
        and rig.status._rig_problem.endswith("rigctld answered RPRT -5")
        and rig.tnc.sent == []
    ), "the page is told the code; the log has rigctld's words"
    rigd.radio_on = True
    assert await rig.status.send_now() == "" and rig.status.rig_state == "on"


async def test_send_now_says_why_it_sends_nothing() -> None:
    assert await Rig(None).status.send_now() == "the status is off"
    assert await Rig(None, station_status="QRV", status_source="off").status.send_now() == "the status is off"
    assert await Rig(None, status_source="text").status.send_now() == "there is no status text"
    assert code_of(await Rig(None, status_source="rig").status.send_now())[0] == "status.no_rig"
    assert "more than the 55" in await Rig(None, station_status="x" * 56).status.send_now()
    assert await Rig(await rigctld(), status_template="").status.send_now() == "there is no status text"


async def test_send_now_obeys_the_tnc() -> None:
    rig = Rig(None, station_status="QRV")
    rig.tnc.state = Source.State.WAITING
    assert "not connected" in await rig.status.send_now() and rig.tnc.sent == []
    rig.tnc.state = Source.State.CONNECTED
    rig.tnc.takes = False
    assert "did not take" in await rig.status.send_now() and rig.status.last_sent_at is None
    rig.tnc.takes = True
    assert await rig.status.send_now() == "" and len(rig.tnc.sent) == 1


async def test_send_now_with_no_call_set_sends_nothing_and_the_log_says_so_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    rig = Rig(None, station_status="QRV", station_call="")
    assert await rig.status.send_now() == "set your call first" and await rig.status.send_now() == "set your call first"
    assert (
        rig.tnc.sent == []
        and [r.getMessage() for r in caplog.records].count("no status sent: set your call first") == 1
    )


# ---- the command ---------------------------------------------------------------------------------


async def test_the_command_sends_the_status_and_the_page_is_told_the_text(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    e.ctl.rigstatus.poll_sec = 3600
    await e.start()
    assert await e.ctl.save_config(
        replace(e.ctl.config, station_status="QRV 145.500", status_source="text", beacon_interval_min=60)
    )
    page = await e.ws()
    await page.until(lambda: len(page.of("status")) >= 1)
    await page.send({"cmd": "status_now"})
    await page.until(
        lambda: any(
            r["tnc2"].endswith("QRV 145.500") and r["direction"] == "out" for r in page.topics["packets"].values()
        )
    )
    await page.until(lambda: page.of("status")[-1]["station_status"] == "QRV 145.500")
    assert page.of("error") == []
    assert e.ctl.rigstatus.frames is e.beacon.frames, (
        "the report is made by the station's one maker of frames, the beacons'"
    )
    await e.stop()


async def test_the_command_still_sends_while_the_beacon_is_off(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    e.ctl.rigstatus.poll_sec = 3600
    await e.start()
    assert await e.ctl.save_config(
        replace(e.ctl.config, station_status="QRV 145.500", status_source="text", beacon_interval_min=0)
    )
    page = await e.ws()
    await page.until(lambda: len(page.of("status")) >= 1)
    await page.send({"cmd": "status_now"})
    frames = [f.tnc2() for f in await said(e, 1, 5.0)]
    assert frames and frames[0].endswith("zQRV 145.500"), frames
    assert not [m for m in page.messages if m.get("type") == "error"]
    await e.stop()


async def test_the_command_is_an_error_when_nothing_could_be_sent(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("status")) >= 1)
    await page.send({"cmd": "status_now"})
    assert (await page.expect("error"))["text"] == "status_now: nothing was sent: the status is off"
    await e.stop()


async def test_the_error_of_a_radio_that_is_not_connected_names_the_radio_which_the_pages_sentence_is_made_of(
    tmp_path: Path,
) -> None:
    """Why nothing was sent goes to the page as the code of the reason and the values of its
    sentence, and the page's sentence of `radio.not_connected` says the radio ("radio FM is not
    connected", in its language): its id, by which the page names it, and its name for a page that
    does not know it. A line's own reason has neither (source.unusable_because); the registry's
    radio adds them (radioregistry.LiveRadio.why_unusable). Without them the page would show the
    sentence with its placeholder in it."""
    e = Env(tmp_path, web=True, radio=False)
    await e.start()
    assert await e.ctl.save_config(replace(e.ctl.config, station_status="QRV 145.500", status_source="text"))
    page = await e.ws()
    for command, code in (("status_now", "status.not_sent"), ("beacon_now", "beacon.not_sent")):
        await page.send({"cmd": command})
        error = await page.expect("error")
        assert (error["cmd"], error["code"], error["params"]) == (
            command,
            code,
            {"why": "radio.not_connected", "radio": 1, "name": "Packet"},
        ), error
    await e.stop()
