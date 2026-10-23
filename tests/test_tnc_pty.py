"""The search for the radio among device files, and a port that another program holds (Linux: /proc), on pseudo-terminal pairs: the real thing behind the globs of `serial/pattern`. The search is made on
Linux only (neoaprs/serialprobe.py); on Windows and macOS the radio is the port that was named or remembered, which the other test files cover with the fake radio. The whole file is POSIX-only."""
import asyncio
import select
from dataclasses import replace
from pathlib import Path

from neoaprs import serialport
from neoaprs.source import Backoff, Source
from neoaprs.tnc import ENTER_KISS, Tnc
from tests.support.env import Env, until
from tests.support.ptyline import Ptys, close_pty, feed, held_by_a_program, heard, posix_only
from tests.test_silent import QUICK
from tests.test_tnc import MONITOR_LINE, SETTLE, kiss_of, nothing_runs, tiny_backoff, ui_frame
from tests.test_wiring import frame_bytes

pytestmark = posix_only


async def hear(master: int, count: int = 1, timeout_sec: float = 2.0) -> bytes:
    """What the port has written, read without blocking the loop that the TNC runs on."""
    return await asyncio.to_thread(heard, master, count, timeout_sec)


async def drain(master: int) -> None:
    while True:
        await hear(master, 4096, 0.01)
        await asyncio.sleep(0.005)


# ---- the probe

async def make_links(tmp_path: Path, ptys: Ptys, count: int) -> tuple[list[int], str]:
    masters = []
    for n in range(1, count + 1):
        master, path = ptys()
        (tmp_path / f"port_{n}").symlink_to(path)
        masters.append(master)
    return masters, str(tmp_path / "port_*")


async def keep_feeding(master: int, data: bytes) -> None:
    while True:
        feed(master, data)
        await asyncio.sleep(0.03)


async def test_the_probe_picks_the_port_that_sends_a_kiss_frame(ptys: Ptys, tmp_path: Path) -> None:
    (_, second), pattern = await make_links(tmp_path, ptys, 2)
    feeder = asyncio.create_task(keep_feeding(second, kiss_of(ui_frame())))
    tnc = Tnc(pattern=pattern, probe_seconds=5.0, backoff=tiny_backoff())
    try:
        await tnc.start()
        assert tnc.state is Source.State.CONNECTED and tnc.path == str(tmp_path / "port_2")
        assert tnc.describe().startswith(f"{tmp_path / 'port_2'} at 9600")
        await until(lambda: tnc.stats.packets >= 1)
    finally:
        feeder.cancel()
        await tnc.stop()


async def test_the_probe_skips_a_port_it_cannot_open_and_takes_a_tnc_in_command_mode(ptys: Ptys, tmp_path: Path) -> None:
    (first, second), pattern = await make_links(tmp_path, ptys, 2)
    import serial  # type: ignore[import-untyped]
    held = serial.Serial(str(tmp_path / "port_1"), exclusive=True)           # another program has the first port
    feeder = asyncio.create_task(keep_feeding(second, MONITOR_LINE))
    tnc = Tnc(pattern=pattern, backoff=tiny_backoff(), settle_sec=SETTLE)
    try:
        await tnc.start()
        assert tnc.path == str(tmp_path / "port_2")
        assert await hear(second, len(ENTER_KISS), 10.0) == ENTER_KISS       # (a long wait: the machine may be busy with other tests)
    finally:
        feeder.cancel()
        await tnc.stop()
        held.close()
    assert first


async def test_a_search_that_ran_out_of_time_is_waiting_and_tries_again(ptys: Ptys, tmp_path: Path) -> None:
    _, pattern = await make_links(tmp_path, ptys, 2)
    tnc = Tnc(pattern=pattern, probe_seconds=0.05, backoff=tiny_backoff())
    try:
        await tnc.start()
        assert tnc.state is Source.State.WAITING
        assert tnc.problem == f"no port delivers KISS frames (tried {tmp_path / 'port_1'}, {tmp_path / 'port_2'})"
        await until(lambda: any("trying again" in line for line in tnc.lines) and tnc.line_count > 3)
    finally:
        await tnc.stop()


