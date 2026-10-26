"""The daemon's paths that the tests with a real process do not reach (neoaprs/daemon.py), in the test's own process: the command to run after an update handed back, the exit codes of `main`, a log that
cannot be reopened, a data folder that cannot be made private or is held by another program, and a database that fails under the daemon (a migration that breaks midway, a file another writer holds):
the daemon ends with 2 and says why, the file is as it was or at the step before, the copy is in backup/, and the next start finds it usable."""
import io
import logging
import logging.handlers
import os
import sqlite3
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from neoaprs import daemon as entry
from neoaprs import migrations as migrations_module
from neoaprs import selfreplace
from neoaprs.controller import Controller
from neoaprs.daemon import DATABASE_UNUSABLE, _LogFile, _private_data_dir, _take_the_data_folder, main, setup_logging
from neoaprs.instancelock import InstanceLock
from neoaprs.migrations import MIGRATIONS, SCHEMA_VERSION
from neoaprs.store import DB_NAME
from tests.support.daemonrun import InProcess, arguments, log_text, signals_restored as signals_restored  # noqa: F401
from tests.support.migrated import opened
from tests.test_migrations import NEXT, broken, raw, v_next, version_three, with_steps
from tests.support.clock import FixedClock


@pytest.fixture
def umask_kept() -> Iterator[None]:
    old = os.umask(0o077)
    yield
    os.umask(old)


# ---- main
def fake_run(code: int = 0, then: Callable[[list[list[str]]], None] | None = None, error: BaseException | None = None) -> Callable[..., object]:
    seen: list[object] = []

    async def run(args: object, after: list[list[str]] | None = None) -> int:
        seen.append(args)
        if error is not None:
            raise error
        if then is not None and after is not None:
            then(after)
        return code

    run.seen = seen                                  # type: ignore[attr-defined]
    return run


def test_the_environment_asks_for_debug_like_the_flag(monkeypatch: pytest.MonkeyPatch, umask_kept: None) -> None:
    run = fake_run(7)
    monkeypatch.setattr(entry, "run", run)
    monkeypatch.setenv("NEOAPRS_DEBUG", "1")
    assert main(["--data", "x"]) == 7
    assert run.seen[0].debug is True                    # type: ignore[attr-defined]
    monkeypatch.delenv("NEOAPRS_DEBUG")
    assert main(["--data", "x"]) == 7 and run.seen[1].debug is False      # type: ignore[attr-defined]


def test_ctrl_c_in_the_middle_of_the_run_ends_the_program_with_0(monkeypatch: pytest.MonkeyPatch, umask_kept: None) -> None:
    monkeypatch.setattr(entry, "run", fake_run(error=KeyboardInterrupt()))
    assert main(["--data", "x"]) == 0


def test_a_command_to_run_after_the_daemon_ends_is_run_in_its_place_and_the_program_ends_with_1_when_it_comes_back(monkeypatch: pytest.MonkeyPatch, umask_kept: None) -> None:
    monkeypatch.setattr(entry, "run", fake_run(0, then=lambda after: after.append(["/new/NeoAPRS.AppImage", "--data", "x"])))
    started: list[list[str]] = []
    monkeypatch.setattr(selfreplace, "reexec", started.append)
    assert main(["--data", "x"]) == 1
    assert started == [["/new/NeoAPRS.AppImage", "--data", "x"]]


async def test_run_hands_back_the_command_the_controller_was_given_to_run_after_the_daemon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, signals_restored: None) -> None:
    async def serve(controller: Controller, stop: object, log: logging.Logger) -> int:
        controller.reexec = ["/new/NeoAPRS.AppImage", "--data", str(tmp_path)]
        return 0

    monkeypatch.setattr(entry, "_serve", serve)
    after: list[list[str]] = []
    assert await entry.run(arguments(tmp_path / "data"), after) == 0
    assert after == [["/new/NeoAPRS.AppImage", "--data", str(tmp_path)]]


# ---- the data folder, the log
def test_a_data_folder_that_cannot_be_made_private_is_told_and_the_daemon_goes_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    def refused(path: object, mode: int) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "chmod", refused)
    with caplog.at_level(logging.WARNING):
        _private_data_dir(tmp_path, logging.getLogger("neoaprs.test"))
    assert [r.getMessage() for r in caplog.records] == [f"the data directory {tmp_path} could not be made private ([Errno 1] Operation not permitted): other users of this computer may be able to read the database"]


