"""The reports to PSK Reporter (neoaprs/services/pskreporter.py) on a clock the test holds, sent to a
stand-in on the loopback: which stations are reported, the pace, the descriptors, the size of a
datagram, the queue, and the doors that stay shut."""

import asyncio
import logging
import random
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any

import pytest

from neoaprs import VERSION, ax25, nodevices, pskreport
from neoaprs.cli.supportsummary import _psk_reporter
from neoaprs.coded import CodedError
from neoaprs.config import DEFAULTS, Config
from neoaprs.configvalues import dial_or_empty
from neoaprs.packet import IS, Packet
from neoaprs.radiospec import FM_ID, HF_ID
from neoaprs.reading import Reading
from neoaprs.services import pskreporter
from neoaprs.services.pskreporter import PskReporter
from neoaprs.station import RadioPlace, Station
from neoaprs.tnc2line import frame_of
from neoaprs.tncmode import packet_of
from tests.support.clock import FixedClock
from tests.support.env import idle_for, until
from tests.support.pskdecode import Datagram
from tests.support.pskstandin import PskStandIn
from tests.support.radioconfig import with_radio

HOME = (60.17, 24.94)  # KP20le
DIAL = "28.1800 MHz USB"
QUIET_SEC = 0.1  # the reporter looks every 5 ms here: twenty of its looks
STARTED = int(FixedClock().now.timestamp())


def settings(report: bool = True, dial: str = DIAL, type: str = "mercury", call: str = "OH2GBA-10") -> Config:
    config = with_radio(replace(DEFAULTS, station_call=call), HF_ID, type, True, psk_report=report, psk_dial=dial)
    return with_radio(config, FM_ID, "kiss", True)


class Rig:
    def __init__(self, standin: PskStandIn | None = None, config: Config | None = None, **environ: str) -> None:
        self.clock = FixedClock()
        self.config = config or settings()
        self.position: tuple[float, float] | None = HOME
        self.book: dict[str, Station] = {}
        env = {"NEOAPRS_PSKREPORTER": standin.target} if standin is not None else {}
        self.service = PskReporter(
            lambda: self.config,
            lambda: self.position,
            self.book.get,
            self.clock,
            environ={**env, **environ},
            rng=random.Random(7),
        )
        self.service.tick_sec = 0.005

    def hear(self, line: str, radio: int = HF_ID, snr: float | None = 4.4) -> Packet:
        frame = frame_of(line.encode("latin-1"))
        packet = packet_of("in", ax25.encode(frame), frame, self.clock(), reading=Reading(snr), radio_id=radio)
        self.service.on_packet(packet)
        return packet

    def advance(self, seconds: float) -> None:
        self.clock.advance(seconds)

    def target(self) -> tuple[str, int] | None:
        return self.service._target()

    def queued(self) -> list[pskreport.Report]:
        return [waiting.report for waiting in self.service.queue]


@asynccontextmanager
async def running(rig: Rig) -> AsyncIterator[Rig]:
    await rig.service.start()
    try:
        yield rig
    finally:
        await rig.service.stop()


@pytest.fixture
async def standin():  # type: ignore[no-untyped-def]
    made = await PskStandIn().start()
    yield made
    made.close()


async def test_a_station_heard_directly_is_reported_after_five_minutes_and_a_random_half_minute(
    standin: PskStandIn,
) -> None:
    async with running(Rig(standin)) as rig:
        rig.hear("OH2ABC-7>APRS:!6010.20N/02456.40E-hello")
        due = rig.service._due
        assert due is not None and 300 <= (due - rig.clock()).total_seconds() <= 330
        rig.advance(299)
        await idle_for(0.05)
        assert standin.datagrams == []
        rig.advance(31)
        await until(lambda: standin.datagrams)
        [datagram] = standin.datagrams
        assert datagram.receivers == [
            {"receiverCallsign": "OH2GBA", "receiverLocator": "KP20le", "decodingSoftware": f"NeoAPRS {VERSION}"}
        ]
        assert datagram.senders == [
            {
                "senderCallsign": "OH2ABC",
                "frequency": 28180000,
                "sNR": 4,
                "mode": "NEOAPRS",
                "informationSource": 1,
                "senderLocator": "KP20le",
                "flowStartSeconds": STARTED,
            }
        ]
        assert datagram.sequence == 0 and datagram.templates == [t.id for t in pskreport.TEMPLATES]
        assert rig.service.state(HF_ID)["psk_reports_sent"] == 1 and rig.service.state(FM_ID)["psk_reports_sent"] == 0