async def test_a_search_with_no_port_left_is_waiting_at_once(ptys: Ptys, tmp_path: Path) -> None:
    masters, pattern = await make_links(tmp_path, ptys, 2)
    tnc = Tnc(pattern=pattern, backoff=tiny_backoff())                 # no time limit
    loop = asyncio.get_running_loop()
    for master in masters:
        loop.call_later(0.1, close_pty, master)                        # both cables are pulled during the search
    try:
        await asyncio.wait_for(tnc.start(), 2.0)
        assert tnc.state is Source.State.WAITING and tnc.problem.startswith("no port delivers KISS frames")
    finally:
        await tnc.stop()


async def test_the_search_listens_for_as_long_as_it_takes_and_says_where(ptys: Ptys, tmp_path: Path) -> None:
    (first, second, third), pattern = await make_links(tmp_path, ptys, 3)
    import serial  # type: ignore[import-untyped]
    held = serial.Serial(str(tmp_path / "port_2"), exclusive=True)           # another program has the second port
    loop = asyncio.get_running_loop()
    loop.call_later(0.5, feed, third, kiss_of(ui_frame()))                    # the radio is quiet for half a second; the first port stays silent
    tnc = Tnc(pattern=pattern, backoff=tiny_backoff())
    began = loop.time()
    starting = asyncio.create_task(tnc.start())
    try:
        want = f"listening on {tmp_path / 'port_1'}, {tmp_path / 'port_3'} for the radio"
        await until(lambda: tnc.state is Source.State.CONNECTING and tnc.describe() == want)
        assert any(want in line for line in tnc.lines)
        await asyncio.wait_for(starting, 3.0)
        assert loop.time() - began >= 0.45
        assert tnc.state is Source.State.CONNECTED and tnc.path == str(tmp_path / "port_3") and "for the radio" not in tnc.describe()
        feed(third, kiss_of(ui_frame()))
        await until(lambda: tnc.stats.packets == 1)
    finally:
        await tnc.stop()
        held.close()
        await asyncio.gather(starting, return_exceptions=True)
    assert first and second


async def test_the_search_sends_a_carriage_return_and_takes_a_tnc_that_answers_with_the_prompt(ptys: Ptys, tmp_path: Path) -> None:
    (first, second), pattern = await make_links(tmp_path, ptys, 2)
    tnc = Tnc(pattern=pattern, probe_nudge_sec=0.1, backoff=tiny_backoff(), settle_sec=SETTLE)
    starting = asyncio.create_task(tnc.start())
    try:
        assert await hear(first, 1) == b"\r" and await hear(second, 1) == b"\r"      # every candidate was nudged
        feed(second, b"cmd:")                                                          # only the second one is a TNC in command mode
        await asyncio.wait_for(starting, 3.0)
        assert tnc.path == str(tmp_path / "port_2")
        feed(second, b"cmd:")                                                          # the search has used up the first prompt; the opened port hears the next one
        assert await hear(second, len(ENTER_KISS)) == ENTER_KISS
    finally:
        await tnc.stop()
        await asyncio.gather(starting, return_exceptions=True)


async def test_stop_during_the_search_ends_it_and_leaves_nothing_running(ptys: Ptys, tmp_path: Path) -> None:
    masters, pattern = await make_links(tmp_path, ptys, 2)
    tnc = Tnc(pattern=pattern, backoff=Backoff([30.0]))                # no time limit, a radio that says nothing
    starting = asyncio.create_task(tnc.start())
    await until(lambda: bool(tnc.describe().startswith("listening on")))
    await tnc.stop()
    await asyncio.wait_for(starting, 2.0)
    assert tnc.state is Source.State.STOPPED and len(tnc._tasks) == 0 and tnc.path == "" and "for the radio" not in tnc.describe()
    for n in (1, 2):                                                   # both ports were closed
        again = serialport.SerialPort(str(tmp_path / f"port_{n}"))
        await again.open()
        again.close()
    assert masters


