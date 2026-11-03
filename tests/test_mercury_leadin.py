"""The lead-in tone for a radio that keys itself on the audio (VOX): the Mercury NeoAPRS builds plays `tx_leadin_ms` milliseconds of a steady tone ahead of every frame's preamble (packaging/mercury/leadin.patch, applied by
scripts/build-mercury), because a VOX starts to transmit only after it has heard audio for its attack time and the first milliseconds of the preamble, which the far Mercury acquires on, are lost to it. The patch, the
build script and the document are held to each other; and where the built Mercury is (a checkout after `scripts/build-mercury --install`, the `sim` stage, the release's checks) two real Mercury instances on the simulated
channel (tests/support/hfchannel.py) show it: a station whose radio loses the first 100 ms of every transmission is not heard without the lead-in and is heard with it. Skipped where Mercury is not built."""
import asyncio
import os
import re
from pathlib import Path

import pytest

from neoaprs import kiss, mercury
from neoaprs.mercuryhelper import find, free_ports
from tests.conftest import ROOT
from tests.support.hfchannel import Attack, Channel
from tests.support.realmercury import fifo, start_mercury, stop

PATCH = ROOT / "packaging" / "mercury" / "leadin.patch"
SCRIPT = ROOT / "scripts" / "build-mercury"
DOC = ROOT / "docs" / "mercury.md"
ATTACK_MS = 100.0                       # what the radio loses: a slow VOX (a quick one needs 20 to 40 ms), more than the preamble's 110 ms less what a frame survives (docs/mercury.md has the table)
FRAMES = 2
FIRST_PORT = 18900                      # (this test's own ports: four Mercury instances, 10 apart, their control ports 200 above)
PAYLOAD = b"OH2A>APNEO1:=6010.20N/02456.40E-a packet for the lead-in"


def test_the_patch_adds_the_key_to_the_source_and_the_build_applies_it_and_says_so() -> None:
    text = PATCH.read_text(encoding="utf-8")
    assert text.count('+#define CFG_KEY_TX_LEADIN_MS        "audio:tx_leadin_ms"') == 1 and "+++ b/modem/modem.c" in text and "+++ b/common/mercury_engine.c" in text
    assert "+int  modem_get_tx_leadin_ms(void);" in text and "tx_leadin_ms = 0" in text, "off unless the ini says so"
    script = SCRIPT.read_text(encoding="utf-8")
    assert "leadin.patch" in script and "LEADIN_KEY" in script, "applied after the loopback patch, and the key looked for in the patched source"
    assert "leadin.patch" in script[script.index("SOURCE.txt"):], "the source offer names the change (GPL)"


def test_the_document_has_the_table_and_the_lead_in_the_daemon_writes_is_the_one_it_measured() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "scripts/mercury-measure vox" in text and "What `scripts/mercury-measure vox` measured" in text
    assert re.search(rf"`LEADIN_MS` \({mercury.LEADIN_MS} ms\)", text), "the value of the constant is the one the document gives"


def deliver_ports(case: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """The two Mercury instances of a case on a pair of ports each: (broadcast, control) of the sender and of the receiver."""
    return free_ports(FIRST_PORT + 20 * case, 10), free_ports(FIRST_PORT + 20 * case + 10, 10)


async def heard(reader: asyncio.StreamReader, seconds: float) -> bool:
    """Whether a KISS frame comes in `seconds` (the receiver's broadcast port)."""
    decoder = kiss.KissDecoder()

    async def one() -> bool:
        while data := await reader.read(4096):
            if decoder.feed(data):
                return True
        return False
    try:
        return await asyncio.wait_for(one(), seconds)
    except TimeoutError:
        return False


async def delivered(program: str, folder: Path, case: int, leadin_ms: int) -> int:
    """Frames of FRAMES that reach B from A when A's radio loses the first ATTACK_MS of every transmission, with A's Mercury playing a lead-in of `leadin_ms`."""
    folder.mkdir()
    (sender, receiver) = deliver_ports(case)
    channel = Channel(snr_db=20.0, seed=case)
    pipes = {name: (fifo(folder, f"{name}-rx"), fifo(folder, f"{name}-tx")) for name in ("A", "B")}
    for name, (rx, tx) in pipes.items():
        channel.add(name, rx, tx)
    channel.set_link("A", "B", shaper=Attack(lambda: channel.blocks, ATTACK_MS), symmetric=False)
    channel.start()
    processes = [start_mercury(program, folder, "a", *pipes["A"], sender, busy_detect=False, leadin_ms=leadin_ms), start_mercury(program, folder, "b", *pipes["B"], receiver, busy_detect=False)]
    writers: list[asyncio.StreamWriter] = []
    try:
        streams = []
        for ports in (sender, receiver):
            for _ in range(150):
                try:
                    streams.append(await asyncio.open_connection("127.0.0.1", ports[0]))
                    break
                except OSError:
                    await asyncio.sleep(0.2)
            else:
                pytest.fail(f"Mercury did not open its port {ports[0]}")
        writers = [writer for _, writer in streams]
        await asyncio.sleep(2.0)                                    # (the receivers take their noise floor from what they hear)
        count = 0
        for _ in range(FRAMES):
            writers[0].write(kiss.encode(PAYLOAD))
            count += await heard(streams[1][0], 6.0)
        return count
    finally:
        for writer in writers:
            writer.close()
        for process in processes:
            stop(process, 5.0)
        channel.stop()


async def test_a_frame_that_loses_its_first_100_ms_is_heard_with_the_lead_in_and_not_without(tmp_path: Path) -> None:
    program = find()
    if program is None or not hasattr(os, "mkfifo") or "tx_leadin_ms" not in (Path(program[0]).parent / "SOURCE.txt").read_text(encoding="utf-8", errors="replace"):
        pytest.skip("the Mercury that scripts/build-mercury --install builds (with the lead-in) and named pipes are needed")
    without, with_leadin = await asyncio.gather(delivered(program[0], tmp_path / "without", 0, 0), delivered(program[0], tmp_path / "with", 1, mercury.LEADIN_MS))
    assert (without, with_leadin) == (0, FRAMES), f"without the lead-in {without} of {FRAMES}, with {mercury.LEADIN_MS} ms of it {with_leadin} of {FRAMES}"
