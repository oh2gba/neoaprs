"""The Tnc on a line whose profile reads text (tncprofile.TNC_TEXT, neoaprs/tnctextreader.py) on a
fake radio that types what real devices type (tests/fixtures/text/): it writes nothing, ever, while
a profile that can be asked writes at once on the same timings.
"""

import asyncio
import json
import logging
from pathlib import Path

import pytest

from neoaprs import ax25
from neoaprs.packet import Packet
from neoaprs.source import Source
from neoaprs.tnc import Tnc
from neoaprs.tncprofile import KENWOOD_TNC2, TNC_TEXT
from tests.support.env import idle_for, until
from tests.support.files import fixture_bytes
from tests.support.ptyline import Ptys, feed, heard, posix_only
from tests.test_silent import QUICK
from tests.test_tnc import Rigs, kiss_of, stops_rigs, tiny_backoff, ui_frame
from tests.test_tnc_pty import make_links
from tests.support.logs import warnings_in

FORMS = ("tnc2-oneline.txt", "tnc2-headerln.txt", "tnc2-7e1.bin", "kantronics.txt", "aea.txt", "yaesu.txt")


@pytest.fixture
def rig() -> Rigs:
    return Rigs()


@pytest.mark.slow("runs a daemon with its radios and services through its loop")
@stops_rigs
async def test_a_line_that_reads_text_writes_nothing_while_a_tnc_that_can_be_asked_is_written_to_at_once_on_the_same_timings(
    rig: Rigs,
) -> None:
    asked = await rig(profile=KENWOOD_TNC2, **QUICK)
    text = await rig(profile=TNC_TEXT, **QUICK)
    assert await asked.radio.said(1, 1.0) != b"", "the same keep-alive asks a TNC that can be asked at once"
    text.radio.feed(fixture_bytes("text/tnc2-oneline.txt"))
    await until(lambda: text.tnc.stats.packets == 3)
    await idle_for(1.0)  # (ten quiet periods of the keep-alive's)
    assert not text.tnc.send_frame(ui_frame()), "a frame is refused"
    assert await text.tnc.send(ax25.encode(ui_frame())) is False
    await text.tnc.reopen_port()
    await until(lambda: text.tnc.state is Source.State.CONNECTED)
    await text.radio.connected()
    text.radio.feed(fixture_bytes("text/tnc2-manual.txt"))
    await until(lambda: text.tnc.stats.packets == 5)
    await idle_for(0.5)
    assert await text.radio.said(1, 0.2) == b"" and text.tnc.stats.bytes_out == 0, "not one byte left on its line"
    assert not text.tnc.usable and text.tnc.why_unusable() == "RX only: nothing is sent"
    assert any("not sent: RX only: nothing is sent" in line for line in text.tnc.lines), (
        "the Terminal says why the frame was not sent"
    )
    assert [p.direction for p in text.packets] == ["in"] * 5, "nothing is reported as sent"


@stops_rigs
@pytest.mark.parametrize("name", FORMS)
async def test_every_form_gives_packets_of_the_radio_and_what_began_like_a_header_and_is_none_is_rejected(
    rig: Rigs, name: str
) -> None:
    r = await rig(profile=TNC_TEXT)
    r.tnc.radio_id, r.tnc.radio_name = 7, "Yaesu"
    want = json.loads(fixture_bytes(f"text/{Path(name).stem}.json"))
    data = fixture_bytes(f"text/{name}")
    for at in range(0, len(data), 17):  # (a serial line delivers a few bytes at a time)
        r.radio.feed(data[at : at + 17])
        await asyncio.sleep(0.001)
    await until(lambda: r.tnc.stats.packets == len(want["frames"]) and r.tnc.stats.rejected == want["rejected"])
    assert [(p.source, p.destination, list(p.path), p.info.decode("latin-1")) for p in r.packets] == [
        (f["source"], f["destination"], f["path"], f["info"]) for f in want["frames"]
    ]
    assert all(p.radio_id == 7 and p.direction == "in" and ax25.decode(p.raw).is_ui for p in r.packets), (
        "the radio's id; the raw is the AX.25 frame made of the text"
    )
    assert "text" in r.tnc.describe() and "KISS" not in r.tnc.describe()
    assert sum("rejected, not a frame" in line for line in r.tnc.lines) == want["rejected"]


