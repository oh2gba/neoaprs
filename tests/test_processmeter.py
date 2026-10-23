"""What the daemon costs the machine (neoaprs/web/processmeter.py): the CPU share as a pure function of two samples, the meter that takes them, and the three fields of the status over the socket."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.support.env import Env
from neoaprs.web import processmeter, winmemory
from neoaprs.web.processmeter import MIN_SPAN_SEC, ProcessMeter, Sample, cpu_percent, cpu_seconds, resident_mb


# ---- the share of the CPU ------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("before, after, percent", [
    (Sample(0.0, 0.0), Sample(10.0, 0.03), 0.3), (Sample(5.0, 1.0), Sample(15.0, 6.0), 50.0), (Sample(0.0, 0.0), Sample(10.0, 10.0), 100.0), (Sample(0.0, 0.0), Sample(10.0, 25.0), 250.0),
    (Sample(0.0, 0.0), Sample(10.0, 0.0), 0.0), (Sample(0.0, 0.0), Sample(3.0, 0.0449), 1.5), (Sample(0.0, 0.0), Sample(3.0, 0.0451), 1.5)])
def test_the_share_is_the_cpu_time_over_the_wall_time_to_a_tenth(before: Sample, after: Sample, percent: float) -> None:
    assert cpu_percent(before, after) == percent


def test_a_span_that_is_none_or_backwards_and_a_cpu_clock_that_went_back_are_zero() -> None:
    assert cpu_percent(Sample(5.0, 1.0), Sample(5.0, 2.0)) == 0.0
    assert cpu_percent(Sample(5.0, 1.0), Sample(4.0, 2.0)) == 0.0
    assert cpu_percent(Sample(0.0, 2.0), Sample(10.0, 1.0)) == 0.0


# ---- the meter -----------------------------------------------------------------------------------------------------------------------------------

class Dials:
    """A clock and a CPU time the test turns."""

    def __init__(self) -> None:
        self.at, self.cpu = 100.0, 7.0

    def meter(self) -> ProcessMeter:
        return ProcessMeter(lambda: self.at, lambda: self.cpu, lambda: 42.25)


def test_the_meter_counts_from_the_previous_sample_and_tells_the_memory() -> None:
    dials = Dials()
    meter = dials.meter()
    dials.at, dials.cpu = 110.0, 7.5
    assert meter.sample() == (5.0, 42.25)
    dials.at, dials.cpu = 120.0, 7.6
    assert meter.sample()[0] == 1.0, "the span is the one since the sample before, not since the start"


def test_samples_closer_than_a_second_share_the_reading_and_keep_the_baseline() -> None:
    dials = Dials()
    meter = dials.meter()
    dials.at, dials.cpu = 110.0, 8.0
    assert meter.sample()[0] == 10.0
    dials.at, dials.cpu = 110.0 + MIN_SPAN_SEC / 2, 8.4
    assert meter.sample()[0] == 10.0, "a page that opens a moment later is told the reading that was taken"
    dials.at, dials.cpu = 120.0, 9.0
    assert meter.sample()[0] == 10.0, "the next reading counts from the last one that was taken (1 s of CPU in 10 s)"


def test_the_first_sample_before_a_second_has_passed_is_zero() -> None:
    dials = Dials()
    meter = dials.meter()
    dials.at, dials.cpu = 100.2, 7.1
    assert meter.sample()[0] == 0.0


def test_this_process_has_cpu_time_and_a_resident_set() -> None:
    first = cpu_seconds()
    sum(range(200_000))
    assert cpu_seconds() >= first > 0
    memory = resident_mb()
    assert memory is not None and 5.0 < memory < 4096.0


def test_a_meter_whose_system_does_not_say_has_no_memory_and_still_the_share() -> None:
    meter = ProcessMeter(lambda: 100.0, lambda: 7.0, lambda: None)
    assert meter.sample() == (0.0, None)


# ---- the other systems

@pytest.mark.skipif(sys.platform == "win32", reason="Windows has it")
def test_the_working_set_is_not_there_to_read_off_windows() -> None:
    assert winmemory.working_set_mb() is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_on_windows_the_working_set_is_read_from_psapi() -> None:
    memory = winmemory.working_set_mb()
    assert memory is not None and 5.0 < memory < 4096.0


def test_windows_where_the_call_cannot_be_made_has_no_memory_and_no_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def refused(*args: object, **kwargs: object) -> None:
        raise OSError("no such library")

    monkeypatch.setattr(winmemory, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(winmemory.ctypes, "WinDLL", refused, raising=False)        # (the failed call, whether this is Windows or not)
    assert winmemory.working_set_mb() is None


def test_the_meter_asks_windows_for_the_working_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(processmeter, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(processmeter, "working_set_mb", lambda: 31.5)
    assert resident_mb() == 31.5
    monkeypatch.setattr(processmeter, "working_set_mb", lambda: None)
    assert resident_mb() is None


def test_macos_reads_the_peak_in_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = pytest.importorskip("resource")
    monkeypatch.setattr(processmeter, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(resource, "getrusage", lambda who: SimpleNamespace(ru_maxrss=64 * 1024 * 1024))
    assert resident_mb() == 64.0


def test_a_system_without_proc_has_no_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_proc(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("no /proc")

    monkeypatch.setattr(processmeter, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(processmeter, "open", no_proc, raising=False)
    assert resident_mb() is None


# ---- over the socket -----------------------------------------------------------------------------------------------------------------------------

async def test_the_status_over_the_socket_has_the_share_the_memory_and_the_uptime(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    first = await page.expect("status")
    assert first["uptime_sec"] == 0 and isinstance(first["cpu_percent"], float) and first["cpu_percent"] >= 0.0
    assert isinstance(first["rss_mb"], float) and first["rss_mb"] > 5.0
    assert round(first["cpu_percent"], 1) == first["cpu_percent"] and round(first["rss_mb"], 1) == first["rss_mb"]
    e.now.advance(3700)
    await page.send({"cmd": "status"})
    await page.until(lambda: len(page.of("status")) == 2)
    assert page.of("status")[-1]["uptime_sec"] == 3700
