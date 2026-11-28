"""Tests for the AIS receiver connection (neoaprs/aisfeed.py): line cutting within the limits (1024
bytes a line, 200 lines a second), reading to the end, and the no-devices switch.
"""

import asyncio

import pytest

from neoaprs import aisfeed, nodevices
from neoaprs.layerthing import AIS_LINE_MAX, AIS_LINES_PER_SEC
from tests.support.fakeais import ais_receiver


def test_bytes_are_cut_into_lines_and_a_line_is_kept_until_its_end_comes() -> None:
    lines = aisfeed.Lines()
    assert lines.feed(b"!AIVDM,1\r\n!AIV", 0.0) == ["!AIVDM,1"]
    assert lines.feed(b"DM,2\n\n  \n", 0.0) == ["!AIVDM,2"]
    assert lines.feed("!AIVDM,\xc3\xa5\n".encode("latin-1"), 0.0) == ["!AIVDM,��"], (
        "what is not ASCII is not NMEA, and does not break the reading"
    )


def test_a_line_longer_than_1024_bytes_is_passed_over_to_its_end_in_whatever_pieces_it_comes() -> None:
    lines = aisfeed.Lines()
    assert lines.feed(b"a" * (AIS_LINE_MAX + 1) + b"\nok1\n", 0.0) == ["ok1"], "complete in one piece"
    assert lines.feed(b"c" * AIS_LINE_MAX + b"\n", 0.0) == ["c" * AIS_LINE_MAX], "the longest that is read"
    assert (
        lines.feed(b"b" * 800, 0.0) == []
        and lines.feed(b"b" * 800, 0.0) == []
        and lines.feed(b"b" * 800 + b"\nok2\nok", 0.0) == ["ok2"]
    ), "in three"
    assert lines.feed(b"3\n", 0.0) == ["ok3"]
    assert lines.passed_over == 2


def test_a_stream_without_a_line_end_never_grows_the_memory_beyond_one_line() -> None:
    lines = aisfeed.Lines()
    for _ in range(1000):
        assert lines.feed(b"x" * 4096, 0.0) == []
    assert len(lines._rest) <= AIS_LINE_MAX


def test_at_most_200_lines_a_second_are_read_and_the_rest_of_that_second_is_passed_over() -> None:
    lines = aisfeed.Lines()
    flood = b"".join(b"line%d\n" % n for n in range(1000))
    assert len(lines.feed(flood, 5.2)) == AIS_LINES_PER_SEC
    assert lines.feed(b"more\n", 5.9) == [], "still the same second"
    assert lines.feed(b"next\n", 6.0) == ["next"], "the next second begins again"
    assert lines.passed_over == 800 + 1


async def test_the_connection_is_read_to_its_end_and_each_batch_is_handed_on() -> None:
    receiver = await ais_receiver()
    reader, writer = await aisfeed.connect("127.0.0.1", receiver.port)
    got: list[str] = []
    reading = asyncio.create_task(aisfeed.read(reader, aisfeed.Lines(), lambda batch: got.extend(batch), lambda: 0.0))
    await receiver.until_connected()
    receiver.send("one", "two")
    receiver.drop()
    await asyncio.wait_for(reading, 30)
    writer.close()
    assert got == ["one", "two"]


async def test_a_refused_connection_is_an_os_error() -> None:
    receiver = await ais_receiver()
    port = receiver.port
    await receiver.stop()
    with pytest.raises(OSError):
        await aisfeed.connect("127.0.0.1", port)


@pytest.fixture
def under_the_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    """The no-devices switch is on in this test's own process too (tests/conftest.py lifts it for
    every test that does not ask for a fixture of this name)."""
    monkeypatch.setenv(nodevices.ENV, "1")


async def test_under_the_no_devices_switch_a_receiver_that_is_not_this_computer_is_refused_as_a_server_that_is_not_there(
    monkeypatch: pytest.MonkeyPatch, under_the_switch: None
) -> None:
    opened: list[object] = []
    monkeypatch.setattr(asyncio, "open_connection", lambda *a, **k: opened.append(a))
    with pytest.raises(ConnectionRefusedError):
        await aisfeed.connect("192.0.2.1", 10110)
    assert opened == []


async def test_under_the_no_devices_switch_a_port_a_real_modem_may_listen_on_is_refused_even_on_this_computer(
    monkeypatch: pytest.MonkeyPatch, under_the_switch: None
) -> None:
    opened: list[object] = []
    monkeypatch.setattr(asyncio, "open_connection", lambda *a, **k: opened.append(a))
    with pytest.raises(ConnectionRefusedError):
        await aisfeed.connect("127.0.0.1", 10110)
    assert opened == []
