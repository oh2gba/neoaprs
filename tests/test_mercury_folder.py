"""The radio's own folder of its Mercury modem (neoaprs/mercuryclaims.py `take_folder`, mercurymodem.py): the modem of radio 2 keeps its configuration, its process id, the speaker's pipes and what the program writes
where it runs in `radios/2/` of the data folder, and what a NeoAPRS of one HF radio left in the data folder is taken over at its first start: the configuration moved, the process id of a Mercury it left running
honoured once (that Mercury is ended, and the file is the radio's from then on), the speaker's old pipes removed; another radio's modem leaves them for radio 2. A modem made without a folder keeps today's shape, its
files in the data folder. The program is the tests' stand-in (tests/support/fakemercury.py)."""
import os
import signal
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs import mercuryclaims, mercurystale
from neoaprs.claims import Claims
from neoaprs.config import Config
from neoaprs.mercuryclaims import RADIOS_FOLDER, radio_folder
from neoaprs.mercurymodem import INI_FILE, PID_FILE, Mercury, take_folder
from neoaprs.mercuryspeaker import CAPTURE_FIFO, PLAYBACK_FIFO
from neoaprs.radiotype import HF_ID
from neoaprs.source import Backoff
from tests.support import fakemercury
from tests.support.env import Env, until_started
from tests.support.fakemercury import of_radio
from tests.test_mercury_modem import HF, QUICK, _alive, _ports_of_this_test, stopped  # noqa: F401 (the fixture keeps two tests from taking the same ports)


def old_modem(data: Path) -> Mercury:
    """The modem as a NeoAPRS of one HF radio made it: its files in the data folder."""
    m = Mercury(data, finder=fakemercury.program, backoff=QUICK, control_backoff=Backoff([0.05, 0.05]))
    m.ports = lambda: []
    return m


def with_radio_five(config: Config) -> Config:
    """The settings with radio 5 an HF radio of its own beside radio 2: its own sound card and VOX (a modem reads its own radio's, mercurymodem.own_choice)."""
    hf = config.radio(HF_ID)
    assert hf is not None
    five = replace(hf, id=5, position=5, settings={**hf.settings, "sound_card": "plughw:2,0", "keying": "vox"})
    return replace(config, radios=(*config.radios, five))


def radio_modem(data: Path, holder: int = HF_ID) -> Mercury:
    m = Mercury(data, finder=fakemercury.program, backoff=QUICK, control_backoff=Backoff([0.05, 0.05]), **of_radio(data, holder))
    m.ports = lambda: []
    return m


def test_a_radios_folder_is_its_id_under_radios_of_the_data_folder_and_a_modem_without_one_is_in_the_data_folder(tmp_path: Path) -> None:
    assert radio_folder(tmp_path, 2) == tmp_path / RADIOS_FOLDER / "2" == tmp_path / "radios" / "2"
    assert radio_modem(tmp_path, 5).home == tmp_path / "radios" / "5" and old_modem(tmp_path).home == tmp_path
    assert radio_modem(tmp_path)._audio.capture.parent == tmp_path / "radios" / "2", "the speaker's pipes are the radio's too"
    take_folder(tmp_path, tmp_path)
    assert list(tmp_path.iterdir()) == [], "a modem whose folder is the data folder takes nothing over and makes nothing"


@pytest.mark.skipif(sys.platform == "win32", reason="the command line of another process is not read on Windows: a pid there is ended only when its program file is mercury.exe")
async def test_what_an_older_neoaprs_left_in_the_data_folder_moves_to_radio_2s_folder_and_its_mercury_is_ended_once(tmp_path: Path) -> None:
    first = old_modem(tmp_path)
    await first.start(HF)
    await until_started(lambda: first.state == "running")
    orphan = first.pid
    first._program._process = None                                        # (the older daemon crashed: its program lives on, its files stay in the data folder)
    await first.stop()
    for name in (CAPTURE_FIFO, PLAYBACK_FIFO):
        (tmp_path / name).write_text("")                                   # (the speaker's pipes of an older run)
    assert _alive(orphan) and (tmp_path / PID_FILE).read_text() == str(orphan) and (tmp_path / INI_FILE).exists()
    m = radio_modem(tmp_path)
    try:
        await m.start(HF)
        await until_started(lambda: not _alive(orphan))
        await until_started(lambda: m.state == "running")
        assert [p.name for p in tmp_path.iterdir()] == [RADIOS_FOLDER], "nothing of the modem is left in the data folder"
        assert (m.home / PID_FILE).read_text() == str(m.pid) and "busy_detect = true" in (m.home / INI_FILE).read_text()
        await m.stop()
        await m.start(replace(HF, mercury_keying="vox"))
        await until_started(lambda: m.state == "running")
        assert [p.name for p in tmp_path.iterdir()] == [RADIOS_FOLDER] and "tx_leadin_ms" in (m.home / INI_FILE).read_text(), "the next start is the radio's folder's alone"
    finally:
        await stopped(m)
        if _alive(orphan):
            assert orphan is not None
            os.kill(orphan, signal.SIGTERM)


