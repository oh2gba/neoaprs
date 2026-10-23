"""The serial port on a real device file: a pseudo-terminal pair stands in for /dev/ttyUSB0, so pyserial's POSIX code runs (the lock, the abort pipe, a device that goes away), and so does what only Linux can say:
which program has a device open (/proc), and the globs of the search. POSIX only; the same behaviour on the fake radio, on every system, is in tests/test_serialport.py."""
import asyncio
import errno
import logging
import os
import select
import subprocess
import sys
from pathlib import Path

import pytest

from neoaprs.kiss import KissDecoder, encode
from neoaprs.serialholders import held_by, holders
from neoaprs.serialport import SerialError, SerialPort
from neoaprs.serialprobe import candidate_ports, probe
from tests.support.env import until
from tests.support.ptyline import Ptys, close_pty, feed, heard, held_by_a_program, posix_only

pytestmark = posix_only


async def opened(path: str) -> SerialPort:
    port = SerialPort(path)
    await port.open()
    return port


# ---- reading and writing a device

async def test_chunks_and_writes_go_through_the_threads_on_a_device(ptys: Ptys) -> None:
    master, path = ptys()
    chunks = bytearray()
    port = SerialPort(path, 9600)
    port.data.connect(chunks.extend)
    await port.open()
    try:
        sent = bytes(range(256)) * 8
        feed(master, sent)
        await until(lambda: len(chunks) >= len(sent))
        assert bytes(chunks) == sent
        frame = encode(b"hello", port=0)
        assert port.write(frame) == len(frame)
        assert await asyncio.to_thread(heard, master, len(frame)) == frame
    finally:
        port.close()


async def test_closing_a_device_wakes_the_reader_at_once_and_the_port_opens_again(ptys: Ptys) -> None:
    _, path = ptys()
    port = await opened(path)
    began = asyncio.get_running_loop().time()
    port.close()
    assert asyncio.get_running_loop().time() - began < 0.3, "cancel_read woke the reader; it did not wait out its timeout"
    again = await opened(path)
    again.close()


# ---- a line that dies

async def test_a_device_that_goes_away_emits_dropped_once_and_closes_the_port(ptys: Ptys) -> None:
    master, path = ptys()
    reasons: list[str] = []
    port = SerialPort(path)
    port.dropped.connect(reasons.append)
    await port.open()
    close_pty(master)
    await until(lambda: reasons)
    await asyncio.sleep(0.2)
    assert len(reasons) == 1 and reasons[0]
    assert not port.is_open
    with pytest.raises(SerialError):
        port.write(b"x")


async def test_a_device_file_that_is_not_there_raises_serial_error_with_the_systems_words(tmp_path: Path) -> None:
    port = SerialPort(str(tmp_path / "nothing-here"))
    with pytest.raises(SerialError, match="No such file or directory"):
        await port.open()
    assert not port.is_open


# ---- the lock: one owner at a time

TRY_LOCK = "import fcntl, os, sys\nfd = os.open(sys.argv[1], os.O_RDWR | os.O_NOCTTY)\ntry:\n    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\nexcept OSError as e:\n    sys.exit(e.errno)\n"


def lock_status(path: str) -> int:
    """What another process's try to lock `path` comes to: 0, or the errno it failed with."""
    return subprocess.run([sys.executable, "-c", TRY_LOCK, path], check=False).returncode


async def test_a_device_is_opened_by_one_owner_at_a_time_and_the_second_is_told_why(ptys: Ptys) -> None:
    _, path = ptys()
    first = await opened(path)
    try:
        with pytest.raises(SerialError, match="in use by another program"):
            await SerialPort(path).open()               # exclusive: the daemon and a capture script cannot read the same line
        with pytest.raises(SerialError, match="already open"):
            await first.open()
    finally:
        first.close()
    second = await opened(path)
    second.close()


async def test_another_program_that_locks_the_device_is_refused_while_we_hold_it_and_gets_it_after_the_close(ptys: Ptys) -> None:
    _, path = ptys()
    assert lock_status(path) == 0, "nobody holds the port yet"
    port = await opened(path)
    try:
        assert lock_status(path) == errno.EAGAIN, "the lock pyserial takes is a flock; a program that takes one too is refused"
    finally:
        port.close()
    assert lock_status(path) == 0, "closing the port gives the lock back"


# ---- the globs

def make_dev(tmp_path: Path) -> Path:
    """A fake /dev: ttyUSB0 and ttyUSB1 (one of them behind a by-id link), ttyACM0, a brainbox link to ttyUSB1, a by-id link that leads nowhere, and a file that no pattern names."""
    dev = tmp_path / "dev"
    (dev / "serial" / "by-id").mkdir(parents=True)
    for name in ("ttyUSB0", "ttyUSB1", "ttyACM0", "ttyS0"):
        (dev / name).touch()
    (dev / "serial" / "by-id" / "usb-FTDI_FT232R-if00-port0").symlink_to(dev / "ttyUSB0")
    (dev / "serial" / "by-id" / "usb-gone-if00-port0").symlink_to(dev / "ttyUSB9")
    (dev / "brainbox_3").symlink_to(dev / "ttyUSB1")
    return dev


