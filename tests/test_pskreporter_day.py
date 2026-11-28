"""A Mercury radio's reports to PSK Reporter against a whole daemon and a page on its socket: the
radio hears stations on the fake Mercury's air, the clock is moved on, and the datagrams that reach a
stand-in of PSK Reporter on the loopback are read back as its collector reads them."""

from pathlib import Path

import pytest

from neoaprs import VERSION, pskreport
from neoaprs.radiospec import HF_ID
from tests.support.air import on_air
from tests.support.env import Env, idle_for, until
from tests.support.fakemercury import Air, FakeMercury
from tests.support.pskstandin import PskStandIn
from tests.support.wsclient import WsClient

TEN = "28.1800 MHz USB"
FORTY = "7.0541 MHz USB"
QUIET_SEC = 0.3  # the reporter's tick is 10 ms here: this is thirty of its looks


async def hear(e: Env, radio: FakeMercury, source: str, info: bytes, path: str = "", snr: float | None = None) -> None:
    """The radio hears a frame, its SNR said on the control port first as Mercury says it."""
    if snr is not None:
        radio.say_control(f"SN {snr}")
        await until(lambda: e.mercury.snr == snr)
    before = e.ctl.radios.get(HF_ID).line.stats.packets  # type: ignore[union-attr]
    radio.feed(on_air(source, info, path=path))
    await until(lambda: e.ctl.radios.get(HF_ID).line.stats.packets > before)  # type: ignore[union-attr]


async def set_radio(page: WsClient, e: Env, **values: str) -> None:
    await page.send({"cmd": "set_config", "values": {f"radio/{HF_ID}/{k}": v for k, v in values.items()}})

    def stored() -> bool:
        spec = e.ctl.config.radio(HF_ID)
        return spec is not None and all(spec.settings.get(k) == v for k, v in values.items())

    await until(stored)


@pytest.mark.slow("runs a daemon with its radios and services through its loop")
async def test_a_mercury_radio_reports_the_stations_it_hears_directly_once_each_and_a_changed_dial_on_its_band(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    standin = await PskStandIn().start()
    monkeypatch.setenv("NEOAPRS_PSKREPORTER", standin.target)
    air = Air(frame_sec=0.2)
    e = Env(tmp_path, radio=air.station(), web=True)  # (the HF radio alone)
    await e.start()
    try:
        e.ctl.pskreporter.tick_sec = 0.01
        radio = e.hf_radio
        assert radio is not None and e.ctl.config.radio(HF_ID).type == "mercury"  # type: ignore[union-attr]
        page = await e.ws()

        # ---- 1. the tick off, then on with no dial: nothing is reported
        await hear(e, radio, "OH2AAA", b"!6010.20N/02456.40E-before the tick")
        await set_radio(page, e, psk_report="true")
        await hear(e, radio, "OH2AAA", b"!6010.20N/02456.40E-no dial yet")
        e.now.advance(331)  # type: ignore[attr-defined]
        await idle_for(QUIET_SEC)
        assert standin.datagrams == [] and not e.ctl.pskreporter.queue

        # ---- 2. on 10 m: one direct with a position, one direct without, one through a
        # digipeater, our own call, and the first again within five minutes
        await set_radio(page, e, psk_dial=TEN)
        heard_at = int(e.now().timestamp())
        await hear(e, radio, "OH2ABC-7", b"!6010.20N/02456.40E-direct, placed", snr=6.4)
        await hear(e, radio, "OH2DEF", b">direct, no position", snr=-3.0)
        await hear(e, radio, "OH2GHI", b"!6110.20N/02356.40E-through a digipeater", path="OH2RCH-2*,WIDE2-1")
        await hear(e, radio, "OH2GBA-5", b"!6010.20N/02456.40E-our own call")
        e.now.advance(60)  # type: ignore[attr-defined]
        await hear(e, radio, "OH2ABC-7", b"!6010.20N/02456.40E-again within five minutes")
        e.now.advance(271)  # type: ignore[attr-defined]
        await until(lambda: standin.datagrams, 10.0)
        [first] = standin.datagrams
        assert first.receivers == [
            {"receiverCallsign": "OH2GBA", "receiverLocator": "KP20le", "decodingSoftware": f"NeoAPRS {VERSION}"}
        ]
        assert sorted(first.senders, key=lambda s: s["senderCallsign"]) == [
            {
                "senderCallsign": "OH2ABC",
                "frequency": 28180000,
                "sNR": 6,
                "mode": "NEOAPRS",
                "informationSource": 1,
                "senderLocator": "KP20le",
                "flowStartSeconds": heard_at,
            },
            {
                "senderCallsign": "OH2DEF",
                "frequency": 28180000,
                "sNR": -3,
                "mode": "NEOAPRS",
                "informationSource": 1,
                "flowStartSeconds": heard_at,
            },
        ]
        assert first.templates == [t.id for t in pskreport.TEMPLATES] and first.sequence == 0

        # ---- 3. the dial changed to 40 m: the 10 m report that waits goes with the old dial, and the
        # same call within five minutes is reported on 40 m
        await hear(e, radio, "OH2ABC-7", b"!6010.20N/02456.40E-on 10 m again")
        await hear(e, radio, "OH2ABC-7", b"!6010.20N/02456.40E-twice on 10 m")
        await set_radio(page, e, psk_dial=FORTY)
        await hear(e, radio, "OH2ABC-7", b"!6010.20N/02456.40E-on 40 m")
        e.now.advance(331)  # type: ignore[attr-defined]
        await until(lambda: len(standin.datagrams) == 2, 10.0)
        second = standin.datagrams[1]
        assert [(s["senderCallsign"], s["frequency"]) for s in second.senders] == [
            ("OH2ABC", 7054100),
        ]
        assert second.templates and second.sequence == 2 and second.session == first.session
        assert len({address for _, address in standin.raw}) == 1, "one socket for the session"

        # ---- 4. heard, then the tick off before the round: nothing of it goes, and nothing after
        await hear(e, radio, "OH2UVW", b"!6010.20N/02456.40E-before the tick goes off")
        assert e.ctl.pskreporter.queue
        await set_radio(page, e, psk_report="false")
        await until(lambda: not e.ctl.pskreporter.queue)
        await hear(e, radio, "OH2XYZ", b"!6010.20N/02456.40E-after the tick")
        e.now.advance(331)  # type: ignore[attr-defined]
        await idle_for(QUIET_SEC)
        assert len(standin.datagrams) == 2
        assert e.ctl.pskreporter.state(HF_ID)["psk_reports_sent"] == 3
    finally:
        await e.stop()
        standin.close()
