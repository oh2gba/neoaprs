"""Two faults of a Windows station's report: a radio set to the computer's incoming Bluetooth port,
and a port whose writes time out (`SerialTimeoutException: Write timeout`): neither is shown as a
connected radio.
"""

import logging
import threading
import time
from types import SimpleNamespace

import pytest
import serial  # type: ignore[import-untyped]

from neoaprs import ax25, serialport, serialprobe
from neoaprs.claims import Claims
from neoaprs.coded import code_of
from neoaprs.radiospec import RadioSpec
from neoaprs.radiotype import FM_ID
from neoaprs.serialprobe import PortInfo
from neoaprs.source import Backoff, Source
from neoaprs.tnc import Tnc
from neoaprs.tncprofile import KISS
from neoaprs.web.radioview import radio_row
from tests.support.env import idle_for, until

INCOMING = PortInfo(
    "COM8",
    "Serie estándar sobre el vínculo Bluetooth (COM8)",
    "BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0000\\8&C3F3ED0&0&000000000000_00000000",
    None,
    None,
)


class StuckSer:
    """A pyserial object of a port that takes no data: every write times out until `takes`."""

    def __init__(self) -> None:
        self.takes = False
        self.incoming = b""
        self.lock = threading.Lock()
        self.in_waiting = 0
        self.unplugged = False

    def open(self) -> None:
        if self.unplugged:
            raise serial.SerialException(
                "could not open port 'COM8': FileNotFoundError(2, 'El sistema no puede encontrar el archivo especificado.', None, 2)"
            )

    def read(self, size: int = 1) -> bytes:
        time.sleep(0.01)
        if self.unplugged:
            raise serial.SerialException("ClearCommError failed (PermissionError(13, 'Acceso denegado.', None, 5))")
        with self.lock:
            data, self.incoming = self.incoming, b""
        return data

    def write(self, data: bytes) -> int:
        if not self.takes:
            raise serial.SerialTimeoutException("Write timeout")
        return len(data)

    def close(self) -> None:
        pass


def row_of(tnc: Tnc) -> tuple[str, object]:
    spec = RadioSpec(FM_ID, "fm", "kiss", "", True, 1)
    at_work = SimpleNamespace(
        line=tnc,
        beacon=SimpleNamespace(last_sent=None, next_due=None, interval_min=0, problem=""),
        driver=SimpleNamespace(card=None),
        driver_key="tnc",
    )
    row = radio_row(spec, [spec], at_work, Claims())
    return row["state"], row["problem"]


def frame() -> ax25.Frame:
    return ax25.Frame(ax25.Address("APZNEO"), ax25.Address.parse("EA8EE-10"), (), info=b">test")


async def test_a_radio_set_to_the_incoming_bluetooth_port_waits_with_its_own_problem_and_opens_nothing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(serialprobe, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(serialprobe, "available_ports", lambda: [INCOMING])
    monkeypatch.setattr(serialport, "_build", lambda path, baud: pytest.fail("the port was opened"))
    tnc = Tnc("COM8", profile=KISS, backoff=Backoff([0.05]))
    try:
        with caplog.at_level(logging.WARNING, "neoaprs"):
            await tnc.start()
            await idle_for(0.2)
        assert tnc.state is Source.State.WAITING
        assert code_of(tnc.problem) == ("radio.incoming_port", {"port": "COM8"})
        assert row_of(tnc) == ("waiting", {"code": "radio.incoming_port", "params": {"port": "COM8"}})
        said = [r.getMessage() for r in caplog.records]
        assert said == ["tnc: COM8 is the computer's incoming Bluetooth port: choose the device's other port"], (
            "said once: only new settings try it again"
        )
    finally:
        await tnc.stop()


async def test_after_a_write_timed_out_the_radio_is_not_shown_connected_until_data_goes_through(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    ser = StuckSer()
    monkeypatch.setattr(serialport, "_build", lambda path, baud: ser)
    tnc = Tnc("COM8", profile=KISS, backoff=Backoff([0.05]), check_sec=0)
    try:
        await tnc.start()
        assert row_of(tnc) == ("connected", None)
        with caplog.at_level(logging.INFO, "neoaprs"):
            assert tnc.send_frame(frame())
            await until(lambda: tnc.write_stuck is not None)
            await until(lambda: tnc.state is Source.State.CONNECTED)
        problem = {"code": "radio.write_timeout", "params": {"seconds": serialport.WRITE_TIMEOUT_SEC}}
        assert row_of(tnc) == ("waiting", problem), "the bare reopen does not make it connected"
        assert not any("the line is gone" in r.getMessage() for r in caplog.records)
        assert any(
            r.levelno == logging.WARNING
            and "COM8: a write timed out: the device did not take the data within 2 s" in r.getMessage()
            for r in caplog.records
        )
        assert tnc.send_frame(frame()), "frames still go to the port, so that one may get through"
        await until(lambda: tnc.state is Source.State.CONNECTED and tnc.stats.opens >= 3)
        assert row_of(tnc) == ("waiting", problem)
        ser.takes = True
        assert tnc.send_frame(frame())
        await until(lambda: tnc.write_stuck is None)
        assert row_of(tnc) == ("connected", None) and any("the port takes data again" in line for line in tnc.lines)
    finally:
        await tnc.stop()


async def test_a_byte_that_comes_ends_the_write_problem_too(monkeypatch: pytest.MonkeyPatch) -> None:
    ser = StuckSer()
    monkeypatch.setattr(serialport, "_build", lambda path, baud: ser)
    tnc = Tnc("COM8", profile=KISS, backoff=Backoff([0.05]), check_sec=0)
    try:
        await tnc.start()
        tnc.send_frame(frame())
        await until(lambda: tnc.write_stuck is not None and tnc.state is Source.State.CONNECTED)
        with ser.lock:
            ser.incoming = b"\xc0"
        await until(lambda: tnc.write_stuck is None)
        assert row_of(tnc) == ("connected", None)
    finally:
        await tnc.stop()


def test_the_start_line_of_a_radio_with_no_port_says_what_is_true_where_ports_are_not_searched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from neoaprs import tncdriver
    from neoaprs.tncdriver import TncSettings, radio_words

    settings = TncSettings("", 9600, KISS, True, (), "/dev/serial/by-id/*")
    monkeypatch.setattr(tncdriver, "can_search", lambda: True)
    assert "the first port that matches /dev/serial/by-id/* and talks KISS" in radio_words(settings)
    monkeypatch.setattr(tncdriver, "can_search", lambda: False)
    words = radio_words(settings)
    assert "/dev/serial" not in words and "no port chosen yet: this system's ports are not searched" in words


async def test_a_port_lost_after_the_write_problem_shows_its_own_problem_not_the_write_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ser = StuckSer()
    monkeypatch.setattr(serialport, "_build", lambda path, baud: ser)
    tnc = Tnc("COM8", profile=KISS, backoff=Backoff([0.05]), check_sec=0)
    try:
        await tnc.start()
        tnc.send_frame(frame())
        await until(lambda: tnc.write_stuck is not None and tnc.state is Source.State.CONNECTED)
        assert row_of(tnc)[1] == {"code": "radio.write_timeout", "params": {"seconds": serialport.WRITE_TIMEOUT_SEC}}
        ser.unplugged = True
        await until(lambda: tnc.state is Source.State.WAITING and tnc.stats.opens >= 2 and "COM8:" in tnc.problem)
        assert tnc.write_stuck is None
        assert row_of(tnc) == ("waiting", {"code": "radio.not_connected", "params": {"name": "FM"}})
    finally:
        await tnc.stop()