@stops_rigs
async def test_a_7_bit_line_is_told_once_in_the_log_and_not_on_the_page(
    rig: Rigs, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="neoaprs.tnc")
    r = await rig(profile=TNC_TEXT)
    r.radio.feed(fixture_bytes("text/tnc2-7e1.bin") * 2)
    await until(lambda: r.tnc.stats.packets == 6)
    assert caplog.text.count("the TNC sends 7-bit characters (even parity): letters outside ASCII are lost") == 1
    assert not any("7-bit" in line for line in r.tnc.lines) and r.tnc.problem == ""


@stops_rigs
async def test_a_line_whose_information_is_longer_than_ax25_carries_is_rejected_as_no_frame_and_is_no_fault_of_ours(
    rig: Rigs, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    r = await rig(profile=TNC_TEXT)
    r.radio.feed(b"OH2AB>APRS,WIDE1-1:>" + b"x" * 300 + b"\r\nOH2CD>APRS:>after\r\n")
    await until(lambda: r.tnc.stats.rejected == 1 and r.tnc.stats.packets == 1)
    assert [p.source for p in r.packets] == ["OH2CD"]
    assert (
        sum(
            "rejected, not a frame (an information field of 301 bytes, more than the 256 AX.25 allows)" in line
            for line in r.tnc.lines
        )
        == 1
    )
    assert not any("internal error" in line for line in r.tnc.lines) and not warnings_in(caplog), (
        "ordinary bad input, said at no level of a fault"
    )


@stops_rigs
async def test_a_device_that_sends_kiss_frames_after_text_is_read_as_kiss_and_still_never_written_to(rig: Rigs) -> None:
    r = await rig(profile=TNC_TEXT)
    r.radio.feed(fixture_bytes("text/yaesu.txt"))
    await until(lambda: r.tnc.stats.packets == 2)
    r.radio.feed(kiss_of(ui_frame("OH2KIS-1")) + kiss_of(ui_frame("OH2KIS-2")))
    await until(lambda: r.tnc.stats.packets == 4)
    assert [p.source for p in r.packets[2:]] == ["OH2KIS-1", "OH2KIS-2"] and "KISS" in r.tnc.describe()
    assert not r.tnc.send_frame(ui_frame()) and await r.radio.said(1, 0.3) == b""


def packets_of(tnc: Tnc) -> list[Packet]:
    found: list[Packet] = []
    tnc.packet.connect(found.append)
    return found


@posix_only
@pytest.mark.parametrize("name", ["yaesu.txt", "tnc2-7e1.bin"])
async def test_the_search_finds_the_port_that_types_heard_packets_and_writes_to_no_port(
    ptys: Ptys, tmp_path: Path, name: str
) -> None:
    (quiet, typing), pattern = await make_links(tmp_path, ptys, 2)
    data = fixture_bytes(f"text/{name}")

    async def keep_typing() -> None:
        while True:
            feed(typing, data)
            await asyncio.sleep(0.05)

    feeder = asyncio.create_task(keep_typing())
    tnc = Tnc(pattern=pattern, profile=TNC_TEXT, probe_seconds=5.0, backoff=tiny_backoff(), probe_nudge_sec=0.05)
    found = packets_of(tnc)
    try:
        await tnc.start()
        assert tnc.state is Source.State.CONNECTED and tnc.path == str(tmp_path / "port_2")
        await until(lambda: len(found) >= 2)
    finally:
        feeder.cancel()
        await tnc.stop()
    for master in (quiet, typing):
        assert await asyncio.to_thread(heard, master, 1, 0.2) == b"", (
            "no carriage return was written to any port, quiet or typing"
        )
