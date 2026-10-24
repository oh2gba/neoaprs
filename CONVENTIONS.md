# NeoAPRS conventions

Read this before writing a module. `docs/ARCHITECTURE.md` has the layers, `docs/development.md` how it is built and checked, `tests/README.md` the tests, `ROADMAP.md` what is planned.

## Language and tools

- Python 3.13, the venv in `.venv` of a development clone, made by `uv sync --frozen` (`docs/development.md`, "Set up and run"). `pyproject.toml` and `uv.lock`
  are the only list of dependencies. Standard library first.
- A mature library is fine where the standard library would mean writing a driver. These are the exceptions, and where each lives (`tests/test_architecture.py`
  holds the first four to it; the list is in `docs/ARCHITECTURE.md`):
  - **pyserial** (`serial`) for the radio's serial port, only in the adapters layer (`neoaprs/serialport.py`);
  - **Tornado** for the page's server, only in `neoaprs/web/`;
  - **pydantic** v2 (with its `pydantic_core`, `annotated-types` and `typing-inspection`) in the wire modules of `neoaprs/web/` and nowhere else; the rest of
    `neoaprs/` stays pydantic-free, because the core knows nothing of the wire format. Why: a model for every command and message gives validation with an error
    that names the field, one place where the format is written down, and the JSON Schema and TypeScript types for the page, generated;
  - **cryptography** for the certificates of the secure connection, only in `neoaprs/web/tls.py`;
  - the desktop app's toolkits (the extra `app` of `pyproject.toml`: PySide6 with its web engine on Linux and macOS, pywebview, pystray and Pillow on Windows),
    only in the shells of `neoaprs/desktop/`, so that everything else of the app runs and is tested without them.
- No `aprslib`, no `pyserial-asyncio`. The APRS parser is ours (`neoaprs/ax25.py`, `neoaprs/aprs*.py`, tested against captured frames). The serial line is read
  and written by a thread of its own that hands the bytes to the one event loop with `call_soon_threadsafe` (`neoaprs/serialport.py`); no descriptor goes to the
  loop, which Windows could not wait for.
- SQL is written in one place: a statement is a function of a connection in `neoaprs/storesql.py` (and the `*sql.py` modules beside it), run by the database
  thread (`await db.read(fn)`, `await db.write(fn)`, `db.write_nowait(fn)`). No other module imports `sqlite3`, calls `execute` or holds a string that begins
  like a statement (`tests/test_architecture.py`).
- The layers are in `docs/ARCHITECTURE.md`. The size limits are here, and `tests/test_size_ratchet.py` holds them: a module of `neoaprs/` has at most **400
  lines**, a class **300**, a function **60**, and a function a cyclomatic complexity of at most **12**.
- NeoAPRS is an installable package with one command: `pip install` or `uv tool install` of the wheel gives `neoaprs`, and `neoaprsw` (the same without a
  console window, for Windows) and `neoaprs-app` (the desktop app, with the extra `app`). `python -m neoaprs` is the same command, and in a clone the venv has
  it installed in editable mode.
- Everything the program needs at run time is inside `neoaprs/`, among it the built page `neoaprs/page/` (committed, package data, built by
  `scripts/build-page`) and the unit template `neoaprs/cli/neoaprs.service`. The version is `VERSION` in `neoaprs/__init__.py` and nowhere else
  (`pyproject.toml` reads it); the build backend is hatchling.
- Type hints on every function. `mypy --strict` must pass on `neoaprs/` and `tests/support/`.
- pytest, `asyncio_mode = auto`: an `async def test_*` just works. Run `.venv/bin/pytest -q tests/test_x.py`.
- Comments and documents say what a thing is and why, in a sentence or two, in plain sentences. No docstring boilerplate that repeats the name, and no history:
  no review finding by number, no branch or release as the reason for code, no "was X, now Y".
- Names: modules and functions `snake_case`, classes `CapWords`. Fields in `snake_case`. Enums are `enum.Enum` classes with the names in CAPS: `Source.State.CONNECTED`.