def test_an_old_process_id_beside_one_of_the_radios_own_is_honoured_where_it_is_and_the_radios_is_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ended: list[tuple[Path, str, Path]] = []
    monkeypatch.setattr(mercuryclaims, "end_stale", lambda pid_file, ini, program: ended.append((pid_file, pid_file.read_text(), ini)) or pid_file.unlink())
    home = radio_folder(tmp_path, HF_ID)
    home.mkdir(parents=True)
    (home / PID_FILE).write_text("4321")
    (home / INI_FILE).write_text("; the radio's own\n")
    (tmp_path / PID_FILE).write_text("1234")
    (tmp_path / INI_FILE).write_text("; an older NeoAPRS's\n")
    take_folder(tmp_path, home)
    assert ended == [(tmp_path / PID_FILE, "1234", tmp_path / INI_FILE)], "the older one's Mercury is ended, as the one it ran with the data folder's configuration: its file names it once"
    assert (home / PID_FILE).read_text() == "4321" and (home / INI_FILE).read_text() == "; the radio's own\n" and list(tmp_path.iterdir()) == [tmp_path / RADIOS_FOLDER]
    take_folder(tmp_path, home)
    assert len(ended) == 1, "honoured once: the data folder names nothing any more"


async def test_another_radios_modem_leaves_what_an_older_neoaprs_left_in_the_data_folder_for_radio_2(tmp_path: Path) -> None:
    (tmp_path / INI_FILE).write_text("; an older NeoAPRS's\n")
    (tmp_path / PID_FILE).write_text(str(os.getpid()))                     # (an id that is never a Mercury: nothing of the test's is ended)
    m = radio_modem(tmp_path, 5)
    try:
        await m.start(HF)
        await until_started(lambda: m.state == "running")
        assert (tmp_path / INI_FILE).read_text() == "; an older NeoAPRS's\n" and (tmp_path / PID_FILE).read_text() == str(os.getpid()), "radio 2's to take over, not radio 5's"
        assert (m.home / PID_FILE).read_text() == str(m.pid) and m.home == radio_folder(tmp_path, 5)
    finally:
        await stopped(m)
    take_folder(tmp_path, radio_folder(tmp_path, 7), inherit=False)
    assert (tmp_path / INI_FILE).exists() and radio_folder(tmp_path, 7).is_dir()


@pytest.mark.skipif(sys.platform == "win32", reason="no named pipes: the speaker runs on the default sound devices")
async def test_the_speakers_pipes_follow_the_folder_the_modem_is_given_after_it_was_made(tmp_path: Path) -> None:
    m = old_modem(tmp_path)
    m.folder = radio_folder(tmp_path, HF_ID)
    m.folder.mkdir(parents=True)
    assert await m._speaker_audio() is not None
    assert m._audio.capture == m.home / CAPTURE_FIFO and m._audio.playback == m.home / PLAYBACK_FIFO and m._audio.capture.exists()
    assert not (tmp_path / CAPTURE_FIFO).exists(), "nothing of the speaker in the data folder"


async def test_a_radios_folder_that_cannot_be_made_is_the_problem_and_tried_again_after_the_back_off(tmp_path: Path) -> None:
    (tmp_path / RADIOS_FOLDER).write_text("not a folder")
    m = radio_modem(tmp_path)
    await m.start(HF)
    try:
        assert m.state == "waiting" and m.reason == "not_started" and m.problem.startswith("Mercury's folder could not be made in the data folder: ") and m.starts == 0
        (tmp_path / RADIOS_FOLDER).unlink()
        await until_started(lambda: m.state == "running")
        assert m.home.is_dir() and m.starts == 1
    finally:
        await stopped(m)