@pytest.mark.parametrize(
    "line",
    [
        "OH2ABC>APRS,OH2RCH-2*,WIDE2-1:!6010.20N/02456.40E-via a digipeater",
        "OH2ABC>APRS,WIDE1*:!6010.20N/02456.40E-via a used alias",
        "OH2RCH>APRS:}OH2ABC>APRS,TCPIP,OH2RCH*:!6010.20N/02456.40E-third party",
        "OH2GBA>APRS:!6010.20N/02456.40E-our own call",
        "OH2GBA-7>APRS:!6010.20N/02456.40E-our own call with another SSID",
        "N0CALL>APRS:!6010.20N/02456.40E-a placeholder",
        "WIDE>APRS:!6010.20N/02456.40E-no amateur call",
    ],
)
def test_what_is_not_heard_directly_from_another_amateur_is_never_reported(line: str) -> None:
    rig = Rig()
    rig.hear(line)
    assert rig.queued() == []


def test_an_internet_packet_another_radio_and_the_dummy_hf_radio_report_nothing() -> None:
    rig = Rig()
    packet = rig.hear("OH2ABC>APRS:!6010.20N/02456.40E-", radio=FM_ID)
    rig.service.on_packet(replace(packet, via=IS, radio_id=None))
    rig.service.on_packet(replace(packet, via="dummy", radio_id=HF_ID))
    assert rig.queued() == []
    rig.config = settings(type="dummy-hf")
    rig.hear("OH2ABC>APRS:!6010.20N/02456.40E-")
    assert rig.queued() == []
    rig.config = settings()
    rig.hear("OH2ABC>APRS:!6010.20N/02456.40E-")
    assert [r.call for r in rig.queued()] == ["OH2ABC"], "the same packet on the Mercury radio"


@pytest.mark.parametrize(("report", "dial"), [(False, DIAL), (True, ""), (False, "")])
def test_nothing_is_reported_while_the_tick_is_off_or_the_dial_is_empty(report: bool, dial: str) -> None:
    rig = Rig(config=settings(report, dial))
    rig.hear("OH2ABC>APRS:!6010.20N/02456.40E-")
    assert rig.queued() == [] and rig.service._due is None


def test_a_call_is_reported_once_in_five_minutes_on_a_band_and_again_on_another() -> None:
    rig = Rig()
    rig.hear("OH2ABC-7>APRS:!6010.20N/02456.40E-first")
    rig.advance(60)
    rig.hear("OH2ABC-9>APRS:>another SSID of the same call, within five minutes")
    assert [r.heard_at for r in rig.queued()] == [STARTED], "the first stays as it was"
    rig.config = settings(dial="7.0541 MHz USB")
    rig.hear("OH2ABC>APRS:>on 40 m")
    assert [r.frequency_hz for r in rig.queued()] == [28180000, 7054100]
    rig.advance(240)
    rig.config = settings()
    rig.hear("OH2ABC>APRS:>five minutes after the first on 10 m")
    assert len(rig.queued()) == 3


def test_the_sender_is_placed_by_its_packet_else_where_a_radio_heard_it_last_else_left_out() -> None:
    rig = Rig()
    now = rig.clock()
    rig.hear("OH2ABC>APRS:>no position, never placed")
    rig.book["OH2DEF-9"] = Station("OH2DEF-9", first_heard=now, last_heard=now, radio=RadioPlace(61.5, 23.8, now, "rf"))
    rig.hear("OH2DEF-9>APRS:>placed by the radio")
    rig.book["OH2GHI"] = Station("OH2GHI", first_heard=now, last_heard=now, radio=RadioPlace(61.5, 23.8, now, "dummy"))
    rig.hear("OH2GHI>APRS:>placed by the Dummy radio only", snr=None)
    rig.hear("OH2JKL>APRS:!6010.20N/02456.40E-placed by its packet", snr=-30.6)
    assert [(r.call, r.locator, r.snr) for r in rig.queued()] == [
        ("OH2ABC", None, 4),
        ("OH2DEF", "KP11vm", 4),
        ("OH2GHI", None, None),
        ("OH2JKL", "KP20le", -31),
    ]


