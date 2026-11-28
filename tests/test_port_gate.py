"""NeoAPRS never gets in its own way on a port (neoaprs/portgate.py, serialport.py, serialprobe.with_links):
Windows refuses a second open of a COM port with "access denied" even from the same program, so the
listing of the ports opens none, and one port has one open under way at a time. Then the station of the
report: a tracker that does not answer is said not to answer every time, never "in use"."""

import asyncio
import logging
import os
import threading
from typing import Any

import pytest
import serial  # type: ignore[import-untyped]

from neoaprs import portgate, serialport, serialprobe
from neoaprs.serialport import SerialError, SerialPort
from neoaprs.serialprobe import PortInfo
from neoaprs.source import Backoff, Source
from neoaprs.tnc import Tnc
from neoaprs.tncprofile import KISS
from neoaprs.web import handlers
from tests.support.env import until

COM7 = PortInfo(
    "COM7",
    "Standard Serial over Bluetooth link (COM7)",
    "BTHENUM\\{00001101}_VID&0001&0&000CBF18376C_C00000000",
    None,
    None,
)


# ---- the listing


def test_the_listing_of_the_ports_never_resolves_a_com_name(monkeypatch: pytest.MonkeyPatch) -> None:
    resolved: list[str] = []
    real = os.path.realpath

    def opens(path: str, **kwargs: Any) -> str:
        if "COM" not in str(path):
            return real(path, **kwargs)
        resolved.append(path)
        raise PermissionError(13, "the device is opened", path, 31)

    monkeypatch.setattr(serialprobe.os.path, "realpath", opens)
    assert serialprobe.with_links([COM7], dirs=()) == [COM7], "no link: the ports as they are"
    assert resolved == [], "nothing to compare with: nothing resolved"
    monkeypatch.setattr(serialprobe, "_on_windows", lambda: True)
    assert serialprobe.with_links([COM7]) == [COM7] and resolved == []