async def test_two_radios_modems_keep_their_files_apart(tmp_path: Path) -> None:
    claims = Claims()
    two = Mercury(tmp_path, finder=fakemercury.program, backoff=QUICK, control_backoff=Backoff([0.05, 0.05]), **of_radio(tmp_path, 2, claims))
    five = Mercury(tmp_path, finder=fakemercury.program, backoff=QUICK, control_backoff=Backoff([0.05, 0.05]), **of_radio(tmp_path, 5, claims))
    two.ports = five.ports = lambda: []
    try:
        await two.start(HF)
        await five.start(with_radio_five(HF))
        await until_started(lambda: two.running and five.running)
        assert (two.home / PID_FILE).read_text() == str(two.pid) and (five.home / PID_FILE).read_text() == str(five.pid) and two.pid != five.pid
        assert "tx_leadin_ms" not in (two.home / INI_FILE).read_text() and "tx_leadin_ms" in (five.home / INI_FILE).read_text(), "each its own configuration (VOX has the lead-in)"
        assert (two.sound_card, five.sound_card) == ("plughw:1,0", "plughw:2,0"), "each on its own radio's sound card"
    finally:
        await stopped(two)
        await stopped(five)


@pytest.mark.skipif(sys.platform == "win32", reason="the command line of another process is not read on Windows: there the time the process was made tells (tests/test_mercury_pidfile.py)")
async def test_a_radios_old_file_naming_another_radios_live_mercury_ends_nothing(tmp_path: Path) -> None:
    """After a power cut both radios' files survive, and radio 2's fresh Mercury may get the id in radio 5's old file: radio 5's start leaves radio 2's Mercury alone, which runs with its own configuration."""
    claims = Claims()
    two = Mercury(tmp_path, finder=fakemercury.program, backoff=QUICK, control_backoff=Backoff([0.05, 0.05]), **of_radio(tmp_path, 2, claims))
    five = Mercury(tmp_path, finder=fakemercury.program, backoff=QUICK, control_backoff=Backoff([0.05, 0.05]), **of_radio(tmp_path, 5, claims))
    two.ports = five.ports = lambda: []
    try:
        await two.start(HF)
        await until_started(lambda: two.running)
        live = two.pid
        five.home.mkdir(parents=True)
        (five.home / PID_FILE).write_text(str(live))                     # (radio 5's file of before the power cut, whose id radio 2's Mercury has now)
        await five.start(with_radio_five(HF))
        await until_started(lambda: five.running)
        assert two.running and two.pid == live and _alive(live) and two.starts == 1, "radio 2's Mercury runs on, never ended by radio 5's start"
        assert (five.home / PID_FILE).read_text() == str(five.pid)
    finally:
        await stopped(two)
        await stopped(five)


@pytest.mark.skipif(sys.platform == "win32", reason="the command line of another process is not read on Windows: a pid there is ended only when its program file is the radio's")
async def test_a_mercury_a_killed_daemon_left_for_a_radio_that_is_off_or_gone_now_is_ended_at_the_next_start(tmp_path: Path) -> None:
    """Mercury.stop never runs for a radio that is not started, and nothing ends a Mercury when its daemon dies: the next daemon's start ends it (mercuryclaims.end_left_behind), whether its radio is off, removed
    or no radio of the settings at all, so that it does not hold the sound card and the keying line."""
    first = radio_modem(tmp_path, 5)
    await first.start(HF)
    await until_started(lambda: first.state == "running")
    orphan = first.pid
    assert orphan is not None
    first._program._process = None                                        # (the daemon was killed: its program lives on, the pid file stays)
    await first.stop()
    try:
        assert _alive(orphan) and (first.home / PID_FILE).read_text() == str(orphan)
        e = Env(tmp_path, operator=False)                                   # (the next daemon: its settings have no radio 5)
        await e.start()
        try:
            assert e.ctl.config.radio(5) is None and mercurystale.gone(orphan) and not (first.home / PID_FILE).exists(), "ended before any radio started, and its file consumed"
        finally:
            await e.stop()
    finally:
        if _alive(orphan) and not mercurystale.gone(orphan):
            os.kill(orphan, signal.SIGTERM)