def test_without_a_position_of_ours_nothing_is_queued_and_the_log_says_it_once_a_day(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, "neoaprs.pskreporter")
    rig = Rig()
    rig.position = None
    rig.service.settings_changed(rig.config)
    for _ in range(3):
        rig.hear("OH2ABC>APRS:>heard")
        rig.advance(3600)
    said = lambda: [r for r in caplog.records if "no position" in r.getMessage()]  # noqa: E731
    assert rig.queued() == [] and len(said()) == 1
    rig.advance(21 * 3600)
    rig.hear("OH2ABC>APRS:>a day later")
    assert len(said()) == 2


async def test_the_descriptors_go_in_the_first_three_datagrams_then_hourly_and_the_sequence_counts_reports(
    standin: PskStandIn,
) -> None:
    async with running(Rig(standin)) as rig:
        for round in range(5):
            for i in range(round + 1):
                rig.hear(f"OH{round}A{i:02d}>APRS:>heard")
            rig.advance(331 if round < 4 else 3600)
            await until(lambda round=round: len(standin.datagrams) == round + 1)  # type: ignore[misc]
    assert [bool(d.templates) for d in standin.datagrams] == [True, True, True, False, True]
    assert [d.sequence for d in standin.datagrams] == [0, 1, 3, 6, 10]
    assert len({d.session for d in standin.datagrams}) == 1 and len({addr for _, addr in standin.raw}) == 1, (
        "one session and one socket: the same source port every time"
    )
    assert all(b.sent_at - a.sent_at >= 300 for a, b in zip(standin.datagrams, standin.datagrams[1:], strict=False))


@pytest.mark.parametrize("step_sec", [3600.0, -3600.0])
async def test_a_stepped_clock_neither_sends_early_nor_stops_reporting_and_the_report_keeps_its_heard_time(
    standin: PskStandIn, step_sec: float
) -> None:
    async with running(Rig(standin)) as rig:
        await idle_for(QUIET_SEC)
        rig.hear("OH2ABC-7>APRS:!6010.20N/02456.40E-hello")
        rig.advance(60)
        rig.clock.step(step_sec)  # the network time sets the clock; the monotonic time stands
        await idle_for(QUIET_SEC)
        rig.advance(200)
        await idle_for(QUIET_SEC)
        assert standin.datagrams == [], "five minutes have not gone by since the station was heard"
        rig.hear("OH2ABC-9>APRS:>the same call, two minutes after the first by the monotonic time")
        assert len(rig.queued()) == 1, "the call's five minutes follow the step too"
        rig.advance(70)
        await until(lambda: standin.datagrams)
        [datagram] = standin.datagrams
        assert [s["flowStartSeconds"] for s in datagram.senders] == [STARTED]


async def test_full_datagrams_go_at_once_and_the_rest_waits_for_the_next_round(standin: PskStandIn) -> None:
    async with running(Rig(standin)) as rig:
        for i in range(80):
            rig.hear(f"OH{i % 10}A{i:02d}>APRS:!6010.20N/02456.40E-")
        rig.advance(331)
        await until(lambda: len(standin.datagrams) >= 2)
        await idle_for(QUIET_SEC)
        first_round = list(standin.datagrams)
        left = len(rig.queued())
        assert len({d.sent_at for d in first_round}) == 1 and 0 < left < 80
        assert pskreport.fitting(receiver_of(first_round[0]), rig.queued()) == left, "what waits is not a full one"
        due = rig.service._due
        assert due is not None and (due - rig.clock()).total_seconds() >= 300
        rig.advance(331)
        await until(lambda: len(standin.senders) == 80)
    assert len(standin.datagrams) == len(first_round) + 1
    assert standin.datagrams[-1].sent_at - first_round[0].sent_at >= 300
    assert all(len(data) <= pskreport.MAX_DATAGRAM for data, _ in standin.raw)
    assert standin.datagrams[1].sequence == len(standin.datagrams[0].senders)


