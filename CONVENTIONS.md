# NeoAPRS conventions

Read this before writing a module. `docs/ARCHITECTURE.md` has the layers and the limits, `tests/README.md` the tests, `ROADMAP.md` what is planned.

## Language and tools

- Python 3.13, the venv in `.venv` of a development clone, made by `uv sync --frozen` (`docs/MANUAL.md`, "Development"; `pyproject.toml` and `uv.lock` are the only list of dependencies). Standard library first. A mature library
  is fine where the standard library would mean writing a driver: **pyserial** (`serial`) for the radio's serial port, only in the adapters layer (`neoaprs/serialport.py`), and nowhere in the foundation or domain
  layers (`tests/test_architecture.py` holds it). Tornado only in `neoaprs/web/` (the page's server). Nothing else from pip at runtime, with two exceptions: the desktop app's toolkits (the extra `app` of `pyproject.toml`: PySide6 with its web engine on Linux and macOS, pywebview, pystray and Pillow on Windows), only in the shells of `neoaprs/desktop/` (`qtshell.py`, `qtwindow.py`, `winshell.py`: `tests/test_architecture.py` holds it), so that everything else of the app runs and is tested without them; and pydantic v2 (with its `pydantic_core`, `annotated-types` and
  `typing-inspection`) in the wire modules of `neoaprs/web/` and nowhere else; the rest of `neoaprs/` stays pydantic-free: the core knows nothing of the wire format. Why pydantic: a model for every command and message gives validation
  with an error that names the field, one place where the format is written down, and the JSON Schema and TypeScript types for the page, generated.
- No `aprslib`, no `pyserial-asyncio`: the APRS parser is ours (`neoaprs/ax25.py`, `neoaprs/aprs*.py`, tested against captured frames) and the serial line is read and written by a thread of its own that hands the bytes to the one event loop with `call_soon_threadsafe` (`neoaprs/serialport.py`; no descriptor goes to the loop, which Windows could not wait for).
- SQL is written in one place: a statement is a function of a connection in `neoaprs/storesql.py` (and the `*sql.py` modules beside it: `packetsql.py`, `messagesql.py`), run by the database thread (`await db.read(fn)`, `await db.write(fn)`, `db.write_nowait(fn)`);
  no other module imports `sqlite3`, calls `execute` or holds a string that begins like a statement (`tests/test_architecture.py`).
- Layers, size limits (module 400 lines, class 300, function 60, complexity 12): `docs/ARCHITECTURE.md`; `tests/test_architecture.py` and `tests/test_size_ratchet.py` hold them.
- NeoAPRS is an installable package with one command: `pip install` or `uv tool install` of the wheel gives `neoaprs` (and `neoaprsw`, the same without a console window, for Windows, and `neoaprs-app`, the desktop app, with the extra `app`); `python -m neoaprs` is the same command, and in a clone the venv has it
  installed in editable mode (`uv sync`). Everything the program needs at run time is inside `neoaprs/`: the page's server `neoaprs/web/`, the built page `neoaprs/page/` (committed, package data; built by `scripts/build-page`), the commands `neoaprs/cli/`, the desktop app `neoaprs/desktop/` (with its icon), the unit template
  `neoaprs/cli/neoaprs.service`. The version is `VERSION` in `neoaprs/__init__.py` and nowhere else (`pyproject.toml` reads it); the build backend is hatchling.
- Type hints on every function. `mypy --strict` must pass on `neoaprs/` and `tests/support/`.
- pytest, `asyncio_mode = auto`: an `async def test_*` just works. Run `.venv/bin/pytest -q tests/test_x.py`.
- Comments and documents say what a thing is and why, in a sentence or two, in plain sentences. No docstring boilerplate that repeats the name, and no history: no review finding by number, no branch or release as the reason for code, no "was X, now Y".
- Names: modules and functions `snake_case`, classes `CapWords`. Fields in `snake_case`. Enums are `enum.Enum` classes with the names in CAPS: `Source.State.CONNECTED`.

## Time

- Every `datetime` is timezone-aware UTC. `neoaprs.clock.utcnow()` gives one. Never `datetime.now()` without `tz=UTC`, never naive datetimes.
- Anything that depends on the time takes a clock: `Clock = Callable[[], datetime]`, default `utcnow`. Tests pass a fixed clock (`tests/support/clock.py` has `FixedClock`).
- Durations are `int` seconds or `float` seconds in names ending `_sec`. Milliseconds appear only inside asyncio sleeps and in the busy time of SQLite (`busy_ms`).

## Signals, tasks, sources

- `neoaprs.signal.Signal[[Args]]` is the only observer: `s = Signal[[Packet]]()`, `s.connect(fn)`, `s.emit(packet)`; synchronous, exceptions in a handler are logged and do not stop the others. Signals are connected in one place, the composition root (`neoaprs/wiring.py`).
- A timer is an asyncio task with `await asyncio.sleep(...)` in a loop. Every task a part starts is in a `TaskSet` (`neoaprs/tasks.py`) and is cancelled when the part stops; the Controller's `tasks` is the one for the parts it makes.
- Every feed of packets derives from `neoaprs.source.Source` (read it): `async def start()`, `async def stop()`, `async def reconnect()`, `async def send(data) -> bool`, `describe() -> str`; inside: `_set_state`, `_set_problem`, `_note`, `_saw`, `_reject`,
  `self.stats`, `self.now()`. Reconnection uses `neoaprs.source.Backoff`. A source never raises out of its tasks: it logs, sets `WAITING` with the problem text, and retries.

## Tests

- What tests are built from lives in `tests/support/` (the `Env` daemon, the clock, the guards, the storage helpers; see `tests/README.md`), not in test modules. Fixtures in `tests/fixtures`, `tests/support/files.py` has `fixture_bytes(name)`.
- Four guards run for every test (`tests/support/guards.py`): nothing leaves this machine (HOME, the XDG folders and Windows's USERPROFILE, LOCALAPPDATA and APPDATA are empty; a connect, a datagram or a name lookup to an address that is not on the loopback fails the test), no task and no database thread is left
  running, no ERROR is logged unless the test says `@pytest.mark.expects_errors`, and no test opens the operator's radio (`/dev/brainbox_*`, `/dev/tty*`: the tests use a fake radio on the loopback, `tests/support/fakeradio.py`, and a pseudo-terminal pair, `tests/support/ptyline.py`, where a device file is the point). Markers `unit` / `integration` / `e2e` / `safety` are given automatically (`pytest -m unit`).
- The radio is never opened by a test: the tests use a fake radio, a TCP server on the loopback (`tests/support/fakeradio.py`), which works on every system, and, for the few tests about a device file, a pseudo-terminal pair (`os.openpty`, POSIX only, marked `posix_only`); the live port is tried by the operator from a terminal.
- Property tests (Hypothesis, from the `dev` group of `pyproject.toml`) live in `tests/test_properties_*.py`; the docstring of each says the property in one line. `HYPOTHESIS_PROFILE=ci` (the default) is derandomised and keeps no example database, so a run is
  reproducible; `HYPOTHESIS_PROFILE=dev` explores with a random seed and 2000 examples.
- A signal's handler cannot fail a test: `Signal` logs and goes on. A test that checks what a handler sees collects the faults in a list and asserts on it afterwards.

## Documents, scripts, units

- A document gets a row in `docs/README.md` and is changed in the same commit as the code it describes. A release gets a section in `CHANGELOG.md`, newest first, grouped by area, with no commit hashes; what is planned is in `ROADMAP.md` and nowhere else.
- A script in `scripts/` starts with a comment (or a docstring) that says what it is for, answers `--help` without doing anything else, and has a row in the table "Scripts" of `docs/MANUAL.md`; a unit (`neoaprs/cli/neoaprs.service`, the template that `neoaprs service install` fills in) has a row in `systemd/README.md`. A script that only calls a command of the package (`scripts/install.sh`, `scripts/neoaprs-db`, `scripts/replay`, `scripts/capture`, `scripts/fetch-basemap`) stays a thin wrapper: the code is in `neoaprs/cli/`. `tests/test_hygiene.py` and `tests/test_docs.py` fail when one is missing.
- The repository is public at https://github.com/oh2gba/neoaprs (GPL-3.0-or-later); commits go to `master`.

## Environment variables

Every `NEOAPRS_*` variable the code, the scripts, the units or the tests use is in this table, and only here (the manual and the other documents point to it). `tests/test_docs.py` fails for a name used anywhere that is not in the table, and for a name in the table that nothing uses.

| variable | read by | what it does |
|---|---|---|
| `NEOAPRS_DATA_DIR` | the daemon and the commands | the data folder of `neoaprs` and `python -m neoaprs` (the daemon, `service`, `db`, `map`, `doctor`), else `~/.local/share/neoaprs` (`$XDG_DATA_HOME/neoaprs`) on Linux, `%LOCALAPPDATA%\NeoAPRS` on Windows, `~/Library/Application Support/NeoAPRS` on macOS; `--data` wins. The scripts use `./data` |
| `NEOAPRS_DEBUG` | the daemon | `1` is `--debug`: more is logged |
| `NEOAPRS_SERIAL_PATTERN` | the daemon, `capture` and the tests | the globs the search for the radio listens to (space-separated, like `serial/pattern`); when set and not empty it is used instead of `serial/pattern` and the default, but not instead of a port that was named. `tests/conftest.py` sets it to a pattern that matches nothing, so that no daemon or command a test starts opens a serial device of the machine; a test of the search gives its own pattern (a folder of pseudo-terminals) or clears the variable |
| `NEOAPRS_UPDATE_CHECK` | the daemon (`neoaprs/services/updatecheck.py`), the smoke scripts and the workflows | `0` switches the daily update check off for this run, whatever `update/check` says; `tests/conftest.py` sets it for every test and every process a test starts, and `ProcessGuard` refuses a `neoaprs` that a test starts without it, so that no test asks the version page on the internet. `scripts/smoke.py`, `scripts/smoke-appimage`, `scripts/screenshots.py` and the workflows set it too |
| `NEOAPRS_OUT` | `ui/vite.config.ts`, `scripts/build-page`, `tests/test_page_build.py` | the folder Vite builds the page into: `scripts/build-page` points it at `neoaprs/page/`, the page test at a temporary folder to compare with it; else `ui/dist` |
| `NEOAPRS_PYTHON` | `scripts/check`, `scripts/dup-check`, `scripts/neoaprs-db`, `scripts/replay`, `scripts/capture`, `scripts/fetch-basemap` | the Python they run, else the uv venv |
| `NEOAPRS_JSCPD` | `scripts/dup-check` | the command that stands in for jscpd (`tests/test_dup_check.py` gives it a stand-in that writes a report); else the jscpd of `ui/node_modules` |
| `NEOAPRS_TEST_WORKERS`, `NEOAPRS_TEST_WORKERS_MAX` | `scripts/check` | how many tests the pytest stage runs side by side: the cores, at most 12; 0 is one after the other |
| `NEOAPRS_VALIDATE_OUT`, `NEOAPRS_VALIDATE_RAISE` | `neoaprs/web/outbound.py` | `1` checks every message the daemon sends to a page against the `Message` union of `neoaprs/web/protocol.py` (and the `state` and `patch` of a topic against the type of its value); a mismatch is logged once for each message type, and with `NEOAPRS_VALIDATE_RAISE=1` it raises. `tests/conftest.py` sets both to `1`; `NEOAPRS_VALIDATE_OUT=0 pytest` runs the tests the way production runs |
| `NEOAPRS_FROM`, `NEOAPRS_TEXT`, `NEOAPRS_AT`, `NEOAPRS_MSG_ID` | the command of `messages/alert_command` (`neoaprs/services/alerts.py`) | set by the daemon for the command it runs when a message to us arrives, not read: the sender's call, the text, when it was heard (ISO 8601, UTC) and the message id (empty when the message had none) |
| `NEOAPRS_WHEEL_URL` | `packaging/install.sh.in` (the rendered `install.sh`) | the address of the wheel the install script installs, in place of the one of its release; the release workflow's test of the script gives it the wheel it has just built |
| `NEOAPRS_BUILD_CACHE` | `scripts/build-appimage` | the folder the pinned build tools (CPython, appimagetool, the AppImage runtime) are kept in once downloaded; else `~/.cache/neoaprs-build` |
| `NEOAPRS_TEST_ORDER` | `tests/conftest.py` | `reverse` or `shuffle[:SEED]` runs the test files in another order, to find a test that depends on an earlier one |

## Data

All of it in the one database `neoaprs.sqlite` in the data folder (`docs/MANUAL.md`, "Run it"): the settings as rows, every packet, and the stations (a cache of the station book that the daemon rebuilds from the packets and a later migration may drop). Only the log of the program is a file, `neoaprs.log`, rotated (20 MB, five files).

## The database schema

- A schema change is a new function at the end of `MIGRATIONS` in `neoaprs/migrations.py`, never an edit of one that has been released: `tests/test_migrations.py::test_an_applied_migration_is_frozen` fails on an edited migration. Everything a migration needs is inside it or frozen beside it (the SQL as text, not a constant that other code uses).
- Tables of data the operator would mourn are `STRICT`, with `CHECK`s for what the program can produce (and only that) and a name on each CHECK so that the error says which. Rows go in through a gate that makes the types right.
- A migration that rebuilds a table runs in the transaction `open_database` opens, repairs what the new table would refuse (keeping the original in the row), checks that every row came through, and raises on any doubt: the rollback leaves the old table. Every step is a transaction of its own, and a file that holds anything is copied whole into `backup/` before the first step runs.
- Every migration gets a test with a database of the version before it, seeded with realistic rows and compared with a database made fresh.