def test_a_port_that_cannot_be_resolved_is_listed_as_it_is(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    (tmp_path / "radio").symlink_to("/dev/null")

    real = os.path.realpath

    def resolve(path: str, **kwargs: Any) -> str:
        if path == "COM7":
            raise PermissionError(13, "the device is opened", path, 31)
        return "/dev/null" if "radio" in str(path) or path == "/dev/null" else real(path, **kwargs)

    monkeypatch.setattr(os.path, "realpath", resolve)
    monkeypatch.setattr(serialprobe, "_on_windows", lambda: False)  # (the links of a system that has them)
    null = PortInfo("/dev/null", "", "", None, None)
    assert [p.device for p in serialprobe.with_links([COM7, null], dirs=(str(tmp_path),))] == [
        "COM7",
        "/dev/null",
        str(tmp_path / "radio"),
    ]


def test_a_listing_that_fails_gives_the_page_no_ports_and_no_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fails() -> list[PortInfo]:
        raise PermissionError(13, "Access is denied", "\\\\.\\COM7", 31)

    monkeypatch.setattr(handlers, "offered_ports", fails)
    with caplog.at_level(logging.WARNING, "neoaprs"):
        assert handlers.listed_ports() == []
    assert "listing the ports failed" in caplog.text and not any(r.levelno >= logging.ERROR for r in caplog.records)


# ---- one open at a time


class WindowsCom:
    """A COM port as Windows has it: one open handle at a time, a second open is refused with error 5
    at once; its own open blocks for `block_sec`, then fails with `fails` (121) or opens."""

    def __init__(self, block_sec: float = 0.0, fails: str = "") -> None:
        self.block_sec, self.fails = block_sec, fails
        self.lock = threading.Lock()
        self.handles = 0  # opens under way or open
        self.entered = 0
        self.most = 0
        self.release = threading.Event()
        self.waits = False

    def ser(self, path: str, baud: int) -> Any:
        return _Handle(self, path)


class _Handle:
    in_waiting = 0

    def __init__(self, com: WindowsCom, path: str) -> None:
        self.com, self.path, self.mine = com, path, False

    def open(self) -> None:
        com = self.com
        with com.lock:
            com.entered += 1
            if com.handles:
                raise serial.SerialException(
                    f"could not open port '{self.path}': PermissionError(13, 'Access is denied.', None, 5)"
                )
            com.handles += 1
            com.most = max(com.most, com.handles)
            self.mine = True
        if com.waits:
            assert com.release.wait(10), "the test never let the open go on"
        elif com.block_sec:
            threading.Event().wait(com.block_sec)  # (the stand-in for CreateFile's own time)
        if com.fails:
            self._let_go()
            raise serial.SerialException(com.fails)

    def _let_go(self) -> None:
        with self.com.lock:
            if self.mine:
                self.com.handles -= 1
                self.mine = False

    def read(self, size: int = 1) -> bytes:
        threading.Event().wait(0.01)
        return b""

    def write(self, data: bytes) -> int:
        return len(data)

    def close(self) -> None:
        self._let_go()


def on_windows(monkeypatch: pytest.MonkeyPatch, com: WindowsCom) -> None:
    monkeypatch.setattr(serialport, "_build", com.ser)
    monkeypatch.setattr(serialport, "_on_windows", lambda: True)
    monkeypatch.setattr(serialport, "_bluetooth_com", lambda path: True)


async def test_an_open_given_up_on_is_waited_for_before_the_next_open_of_the_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    com = WindowsCom()
    com.waits = True
    on_windows(monkeypatch, com)
    first = asyncio.create_task(SerialPort("COM7").open())
    await until(lambda: com.entered == 1)
    first.cancel()  # a stop or a restart: the open's thread runs on in CreateFile
    with pytest.raises(asyncio.CancelledError):
        await first
    second = SerialPort("COM7")
    opening = asyncio.create_task(second.open())
    for _ in range(20):
        await asyncio.sleep(0)
    assert com.entered == 1, "the second open waits at the gate"
    com.release.set()
    await opening
    assert second.is_open and com.most == 1
    second.close()


async def test_a_port_this_program_holds_is_not_opened_again_and_is_not_called_another_programs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    com = WindowsCom()
    on_windows(monkeypatch, com)
    radio = SerialPort("COM7")
    await radio.open()
    with pytest.raises(SerialError) as caught:
        await SerialPort("\\\\.\\com7").open()
    assert "NeoAPRS has the port open already" in str(caught.value) and com.entered == 1
    radio.close()
    await until(lambda: not portgate.held("COM7"))
    again = SerialPort("COM7")
    await again.open()
    again.close()


async def test_a_gate_kept_too_long_is_said_as_our_own_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(portgate, "OPEN_WAIT_SEC", 0.01)
    with portgate.turn("COM7"):
        with pytest.raises(SerialError, match="another open of the port by NeoAPRS"):
            await SerialPort("COM7").open()


# ---- the station of the report


TIMEOUT_121 = "could not open port 'COM7': OSError(22, 'Se agotó el tiempo de espera del semáforo.', None, 121)"
# CreateFile took about 5 s on the user's machine; a shorter block shows the same overlaps
BLOCK_SEC = 0.5


@pytest.mark.slow("many opens that each block half a second")
async def test_a_tracker_that_does_not_answer_is_said_not_to_answer_every_time_never_in_use(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    com = WindowsCom(BLOCK_SEC, TIMEOUT_121)
    on_windows(monkeypatch, com)
    monkeypatch.setattr(serialprobe, "_on_windows", lambda: True)
    monkeypatch.setattr(serialprobe, "can_search", lambda: False)  # (Windows has no search of the ports)
    tnc = Tnc("COM7", profile=KISS, backoff=Backoff([0.01]), check_sec=0)
    others: list[str] = []

    async def find_my_radio() -> None:
        while True:  # a search and Find my radio try the same port meanwhile
            try:
                await SerialPort("COM7").open()
            except SerialError as e:
                others.append(str(e))

    with caplog.at_level(logging.WARNING, "neoaprs.tnc"):
        finder = asyncio.create_task(find_my_radio())
        try:
            await tnc.start()
            await until(lambda: com.entered >= 2)
            await tnc.start()  # a restart while an open is under way
            for _ in range(3):
                assert serialprobe.with_links([COM7]) == [COM7]  # the page asks for the list meanwhile
                await until(lambda: tnc.state is Source.State.WAITING, 10)
                await until(lambda: tnc.state is not Source.State.WAITING, 10)
            await until(lambda: tnc.state is Source.State.WAITING, 10)
        finally:
            finder.cancel()
            await tnc.stop()
    said = [r.getMessage() for r in caplog.records if "trying again" in r.getMessage()]
    assert len(said) >= 3
    assert all("the device does not answer" in s and "(Windows error 121)" in s for s in said), said
    assert com.most == 1, "never two opens of the port at once"
    assert not any("Windows error 5" in s for s in said + others)