def receiver_of(datagram: Datagram) -> pskreport.Receiver:
    found = datagram.receivers[0]
    return pskreport.Receiver(found["receiverCallsign"], found["receiverLocator"], found["decodingSoftware"])


@pytest.mark.parametrize(
    ("after", "told"),
    [
        (settings(report=False), True),
        (settings(dial=""), True),
        (settings(dial="7.0541 MHz USB"), True),
        (with_radio(settings(), HF_ID, enabled=False), True),
        (settings(report=False), False),
        (settings(dial="7.0541 MHz USB"), False),
    ],
)
async def test_a_report_waiting_goes_with_the_permission_of_its_radio_and_dial(
    standin: PskStandIn, after: Config, told: bool
) -> None:
    """Told: the settings are saved (settings_changed); not told: the send checks again by itself."""
    async with running(Rig(standin)) as rig:
        rig.hear("OH2ABC>APRS:!6010.20N/02456.40E-")
        rig.config = after
        if told:
            rig.service.settings_changed(after)
            assert rig.queued() == [] and rig.service._due is None
        rig.advance(331)
        await idle_for(QUIET_SEC)
    assert standin.datagrams == [], "sent on neither the old dial nor the new one"


def test_a_station_without_a_call_drops_what_waits_and_says_so_once(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.pskreporter")
    rig = Rig()
    rig.hear("OH2ABC>APRS:>heard")
    rig.config = settings(call="")
    for _ in range(2):
        rig.service.settings_changed(rig.config)
    assert rig.queued() == []
    assert len([r for r in caplog.records if "no call" in r.getMessage()]) == 1


@pytest.mark.parametrize("snr", [float("nan"), float("inf"), float("-inf")])
def test_an_snr_that_is_no_number_is_an_unknown_one(snr: float) -> None:
    rig = Rig()
    rig.hear("OH2ABC>APRS:>heard", snr=snr)
    assert [(r.call, r.snr) for r in rig.queued()] == [("OH2ABC", None)]


async def test_a_round_that_fails_ends_nothing_and_the_next_one_sends(
    standin: PskStandIn, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, "neoaprs.pskreporter")
    made = pskreporter.datagram
    calls: list[int] = []

    def breaks_once(*args: Any, **kwargs: Any) -> bytes:
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("a value no datagram takes")
        return made(*args, **kwargs)

    monkeypatch.setattr(pskreporter, "datagram", breaks_once)
    async with running(Rig(standin)) as rig:
        rig.hear("OH2ABC>APRS:>heard")
        rig.advance(331)
        await until(lambda: calls and rig.service._due is not None)
        assert standin.datagrams == [] and len(rig.queued()) == 1
        rig.advance(331)
        await until(lambda: standin.datagrams)
    assert len([r for r in caplog.records if "a round of reports failed" in r.getMessage()]) == 1


async def test_a_socket_the_network_refuses_is_made_anew_and_a_failed_send_counts_nothing(
    standin: PskStandIn, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, "neoaprs.pskreporter")
    async with running(Rig(standin)) as rig:
        rig.hear("OH2ABC>APRS:>heard")
        rig.advance(331)
        await until(lambda: standin.datagrams)
        transport = rig.service._transport
        assert transport is not None

        def refused(data: bytes, address: Any = None) -> None:
            raise OSError("Network is unreachable")

        transport.sendto = refused  # type: ignore[method-assign]
        rig.hear("OH2DEF>APRS:>heard")
        rig.advance(331)
        await until(lambda: rig.service._transport is None and rig.service._due is not None)
        assert len(rig.queued()) == 1 and rig.service.state(HF_ID)["psk_reports_sent"] == 1
        rig.service._failed(OSError("Connection refused"))
        rig.advance(331)
        await until(lambda: len(standin.datagrams) == 2)
        assert rig.service.state(HF_ID)["psk_reports_sent"] == 2
    assert len({address for _, address in standin.raw}) == 2, "a new socket after the failure"
    assert len([r for r in caplog.records if "could not be sent" in r.getMessage()]) == 1


@pytest.mark.parametrize("dial", ["0.0000 MHz USB", "0.0999 MHz USB", "7.0541 MHz LSB", "7.0541"])
def test_a_dial_to_report_on_is_usb_and_above_zero(dial: str) -> None:
    with pytest.raises(CodedError) as refused:
        dial_or_empty(dial)
    assert refused.value.code == "setting.not_dial"
    assert dial_or_empty("0.1000 MHz USB") == "0.1000 MHz USB" and dial_or_empty(" ") == ""


def test_the_queue_keeps_the_newest_500_and_says_it_dropped_the_oldest_once(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, "neoaprs.pskreporter")
    rig = Rig()
    for i in range(520):
        rig.hear(f"O{i % 10}A{i:03d}>APRS:>heard")
    assert len(rig.queued()) == pskreporter.QUEUE_MAX and rig.queued()[0].call == "O0A020"
    assert len([r for r in caplog.records if "the oldest are dropped" in r.getMessage()]) == 1


async def test_with_the_check_off_and_no_stand_in_nothing_is_sent(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.pskreporter")
    async with running(Rig(NEOAPRS_UPDATE_CHECK="0")) as rig:
        rig.hear("OH2ABC>APRS:>heard")
        rig.advance(331)
        await until(lambda: any("is not set" in r.getMessage() for r in caplog.records))
        assert rig.service.state(HF_ID)["psk_reports_sent"] == 0 and rig.queued() == []


@pytest.fixture
def under_the_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    """The no-devices switch is on in this test's own process too (tests/conftest.py lifts it for
    every test that does not ask for a fixture of this name)."""
    monkeypatch.setenv(nodevices.ENV, "1")


def test_the_real_host_is_shut_under_the_no_devices_switch_and_a_stand_in_of_this_computer_is_not(
    monkeypatch: pytest.MonkeyPatch, under_the_switch: None
) -> None:
    assert Rig().target() is None
    assert Rig(NEOAPRS_PSKREPORTER="pskreporter.info:14739").target() is None
    assert Rig(NEOAPRS_PSKREPORTER="127.0.0.1:4739").target() == ("127.0.0.1", 4739)
    assert Rig(NEOAPRS_PSKREPORTER="localhost").target() is None, "not host:port"
    monkeypatch.setenv(nodevices.ENV, "0")
    assert Rig().target() == ("report.pskreporter.info", 4739)


async def test_a_name_that_cannot_be_looked_up_keeps_the_reports_and_is_logged_once(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    caplog.set_level(logging.INFO, "neoaprs.pskreporter")

    async def no_name(host: str, port: int, **_: object) -> object:
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", no_name)
    async with running(Rig(NEOAPRS_PSKREPORTER="no-such-host.invalid:4739")) as rig:
        for round in range(3):
            rig.hear(f"OH2AB{round}>APRS:>heard")
            rig.advance(400)
            await until(lambda: rig.service._due is not None and rig.service._due > rig.clock())
        assert len(rig.queued()) == 3
    assert len([r for r in caplog.records if "could not be looked up" in r.getMessage()]) == 1


def test_the_support_summary_says_whether_the_radio_reports_on_which_dial_and_how_many_went() -> None:
    spec = settings().radio(HF_ID)
    assert spec is not None
    sent = {"psk_reports_sent": 12, "psk_last_sent": "2026-11-26T20:15:00+00:00"}
    assert _psk_reporter(spec, sent) == [
        ("PSK Reporter", "on, 28.1800 MHz USB, 12 reports sent, the last 2026-11-26T20:15:00+00:00")
    ]
    off = settings(report=False).radio(HF_ID)
    assert off is not None and _psk_reporter(off, sent) == [("PSK Reporter", "off")]
    no_dial = settings(dial="").radio(HF_ID)
    assert no_dial is not None and _psk_reporter(no_dial, {}) == [
        ("PSK Reporter", "on, no dial, 0 reports sent, the last never")
    ]