def test_a_second_daemon_is_refused_without_a_console_to_say_it_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    held = InstanceLock(tmp_path)
    held.acquire()
    try:
        monkeypatch.setattr(sys, "stderr", None)
        assert _take_the_data_folder(tmp_path) is None
    finally:
        held.release()
    monkeypatch.undo()
    assert _take_the_data_folder(tmp_path) is not None


def test_a_stderr_that_is_not_a_text_stream_gets_the_warnings_as_they_are(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pipe = io.StringIO()
    monkeypatch.setattr(sys, "stderr", pipe)
    setup_logging(tmp_path, False)
    logging.getLogger("neoaprs.test").warning("a warning")
    logging.getLogger("neoaprs.test").info("not for the journal")
    assert "WARNING  a warning" in pipe.getvalue() and "not for the journal" not in pipe.getvalue()
    assert "not for the journal" in (tmp_path / "neoaprs.log").read_text(encoding="utf-8")


def test_a_rollover_that_fails_before_the_file_is_closed_leaves_the_log_open_and_is_tried_again_later(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handler = _LogFile(tmp_path / "x.log", maxBytes=100, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("neoaprs.test.rollover")
    logger.propagate, logger.level = False, logging.INFO
    logger.addHandler(handler)

    def refused(self: object) -> None:
        raise PermissionError(13, "in use")

    monkeypatch.setattr(logging.handlers.RotatingFileHandler, "doRollover", refused)
    for n in range(10):
        logger.info("line %d %s", n, "x" * 20)
    assert handler.stream is not None and (tmp_path / "x.log").read_text(encoding="utf-8").count("line ") == 10
    assert handler._not_before > 0
    handler.close()
    logger.removeHandler(handler)


# ---- the database under the daemon
@pytest.mark.expects_errors
async def test_a_migration_that_breaks_midway_ends_the_daemon_with_2_and_the_file_and_its_copy_are_usable_by_the_next_start(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, signals_restored: None) -> None:
    data = tmp_path / "data"
    data.mkdir()
    s = opened(data / DB_NAME)
    s.db.execute("INSERT INTO settings (key, value) VALUES ('station/call', 'OH2GBA')")
    s.close()
    with_steps(monkeypatch, v_next, broken)
    first = InProcess(data)
    assert await first.ended() == DATABASE_UNUSABLE
    log = log_text(data)
    assert "the database could not be used" in log and "the disk is full" in log
    db = raw(data / DB_NAME)
    assert db.execute("PRAGMA user_version").fetchone()[0] == NEXT, "the step that went through stays; the one that broke is rolled back"
    assert db.execute("SELECT value FROM settings").fetchall() == [("OH2GBA",)]
    assert "half" not in {r[0] for r in db.execute("SELECT name FROM sqlite_master")}
    db.close()
    assert len(list((data / "backup").glob(f"premigrate-v{SCHEMA_VERSION}-to-v{NEXT + 1}-*.sqlite"))) == 1

    def fixed(db: sqlite3.Connection) -> None:
        db.execute("CREATE TABLE fixed (x INTEGER) STRICT")

    monkeypatch.setattr(migrations_module, "MIGRATIONS", [*MIGRATIONS, v_next, fixed])
    monkeypatch.setattr(migrations_module, "SCHEMA_VERSION", NEXT + 1)
    second = InProcess(data)
    assert await second.running()
    assert await second.stop() == 0
    db = raw(data / DB_NAME)
    assert db.execute("PRAGMA user_version").fetchone()[0] == NEXT + 1 and db.execute("SELECT value FROM settings").fetchall() == [("OH2GBA",)]
    assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    db.close()


@pytest.mark.expects_errors
async def test_a_file_that_another_writer_holds_ends_the_daemon_with_2_untouched_and_it_starts_once_the_writer_is_gone(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, signals_restored: None) -> None:
    data = tmp_path / "data"
    data.mkdir()
    version_three(data / DB_NAME, FixedClock())
    holder = raw(data / DB_NAME)
    holder.execute("BEGIN IMMEDIATE")
    real = entry.Controller
    monkeypatch.setattr(entry, "Controller", lambda *args, **kwargs: real(*args, **{**kwargs, "busy_ms": 20}))     # (the daemon waits seconds for a writer; the test does not)
    try:
        first = InProcess(data)
        assert await first.ended() == DATABASE_UNUSABLE
        assert "locked" in log_text(data)
        assert raw(data / DB_NAME).execute("PRAGMA user_version").fetchone() == (3,)
    finally:
        holder.execute("ROLLBACK")
        holder.close()
    second = InProcess(data)
    assert await second.running()
    assert await second.stop() == 0
    assert raw(data / DB_NAME).execute("PRAGMA user_version").fetchone() == (SCHEMA_VERSION,)