def test_a_device_with_several_names_is_listed_once_under_the_name_of_the_earliest_glob(tmp_path: Path) -> None:
    dev = make_dev(tmp_path)
    pattern = f"{dev}/serial/by-id/* {dev}/ttyUSB* {dev}/ttyACM*"
    assert candidate_ports(pattern) == [str(dev / "serial/by-id/usb-FTDI_FT232R-if00-port0"), str(dev / "ttyACM0"), str(dev / "ttyUSB1")]
    assert candidate_ports(f"{dev}/ttyUSB* {dev}/serial/by-id/*") == [str(dev / "ttyUSB0"), str(dev / "ttyUSB1")]
    assert candidate_ports(f"{dev}/brainbox_* {dev}/ttyUSB*") == [str(dev / "brainbox_3"), str(dev / "ttyUSB0")]


def test_the_globs_are_separated_by_any_space_and_a_missing_folder_matches_nothing(tmp_path: Path) -> None:
    dev = make_dev(tmp_path)
    assert candidate_ports(f"  {dev}/ttyACM*\t{dev}/nowhere/* {dev}/ttyS*  ") == [str(dev / "ttyACM0"), str(dev / "ttyS0")]


# ---- another program has the port

async def test_a_port_held_by_another_program_is_still_skipped_by_the_probe_among_the_resolved_ones(tmp_path: Path, ptys: Ptys) -> None:
    dev = tmp_path / "dev"
    dev.mkdir()
    held_master, held_path = ptys()
    radio_master, radio_path = ptys()
    (dev / "ttyUSB0").symlink_to(held_path)
    (dev / "ttyUSB1").symlink_to(radio_path)
    (dev / "by-id-held").symlink_to(held_path)
    paths = candidate_ports(f"{dev}/by-id-* {dev}/ttyUSB*")
    assert paths == [str(dev / "by-id-held"), str(dev / "ttyUSB1")]
    frame = encode(b"x")
    feeder = asyncio.create_task(keep_feeding(radio_master, frame))
    with held_by_a_program(held_path):
        found = await probe(paths, 9600, 3.0, lambda data: bool(KissDecoder().feed(data)), skip=())
    feeder.cancel()
    await asyncio.gather(feeder, return_exceptions=True)
    assert found == str(dev / "ttyUSB1")
    assert held_master != radio_master


async def keep_feeding(master: int, data: bytes) -> None:
    """The radio talking on a line: a port that opens late still hears it."""
    while True:
        feed(master, data)
        await asyncio.sleep(0.02)


def is_kiss(data: bytes) -> bool:
    return bool(KissDecoder().feed(data))


async def test_probe_returns_none_when_nothing_is_valid_and_closes_every_port_it_opened(ptys: Ptys) -> None:
    paths = [ptys()[1] for _ in range(2)]
    assert await probe(paths, 9600, 0.05, lambda data: False) is None
    for path in paths:                                        # a port left open would still hold the exclusive lock
        await open_within(path, 2.0)                          # (each port is closed as the probe ends: its thread may take a moment)


async def open_within(path: str, seconds: float) -> None:
    deadline = asyncio.get_running_loop().time() + seconds
    while True:
        again = SerialPort(path)
        try:
            await again.open()
        except SerialError:
            if asyncio.get_running_loop().time() > deadline:
                raise
            await asyncio.sleep(0.05)
            continue
        again.close()
        return


async def test_cancelling_the_probe_closes_every_port(ptys: Ptys) -> None:
    paths = [ptys()[1] for _ in range(3)]
    task = asyncio.get_running_loop().create_task(probe(paths, 9600, None, lambda data: False, nudge=b"\r"))
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    for path in paths:                                        # a port left open would still hold the exclusive lock
        await open_within(path, 2.0)                          # an open that was under way when the probe was cancelled is closed by its own thread, a moment later


async def test_probe_gives_up_on_a_port_that_dies_while_listening_and_goes_on(ptys: Ptys) -> None:
    dying_master, dying = ptys()
    talking_master, talking = ptys()
    feeder = asyncio.get_running_loop().create_task(keep_feeding(talking_master, b"x"))
    loop = asyncio.get_running_loop()
    loop.call_later(0.05, close_pty, dying_master)
    try:
        assert await probe([dying, talking], 9600, 5.0, lambda data: bool(data)) == talking
    finally:
        feeder.cancel()
        await asyncio.gather(feeder, return_exceptions=True)


def comm(child: subprocess.Popen[str]) -> str:
    """The name /proc gives the process."""
    return Path(f"/proc/{child.pid}/comm").read_text(encoding="utf-8").strip()