async def test_stop_during_a_search_that_the_retry_started_ends_it_too(ptys: Ptys, tmp_path: Path) -> None:
    (master,), pattern = await make_links(tmp_path, ptys, 1)
    tnc = Tnc(pattern=pattern, probe_seconds=0.05, backoff=Backoff([0.05]))
    await tnc.start()
    assert tnc.state is Source.State.WAITING
    await until(lambda: tnc.state is Source.State.CONNECTING)
    await tnc.stop()
    assert tnc.state is Source.State.STOPPED and len(tnc._tasks) == 0 and master


async def test_no_port_that_matches_the_pattern_is_waiting_too(tmp_path: Path) -> None:
    tnc = Tnc(pattern=str(tmp_path / "none_*"), backoff=tiny_backoff())
    try:
        await tnc.start()
        assert tnc.state is Source.State.WAITING and tnc.problem == f"no port matches {tmp_path / 'none_*'}"
    finally:
        await tnc.stop()


async def test_a_named_port_that_cannot_be_opened_is_followed_by_a_probe_and_then_by_the_named_port_again(ptys: Ptys, tmp_path: Path) -> None:
    (second,), pattern = await make_links(tmp_path, ptys, 1)
    feeder = asyncio.create_task(keep_feeding(second, kiss_of(ui_frame())))
    named = tmp_path / "remembered"
    tnc = Tnc(str(named), pattern=pattern, probe_seconds=5.0, backoff=tiny_backoff())
    try:
        await tnc.start()
        assert tnc.state is Source.State.WAITING and "No such file or directory" in tnc.problem
        await until(lambda: tnc.state is Source.State.CONNECTED)
        assert tnc.path == str(tmp_path / "port_1"), "the next attempt listened to the ports of the pattern"
        (tmp_path / "port_1").unlink()
        close_pty(second)                                        # the cable is pulled; the named port is back by the time the next attempt comes
        master, path = ptys()
        named.symlink_to(path)
        await until(lambda: tnc.state is Source.State.CONNECTED and tnc.path == str(named))
        assert master
    finally:
        feeder.cancel()
        await tnc.stop()


async def test_a_named_port_that_another_program_holds_is_waiting_with_the_holder_and_is_opened_once_it_is_gone(ptys: Ptys) -> None:
    master, path = ptys()
    tnc = Tnc(path, backoff=tiny_backoff(), fallback_probe=False)
    try:
        with held_by_a_program(path) as child:
            await tnc.start()
            name = open(f"/proc/{child.pid}/comm").read().strip()
            assert tnc.state is Source.State.WAITING and tnc.stats.opens == 0
            assert tnc.problem == f"{path}: held by {name} (pid {child.pid})"
            await asyncio.sleep(0.3)                                 # (several attempts later)
            assert tnc.state is Source.State.WAITING and tnc.stats.opens == 0 and not select.select([master], [], [], 0)[0], "the held port is not opened, nothing is written to it"
        await until(lambda: tnc.state is Source.State.CONNECTED)
        assert tnc.path == path and tnc.stats.opens == 1
    finally:
        await tnc.stop()


async def test_the_search_leaves_a_held_port_and_a_skipped_port_alone(ptys: Ptys, tmp_path: Path) -> None:
    (held_master, skipped_master, radio), pattern = await make_links(tmp_path, ptys, 3)
    feeder = asyncio.create_task(keep_feeding(radio, kiss_of(ui_frame())))
    tnc = Tnc(pattern=pattern, probe_seconds=5.0, backoff=tiny_backoff(), probe_nudge_sec=0.05, skip=(str(tmp_path / "port_2"),))
    try:
        with held_by_a_program(str(tmp_path / "port_1")):
            await tnc.start()
            assert tnc.state is Source.State.CONNECTED and tnc.path == str(tmp_path / "port_3")
        assert not select.select([held_master, skipped_master], [], [], 0)[0], "no carriage return went to either"
    finally:
        feeder.cancel()
        await tnc.stop()