## Words

One word for one thing, in the code, the page and the documents. The wire and database names are not renamed, because that is a protocol change.

| word | means | not to be confused with |
|---|---|---|
| **settings**, **config** | what the operator sets: the rows of the table `settings`, the immutable value `Config` (`neoaprs/config.py`), the topic `config` and the command `set_config`; the page's Settings tab and the Beacon tab show them. "Settings" in text, `config` in code | `Store.settings()` is the rows, `Config` the value made of them |
| **timeout**, **hide** | how long a station stays on the map after its last position. The operator reads "timeout". The policy constant says `HIDE_AFTER_MIN`; it is fixed, there is no setting and no per-station value | the page's `aging`, which is how a marker dims on the way to it |
| **radio**, **TNC**, **rig** | the **radio** is what transmits and what the operator talks of ("the radio is silent", the footer, the radio status). The **TNC** is the box that speaks KISS: `Tnc` is the feed of packets, the topic is `tnc`, the setting `tnc/profile` says what kind it is. `Radio` is the small Protocol that the services need of the `Tnc`. A **rig** is a radio that rigctld can read the frequency of (`rigstatus`, "Rigctld") | the TNC of a radio built in (TH-D7) and a separate TNC |
| **status** | three things, each with its own word: the **status** or **status report** is the APRS packet that says what we are doing (`station/status`, `status/*`, `status_now`); the **radio status** is the state of the TNC link (the topic `tnc`, the Settings tab, the footer's "Radio: ..."); the **`status` message** is what the daemon tells every page every 10 seconds (cost of the process, the newest version) | |
| **path**, **route**, **chain** | the **path** is the digipeaters we ask for in a packet we send (`beacon/path`, a station's path, `via`). The **route** is what a received packet went by (`neoaprs/route.py`, `last_route`, "via OH2RCH-2"). The **chain** is the hops of a message of ours that were heard back (`neoaprs/chain.py`, "the chain of digipeaters") | |
| **email gateway** | the APRS-IS station `EMAIL-2`. The page has an **Email tab** that sends mail through it and keeps the addresses used before as its address book. The gateway's own **shortcuts** (names for addresses) are not used by the page | |
| **sender** | the station a message or bulletin is from. The part that spaces our own frames is `Sender` (`neoaprs/services/sender.py`), the frame scheduler | |
| **heard**, **overheard** | a packet we received is **heard**. A message to another station that we only received is **overheard** | |

## Time

- Every `datetime` is timezone-aware UTC. `neoaprs.clock.utcnow()` gives one. Never `datetime.now()` without `tz=UTC`, never naive datetimes.
- Anything that depends on the time takes a clock: `Clock = Callable[[], datetime]`, default `utcnow`. Tests pass a fixed clock (`tests/support/clock.py` has `FixedClock`).
- Durations are `int` seconds or `float` seconds in names ending `_sec`. Milliseconds appear only inside asyncio sleeps and in the busy time of SQLite (`busy_ms`).

## Numbers that are not settings

A number the program decides (how long things are kept, the keep-alive time, the attempts of a message) is a named constant in the module that owns it, and the
ones that several layers need are in `neoaprs/policy.py`. A number the page checks a value against is written once, in the daemon, and reaches the page through
`scripts/gen-protocol.py` (`LIMITS` in `ui/src/protocol/lists.ts`), never typed again in the page. A rule that is code, not a number, gets conformance vectors
that both the daemon and the page are tested against (`ui/src/protocol/vectors.json`).

## Signals, tasks, sources

- `neoaprs.signal.Signal[[Args]]` is the only observer: `s = Signal[[Packet]]()`, `s.connect(fn)`, `s.emit(packet)`; synchronous, exceptions in a handler are
  logged and do not stop the others. Signals are connected in one place, the composition root (`neoaprs/wiring.py`).
- A timer is an asyncio task with `await asyncio.sleep(...)` in a loop. Every task a part starts is in a `TaskSet` (`neoaprs/tasks.py`, given the logger that
  tells a task's failure) and is cancelled when the part stops. The Controller's `tasks` is the one for the parts it makes.
- Every feed of packets derives from `neoaprs.source.Source` (read it): `async def start()`, `async def stop()`, `async def send(data) -> bool`,
  `describe() -> str`; inside: `_set_state`, `_set_problem`, `_note`, `_saw`, `_reject`, `self.stats`, `self.now()`.
- Reconnection uses `neoaprs.source.Backoff`. A source never raises out of its tasks: it logs, sets `WAITING` with the problem text, and retries.

## Errors and the wire

- A refusal that the operator can cause carries a stable code and its values: `CodedError(text, code, **params)` (`neoaprs/coded.py`), and for a setting
  `SettingError` (`neoaprs/config.py`), which adds the key. The English `text` is for the log and for a code the page has no sentence for; the page goes by
  `cmd`, `key` and `code`, never by parsing the words (`docs/development.md`, "The wire").
- Every word the page says to a person is a message of the catalogue (`ui/src/i18n/en/`), asked for by `t("area.thing.detail", { values })`: never written into a
  template or a `lib/` function, never a sentence glued from pieces (a plural is `{ one, other }`, a number or a name a `{value}`), and the page never decides
  by the words of a text (`docs/development.md`, "Translations").
- Wire rows are built from the domain objects through their models in `neoaprs/web/*wire.py`. A field is added to the model and the object only, and the
  golden-file test of `tests/test_wire_rows.py` shows the JSON.

## The page's controls

- One height for every text button, input and select of a form or a toolbar: `--control-h` (32 px, `ui/src/styles/tokens.css`), set once on `.btn` and `.input` in `controls.css`. A button is `.btn` (secondary) or `.btn primary` (filled; `danger` for the second press of
  a destructive one); only `.btn.small` (`--control-h-small`, 24 px) is lower, and only inside a list row, a bubble or a line of text. An icon-only button is `IconButton` (`.xbtn`, 32 px; 28 px in the rows of the Stations table).
- No stylesheet but `controls.css` gives a `.btn` a height, padding or font size, and no component gives a button an inline style (`ui/src/styles/buttons.test.ts` holds both); a new kind of button is a class that changes colour or width, never size.

## Tests

- What tests are built from lives in `tests/support/` (the `Env` daemon, the clock, the guards, the storage helpers), not in test modules. Fixtures are in
  `tests/fixtures`; `tests/support/files.py` has `fixture_bytes(name)`. `tests/README.md` describes the suite.
- Four guards run for every test (`tests/support/guards.py`): nothing leaves this machine, no task and no database thread is left running, no ERROR is logged
  unless the test says `@pytest.mark.expects_errors`, and no test opens the operator's radio. Markers `unit` / `integration` / `safety` are given automatically
  (`pytest -m unit`).
- A test waits for a condition (`until`), never for a time; what is a time is named (`idle_for`).
- Property tests (Hypothesis, from the `dev` group of `pyproject.toml`) live in `tests/test_properties_*.py`; the docstring of each says the property in one line.
- A signal's handler cannot fail a test: `Signal` logs and goes on. A test that checks what a handler sees collects the faults in a list and asserts on it afterwards.

## Documents, scripts, units

- A document gets a row in `docs/README.md` and is changed in the same commit as the code it describes. A release gets a section in `CHANGELOG.md`, newest
  first, grouped by area, with no commit hashes; what is planned is in `ROADMAP.md` and nowhere else.
- The manual for the person who runs NeoAPRS (`docs/manual/`) is written in short paragraphs, headings and lists, in plain words. It names no component,
  function or source file, and no version number (`<version>` stands for it). The table of settings in it is made from the code (`scripts/doc-settings`). How
  things work inside goes to `docs/daemon.md` and `docs/development.md`. `tests/test_docs.py` holds all of this.
- A script in `scripts/` starts with a comment (or a docstring) that says what it is for, answers `--help` without doing anything else, and has a row in the
  table "Scripts" of `docs/development.md`. A unit (`neoaprs/cli/neoaprs.service`, the template that `neoaprs service install` fills in) has a row in
  `systemd/README.md`. A script that only calls a command of the package (`scripts/install.sh`, `scripts/neoaprs-db`, `scripts/replay`, `scripts/capture`,
  `scripts/fetch-basemap`) stays a thin wrapper: the code is in `neoaprs/cli/`. `tests/test_hygiene.py` and `tests/test_docs.py` fail when one is missing.
- The repository is public at https://github.com/oh2gba/neoaprs (GPL-3.0-or-later); commits go to `master`.

## Environment variables

Every `NEOAPRS_*` variable the code, the scripts, the units or the tests use is in this table, and only here (the manual and the other documents point to it).
`tests/test_docs.py` fails for a name used anywhere that is not in the table, and for a name in the table that nothing uses.

| variable | read by | what it does |
|---|---|---|
| `NEOAPRS_DATA_DIR` | the daemon and the commands | the data folder of `neoaprs` and `python -m neoaprs` (the daemon, `service`, `db`, `map`, `doctor`), else `~/.local/share/neoaprs` (`$XDG_DATA_HOME/neoaprs`) on Linux, `%LOCALAPPDATA%\NeoAPRS` on Windows, `~/Library/Application Support/NeoAPRS` on macOS; `--data` wins. The scripts use `./data` |
| `NEOAPRS_DEBUG` | the daemon | `1` is `--debug`: more is logged |
| `NEOAPRS_SERIAL_PATTERN` | the daemon, `capture` and the tests | the globs the search for the radio listens to (space-separated, like `serial/pattern`); when set and not empty it is used instead of `serial/pattern` and the default, but not instead of a port that was named. `tests/conftest.py` sets it to a pattern that matches nothing, so that no daemon or command a test starts opens a serial device of the machine; a test of the search gives its own pattern (a folder of pseudo-terminals) or clears the variable |
| `NEOAPRS_UPDATE_CHECK` | the daemon (`neoaprs/services/updatecheck.py`), the smoke scripts and the workflows | `0` switches the daily update check off for this run (the check is otherwise always on); `tests/conftest.py` sets it for every test and every process a test starts, and `ProcessGuard` refuses a `neoaprs` that a test starts without it, so that no test asks the version page on the internet. `scripts/smoke.py`, `scripts/smoke-appimage`, `scripts/screenshots.py` and the workflows set it too |
| `NEOAPRS_INSTALL_KIND` | the daemon (`neoaprs/cli/installkind.py`, `neoaprs/services/selfinstall.py`) | for development only (the screenshots of the update's steps): the install kind the daemon says it is, instead of the one it finds, with words after it (`deb arm64 service`, `appimage /home/ham/NeoAPRS.AppImage`). Update now of a simulated kind is a rehearsal: the file is downloaded and checked, then deleted; nothing is installed and nothing restarts |
| `NEOAPRS_UPDATE_FROM` | the daemon (`neoaprs/services/selfinstall.py`) | for development and tests only, and only together with `NEOAPRS_INSTALL_KIND` (a rehearsal) or `NEOAPRS_UPDATE_TEST=1` (a real install): the address of a folder that holds a folder `v<version>` of release files and their `SHA256SUMS`, where Update now downloads from instead of GitHub. Only http or https on `127.0.0.1` or `localhost` is taken (a fake server of this computer); any other address, or no switch, leaves GitHub |
| `NEOAPRS_UPDATE_TEST` | the daemon (`neoaprs/services/selfinstall.py`), `scripts/update-e2e.py` | test only, never for a user's install: `1` lets `NEOAPRS_UPDATE_FROM` stand in for GitHub while Update now installs for real (the Windows installer runs, the AppImage is replaced). The release workflow's end-to-end test of Update now sets it for the daemon of the old version it updates (docs/development.md, "Update now") |
| `NEOAPRS_OUT` | `ui/vite.config.ts`, `scripts/build-page`, `tests/test_page_build.py` | the folder Vite builds the page into: `scripts/build-page` points it at a temporary folder that it renames to `neoaprs/page/`, the page test at a temporary folder to compare with it; else `ui/dist` |
| `NEOAPRS_PYTHON` | `scripts/check`, `scripts/dup-check`, `scripts/neoaprs-db`, `scripts/replay`, `scripts/capture`, `scripts/fetch-basemap` | the Python they run, else the uv venv |
| `NEOAPRS_JSCPD` | `scripts/dup-check` | the command that stands in for jscpd (`tests/test_dup_check.py` gives it a stand-in that writes a report); else the jscpd of `ui/node_modules` |
| `NEOAPRS_TEST_WORKERS`, `NEOAPRS_TEST_WORKERS_MAX` | `scripts/check` | how many tests the pytest stage runs side by side: the cores, at most 12; 0 is one after the other |
| `NEOAPRS_VALIDATE_OUT`, `NEOAPRS_VALIDATE_RAISE` | `neoaprs/web/outbound.py` | `1` checks every message the daemon sends to a page against the `Message` union of `neoaprs/web/protocol.py` (and the `state` and `patch` of a topic against the type of its value); a mismatch is logged once for each message type, and with `NEOAPRS_VALIDATE_RAISE=1` it raises. `tests/conftest.py` sets both to `1`; `NEOAPRS_VALIDATE_OUT=0 pytest` runs the tests the way production runs |
| `NEOAPRS_FROM`, `NEOAPRS_TEXT`, `NEOAPRS_AT`, `NEOAPRS_MSG_ID` | the command of `messages/alert_command` (`neoaprs/services/alerts.py`) | set by the daemon for the command it runs when a message to us arrives, not read: the sender's call, the text, when it was heard (ISO 8601, UTC) and the message id (empty when the message had none) |
| `NEOAPRS_WHEEL_URL` | `packaging/install.sh.in` (the rendered `install.sh`) | the address of the wheel the install script installs, in place of the one of its release; the release workflow's test of the script gives it the wheel it has just built |
| `NEOAPRS_BUILD_CACHE` | `scripts/build-appimage` | the folder the pinned build tools (CPython, appimagetool, the AppImage runtime) are kept in once downloaded; else `~/.cache/neoaprs-build` |
| `NEOAPRS_TEST_ORDER` | `tests/conftest.py` | `reverse` or `shuffle[:SEED]` runs the test files in another order, to find a test that depends on an earlier one |

## Data

All of it in the one database `neoaprs.sqlite` in the data folder (`docs/manual/start.md`, "The data folder"): the settings as rows, every packet, and the
stations (a cache of the station book that the daemon rebuilds from the packets and a later migration may drop). Only the log of the program is a file,
`neoaprs.log`, rotated (20 MB, five files).

## The database schema

- A schema change is a new function at the end of `MIGRATIONS` in `neoaprs/migrations.py`, never an edit of one that has been released:
  `tests/test_migrations.py::test_an_applied_migration_is_frozen` fails on an edited migration. Everything a migration needs is inside it or frozen beside it
  (the SQL as text, not a constant that other code uses).
- Tables of data the operator would mourn are `STRICT`, with `CHECK`s for what the program can produce (and only that) and a name on each CHECK so that the
  error says which. Rows go in through a gate that makes the types right.
- A migration that rebuilds a table runs in the transaction `open_database` opens, repairs what the new table would refuse (keeping the original in the row),
  checks that every row came through, and raises on any doubt: the rollback leaves the old table. Every step is a transaction of its own, and a file that holds
  anything is copied whole into `backup/` before the first step runs.
- Every migration gets a test with a database of the version before it, seeded with realistic rows and compared with a database made fresh.