def test_holders_names_the_other_process_that_has_the_device_open_and_is_empty_once_it_is_gone(ptys: Ptys) -> None:
    _, path = ptys()
    assert holders(path) == [] and held_by(path) == "", "this process holds the slave itself and does not count"
    with held_by_a_program(path) as child:
        assert holders(path) == [child.pid]
        assert held_by(path) == f"held by {comm(child)} (pid {child.pid})"
    assert holders(path) == []


def test_holders_looks_through_a_link_to_the_device(ptys: Ptys, tmp_path: Path) -> None:
    _, path = ptys()
    link = tmp_path / "brainbox_2"
    link.symlink_to(path)
    with held_by_a_program(str(link)) as child:                      # opened through the link, found through the device and through the link
        assert holders(path) == [child.pid] == holders(str(link))


def test_holders_of_a_path_that_is_not_there_is_an_empty_list(tmp_path: Path) -> None:
    assert holders(str(tmp_path / "nothing-here")) == []
    assert holders(str(tmp_path / "dangling")) == []


def test_holders_without_proc_is_an_empty_list(ptys: Ptys, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _, path = ptys()
    with held_by_a_program(path):
        monkeypatch.setattr("neoaprs.serialholders.PROC", str(tmp_path / "no-proc"))
        assert holders(path) == []


def test_a_process_whose_descriptors_cannot_be_read_is_skipped(ptys: Ptys, monkeypatch: pytest.MonkeyPatch) -> None:
    _, path = ptys()
    real_listdir = os.listdir

    def refusing(where: str) -> list[str]:
        if where.endswith("/fd"):
            raise PermissionError(13, "Permission denied", where)
        return real_listdir(where)

    with held_by_a_program(path):
        monkeypatch.setattr(os, "listdir", refusing)
        assert holders(path) == []


async def test_probe_does_not_touch_a_port_another_program_holds_and_finds_the_radio_on_another(ptys: Ptys, caplog: pytest.LogCaptureFixture) -> None:
    rotator_master, rotator = ptys()
    radio_master, radio = ptys()
    feeder = asyncio.get_running_loop().create_task(keep_feeding(radio_master, b"x"))
    told: list[list[str]] = []
    try:
        with held_by_a_program(rotator) as child, caplog.at_level(logging.INFO, logger="neoaprs.serialport"):
            assert await probe([rotator, radio], 9600, 1.0, lambda data: bool(data), nudge=b"\r", nudge_after_sec=0.05, on_open=told.append) == radio
            assert [r.getMessage() for r in caplog.records if r.levelno == logging.INFO and "skipping" in r.getMessage()] == [f"probe: skipping {rotator}: held by {comm(child)} (pid {child.pid})"]
    finally:
        feeder.cancel()
        await asyncio.gather(feeder, return_exceptions=True)
    assert told == [[radio]]
    assert not select.select([rotator_master], [], [], 0)[0], "the nudge never reached the held port"


async def test_probe_opens_a_port_again_once_its_holder_is_gone(ptys: Ptys) -> None:
    master, path = ptys()
    feeder = asyncio.get_running_loop().create_task(keep_feeding(master, b"x"))
    try:
        with held_by_a_program(path):
            assert await probe([path], 9600, 0.1, lambda data: bool(data)) is None
        assert await probe([path], 9600, 1.0, lambda data: bool(data)) == path
    finally:
        feeder.cancel()
        await asyncio.gather(feeder, return_exceptions=True)


async def test_probe_never_touches_a_path_in_skip_whether_it_is_named_by_the_device_or_by_a_link(ptys: Ptys, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    excluded_master, excluded = ptys()
    radio_master, radio = ptys()
    link = tmp_path / "brainbox_2"
    link.symlink_to(excluded)
    feeder = asyncio.get_running_loop().create_task(keep_feeding(radio_master, b"x"))
    try:
        for listed, skipped in ((str(link), excluded), (excluded, str(link)), (excluded, excluded)):
            told: list[list[str]] = []
            caplog.clear()
            with caplog.at_level(logging.INFO, logger="neoaprs.serialport"):
                assert await probe([listed, radio], 9600, 1.0, lambda data: bool(data), nudge=b"\r", nudge_after_sec=0.05, on_open=told.append, skip=[skipped]) == radio
            assert told == [[radio]]
            assert [r.levelno for r in caplog.records if f"skipping {listed}" in r.getMessage()] == [logging.INFO]
    finally:
        feeder.cancel()
        await asyncio.gather(feeder, return_exceptions=True)
    assert not select.select([excluded_master], [], [], 0)[0], "nothing was written to a port on the skip list"


async def test_probe_with_every_path_skipped_finds_nothing_at_once(ptys: Ptys) -> None:
    _, path = ptys()
    assert await asyncio.wait_for(probe([path], 9600, None, lambda data: True, skip=[path]), 1.0) is None