async def test_a_search_with_every_port_skipped_or_held_says_so(ptys: Ptys, tmp_path: Path) -> None:
    _, pattern = await make_links(tmp_path, ptys, 2)
    tnc = Tnc(pattern=pattern, probe_seconds=5.0, backoff=tiny_backoff(), skip=(str(tmp_path / "port_1"),))
    try:
        with held_by_a_program(str(tmp_path / "port_2")):
            await asyncio.wait_for(tnc.start(), 2.0)
            assert tnc.state is Source.State.WAITING
            assert tnc.problem.startswith("no port could be listened to") and str(tmp_path / "port_1") in tnc.problem
    finally:
        await tnc.stop()


async def test_a_named_port_that_cannot_be_opened_stays_waiting_when_the_probe_is_off(ptys: Ptys, tmp_path: Path) -> None:
    (second,), pattern = await make_links(tmp_path, ptys, 1)
    feeder = asyncio.create_task(keep_feeding(second, kiss_of(ui_frame())))
    tnc = Tnc(str(tmp_path / "remembered"), pattern=pattern, backoff=tiny_backoff(), fallback_probe=False)
    try:
        await tnc.start()
        await asyncio.sleep(0.4)
        assert tnc.state is Source.State.WAITING and tnc.stats.opens == 0 and "No such file or directory" in tnc.problem
    finally:
        feeder.cancel()
        await tnc.stop()




async def test_a_reopen_that_fails_falls_to_the_search_for_the_radio(ptys: Ptys, tmp_path: Path) -> None:
    link = tmp_path / "radio"
    quiet, path = ptys()
    link.symlink_to(path)
    other, other_path = ptys()
    (tmp_path / "other_1").symlink_to(other_path)
    tnc = Tnc(str(link), pattern=str(tmp_path / "other_*"), probe_seconds=5.0, probe_nudge_sec=99.0, settle_sec=SETTLE, backoff=tiny_backoff(), probe_sec=0.05, **{**QUICK, "answer_sec": 0.0, "reply_sec": 0.0})
    await tnc.start()
    feeder = asyncio.create_task(drain(quiet))
    talker = feeder
    try:
        await until(lambda: tnc.state is Source.State.SILENT)
        link.unlink()                                                # the device is gone
        talker = asyncio.create_task(keep_feeding(other, kiss_of(ui_frame())))     # (the radio is behind another port now)
        await until(lambda: tnc.state is Source.State.CONNECTED and tnc.path == str(tmp_path / "other_1"), 5.0)
        assert tnc.stats.port_reopens == 1 and tnc.watchdog.probes == 0
        assert any("No such file" in line for line in tnc.lines)
    finally:
        feeder.cancel()
        talker.cancel()
        await asyncio.gather(feeder, talker, return_exceptions=True)
        await tnc.stop()
    nothing_runs(tnc)




async def keep_feeding_frame(master: int) -> None:
    while True:
        feed(master, frame_bytes("OH2PRB"))
        await asyncio.sleep(0.03)


async def test_the_search_listens_to_the_pattern_of_the_settings_and_a_new_pattern_restarts_it(tmp_path: Path, search_pattern_from_settings: None) -> None:
    e = Env(tmp_path, radio=False)
    e.ctl.pattern_override = ""                                    # (the Env gives its folder as the pattern of the run; here the settings decide)
    first_master, first = e.new_pty("first_1")
    second_master, second = e.new_pty("second_1")
    await e.ctl.open_database()
    assert await e.ctl.store.put_settings({"serial/pattern": f"{e.ports}/first_*"})
    feeders = [asyncio.create_task(keep_feeding_frame(first_master)), asyncio.create_task(keep_feeding_frame(second_master))]
    try:
        await e.start(connected=False)
        await until(lambda: e.tnc.state is Source.State.CONNECTED and e.tnc.path == first)
        assert e.tnc.pattern == f"{e.ports}/first_*"
        assert await e.ctl.save_config(replace(e.ctl.config, serial_port="", serial_last_port="", serial_pattern=f"{e.ports}/second_*"))
        await until(lambda: e.tnc.state is Source.State.CONNECTED and e.tnc.path == second)
        assert e.tnc.pattern == f"{e.ports}/second_*"
        await e.stop()
    finally:
        for feeder in feeders:
            feeder.cancel()
        await asyncio.gather(*feeders, return_exceptions=True)


async def test_the_port_the_search_found_is_stored_and_tried_first_next_time(tmp_path: Path) -> None:
    e = Env(tmp_path, radio=False)
    master, link = e.new_pty("probe_1")
    feeder = asyncio.create_task(keep_feeding_frame(master))
    try:
        await e.start(connected=False)
        await e.until_connected()
        assert e.tnc.path == link
        async def stored() -> str | None:
            return await e.ctl.store.setting("serial/last_port")
        for _ in range(100):
            if await stored() == link:
                break
            await asyncio.sleep(0.02)
        assert await stored() == link and e.ctl.config.serial_last_port == link and await e.ctl.store.setting("serial/port") is None
        await e.stop()
        again = Env(tmp_path, radio=False, ports=e.ports)                 # (the same "/dev")
        await again.start(connected=False)
        await until(lambda: again.tnc.state is Source.State.CONNECTED)
        assert again.tnc.port == link, "the remembered port is the one the Tnc is started with"
        assert again.tnc.path == link and await again.ctl.store.setting_rev("serial/last_port") == 1, "found at the remembered path: nothing to store again"
        await again.stop()
    finally:
        feeder.cancel()
        await asyncio.gather(feeder, return_exceptions=True)


async def test_a_remembered_port_that_is_gone_is_followed_by_the_search_and_the_new_one_is_stored(tmp_path: Path) -> None:
    e = Env(tmp_path, radio=False)
    master, link = e.new_pty("probe_1")
    await e.start(connected=False)
    await e.ctl.store.put_setting("serial/last_port", str(e.ports / "gone"))
    await e.stop()
    again = Env(tmp_path, radio=False, ports=e.ports)
    feeder = asyncio.create_task(keep_feeding_frame(master))
    try:
        await again.start(connected=False)
        await until(lambda: again.tnc.port == str(e.ports / "gone") and again.tnc.stats.opens == 0 and again.tnc.state is Source.State.WAITING)
        await until(lambda: again.tnc.state is Source.State.CONNECTED)
        assert again.tnc.path == link
        for _ in range(100):
            if await again.ctl.store.setting("serial/last_port") == link:
                break
            await asyncio.sleep(0.02)
        assert await again.ctl.store.setting("serial/last_port") == link
        await again.stop()
    finally:
        feeder.cancel()
        await asyncio.gather(feeder, return_exceptions=True)


async def test_a_device_file_that_vanishes_and_comes_back_is_waiting_with_a_reason_and_the_port_is_reopened(ptys: Ptys, tmp_path: Path) -> None:
    link = tmp_path / "radio"
    tnc = Tnc(str(link), backoff=tiny_backoff(), fallback_probe=False)
    await tnc.start()
    try:
        assert tnc.state is Source.State.WAITING and "No such file or directory" in tnc.problem
        master, path = ptys()
        link.symlink_to(path)                                    # the cable is plugged in
        await until(lambda: tnc.state is Source.State.CONNECTED)
        assert tnc.stats.opens == 1 and tnc.problem == ""
        close_pty(master)                                        # and pulled out
        await until(lambda: tnc.state is Source.State.WAITING)
        assert tnc.problem and tnc.last_error and "lost" in tnc.last_error
        link.unlink()
        master, path = ptys()
        link.symlink_to(path)
        await until(lambda: tnc.state is Source.State.CONNECTED)
        assert tnc.stats.opens == 2
        feed(master, kiss_of(ui_frame()))
        await until(lambda: tnc.stats.packets == 1)
    finally:
        await tnc.stop()
    assert tnc.state is Source.State.STOPPED
