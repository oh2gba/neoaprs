# Development

How NeoAPRS is built, checked, packaged and released. The rules the code is written by are in [`CONVENTIONS.md`](../CONVENTIONS.md), the layers in
[`docs/ARCHITECTURE.md`](ARCHITECTURE.md), the tests in [`tests/README.md`](../tests/README.md), the daemon's behaviour in [`docs/daemon.md`](daemon.md), and
what to keep up to date after a change in [`docs/MAINTAINING.md`](MAINTAINING.md).

NeoAPRS is one process with one asyncio loop: the standard library first, pyserial for the serial port, Tornado for the page, pydantic for the wire only,
cryptography for the secure connection's certificates, a database actor, a systemd user unit, and `scripts/check` as the one gate.

## Set up and run

```bash
uv sync --frozen            # the venv in .venv, from uv.lock
scripts/security-tools      # once: the pinned programs of the stage security (needs the network)
scripts/check               # every stage of the table below: the one gate
scripts/check --stage mypy  # one stage
.venv/bin/pytest -q tests/test_store.py
.venv/bin/python -m neoaprs --data data
```

`uv sync --frozen` makes `.venv` with the package installed in editable mode, so `.venv/bin/neoaprs` and `.venv/bin/python -m neoaprs` are the same command.
Dependencies are in `pyproject.toml` and `uv.lock` only.

- **At run time:** tornado, pydantic, pyserial and cryptography. The extra `app` is the desktop app: pywebview, pystray and Pillow on Windows, PySide6 with its
  web engine elsewhere. `uv sync --frozen --extra app` installs it, which CI does; a plain `uv sync` takes it out again, and the tests of the Qt shell are
  skipped without it. The extra `ble` is bleak, for a Bluetooth LE KISS TNC as a port (`ble://`, `neoaprs/btle.py`); CI installs it too (`--extra app --extra ble`), and the tests of the port use a fake
  bleak (`tests/support/fakeble.py`) and need it only for the one test that looks at the real library's interface. Neither extra is in the deb, the AppImage or the Windows installer.
- **For development:** pytest, pytest-asyncio, pytest-xdist, mypy, ruff, hypothesis and coverage.
- **The build backend** is hatchling. `uv build` makes the sdist and the wheel, about 1.3 MB with the page in it. `tests/test_package.py` installs the wheel
  into a fresh venv and runs `neoaprs --version`, `neoaprs doctor` and the daemon from it.

A new `git worktree` is made ready with `scripts/worktree-setup`: `uv sync --frozen --all-extras` and a real `ui/node_modules` from `npm ci` (from the caches
when they have everything), never a symlink to another checkout.

## The gate

`scripts/check` is the one entry point for "is this tree good": what is run before a push, and what `scripts/release` runs before it commits. It prints one line for each stage with the stage's own time, in the
order of the table below, and under the line of a stage that failed what that stage wrote. The last line is `all green in Ns`; when a stage failed it is `failed in Ns:` with the names, and the exit code is 1.

```
ok    lock            0.1s
FAIL  mypy           21.4s
      | neoaprs/tnc.py:88: error: Incompatible return value type
ok    architecture    4.4s
```

Most of the stages run at once. The default run has three steps:

1. **Alone, one after the other:** `lock`, then `npm ci` when `ui/node_modules` is missing (its line is `npm-ci`; it is no stage). `npm ci` takes the folder away and writes it again, and every stage of the page runs
   from it, so it is done once, before they start. When it fails, each of those stages (`ui-types` to `dup-py`) fails with one line that says so, and the others still run.
2. **At once:** every stage from `ruff` to `security`. On 32 threads about 28 are busy: the 12 workers of `pytest`, the 8 of `ui-tests`, the two runs of `mypy`, and one or two for each of the others.
3. **Alone:** `smoke`. It starts a daemon and gives it real seconds to answer, which a machine busy with step 2 may not leave it.

Every stage runs to its end, whatever the others say, and has a log of its own; the lines still come in the order of the list, each as soon as its stage and the ones before it are done. What two stages of step 2
would write into the same place is kept apart:

- **mypy** keeps its cache by folder and Python version, not by platform, so the run for Windows has a cache folder of its own (`.mypy_cache/win32`); beside the other stages the two runs go side by side.
- **`.pytest_cache`** belongs to the stage `pytest`: `architecture` and `page`, which are pytest runs too, run without the cache plugin.
- **vite** builds twice: the stage `ui-build` into `ui/dist`, the page test into a folder of its own (`NEOAPRS_OUT`). The stage `pytest` leaves `tests/test_page_build.py` to the stage `page`, so the suite builds
  nothing. Nothing else reads `ui/dist`.
- **`sim`, `audit` and `flaky`** run only by name, so alone: the simulation keeps the pace of a sound card and fails on a machine that is busy with anything else, and the hunt takes the cores of the machine for its containers.

The other ways to run it:

- `scripts/check --serial` runs the same stages one after the other in the order of the list and stops at the first failure, with its output as the end of the run; `NEOAPRS_TEST_WORKERS=0` implies it. It is for a
  machine with few cores, where step 2 asks for more than there is, and for reading the output of one failing test in order.
- `scripts/check --stage NAME` runs one stage, `scripts/check --list` prints the names.

A run that is interrupted (Ctrl+C, or a signal that ends it) ends the stages it started and takes its temporary folder away; a TERM sent to the script alone waits for `lock` or `smoke` to end when one of them is running.

Three things it needs of the machine:

- **`uv sync --frozen` once**, and node 22.12 or newer for the stages of the page.
- **`scripts/security-tools` once** (it needs the network): the stage `security` runs pinned programs that this script fetches into the build cache, and the system's php with its XML extensions for Psalm (Debian
  and Ubuntu: the package `php-xml`) or, where php lacks them, docker and the php image pinned in `scripts/security-tools`. A check whose program is not there fails: a check that could not run is never a pass.
- **No sandbox between uv and its cache** (`~/.cache/uv`). The stages `lock` and `smoke` and the package tests of the suite go through uv; with an empty cache and no network they fail or are skipped for a reason
  that is the sandbox's and not the tree's.

The runner itself is tested without one real stage (`tests/test_check_script.py`): `NEOAPRS_CHECK_STAGES` names a file of shell functions that stand in for the stages. The script takes the variable only as a copy
in a folder that has nothing to check, neither `pyproject.toml` nor `neoaprs/` beside `scripts/`, which is what the tests make. In a tree a variable that is set stops the script with exit code 2 before
anything runs, whatever was asked: one left in a shell cannot turn the gate, or the release that asks it, green with nothing checked.

### The stages of scripts/check

| stage | what it checks |
|---|---|
| `lock` | `uv.lock` is current with `pyproject.toml` |
| `ruff` | `ruff check` over the tree: pycodestyle, pyflakes, bugbear and the security rules (S), the Python tools of `scripts/` without `.py` included (`extend-include` in `pyproject.toml`, held exact by `tests/test_lint_scope.py`); what is switched off and why is in `pyproject.toml` |
| `mypy` | `mypy --strict` over `neoaprs/` and `tests/support/`, and over the test files for what is wrong with their names (a function or a constant that Windows lacks, a module or an attribute that is not there; how a test types its doubles is not asked), for Linux and again for `--platform win32`, each run with a cache of its own. A name that only POSIX has is used in a test file by way of `tests/support/ptyline.py` (`SIGHUP`, `mkfifo`, `is_root()`, ...), which imports on Windows too |
| `architecture` | the layers and the size limits (`tests/test_architecture.py`, `tests/test_size_ratchet.py`) |
| `pytest` | the rest of the suite (all but the files of `architecture` and `page`), side by side on the cores of the machine, 12 workers at most, with `--dist loadgroup` so that `tests/test_package.py` and `tests/test_desktop_qt.py` each stay on one worker (`xdist_group`); a test that still runs after two minutes has the stack of every thread printed (`faulthandler_timeout` in `pyproject.toml`), so that one that hangs says where |
| `ui-types` | `vue-tsc --noEmit` over `ui/`: TypeScript strict, the types of the protocol from `ui/src/protocol/` only |
| `ui-lint` | eslint with no warnings (it also refuses the ways besides `v-html` to make markup or code of a text, `ui/eslint.config.js`), prettier `--check`, knip (nothing unused) over `ui/`, and `scripts/css-unused.py` (no rule in `ui/src/styles/` of a class that no source file writes) |
| `ui-tests` | vitest: the logic of `ui/src/lib`, the composables, the components, and the lint rules that keep a station's text a text, run on made-up sources (`ui/src/lib/lintrules.test.ts`); 8 workers at most beside the other stages |
| `ui-build` | `vite build` into `ui/dist` (the build works) |
| `page` | `neoaprs/page/`, what the daemon serves, is what `ui/` builds, and lives under the daemon's Content-Security-Policy (`tests/test_page_build.py`); the test skips its build where there is no node or no `ui/node_modules`, so the stage fails there: nothing was compared |
| `dup` | jscpd over `ui/src`: duplicated code over the threshold of `ui/.jscpd.json` fails |
| `dup-py` | `scripts/dup-check`: the duplication ratchet of the Python half, jscpd over `neoaprs/` and `tests/support/` against `scripts/dup-baseline.json` (`docs/ARCHITECTURE.md`) |
| `security` | `scripts/security-check`, the security checks that need a program of their own and ask nobody: no password, token or key gets to GitHub (no file or folder named `.secrets`, or `.secrets` with anything after it, is tracked or left unignored; the script itself looks for the access token of the secrets manager in every commit `origin` does not have yet, in the index and in every tracked file (`--all-history`: in every commit there is); gitleaks reads the commits of the branch, their messages and the tracked files that are changed or staged), `php -l` and Psalm's taint reports over `server/`, shellcheck over the shell scripts and zizmor over the workflows (neither reads a settings file: a tracked one is a finding), the last two against `scripts/security-baseline.json` ([`docs/security-checks.md`](security-checks.md)) |
| `smoke` | the wheel as a user gets it, as the CI job `smoke` does it: built into a temporary folder, installed into a fresh environment there (uv takes what its cache has, and asks the net only when that is not everything), and `scripts/smoke.py` run against the installed command ([The smoke test](#the-smoke-test)); the daemon it starts opens no device of the machine (`NEOAPRS_NO_DEVICES=1`) and does not ask the version page (`NEOAPRS_UPDATE_CHECK=0`) |
| `sim` | only by name (`scripts/check --stage sim`, not in the default run): `scripts/mercury-sim`, the HF net with real Mercury instances ([The simulators](#the-simulators)); about six minutes, Linux only, the Mercury of the venv built first when it is not there (`scripts/build-mercury --install`, which needs gcc, make and libasound2-dev); the report is left in `build/mercury-sim.json` |
| `audit` | only by name (`scripts/check --stage audit`, not in the default run): `scripts/security-check --audit`, osv-scanner asks the advisory lists about every package of `uv.lock` and `ui/package-lock.json`; it needs the network, and `osv-scanner.toml` lists the advisories set aside, each with its reason; `.github/workflows/audit.yml` runs it every Monday |
| `flaky` | only by name (`scripts/check --stage flaky`, not in the default run): `scripts/flaky`, 20 runs of the CI's command for the tests in the container of `scripts/check-in-container`, half in file order and half shuffled (`tests/support/shuffle.py`, the seed is the number of the run), half the runner's size and half starved, four containers side by side on cores of their own, each run under a time limit; it prints a table of every test that failed with its count, the settings it failed in and its first failing line, and a run that hung or did not reach the tests with its evidence; the logs and `report.txt` are in `build/flaky/`; an hour or more, Linux and docker only |

The stages from `ui-types` to `dup-py` need node 22.12 or newer (on the `PATH`, else the newest in `~/.nvm`) and `ui/node_modules`.

### In a container the size of GitHub's runner

`scripts/check-in-container` runs the commands of the CI's Linux job (`uv sync --frozen --extra app --extra ble`, then the stages `lock`, `ruff`, `mypy`, `architecture` and `pytest` of `scripts/check`, which is what the workflow calls) on a copy of the tree, in a Docker container that has the system, the user, the tools, the threads and the memory of GitHub's runner, so that a test that fails or is skipped there does the same here first. `-- COMMAND...` runs another command in the same place (it makes its own environment: `uv sync` first, or `uv run`), `--starved` gives it half a runner, `--image-only` only builds the image.

- **The machine.** `packaging/ci/Dockerfile`: Ubuntu 24.04 with the system libraries the workflow installs, git, curl, PHP, a compiler and make, uv and node 22 each pinned by version and SHA-256, the Python the workflows name, and the ordinary user `runner` with uid 1001 (as root the tests of file rights are skipped). The image is built when it is missing or the Dockerfile has changed (its tag is the Dockerfile's digest) and without a build context, so no file of the project is in it. The build needs the network.
- **The size.** Four threads that are two cores with their siblings, read from `/sys/devices/system/cpu` and given as a CPU set, 16 GB with no swap beyond it, an init process, and 1 GB of `/dev/shm` for the Qt web engine's tests. A CPU set and not a quota: under `--cpus` `pytest -n auto` still counts every thread of the machine and starts a worker for each. `--starved` is two threads of one core and 7 GB, where the tests that depend on time fail first.
- **The tree.** What goes in is the tree as it is on disk, the tracked files and the untracked ones that are not ignored (git's own list), packed here before docker is asked for anything and unpacked inside the container as a repository of one commit (the tests ask git which files are tracked). The working tree is never mounted: a run cannot change it and does not see this machine's `.venv` or `ui/node_modules`; it makes its own from uv's and npm's caches, which are the volumes `neoaprs-ci-uv` and `neoaprs-ci-npm` and make the second run fast.
- **What stays here.** An untracked file that an ignore rule names is never packed, and neither is a file of access tokens (`.secrets` and whatever follows that name, in any folder), tracked or not and whether an ignore rule names it or not. Every other untracked file goes in, so a key or a token under another name is kept on this machine by a line in `.gitignore` (as `/work/` is). No variable of this machine's environment is passed into the container.
- **Side by side.** A container has no name, publishes no port and has a loopback of its own, so any number of runs, of one worktree or of several, cannot meet on a port. Each takes cores that no other run holds (a label on the container says which threads it has).
- **Inside**, `NEOAPRS_UPDATE_CHECK=0`, `NEOAPRS_NO_DEVICES=1` and `UV_FROZEN=1` are set, and there is no display and no terminal. The output streams through, with a line before and after each command that gives its exit code and its seconds. The exit code is that of the first command that failed; 125 means docker could not build the image or start the container, 2 that docker, git or the list of cores is missing, that the folder is not the working tree of a git repository, or that a file of the tree cannot be read or a folder of it not listed; the last two are said in one line (`check-in-container: nothing was run: ...`) before an image is asked for or a container started. A signal that ends the script removes its container.

```bash
scripts/check-in-container                                                                 # the CI's Linux job
scripts/check-in-container --starved -- uv run pytest -n auto tests/test_serialport.py     # one file on half a runner
```

`docker volume rm neoaprs-ci-uv neoaprs-ci-npm` empties the caches. The images of earlier Dockerfiles stay until they are removed (`docker image ls neoaprs-ci`).

### On a real Windows

`scripts/check-windows` runs what the CI's two Windows jobs run on a real Windows, a VirtualBox machine of this computer reached over SSH, so that a test that fails on `windows-latest` fails here first. It is never a stage of `scripts/check`: it needs a machine that only some developers have, and about six minutes.

- **Where the machine is.** Only from the environment, and nothing is guessed: `NEOAPRS_WINVM` (the machine's VirtualBox name), `NEOAPRS_WINVM_SSH_PORT` (the port on this computer that is forwarded to its SSH), `NEOAPRS_WINVM_SSH_KEY`, `NEOAPRS_WINVM_KNOWN_HOSTS` (a login with a host key that is not in that file fails) and `NEOAPRS_WINVM_USER` (default `John`). With `NEOAPRS_WINVM` unset the script says that the check is not set up here and ends with 2.
- **Power.** A machine that is off is started without a window (`VBoxManage startvm NAME --type headless`), the script waits for its SSH, and when the run is over shuts it down with Windows's own shutdown, asked from inside over SSH and, when that has not turned it off, by the ACPI power button, and waits for it; never a hard power-off, and a machine that does not go off in time is left as it is and said. A machine that was running is left running. `--snapshot NAME` puts the machine back to that snapshot before it starts, for a clean Windows at every run, and is refused while the machine runs. One run at a time on a machine: a lock file in the build cache; a second run says so and stops.
- **The tree.** Packed here as `scripts/check-in-container` packs it (git's list: the tracked files and the untracked ones that are not ignored; never what an ignore rule names, and never a file of access tokens, `.secrets` and whatever follows that name, in any folder), copied with `scp` and unpacked by Windows's own `tar.exe` into `C:\Users\USER\neoaprs-check\RUN-<UTC time>\neoaprs`. Where the machine has git, the tree there is a repository of one commit made of the tracked files; where it has none, the tests that ask git for the tracked files fail there, as they do on a runner without git. The folders of older runs are removed but the newest two. uv is `C:\Users\USER\neotest\uv\uv.exe` in the version the script pins (with its SHA-256, as `scripts/security-tools` pins its programs); when the machine has another or none, the zip is fetched once into the build cache, checked and copied over.
- **The steps**, each a line as `scripts/check` prints it, the output of a failed one under its line, the whole log of every step in a folder of this computer that the first line names: `sync` (`uv sync --frozen --extra app --extra ble`), `lock` (`uv lock --check` with `UV_FROZEN` unset), `ruff`, `pytest` (`uv run pytest -n auto -p no:cacheprovider`), `smoke` (`uv build --wheel`, a fresh environment, the wheel installed, `scripts/smoke.py` with the installed command). A failed step stops none of the later ones but `sync`. Every step runs with `NEOAPRS_NO_DEVICES=1`, `NEOAPRS_UPDATE_CHECK=0` and `UV_PYTHON_PREFERENCE=only-managed`. Where the machine has Git for Windows, the folder of its `sh` and `bash` is on the PATH of every step, as it is on GitHub's runner (`tests/test_install_line.py` reads a script with `sh -n`). mypy is not run: the workflow runs it on Linux only, for both systems.
- **A console for Ctrl+Break.** Tests that end a child they started in its own process group (`tests/support/proc.py`) send it Ctrl+Break, which Windows delivers only inside a console. Before the pytest step the script runs a probe of that in a plain SSH session and, when it does not pass there, in one with a pseudo console (`ssh -tt`), and runs pytest in the one that passes; `--tty` skips the plain try.
- **The exit code** is 0 when every step passed, 1 when a step failed, 2 when the check cannot run (not set up, a missing file or program, a machine that is in no state to be used, a second run, SSH that does not answer).

```bash
scripts/check-windows                                          # the CI's two Windows jobs
scripts/check-windows -- tests/test_replay.py tests/test_scripts.py     # two test files only (sync, then pytest with these arguments)
scripts/check-windows --only smoke --only lock                 # two steps
```

### Clean installs in Docker

`scripts/check-installs` tries what a user does with the files of a release, before a tag, in containers that have nothing of NeoAPRS: the wheel in a fresh environment and the AppImage in the image of `scripts/check-in-container`, the .deb installed with apt in a clean Debian 12 and a clean Ubuntu 24.04 (with the release's checks of the package, Mercury and its libraries, a service install, an install over itself and the removal), and the upgrade. The files are built here by the scripts the release workflow runs (`uv build --wheel`, `scripts/build-mercury --tar`, `scripts/build-deb`, `scripts/build-appimage`) and mounted read-only; no container has a device or a port.

The upgrade starts from the last release, a .deb that is fetched once into the build cache and used only when its SHA-256 is the one pinned in `packaging/ci/old-release.json`. After a release `scripts/check-installs --pin VERSION` fetches that release's .deb and its `SHA256SUMS` and writes the pin once the two agree; until then the check fails, since one that could not run is not a pass. The old daemon is started with a fake TNC for the FM radio and the Dummy HF radio, is given a call, hears stations and sends a message; this build is installed over it with apt, and its daemon must say it is this version and have the stations, the message and the settings. arm64 and macOS and Windows are not tried here.

```bash
scripts/check-installs                      # every check
scripts/check-installs --only upgrade       # one
scripts/check-installs --pin 0.18.2         # after a release, with the network
```

### Local and CI

`.github/workflows/ci.yml` runs on every push to `master` and to a `ci/**` branch, and on every pull request. On Linux its steps are stages of `scripts/check` (`scripts/check --stage NAME`), so that what runs there cannot differ from what is run before a push or in the container; Windows has no bash script and runs the commands themselves.

| job | where | what |
|---|---|---|
| `python` | Linux and Windows, Python 3.13 | the system libraries of the Qt web engine (Linux), `uv sync --frozen --extra app --extra ble`; on Linux the stages `lock`, `ruff`, `mypy` (both systems, the test files too), `architecture` and `pytest`; on Windows `uv lock --check`, `ruff` and `pytest -n auto --dist loadgroup` |
| `smoke` | Linux and Windows | `uv build --wheel`, the wheel installed into a fresh venv, then `scripts/smoke.py --command <venv>/bin/neoaprs` (`Scripts\neoaprs.exe`) |
| `page` | Linux | type check, lint, prettier, knip and the page's tests, the two duplication stages (`scripts/check --stage dup` and `dup-py`), the page's own test (`scripts/check --stage page`), and the committed `neoaprs/page/` is what `ui/` builds |
| `sim` | Linux | the pinned Mercury built from source into the venv (`scripts/build-mercury --install`, as the release's `mercury` job builds it, on the runner's own system), (kept between runs under a key of what the build reads: the script, `neoaprs/mercury.py`, `packaging/mercury/` and the runner's image), then `scripts/mercury-sim` to the end ([The simulators](#the-simulators)); about six minutes, of which the build is one; the report and the log are the artifact `mercury-sim`, and the folders of the run (the daemons' logs, Mercury's output) are `mercury-sim-folders` when it failed |

What only `scripts/check` runs: the `css-unused` check of `ui-lint`, the stage `security` and the stages that run only by name (`sim` is also the job `sim`; `audit` is the weekly workflow `audit.yml`). What only CI runs: the Windows halves of `python` and `smoke`. The workflow can also be started by hand
on any branch (Actions, ci, *Run workflow*, or `gh workflow run ci.yml --ref BRANCH`).

What only makes sense on a POSIX system is marked `posix_only` (`tests/support/ptyline.py`) and skipped on Windows: pseudo-terminals and device files, `/proc`,
file modes, shell scripts and the stand-ins that are shell scripts (the fake `systemctl`), the checks of the repository itself (documents,
scripts, the unit files) and the ones that need `git` and `bash`. Everything else runs on both systems; `tests/README.md` has the details.

The daemon, when a test starts it as a process, is stopped on Windows with Ctrl+Break in a process group of its own (`tests/support/proc.py`): `terminate()` there is a kill.

`NEOAPRS_TEST_WORKERS` and `NEOAPRS_TEST_WORKERS_MAX` set how many tests the `pytest` stage runs side by side (the cores, at most 12: the ports of the Mercury tests are laid out for twelve workers); 0 runs them
one after the other, and the stages of `scripts/check` too, which is what to do to read the output of one failing test in order. `NEOAPRS_PYTHON` is the Python the gate runs, else the one of `.venv`. The stage
`smoke` sets `NEOAPRS_NO_DEVICES=1` and `NEOAPRS_UPDATE_CHECK=0` for the daemon it starts, and `NEOAPRS_CHECK_STAGES` is for the tests of the runner only (in a tree it stops the script). The table "Environment variables" of `CONVENTIONS.md`
lists every variable.

### Coverage

`scripts/coverage` runs the Python suite under coverage.py, side by side like the `pytest` stage, and prints the table of every module of `neoaprs/` (lines, branches, the missing line numbers) and the total.
The rules are `[tool.coverage]` in `pyproject.toml`: branches count, and the daemons and commands that tests start as processes are measured too (`patch = subprocess`). `scripts/coverage -- tests/test_db.py` runs only
the tests after the `--`; `scripts/coverage --ui` is the page's vitest coverage (`src/lib`, `composables`, `components`, `help`, `protocol`, `App.vue`, `AccessGate.vue`, `main.ts`). It is slower than the tests
alone, so it is not a stage of `scripts/check`; nothing is excluded, and there is no floor yet.

### The smoke test

`scripts/smoke.py` is the check an installer or a package must pass. The stage `smoke` of `scripts/check` and the CI job `smoke` run it against the wheel, installed into a fresh environment.

1. It starts a fake KISS TNC on a free TCP port (it plays `tests/fixtures/kiss/thd7-2026-10-21.bin`).
2. It starts the daemon on a temporary data folder with `--port socket://127.0.0.1:PORT --web-port 0`, and reads the page's port from the log line `web page at`.
3. It fetches `/` (200, `<div id="app"`, the Content-Security-Policy header) and the first script under `/assets/`.
4. It opens `/ws` and waits for the TNC to be `connected` and for a packet.
5. It stops the daemon (SIGTERM; Ctrl+Break on Windows) and checks exit code 0, `NeoAPRS ended` as the last line of the log, and `PRAGMA integrity_check` on the database.

Run it against a clone with `.venv/bin/python scripts/smoke.py`, or against an installed command with `--command PATH` (and the Python that has NeoAPRS
installed: it uses Tornado's WebSocket client). It prints what it checks and exits 0, or says the first thing that was wrong with the end of the daemon's log
and exits 1.

## The wire

The page and the daemon talk by JSON over one WebSocket: commands from the page, messages from the daemon, topics that are kept in step.
[`PROTOCOL.md`](../PROTOCOL.md) is the reference. It is generated, with everything else that describes the wire, from the pydantic models of `neoaprs/web/`
(`neoaprs/web/protocol.py` lists them) by `scripts/gen-protocol.py`.

| generated file | what it is |
|---|---|
| `PROTOCOL.md` | the reference: the prose, then the commands and the messages from the models' docstrings and field descriptions |
| `ui/src/protocol/schema.json` | the JSON Schema of the `Command` and `Message` unions and of the value of each topic |
| `ui/src/protocol/protocol.ts` | the TypeScript types made from it (no node, no json-schema-to-typescript) |
| `ui/src/protocol/lists.ts` | the lists the daemon owns and the page shows (the settings' keys, the TNC profiles, the symbol names) and `LIMITS` |
| `ui/src/protocol/errors.json` | the refusals of the daemon that carry a code: for each code the values it passes and the English sentence it writes, found in the source by `scripts/errorcodes.py`; the page's catalogue is held to it by `ui/src/i18n/errors.test.ts` |
| `ui/src/i18n/en/symbols.ts` | the names of the APRS symbols as messages of the English catalogue (`symbol.primary.3e`: the table and the code in hex), written from `SYMBOL_NAMES` of the daemon; `lib/symbols.ts` `symbolText` says one |
| `ui/src/protocol/vectors.json` | conformance vectors for the rules that are code |

Run `.venv/bin/python scripts/gen-protocol.py` after a change to a wire model, a limit or a list; `--check` writes nothing and exits 1 when a file is out of
date, which `tests/test_protocol.py` does inside pytest. `npm run protocol` in `ui/` runs it with `uv run`. The lists are one item to a line, so two edits to
them seldom conflict; after a merge, regenerate rather than resolve by hand.

- **`LIMITS`** is every number the page checks a value against: the ranges of the settings, the lengths of a comment, a message and a status, the minimum
  interval, the object and bulletin limits. It is written from the daemon's own constants (`neoaprs/config.py`, `neoaprs/policy.py`, `neoaprs/ownobject.py`,
  `neoaprs/ownbulletin.py` ...). The page types none of them again.
- **`vectors.json`** holds the rules that are code and not numbers: whether this is a call, the PHG text of this antenna, the beacon these settings make, the
  object and bulletin text rules. Python makes it, and `tests/test_vectors.py` and `ui/src/protocol/vectors.test.ts` hold the daemon and the page to it (the page to the rules
  it has of its own: the PHG text and the beacon are the daemon's alone), and a drift is a test failure.
- **Errors.** An `error` message carries `cmd` (the command it answers; empty for a frame that was no command), `key` (the setting it is about, or null), `code`
  (a stable word such as `setting.range`, `call.ssid` or `message.too_long`; `other` for one without a code yet), `params` (the values the sentence is made of,
  by name) and `text` (the English sentence, for a log and for a code the page has no sentence for). The page goes by `cmd`, `key` and `code`, never by the
  words of `text`. `neoaprs/coded.py` has `CodedError`, and `neoaprs/config.py` a `SettingError` that adds the key.
- **Directed queries.** `query` (`call`, `kind`: `position`, `status`, `heard` or `trace`) sends `?APRSP`, `?APRSS`, `?APRSD` or `?APRST` to a station as a message through `Asking.ask` (`neoaprs/services/asking.py`): the normal path of
  a message (the interlock, the radio's state, the pacing, the station's path), but once, with no message id and one attempt, so that no ack is waited for and none is retried (the specification's queries are not
  numbered); the row is kept as `unconfirmed`, an `out` message with no `msg_id` whose text is one of the four, which the page shows as a note and not a bubble. One query of a kind to a station in 60 seconds
  (`QUERY_EVERY_SEC`), else `query.too_soon` with `call` and `seconds`; a call that is not in the station book is `station.unknown`, one that takes no messages (an object, an item, ourselves, a station whose
  position says it takes none) `query.not_capable`. The answers are the packets and messages the stations send, which the daemon treats as it treats any.
- **Asking QRU.** `qru_ask` (`text`) sends one message to `QRU` through `QruAsk.ask` (`neoaprs/services/qruask.py`): no id, not kept, once, RFONLY after the path of messages; the refusals are `transmit.off` and the interlock's, the radio's reason, and
  `qru.too_soon` with `seconds`. What the servers answer is in the topic `qru` (with how many objects of each answer arrived); the answers are not messages.
- **The TNC** is `TncState` of the topic `tnc`: `searching` is the ports being listened to and `lines` the latest 100 as `{at, text}`; the page parses no sentence for either.
- **The rows** of `stations`, `packets` and the other topics are built from the domain objects through their models (`neoaprs/web/*wire.py`), so a field is
  added to the model and the object only. A golden-file test (`tests/test_wire_rows.py`) holds the JSON of every row kind.
- **Validation.** `NEOAPRS_VALIDATE_OUT=1` checks every message the daemon sends to a page against the `Message` union (and the `state` and `patch` of a topic
  against the type of its value). A mismatch is logged once for each message type, and with `NEOAPRS_VALIDATE_RAISE=1` it raises. `tests/conftest.py` sets both;
  `NEOAPRS_VALIDATE_OUT=0 pytest` runs the tests the way production runs.

## The page

The source is `ui/`: Vue 3, TypeScript strict, Vite, vitest, eslint (no warnings), prettier, knip and jscpd, versions pinned in `ui/package.json` and
`ui/package-lock.json`. `cd ui && npm run dev` serves the source with hot reload on port 5173 and proxies `/ws`, `/basemap.pmtiles` and `/basemap-world.pmtiles`
to a daemon on port 7303.

- `ui/src/lib` is logic without Vue: the socket client `hub.ts`, the symbol sprites, the sorting of the table, the map style, the field checks (`fieldcheck.ts`, driven by `LIMITS`).
- `ui/src/composables` is state and behaviour. `useDaemon` holds the topics as reactive maps, reconnects with a backoff and shows "Daemon offline" in the
  footer. `useDaemonContext` is the one typed context that `App.vue` provides and the panes inject, so the panes take no chain of props. `usePanel`,
  `useSelection`, `useMessagesView`, `useEmail`, `useBulletins`, `useOwnObjects` and `useAppShell` run the panel, the station picked, and the tabs.
- `ui/src/components` has the single-file components, none over 300 lines. They take props and emit events.
- `ui/src/help/` has the small pictures that an (i) note can show under its text (`InfoTip` takes one by name, `help/names.ts`): each is inline SVG 280 by 150 in the colours of the page
  (`styles/helppictures.css`, so that it follows light and dark), its symbols are cut from the map's own sheets, and it has no words in it but calls and codes; its
  description for a screen reader is `help.picture.<name>` in the catalogues. A tab says what it is for in an (i) bar at its top (`TabHelp`).
- `ui/src/styles/` has the CSS by area, imported in order from `main.ts`; `scripts/css-unused.py` (in the stage `ui-lint`) fails for a rule of a class that no
  source file writes. The classes the page builds at run time (`hop-${kind}`, ...) are in its `PREFIXES`, with the file that builds each.
- The tests of `App.vue` are split by tab and area (`ui/src/App.<area>.test.ts`), with a shared harness in `ui/src/test/app.ts`.
- Every type of the wire comes from `ui/src/protocol/`: there is no hand-written copy of a row.
- **The layout** is chosen from the size of the window by `lib/layout.ts` and `composables/useViewport.ts`. The root of the page carries `size-phone`,
  `size-tablet` or `size-desktop`, and the stylesheets go by that class and not by media queries of their own, so that the script and the style never disagree.
  The sizes themselves are in [the manual](manual/page.md#a-phone-a-tablet-and-a-desktop). The page is the height of the window (`100dvh`), keeps clear of the notch and the home bar (`viewport-fit=cover`, `env(safe-area-inset-*)`), gives a touch screen (`pointer: coarse`) controls of at least 40 px and fields of 16 px, and the installed app (`display: standalone`) uses the same layout.

**How it is built.** `scripts/build-page` does `vue-tsc` and `vite build` into a temporary folder and renames it to `neoaprs/page/`, so a test never sees half a
page (`NEOAPRS_OUT` says where Vite writes). `neoaprs/page/` is committed, so the machine that runs NeoAPRS needs no node. `npm ci` runs only when
`ui/node_modules` is not what the lockfile says (`scripts/node-modules-current.mjs` answers that), never through a symlink; `--clean` forces it.

Beside the page `neoaprs/page/` has the manifest and the icons (`ui/public/manifest.webmanifest`, `ui/public/icons/`, made from `site/favicon.svg`) and the
service worker `sw.js`. `vite.config.ts` writes it from `ui/sw/sw.js` once the rest is written, with the build of the page in it (a hash of every other file, which names its two caches): a changed page is a changed worker, and a new version of NeoAPRS that changed nothing in `ui/` is not. The daemon serves them with
`Cache-Control: no-cache`, the manifest as `application/manifest+json`. The worker keeps the hashed files under `assets/`; the shell, the manifest, the icons,
the symbol sheets and the glyph files are asked of the daemon every time and a kept copy is shown only when the daemon cannot be reached; the socket, the login,
the base map and every request that is not a GET are never touched.

**The gates.** The stages `ui-types`, `ui-lint`, `ui-tests`, `ui-build`, `page` and `dup` hold the page. `page` fails (`tests/test_page_build.py`) when
`neoaprs/page/` is not what `ui/` builds, so a change to `ui/` is not done until `scripts/build-page` has run and `neoaprs/page/` is committed with it. The same
test holds the page to the Content-Security-Policy of `neoaprs/web/headers.py`: no inline script, no eval, and MapLibre's worker is a file of
`neoaprs/page/assets`, because it would make one from a blob otherwise, which the policy forbids.

**The assets.** The symbol sheets are in `ui/public/symbols/` (three sprite sheets, 48 px a symbol), with `SOURCE.txt` and `COPYRIGHT.txt` beside them;
`src/lib/symbols.ts` is the one file that knows their layout. The glyph files for the map labels are in `ui/public/fonts/` with `OFL.txt`. The credits shown in
the map's (i) are in [the manual](manual/page.md#credits).

## Translations

The words of the page are in a catalogue, so that a language is a file and not a hunt through the components. Only the page is translated: the manual, the README, the log, the command line, the desktop app's menus, `ui/index.html` (its
`lang` stays `en`; the page sets `<html lang>` at run time) and the page the daemon serves when none is built stay English.

- **The layer** is `ui/src/i18n/`, a small one of our own on `Intl` (no dependency: the needs are plurals, values, numbers and a language that can be switched). `index.ts` has `t(id, values)`, the reactive `locale`, `setLocale`,
  `formatNumber(n, decimals)` and `weekdayShort(date)`; `en/` is the English catalogue by area, `en.ts` joins them (the type of every id comes from it), `locales.ts` lists the languages, `message.ts` reads a message,
  `pseudo.ts` is the pseudo-locale and `errortext.ts` says the daemon's refusals. `t` reads `locale`, so whatever shows its result is drawn again when the language changes; a text kept in a module constant stays in the
  language it was made in, so a function makes the text when it is asked for.
- **An id** is `area.thing.detail` in lower case (`pill.radio_silent`, `error.setting.range`); the area is the part of the page, not the file. A message is a string with `{value}`s; a plural `{ one: "{n} message", other:
  "{n} messages" }`, chosen by the value `n` and the plural rules of the language (a language with more forms has them, `"=0"` is an exact number); or a choice by the text of a value `{ select: "kind", object: "...",
  other: "..." }`. `{{` and `}}` are a literal brace. A number is given as a number and is written with the language's decimal point and no thousands separator; one with a fixed number of decimals goes through
  `formatNumber` first. A message is a whole sentence with its values: never two messages put together (word order and agreement differ), never `n === 1` in the code, never a unit or a word taken from the middle of a sentence.
  The units of measure (km, MB, hPa) and the compass letters are written in the code. What the daemon words itself and the page cannot take apart (the summary of a packet, the reason a packet could not be read, the colour and shape of an area) is shown as it comes; a route (`direct`, `via A → B`) is taken apart and worded by `routeWords` in `lib/routes.ts`.
- **A new text**: write the English in the file of its area in `ui/src/i18n/en/` (a new area is a file and a line in `en.ts`) and use `t("id")` in the template (`{{ t("header.no_call") }}`, `:title="t('...')"`). A function of
  `lib/` that makes a sentence calls `t` itself, so the component stays a view. `ids.test.ts` fails for an id that is asked for and is not there, and for one that nobody asks for.
- **The daemon's refusals** carry `cmd`, `key`, `code` and `params` besides the English `text`. `errortext.ts` says a refusal from the catalogue (`error.<code>`, the values from `params`) when it has the code, and with the
  daemon's English `text` when it has not (a code without a sentence, `other`); the page never decides by the words of `text`. The codes and their sentences are found in the daemon's source by `scripts/errorcodes.py` and written
  to `ui/src/protocol/errors.json` by `scripts/gen-protocol.py`; `ui/src/i18n/errors.test.ts` fails for a code that has no sentence on the page and for a sentence that does not read as the daemon's. A sentence that lists
  something (the settings, the TNC profiles, the characters a message may not have) takes the list from `lists.ts`.
- **A language**: a file `ui/src/i18n/xx.ts` with `export const xx: Catalogue = { ... }` (the type is made from `en.ts`, so a missing or an unknown id does not compile; copy the English and translate; a catalogue over the 400 lines the linter allows a file is split like `en/`: `xx/area.ts` for each area, typed `Record<keyof typeof source, Message>` from the English one, and `xx.ts` joins them; `ja` and `pt-BR` are made so), and in `locales.ts` its
  import and one line `{ code: "xx", name: "Its own name", messages: xx }`. `catalogues.test.ts` holds it to the same ids, the same `{values}` in each message and the plural forms of its language; at run time a message it lacks
  falls back to English. The language is chosen in the Settings tab ("Language", kept in this browser like the other choices of the page); until then it is the first of the browser's languages (`navigator.languages`: `de-AT`
  is `de`, `pt` is `pt-BR`) that the page has, else English.
- **The guard rails.** The tests read English: `src/test/setup.ts` pins it. `literals.test.ts` fails for a word written into a template (a text node, `title`, `placeholder`, `aria-label`, `label`, `alt`, and a string of an
  interpolation or a bound attribute that reads as text); the brand and the units are allowed (`src/test/literals.ts`). A component that is not converted yet is in `ui/src/i18n/unconverted.json` with the number of literals it
  has, a ratchet that only goes down: whoever converts a component takes it out (`I18N_UPDATE=1 npx vitest run src/i18n/literals.test.ts` writes the file from what is found, `I18N_REPORT=1` lists every literal with its line).
  `App.pseudo.test.ts` draws every tab in the pseudo-locale `en-XA` (every message accented, a third longer and in `[!! ... !!]`; it is offered in the Settings tab in development and is not in the built page) and fails for a
  text that is the English of a message of the catalogue; the words of a component that is not converted yet and are the same as a message that is are in its `STILL_ENGLISH` until then.
- **Known limit: the map's labels.** The glyph files of the map (`ui/public/fonts/NotoSans-*`) cover three ranges of Noto Sans (0-255, 256-511, 1024-1279): Latin and Cyrillic. A station name in Japanese, Greek or Arabic is
  not drawn on the map, whatever the language of the page. Fonts for more ranges are a separate decision.

## Scripts

| script | what it is for |
|---|---|
| `scripts/check` | the one gate ([The gate](#the-gate)): the stages of the default list, most of them at once, with a line for each in the order of the list; `--serial` one after the other, stopping at the first failure; `--stage NAME`, `--list` |
| `scripts/check-installs` | the clean installs of a release in Docker: the wheel in a fresh environment, the .deb with apt in `debian:bookworm-slim` and `ubuntu:24.04` as the release's job `deb` does it, the AppImage on a computer with no NeoAPRS, and an upgrade (the last release of `packaging/ci/old-release.json` installed and started with both radios, a station and a message, this build installed over it, `scripts/install-probe.py`); `--only NAME`, `--no-mercury`, `--pin VERSION` pins the old release by its SHA-256 ([Clean installs in Docker](#clean-installs-in-docker)) |
| `scripts/check-in-container` | runs the commands of the CI's Linux job (or `-- COMMAND...`) in a Docker container the size of GitHub's runner, on a copy of the tree as it is on disk; `--starved` is half a runner, `--image-only` builds the image of `packaging/ci/Dockerfile` ([In a container the size of GitHub's runner](#in-a-container-the-size-of-githubs-runner)) |
| `scripts/check-windows` | runs the CI's two Windows jobs (sync, lock, ruff, `pytest -n auto`, the smoke test of the wheel) on a real Windows in a VirtualBox machine of this computer, over SSH, on a copy of the tree as it is on disk; `--only NAME`, `-- ARGS` for pytest, `--snapshot NAME`; never a stage of `scripts/check`, and "not set up" (exit 2) where `NEOAPRS_WINVM` is not set ([On a real Windows](#on-a-real-windows)) |
| `scripts/flaky` | the hunt for tests that fail on some runs only (the stage `flaky` of `scripts/check`): 20 runs in the container of `scripts/check-in-container`, four settings (runner or starved, file order or shuffled), four containers at once, a table of what failed |
| `scripts/install-probe.py` | what the upgrade check of `scripts/check-installs` runs inside its container: `seed` gives the old daemon something to keep over its WebSocket, `verify` finds all of it in the new one and its version |
| `scripts/security-check` | the security checks that need a program of their own, one line each (the stages `security` and `audit` of `scripts/check`): no file or folder named `.secrets`, or `.secrets` with anything after it, tracked or left unignored; the script itself looks for the access token of the secrets manager in every commit `origin` does not have yet, in the index and in every tracked file (`--all-history`: in every commit there is); gitleaks reads the commits of the branch, their messages and the tracked files that are changed or staged; `php -l` and Psalm's taint reports over `server/`, shellcheck over the shell scripts and zizmor over the workflows (neither reads a settings file: a tracked one is a finding), the last two against `scripts/security-baseline.json` (`--update` writes it and never makes it larger unless `--allow-growth`); `--audit` is osv-scanner over both lock files, `--only NAME` one check ([`docs/security-checks.md`](security-checks.md)) |
| `scripts/security-tools` | fetches the programs of `security-check` (gitleaks, shellcheck, zizmor, osv-scanner, Psalm) from their GitHub releases into the build cache, each pinned by version and SHA-256 in the script; `--list` shows each with its version and whether it is there; nothing is installed on the system |
| `scripts/site-check` | compares the live project page with what is committed (every file the last commit has under `site/`, fetched over https, by SHA-256: not what is edited on the disk) and asks the private places (the stored support files and logs, PHP's settings, the version page's logs, each tracked `.htaccess` and PHP helper of `server/neo/`) whether they answer 403: `scripts/site-check https://neo.oh2gba.eu`, after `server/deploy.sh --site` and now and then; not a stage of the gate; exit 1 for a finding, 2 when it could not ask; a new endpoint under `server/neo/` goes in `PUBLIC_PHP` in the script |
| `server/deploy.sh` | uploads the version page, and with `--site` the project page, to the shared host: only regular files that git tracks, the others of the folders are named and skipped, and a tracked link, submodule or name with a control character stops `--site` and `--list` with exit code 2; `--list` shows the upload without the network |
| `scripts/coverage` | the Python suite under coverage.py with the table of every module and the total (`-- ARGS` for pytest); `--ui` is the page's vitest coverage ([Coverage](#coverage)) |
| `scripts/worktree-setup` | makes a fresh git worktree ready for `scripts/check`: `uv sync --frozen --all-extras` and a real `ui/node_modules` (`npm ci`, from the cache when it can), no symlinks |
| `scripts/install.sh` | a clone's wrapper of `neoaprs service install --data ./data --linger` (`--remove` is `service remove`): installs the daemon as a user service that starts at boot; the code is `neoaprs/cli/servicesystemd.py` |
| `scripts/doc-arch` | prints, writes (`--write`) or checks (`--check`) the tables of `docs/ARCHITECTURE.md` that are the data of the architecture test |
| `scripts/doc-settings` | prints, writes (`--write`) or checks (`--check`) the table of settings and the list of fixed values in `docs/manual/settings.md`, made from `neoaprs/config.py` and the constants of the program |
| `scripts/dup-check` | the duplication ratchet of the Python half: jscpd (from `ui/node_modules`) over `neoaprs/` and `tests/support/` against `scripts/dup-baseline.json`; `--update` tightens the baseline and never makes it larger |
| `scripts/errorcodes.py` | the part of `gen-protocol.py` that finds the daemon's refusals with a code in its source, each with the values it passes and the English sentence it writes (`ui/src/protocol/errors.json`) |
| `scripts/dup-compare.py` | the decision of `dup-check`: compares a jscpd report with the baseline, clone by the pair of files it joins |
| `scripts/css-unused.py` | the unused-class check of the page's style sheets (`ui/src/styles/*.css`), run by the stage `ui-lint`: lists the classes that a rule names and no `.vue`, `.ts` or `.html` file of `ui/` writes; the classes the page builds at run time (`hop-${kind}`, ...) are in its `PREFIXES`, with the file that builds each |
| `scripts/neoaprs-db` | a clone's wrapper of `neoaprs db` with `--data` set to the clone's `./data` (a `--data` of your own wins) |
| `scripts/make-icon.py` | draws the desktop app's icon, `neoaprs/desktop/icon.png` and `icon.ico` (they are committed; this is how they were made), and with `--site` the icons of the project page; needs Pillow: `uv run --with Pillow scripts/make-icon.py` |
| `scripts/screenshots.py` | takes the screenshots of the README and of the project page with Playwright, on a daemon of its own and a made-up day on the air ([the project page](#the-project-page)); the version beside Check now is hidden in them, so they are retaken when the page changes, not at each release |
| `scripts/demoscene.py` | the day on the air that `screenshots.py` plays: a KISS TNC on a TCP port of the loopback and a daemon on a clock moved back in time, with stations on the move, weather, messages, email, bulletins and objects, items and bulletins of our own |
| `scripts/mercury-bench` | the bench of APRS over the Mercury HF modem with no radio (Linux): two real Mercury instances cross-wired through named pipes and two daemons with the Mercury radio type attached to them, driven through their sockets: a beacon heard, a message acked with the time it took, the longest message acked; `--keep` keeps the folders of the run. Mercury has to be installed ([`docs/RADIOS.md`](RADIOS.md#mercury-hf-modem)) |
| `scripts/mercury-sim` | the simulation of an HF net with no radio (Linux): N real Mercury instances (5 by default) joined by one simulated channel (`tests/support/hfchannel.py`: every station hears the sum of the others with noise at the chosen SNR and, when asked, through a fading channel, a keyed station hears nothing, two keyed at once collide), a daemon on each, and a scenario checked against what the net must do: every beacon heard by every other station, the longest message around the ring acked, two stations keyed at the same moment losing both frames and a message between them going through after it, an ack lost on its way back (the retry acked, the message kept once), a station whose Mercury dies and comes back, a daemon stopped and started again with a message on its way, a weak link, a poor fading channel at 0 dB (some beacons lost, a message through on its retries, the busy detector's hold on a step in the noise), the first stations with the FM radio too on a KISS hub that is their FM air (`--fm N`: a message to a station heard on FM goes on FM, one to a station heard on HF alone over HF), the first station gating to a fake APRS-IS; `--daemon /usr/bin/neoaprs` runs it against an installed NeoAPRS, `--mercury PATH` against any Mercury, `--fading poor --snr 6` the whole scenario on a fading channel, `--first-port N` beside another run, `--report FILE` writes the counts as JSON, `--keep` keeps the folders. Exit 0 when every expectation held; about six minutes. The CI job `sim` and `scripts/check --stage sim` run it |
| `scripts/mercury-measure` | the measurements behind the numbers NeoAPRS fixes for Mercury ([`docs/mercury.md`](mercury.md)), on the same channel: `autobusy [--batch N] [--record F \| --replay F,F]` (the automatic channel-busy control against Mercury's fixed 14 dB, on the same recorded spectra: `--replay` judges recordings again with no Mercury), `frame` (one frame's levels and times: the RMS and the peak Mercury plays, PTT ON to PTT OFF, the delivery, the busy detector's lag and hang), `decode --snr 0,3,6 [--fading poor]` (frames delivered of 50 at each SNR), `acks` (two daemons: the time to each ack of N messages against the retry schedule), `vox --attack-ms 0,100 --snr 10,3 [--leadin-ms 150]` (frames delivered of 20 when a VOX radio loses the first milliseconds of every transmission, with Mercury's own frame or with the lead-in tone), `beacons` (no Mercury: the random pause against the beacons lost to overlaps over thousands of simulated hours); `--report FILE` writes JSON, `--first-port N` lets runs share the machine |
| `scripts/smoke.py` | the smoke test of an installed NeoAPRS, on any system: a fake KISS TNC on a TCP port plays the capture, the daemon runs on a temporary data folder, the page, its script and `/ws` are checked, the daemon is stopped as its system stops a program and must end with exit code 0, `NeoAPRS ended` and a database that passes `integrity_check`; `--command` names the installed `neoaprs` |
| `scripts/build-mercury` | builds the pinned Mercury (the pins in `neoaprs/mercury.py`) from Rhizomatica's source for Linux with ALSA as its one sound system (PulseAudio replaced by `packaging/mercury/pulse_stub.c`; the TCP listeners bound to the loopback by `packaging/mercury/loopback.patch` on either system, since Mercury has no bind option and no password on its ports; no hamlib, hidapi or OpenSSL) and lays out the folder `mercury/` (the program with RUNPATH `$ORIGIN/lib`, `lib/libasound.so.2`, `share/alsa`, `LICENSE`, `SOURCE.txt`, `dev/watterson_test` for the simulators), or on a Mac with CoreAudio alone, for macOS 14 and newer (the program, `LICENSE`, `SOURCE.txt`); `--windows`, on Linux, cross-compiles `mercury.exe` for 64-bit Windows with MinGW-w64 (`x86_64-w64-mingw32-gcc` and `-ar` on the `PATH`; the Makefile's own `OS=Windows_NT` build, hamlib and TLS left out, hidapi in for a CM108 chip, stripped and `-static`) and lays out `mercury/` with `mercury.exe`, the licences (Mercury, FreeDV, hidapi) and `SOURCE.txt` only, after reading the import table of the file (the DLLs of Windows and no other); `--tar` makes `mercury-<version>-linux-<arch>.tar.gz` (`-macos-arm64` on a Mac, `-windows-x86_64` with `--windows`) for the AppImage, the .deb, the macOS app, the Windows installer (`packaging/windows/bundle_mercury.py`) and the release workflow, `--install` (the default, not with `--windows`) puts the folder in `<venv>/tools/mercury` for the daemon run from the checkout; every run ends by starting the program (`-V`, `-z`, and on Linux once on its fifo backend to see its four ports (the UI interface's included) listen on 127.0.0.1 only). Needs gcc, make, patch, libasound2-dev (for Windows the cross compiler instead of gcc and libasound2-dev); 7 s on 32 cores. |
| `scripts/build-appimage` | builds `dist-appimage/NeoAPRS-<version>-x86_64.AppImage` from the wheel (`--wheel FILE`, else it builds one; `--out DIR`) and the Mercury tarball of `scripts/build-mercury --tar` (`--mercury FILE`, put in `usr/tools/mercury` without its `dev/` folder; `--no-mercury` for a developer's file without it, one of the two is required so that a release cannot lack it), or with `--retag FILE VERSION` the same file saying another version (for the update test); the tools it fetches are pinned by version and SHA-256 in the script and cached in `~/.cache/neoaprs-build` ([the AppImage](#the-appimage)) |
| `scripts/build-deb` | builds `dist-deb/neoaprs_<version>_<arch>.deb` for `--arch amd64` or `arm64` (this machine's by default; either can be made on either) from the wheel (`--wheel FILE`, else it builds one; `--out DIR`) and the Mercury tarball of the same architecture (`--mercury FILE`, put in `/opt/neoaprs/tools/mercury`; `--no-mercury`; one of the two is required); the CPython it fetches is pinned by version and SHA-256 per architecture in the script and cached in `~/.cache/neoaprs-build` ([the .deb](#the-deb)) |
| `scripts/build-macos-app` | builds `dist-macos/NeoAPRS-<version>-arm64.dmg` on a Mac with Apple silicon from the wheel (`--wheel FILE`, else it builds one; `--out DIR`) and the Mercury tarball of `scripts/build-mercury --tar` made on a Mac (`--mercury FILE`, put in `Contents/Resources/tools/mercury` without its `dev/` folder; `--no-mercury` for a developer's app without it, one of the two is required so that a release cannot lack it): the CPython it fetches is pinned by version and SHA-256 in the script and cached in `~/.cache/neoaprs-build`; the launcher is built from `packaging/macos/launcher.c`, the icon by `packaging/macos/make_icns.py`, the pruning is `packaging/appimage/prune.py --macos`, and everything is signed ad hoc ([the macOS app](#the-macos-app)) |
| `scripts/smoke-macos-app` | the smoke test of such an image on a Mac: the image opened and the app copied out, the signature verified, `--version`, the bundled Mercury (`Contents/Resources/tools/mercury/mercury -V` says the pinned version and loads the system's frameworks alone; `--no-mercury` for an app built without it), the install kind, `smoke.py`, the daemon with no radio, the launchd agent `service install` writes, the app on the offscreen platform; on a home folder of its own |
| `scripts/update-e2e.py` | the end-to-end test of Update now with the real files of a release (`windows OLD.exe NEW.exe`, `appimage OLD NEW [--extract-and-run]`): installs the old version, updates it from a fake release on the loopback over the page's socket and checks the new daemon, the data and the machine ([Update now end to end](#update-now-end-to-end)); on a CI runner only |
| `scripts/smoke-appimage` | the smoke test of such a file: `--version`, the bundled Mercury (`usr/tools/mercury/mercury -V` with its own ALSA configuration says the pinned version; `--no-mercury` for a file built without it), `smoke.py`, the daemon with no radio, the unit `service install` writes, the app on the offscreen platform; without FUSE it extracts the file and runs its `AppRun` |
| `scripts/release` | makes a release in one command (`scripts/release 0.9.2 [--dry-run] [--rerun] [--deploy]`): checks master, writes the version and the changelog section, builds the page only when `ui/` changed since the last tag, runs `scripts/check`, commits, pushes, waits for the CI run, tags and pushes the tag, waits for the release run, signs the draft's `SHA256SUMS` with the key `bws` reads from Bitwarden into memory and publishes it, checks the published release, its signature and its links, and with `--deploy` uploads the version page; run again after a failure it skips what is done; `--verify` checks a published release alone ([A release](MAINTAINING.md#a-release)) |
| `scripts/verify-download.py` | checks a file downloaded from a release by hand as Update now does (`FILE [--sums SHA256SUMS] [--signature SHA256SUMS.sig] [--version VERSION]`, the lists beside the file by default): the signature of `SHA256SUMS` with the program's public key, for the version the file's name carries (a file under a fixed name, `NeoAPRS-Setup.exe`, needs `--version`), then the file's SHA-256; nothing is fetched ([Update now](#update-now)) |
| `scripts/release-notes.py` | prints the section of `CHANGELOG.md` for a version (the newest section without one): the notes of the GitHub release, which the release workflow gives to `gh release create`; exit 1 when there is none |
| `scripts/replay` | a clone's wrapper of `neoaprs replay`: plays a capture as a KISS TNC on a TCP port (`--pty`: a pseudo-terminal), so that the daemon runs without the radio |
| `scripts/gps-replay` | a clone's wrapper of `neoaprs gps-replay`: plays a synthetic drive as a gpsd on a TCP port (2948 by default), so that the daemon beacons as a moving station without a car or a GPS ([Trying mobile operation without a vehicle](#trying-mobile-operation-without-a-vehicle)) |
| `scripts/gen-devices.py` | refreshes `neoaprs/devicedata.py`, the snapshot of the APRS device identification list (`tocalls.yaml` of aprsorg/aprs-deviceid, CC BY-SA 2.0) that names a station's device on its card: fetches the list (or reads `--from FILE`) and writes the module with the credit in its head; the only thing that fetches it, the daemon never does; `--check FILE` exits 1 when the module is not what that file makes |
| `scripts/gen-protocol.py` | writes `PROTOCOL.md` and the files of `ui/src/protocol/` (`schema.json`, `protocol.ts`, `lists.ts`, `errors.json`, `vectors.json`, and `ui/src/i18n/en/symbols.ts`) from `neoaprs/web/protocol.py` and the program's constants; run it after a change to a wire model or a limit (`tests/test_protocol.py` fails when they are stale) |
| `scripts/build-page` | builds the page from `ui/` (type check, Vite) into a temporary folder and swaps it in as `neoaprs/page/` with a rename: what the daemon serves and the wheel carries; run it after a change to `ui/` and commit `neoaprs/page/`. `--clean` forces `npm ci` |
| `scripts/node-modules-current.mjs` | the question `build-page` and `worktree-setup` ask: is `ui/node_modules` what `ui/package-lock.json` says (exit 0), or not (exit 1) |
| `scripts/fetch-worldmap` | a clone's wrapper of `neoaprs map --world`: makes the world map that ships with the program ([The world map](#the-world-map)) into `neoaprs/maps/`; run it to refresh the map, commit the two files |
| `scripts/fetch-basemap` | a clone's wrapper of `neoaprs map` with `--data` set to `./data` unless given: makes the base map as the page's Download button does |
| `scripts/capture` | a clone's wrapper of `neoaprs capture`: records the radio's serial port into a file byte for byte, to make test fixtures from a real radio |

In a clone, `scripts/replay`, `scripts/gps-replay`, `scripts/neoaprs-db`, `scripts/capture`, `scripts/fetch-basemap` and `scripts/fetch-worldmap` are the commands of the same name (`gps-replay` is `neoaprs gps-replay`) with the clone's `.venv` and
`./data`. `tests/test_service.py` and `tests/test_install.py` run `scripts/install.sh` against a fake HOME and a fake `systemctl`.

### Trying mobile operation without a vehicle

`scripts/gps-replay` (the command `neoaprs gps-replay`) is a gpsd that is not one. It listens on `127.0.0.1:2948`, prints that address as its first line, and tells a client that asks to watch (`?WATCH={"enable":true,"json":true}`,
as the daemon does) a TPV report a second and a SKY report every fifth, of a synthetic drive (`neoaprs/cli/gpstrip.py`): a car that stands still for 10 seconds, sets off, and goes round a rectangle of 1200 by 800 metres at
`--kmh` (50 by default), slowing for each corner and stopping for 90 seconds in the middle of the last leg, lap after lap. `--at LAT,LON` moves the start (60.43,24.145 by default), `--port` the port, and `--interval S` the
seconds between two reports, each a second of driving, so `--interval 0.2` drives five times faster than the clock. The drive begins when the first client asks to watch, and stands still while none does.

```
scripts/gps-replay                                        # in one terminal: prints 127.0.0.1:2948
scripts/neoaprs-db set gps/source gpsd                    # in another, on the data folder of the clone, before the daemon starts (it reads the settings at its start) ...
scripts/neoaprs-db set gps/host 127.0.0.1:2948
python -m neoaprs --data data --port socket://127.0.0.1:PORT      # ... with scripts/replay for the radio, or the real one
```

The same two settings are on the page's My station tab (the Position choice alone makes the beacon a moving station's; the car preset, `beacon/travel`, is the default). The daemon then reads the fixes as it would a gpsd's, shows them in the topic `gps`, moves its own row on the map, and beacons by SmartBeaconing: the first fix at once, a turn at
each corner, then by time (about every two minutes at 50 km/h), nothing while the car stands. With the replay stopped the fix is stale after two minutes and nothing is sent. Nothing is transmitted unless a TNC takes the
frames: use `scripts/replay` as the radio (it takes what the daemon writes) or switch `station/transmit` off to see only the page. `tests/test_gpsreplay.py` runs the same drive through the daemon's feed, the GPS service and the beacon.

## The simulators

Mercury is tried on three layers, none of which keys a radio:

| layer | what it is | what it proves | where it runs |
|---|---|---|---|
| the fake Mercury (`tests/support/fakemercury.py`, the world of `tests/support/mercuryworld.py`) | a Mercury that is not one: its two ports on the loopback, one air with the frame's time, the cut at 123 bytes, no carrier sense (two frames that overlap are both lost), the control lines; two or three daemons on it with their clocks in the test's hand, and an FM air beside it for a station with both radios | the daemon's side of the exchange at the test's pace: the beacon, a message and its ack, the retry after a collision, the hold while a frame is on the air, an ack lost on its way back, a station that never acks (the four attempts of the schedule, then failed), a daemon started again with a message on its way, the iGate, the frame cap, the choice of radio (`tests/test_mercury_world.py`, `tests/test_two_radios.py`) | the suite, every run, both systems |
| the channel (`tests/support/hfchannel.py`) | the air between real Mercury instances on Mercury's `fifo` audio backend: a thread at a sound card's pace that reads what each transmits and writes what each hears, the sum of the others through a gain, a delay and a Watterson fading channel per link (`Fading`: the CCIR 520-2 presets good, moderate, poor, flutter, as Mercury's own simulator has them), white noise at a chosen SNR in 3 kHz against the measured level of a frame, a keyed station deaf, two keyed in one block a collision | the channel itself: a tone heard at the gain with the asked SNR, the fading's power and spectrum, the collisions, the pace (`tests/test_hfchannel.py`, pure Python, no Mercury; the pipe tests on Linux only) | the suite |
| the real Mercury (`tests/support/realmercury.py`, `scripts/mercury-bench`, `scripts/mercury-sim`, `scripts/mercury-measure`) | the pinned Mercury built by `scripts/build-mercury --install`, two of them cross-wired (the bench) or N on the channel (the simulation), real daemons attached to them with `--hf-port`, driven through their pages' sockets | what Mercury really does with NeoAPRS's frames and in real time: the frame's 3.8 s, the ack in 10 s, the cut, the collisions, the busy detector, a Mercury that dies, a daemon restarted, a fading channel at 0 dB, both radios, the iGate, against the checkout or the installed .deb; and the numbers of [`docs/mercury.md`](mercury.md) | by hand, `scripts/check --stage sim`, and the CI job `sim` on every push to master |

What the real layer has shown so far: the simulation of five stations passed on every run here (142 s before the fading and restart steps, 375 s with them) and against the .deb in a bare Debian 12. It reports the channel's late blocks (a block that started a whole block late or more) and fails above one per mille of them (`LATE_BLOCKS_MAX_PER_MILLE` of `scripts/mercury-sim`: a busy runner stalls the pace now and then). The ports are the one thing two runs on one machine fight over (`--first-port`). A run's figures move by a second or so between runs (the daemons' tickers and
Mercury's 100 ms polls), which is why the scenario checks what happened and reports how long it took rather than holding the times. The fake Mercury's tests moved two things in the daemon's tests on the
way: a test that jumps the clock must do it while the radio is free (a wait that runs while the radio is held is moved on by that time, the frame's 3.8 s on the air), and the modem's tests each ask for
free ports from a base of their own, so that two of them side by side do not both find 8100 free.

## Packaging and releases

What a release holds, on <https://github.com/oh2gba/neoaprs/releases>: `NeoAPRS-Setup-<version>.exe` (the Windows installer),
`NeoAPRS-<version>-x86_64.AppImage`, `NeoAPRS-<version>-arm64.dmg` (the macOS app), `neoaprs_<version>_arm64.deb` and `neoaprs_<version>_amd64.deb`, the installer, the AppImage, the macOS app and the two packages again under fixed names,
`neoaprs-<version>.tar.gz` (the sdist, unadvertised, for packagers), the wheel and `install.sh` (the update of a copy installed with the install line before 0.16 runs `releases/latest/download/install.sh`, which installs the wheel) `SHA256SUMS` and `SHA256SUMS.sig` (its signature, made by `scripts/release`), 15 files, with build provenance attached to each file built
(`gh attestation verify FILE --repo oh2gba/neoaprs`). `.github/workflows/release.yml` makes all of it when a tag `v*` is pushed, and nothing is built by hand.
The steps to take around it are in [`docs/MAINTAINING.md`](MAINTAINING.md#a-release); `scripts/release` takes them in one command.

The installer, the AppImage, the macOS app and both packages carry the Mercury HF modem of the version `neoaprs/mercury.py` pins, so that nothing is fetched or installed when it is used, each built from the pinned source: the `mercury-windows` job's cross-compiled `mercury.exe` in `bin\mercury\`
of the Windows app, the `mercury` job's build in `usr/tools/mercury` of the AppImage and `/opt/neoaprs/tools/mercury` of the packages, and the `macos` job's own build (CoreAudio alone) in
`Contents/Resources/tools/mercury` of the macOS app (`neoaprs/bundled.py` finds it in each: `<sys.prefix>/tools`). All of them bind their ports to the loopback (`packaging/mercury/loopback.patch`), so no system has a firewall rule or a firewall check for Mercury.

| job | where | what |
|---|---|---|
| `verify` | Linux, tags only | in seconds, before anything is built: the tag without the `v` is `VERSION` in `neoaprs/__init__.py`; `CHANGELOG.md` has a section for that version and nothing left under `## Unreleased`; `neoaprs/page/` is what `ui/` builds (a fresh `scripts/build-page` changes nothing; the page has no version in it); the commit is on `master`; and `ci.yml` has a successful run for it (a run still going is waited for, 30 seconds at a time, 20 minutes at most; none, or a red one, fails) |
| `wheel` | Linux | `uv build` (the sdist, and the wheel built from it); the wheel is installed into a fresh environment and `scripts/smoke.py` runs against it |
| `windows` | Windows | the wheel and the locked dependencies (`uv export --frozen --no-dev`, with the extra `app` and the group `pyinstaller`) go into a build environment, every file installed by the hash the lock holds (`--require-hashes`), PyInstaller from its source with them (it is in a group of the lock, not a dependency of the project). `packaging/windows/neoaprs.spec` freezes them into `dist\NeoAPRS` with three programs, `neoaprs.exe` (console), `neoaprsw.exe` (no console: the daemon) and `neoaprs-app.exe` (no console, with the icon: the desktop app), and the page, the icon and the sample capture as data. `bundle_mercury.py` puts the tarball of the `mercury-windows` job in `bin\mercury\` (it takes nothing from the net: it refuses a tarball that is not the pinned Mercury's, by its name, its `SOURCE.txt` and its files): `mercury.exe`, the licences and `SOURCE.txt`. `mercury.exe -V` must say the pinned version, and `packaging/windows/smoke_mercury.py` starts it with no sound card (`-x null`) and reads `netstat -ano`: its four ports (with the UI interface on) must be listening, on 127.0.0.1 and on nothing else; before the installer and again from the installed app. The folder is smoke tested. Inno Setup (`choco install innosetup`) makes the installer from `packaging/windows/neoaprs.iss`; it is run silently (`/VERYSILENT /SUPPRESSMSGBOXES /CURRENTUSER`), and the files, the Start menu entries and the Run key (`neoaprs-app.exe --tray`) are checked. `scripts/smoke.py` runs against `%LOCALAPPDATA%\Programs\NeoAPRS\neoaprs.exe`, `open` and `stop` are tried on a data folder of their own, and `neoaprs-app.exe --tray` is started silently and must start a daemon whose page answers, refuse a second app and end together with its daemon at `neoaprs stop` (started over a daemon that was running, it attaches and leaves it running at `--quit`). The silent uninstall, with the app running, must take the Run key, the files, the app and the daemon away and leave `%LOCALAPPDATA%\NeoAPRS`. Last, [Update now end to end](#update-now-end-to-end): a second installer of the next version is built from the same environment with only `VERSION` changed, and the installed version updates itself to it |
| `mercury-windows` | Linux in a `debian:trixie` container, as Rhizomatica's own release workflow builds its Windows zip | `scripts/build-mercury --windows --tar` cross-compiles the pinned Mercury for 64-bit Windows with MinGW-w64 (`gcc-mingw-w64-x86-64`, `mingw-w64-x86-64-dev`, `mingw-w64-common`) and checks the import table of `mercury.exe` (the DLLs of Windows alone); the job checks the tarball's name and files and that the program says the pinned version; the tarball is the artifact `mercury-windows`, which the `windows` job takes (build material, not a file of the release). The program cannot be run on Linux: the `windows` job starts it |
| `mercury` | Linux in an `ubuntu:22.04` container (glibc 2.35, the floor the AppImage and the .deb document), a runner for each architecture (`ubuntu-latest`, `ubuntu-24.04-arm`) | `scripts/build-mercury --tar` builds the pinned Mercury from source; `mercury -V` must say the pinned version; the tarball is the artifact `mercury-amd64` or `mercury-arm64`, which the two jobs below take (it is build material and not a file of the release) |
| `appimage` | Linux (`ubuntu-22.04`: glibc 2.35, the oldest the Qt wheels run on) | `scripts/build-appimage --wheel` on the wheel of the `wheel` job and `--mercury` on the tarball of `mercury-amd64`; then `scripts/smoke-appimage` on the file, which also starts the Mercury inside |
| `appimage-update` | Linux (`ubuntu-latest`) | [Update now end to end](#update-now-end-to-end) of the file of the `appimage` job, to a copy of it with only `VERSION` changed (`scripts/build-appimage --retag`): once mounted with FUSE, once with `--appimage-extract-and-run` |
| `macos` | macOS (`macos-latest`, Apple silicon) | `scripts/build-mercury --tar` builds the pinned Mercury from source on the Mac (CoreAudio alone, for macOS 14 and newer; Rhizomatica's own universal build asks for macOS 26); `scripts/build-macos-app --wheel` on the wheel of the `wheel` job and `--mercury` on that tarball makes `NeoAPRS.app` and its disk image, signed ad hoc; then `scripts/smoke-macos-app` opens the image and runs the app: the signature, `--version`, the Mercury inside, the install kind (`macos-app`, `arm64`), `scripts/smoke.py` against the launcher, the daemon with no radio, the launchd agent `service install` writes (it must run the Python inside the bundle) and the app on the offscreen platform |
| `deb` | Linux, a runner for each architecture (`ubuntu-latest` for amd64, `ubuntu-24.04-arm` for arm64) | `scripts/build-deb --arch ARCH --wheel` on the wheel of the `wheel` job and `--mercury` on the tarball of `mercury-ARCH`; then, on that runner, `sudo apt install ./neoaprs_<version>_<arch>.deb`, `neoaprs --version`, the kind the package detects (`deb`, with the right architecture), `scripts/smoke.py` against `/usr/bin/neoaprs` run by the package's own Python, `service install` with a `HOME` and a `systemctl` of the test's own (the unit must start `/opt/neoaprs/bin/python3`), an install over itself (the upgrade message) and `apt remove` (the files go, the data stays). The bundled `/opt/neoaprs/tools/mercury/mercury -V` must say the pinned version, and in a `debian:bookworm-slim` container that has no ALSA library the package is installed and `ldd` of Mercury finds no library missing and the bundled `libasound.so.2`, and `mercury -V` and `mercury -z` run with the package's own ALSA configuration |
| `assemble` | Linux | after every job above (a failed update test stops the release here): the six artifacts of the release (by name: never the logs a failed update test left) in one folder, the wheel taken out (it is build material: the supported installs are the ones that carry Mercury), `SHA256SUMS`, and the release notes (`scripts/release-notes.py`: the section of `CHANGELOG.md` for the version) |
| `release` | Linux, tags only | attests the files (`actions/attest-build-provenance`) and runs `gh release create v<version> --verify-tag --draft` with the notes and the 14 files; the release stays a draft, and `scripts/release` signs its `SHA256SUMS`, uploads `SHA256SUMS.sig` (the 15th file) and publishes it, so that no half of a release and no unsigned one is ever seen; a version with a dash (`1.0.0-rc1`) is marked a pre-release, which GitHub never makes `latest`. When the draft of the tag is there already (an earlier run got this far), its files are written over (`gh release upload --clobber`), its `SHA256SUMS.sig` deleted and the notes set again; a release that is published is refused, never written over. The only job with `contents: write` |

Started by hand on a branch (Actions, release, *Run workflow*, or `gh workflow run release.yml --ref BRANCH`) it is a build for testing: the same builds and checks on that
branch, `verify` and `release` skipped, nothing published, and the files kept for a few days as the artifacts of the run (`gh run download RUN_ID`; the run is named "build for testing" in the list;
[`docs/MAINTAINING.md`](MAINTAINING.md#a-build-for-testing) says how to get the files). Started by hand on a tag (`gh workflow run release.yml --ref v<version>`) it is the tag's run again: verified and
published like a pushed tag.

A tag run that failed is run again, never retagged: *Re-run failed jobs* (`gh run rerun RUN_ID --failed`) for a runner, a download or a flaky test (every artifact
is uploaded with `overwrite`, and `assemble` picks the release's artifacts by name, so an attempt after a failed one works); a failure that needs a change in the
code gets the change on `master` and a tag of the next number. The tag of a release stays on the commit it was made for, and the same tag never names two commits.

Nothing signs the installer: Windows SmartScreen says "Windows protected your PC" for an unsigned file the first times, which the README says.

### The world map

The page has a map from the first second, with no download: `neoaprs/maps/basemap-world.pmtiles` is the world to zoom 4 (6 MB: coastlines, borders, forests, the names of countries and cities), with `neoaprs/maps/basemap-world.json` beside it saying which Protomaps daily build it was cut from. It is
package data, so every package has it where the code is: the wheel (and with it the AppImage's and the .deb's site-packages) as `neoaprs/maps/`, and the Windows app, where PyInstaller puts the package's data files (`collect_data_files("neoaprs")` in `packaging/windows/neoaprs.spec`), as
`_internal\neoaprs\maps\`. `neoaprs/worldmap.py` looks in the package beside the code first, then (for a frozen program) in `sys._MEIPASS` and in `_internal` next to the executable. Nothing is copied to the data folder: the daemon serves the shipped file as
`/basemap-world.pmtiles` when the data folder has no good file of that name (one that an older NeoAPRS made, to zoom 5, wins), and the job of Settings, Map, Download makes no world map where one ships. `.gitignore` lets this one `.pmtiles` file in, and `tests/test_package.py` holds that the wheel carries it.

The file is committed, and is not made by the release workflow. Why: a daily build is kept for a short while on build.protomaps.com, so a pinned build cannot be fetched again for a rebuild of an old tag, and a release that depends on that server being up (and on a map that is still there) could not be repeated;
a wheel built from a clone or from the sdist would have no map; and the map changes slowly (continents do not move), so the 6 MB are in history once a year at the most. To refresh it run `scripts/fetch-worldmap` (the latest build, or `--build YYYYMMDD`): it cuts the whole world to zoom 4 out of the build with the program's own cut (`neoaprs/pmtilescut.py`), refuses a world over 8 MB before a tile is fetched, and writes the two files. Check the result on the page at the world's zoom and at a city's, then commit both. Zoom 5 is 15 MB, so zoom 4 it is; the page draws the file magnified beyond its zoom until the detailed map is there.

The detailed map is made without a click (`neoaprs/services/mapauto.py`): the setup guide sends the place as its Position step is left (`set_config`; `map_wanted` when the daemon has the place), and a new place or that command begins the job of the Download button for `map/radius_km` at `map/maxzoom`, unless the detailed map that is there covers nine tenths of the radius round the place. The row `map/auto` of the settings table says whether a job begun is still owed (`wanted`: tried again at the next start; `done`).
Only the daemon switches it on (`Controller(auto_map=True)` in `neoaprs/daemon.py`), so no test or script starts a download of its own accord. A job that fails (no connection) stays `wanted`, the page is told (`later` of the topic `map`) and the next start of the daemon tries again; the operator's Cancel makes it `done`.

### The AppImage

`scripts/build-appimage` builds it from the wheel: the relocatable CPython of python-build-standalone, the locked dependencies of the extra `app` (`uv export`),
the wheel, and appimagetool with its static runtime, each tool pinned by version and SHA-256 at the top of the script. `packaging/appimage/prune.py` takes out
what is not run (tests and Tk of CPython, Qt but the web engine and the modules the app imports); `AppRun` and `neoaprs.desktop` are beside it. `$APPIMAGE`
counts only for an interpreter inside `$APPDIR`, and the unit, `neoaprs open` and the start at sign-in start the AppImage file and not the mount. Mercury is unpacked from the tarball of
`scripts/build-mercury --tar` into `usr/tools/mercury` (the simulators of its `dev/` folder are left out); `AppRun` is not involved: the daemon starts the program with the ALSA configuration of its own folder.

### The macOS app

`scripts/build-macos-app` builds it on a Mac with Apple silicon, from the wheel: the relocatable CPython of python-build-standalone for `aarch64-apple-darwin` (pinned by version and SHA-256 at the top of the script, the
same release as the AppImage's), the locked dependencies of the extra `app` (`uv export`) and the wheel, laid out as `NeoAPRS.app/Contents/Resources`, the Python's own prefix (`bin/`, `lib/`), so that `<sys.prefix>/tools`
of `neoaprs/bundled.py` is `Contents/Resources/tools`, where Mercury goes from the tarball `scripts/build-mercury --tar` made on the same Mac (CoreAudio alone; its `dev/` folder left out). `Contents/MacOS/NeoAPRS` is
`packaging/macos/launcher.c`, a small C program with Python embedded through libpython: it tells Python its home (`Contents/Resources`), makes `sys.executable` the `bin/python3.13` there (what the app starts its daemon
with, and what the launchd agent of `service install` runs), and runs `-m neoaprs` with the arguments it was given, `app` with none, like the AppImage's `AppRun`; it is embedded and not a script that execs Python so
that the process is the bundle's own, which is what the Dock, the menu bar and the microphone prompt go by. It is isolated like `python -I` and writes no bytecode (every module is compiled in advance, because the
signature seals the bundle). `packaging/appimage/prune.py --macos` takes out what is not run, as for the AppImage, in the layout of the macOS wheels (frameworks, `.dylib` plugins, the web engine's helper and locales
inside its framework), and makes the frameworks the bundles codesign and the system expect: the wheels ship them flat, with everything under `Versions/A`, `Resources` and `Helpers` copied a second time
at the top and neither `Versions/Current` nor the link to the library, so the copies go and the links are made. `Info.plist` comes from `packaging/macos/Info.plist.in` (the identifier `eu.oh2gba.neoaprs`, the launchd agent's label; macOS 14 as the floor, the Qt wheels'), the icon from the Windows one's PNG
frames (`packaging/macos/make_icns.py`, no tool of a Mac needed), and the microphone sentence macOS shows when the HF radio's sound card is first opened is in `packaging/macos/lproj/` in the eight languages of the page.
The Mach-O files that are nobody's program (`packaging/macos/sign_list.py`: not the launcher, the helper's program or a framework's library, which codesign would take for their bundles), then the web
engine's helper app with the entitlements Qt ships for it, then the frameworks and then the bundle are signed ad hoc (`codesign --sign -`), from the inside out, which Apple silicon requires of code it runs and which is all
there is without an Apple developer account: the first open is a right-click and Open ([the manual](manual/install.md#macos)). `hdiutil` makes the disk image with the app and a link to Applications. The app is for Apple silicon alone, because
python-build-standalone has no universal CPython; its file is `NeoAPRS-<version>-arm64.dmg`, named like the AppImage. `scripts/smoke-macos-app` tries the image. The install kind is `macos-app`, told by the Python's prefix
being `Resources` of a bundle with its `Info.plist` (`neoaprs/cli/installkind.py`); the update window names the Mac's file and the steps, and the daemon does not replace the bundle itself yet
(`neoaprs/services/selfinstall.py` says why). `tests/test_macos_app.py` builds and runs the launcher on Linux against the venv's Python, prunes a made-up tree, makes the icon and reads the scripts' promises.

### The .deb

`scripts/build-deb` builds it from the wheel with no debhelper: the CPython of python-build-standalone for the architecture (pinned by version and SHA-256 in
the script), the locked dependencies as wheels for that platform (`uv pip install --python-platform`, so either architecture is made on either kind of machine),
the wheel, the files `packaging/deb/` holds (`control.in`, `postinst`, `postrm`, `copyright`, the `neoaprs` command),
`packaging/appimage/prune.py --python-only` for what is not run, the bytecode of everything compiled in advance, and `dpkg-deb`. The result is the same bytes
each time for the same inputs (`SOURCE_DATE_EPOCH` is the last commit's time unless set). It carries the manual (`docs/manual/`), the README and the changelog
as documents, and Mercury (the tarball of `scripts/build-mercury --tar` for the architecture, in `/opt/neoaprs/tools/mercury`), whose program counts in the glibc the package asks for and whose
licences are named in `packaging/deb/copyright`.

Python is started with `-I`, so that a user's `PYTHONPATH` and user site are not mixed in. The upgrade restarts the service of each logged-in user with
`systemctl --user --machine=UID@.host restart neoaprs`, which writes nothing in their homes.

### The Windows installer

Inno Setup, `packaging/windows/neoaprs.iss`, per user with no administrator rights and no UAC prompt, and nothing done to the Windows Firewall: the Mercury it carries binds the loopback, so there is no rule to add or to remove (a block rule that an earlier version added stays, harmless). The tasks, the Start menu group and the uninstaller are
described for the user in [the manual](manual/install.md#windows). The uninstaller runs `neoaprs-app.exe --quit`, `neoaprs.exe stop` and
`neoaprs.exe service remove`, and installing over an older version runs the first two before Setup looks for files in use (its `PrepareToInstall`), so that the user is not asked to close the app and the daemon and the daemon ends cleanly; the same runs again right before the files are replaced, as the safety net. The app is `neoaprs-app.exe` and not
`NeoAPRS.exe`: Windows file names ignore case, and that would be `neoaprs.exe`, the console program.

### Update now

The update the daemon does itself, on a click of the page only (the command `update_now`), for the Windows installer and an AppImage (`neoaprs/services/selfupdate.py`,
`neoaprs/services/selfinstall.py`). The other kinds have the steps on the page (`ui/src/lib/update.ts`); the macOS app is among them for now, its disk image offered as a download (`neoaprs/updateasset.py`
names it), since swapping the bundle under a daemon that imports its modules lazily from it, and restarting the app through launchd, has not been tried on a Mac.

1. `update_now` names a version, which must be the one the update check announced (the `update` of `status`); the command goes over the page's socket, which only
   a page of this computer or one that has logged in with the access key has (`neoaprs/web/access.py`), like every command that changes the daemon.
2. The file for this copy (`neoaprs/updateasset.py`: `NeoAPRS-Setup-<version>.exe`, `NeoAPRS-<version>-x86_64.AppImage`), `SHA256SUMS` and `SHA256SUMS.sig` are fetched from
   `https://github.com/oh2gba/neoaprs/releases/download/v<version>/`. The address is built from the version alone, which must be digits and dots with an
   optional `-rc1`; nothing else of the version page's answer is used (its `url` is never downloaded). A download is https only and may be redirected only to
   `objects.githubusercontent.com` and `release-assets.githubusercontent.com`, where GitHub keeps the files (`neoaprs/updatedownload.py`); TLS is checked by
   the system's certificates. `SHA256SUMS` and its signature come first: a list whose signature does not hold, or that does not name the file once, installs nothing
   (the signature below).
3. The file is written as `<name>.part` while its SHA-256 is computed, with the percent in the topic `update` and `update_cancel` seen between two pieces. A
   SHA-256 that is not the one the signed `SHA256SUMS` gives deletes the file and installs nothing.
4. The installer of the kind puts it in place: on Windows the installer runs silently and detached from the daemon (`installer_argv`: `/VERYSILENT
   /SUPPRESSMSGBOXES /NORESTART /NOCLOSEAPPLICATIONS`, from `update/` of the data folder, where the installer of an earlier update is deleted first, the log in
   `update/install.log`, `/NEOAPRSRESTART=app` when the app holds its lock of the data folder, else `daemon`, and `/NEOAPRSDATA`);
   `packaging/windows/neoaprs.iss` ends the app and the daemon of that folder before it replaces a file and starts again what was running. An AppImage is made
   executable and renamed over the file it runs from (`$APPIMAGE`), the old one kept as `.old` (a hard link, else a copy); the daemon writes
   `neoaprs.restarting` and `neoaprs.stop` into the data folder, ends, and the process runs the file again with its arguments (`neoaprs/selfreplace.py`:
   `execv`, after the descriptors above stderr are closed, with `APPIMAGE_EXTRACT_AND_RUN=1` when `$APPDIR` is no mount point, an AppImage started with
   `--appimage-extract-and-run`, whose runtime takes the flag away; a file that cannot start puts the old one back). The new version deletes the note and the
   `.old` once it runs; the desktop app, which ends with its daemon, waits for it while the note is fresh. A folder the user cannot write offers no Update now.
5. Still running five minutes later, the update says it did not restart.

**The signature.** Update now believes `SHA256SUMS` only with the project's signature, so that whoever can publish a release on GitHub (a stolen account or token) cannot
make a copy of NeoAPRS install a file of his own. The key is an Ed25519 key whose secret half is in Bitwarden Secrets Manager, on no runner of GitHub; its public half,
the base64 of its 32 raw bytes, is `PUBLIC_KEY` of `neoaprs/updateasset.py`, the only place the program has it (`tests/test_updatesign.py` pins it). The release workflow
leaves the release a draft; `scripts/release` (the step sign) reads the key with `bws secret get` into memory, signs, uploads `SHA256SUMS.sig` (the base64 of the 64-byte
signature), checks it with the public key and publishes the release ([A release](MAINTAINING.md#a-release)). What is signed is the line `NeoAPRS SHA256SUMS v<version>`
followed by `SHA256SUMS` as it is (`signed_message`). The version is bound there and not in the list: the list stays exactly what `sha256sum --check --strict` and the
programs from before the signature read, and the version the check holds it to is the one Update now asked for, never one read from the downloaded bytes, so the signed list
of an older release offered as the newer one does not hold. The list must then name the file once, with no line that is not a checksum line (`signed_checksum`). Every way
this can fail (no signature, one that is not 64 bytes of base64, one made with another key or over another list or for another version, a list that is empty, names the
file twice or not at all) is the one problem `unverified`: the page says the update could not be checked and to download it from the project page, the log has the cause,
and the file is never downloaded. `scripts/verify-download.py` does the same check by hand for a downloaded file.

Programs installed before the signature (0.18.2 and older) know nothing of `SHA256SUMS.sig`: they fetch `SHA256SUMS` and the file and compare the SHA-256, as before, and
update to a signed release like to any other, since the list is unchanged (`tests/test_updatesign.py` reads a release's list with their reader). Once updated, a copy
believes only signed lists. `NEOAPRS_UPDATE_KEY` gives the end-to-end test a key of its own, and only together with the fake release of `NEOAPRS_UPDATE_FROM`.

The build provenance of the release's files (`gh attestation verify FILE --repo oh2gba/neoaprs`) is not checked, since it needs `gh`: it is a possible later
step. `NEOAPRS_INSTALL_KIND` (a simulated kind, for the screenshots) turns the last step into a rehearsal that deletes the file. `NEOAPRS_UPDATE_FROM` takes
the release folder of a fake server on `127.0.0.1` or `localhost` instead of GitHub's, only with a simulated kind or with `NEOAPRS_UPDATE_TEST=1` (the test
below); any other address is ignored. No unit test reaches the network: the downloads have a stand-in opener and the job a fake release
(`tests/support/fakerelease.py`).

#### Update now end to end

`scripts/update-e2e.py` is Update now with the real files of a release, on the release workflow's runners only (it installs and replaces files): in every dry
run and for every tag, so that an updater that does not work stops the release. The newer version is the same build with nothing changed but `VERSION`, the
patch number plus one and `-e2e` (`0.6.8-e2e` for 0.6.7): on Windows a second PyInstaller folder and installer from the build environment, for the AppImage
`scripts/build-appimage --retag FILE VERSION`, which unpacks the file, changes `VERSION` and packs it again with the pinned runtime.

1. The old version is put in place: the installer of the `windows` job, run silently with no task (no start at sign-in, no desktop shortcut), or the AppImage
   copied into a folder of its own, with a home folder of its own.
2. Its data folder (a temporary one, with a blank in its name) gets the settings a user would have: `serial/port` is a fake KISS TNC on the loopback (the
   one of `scripts/smoke.py`), `web/port` a fixed port, `update/url` the fake version page. The daemon is started with `NEOAPRS_UPDATE_TEST=1` and
   `NEOAPRS_UPDATE_FROM` set to the fake release server, which serves `v<version>/<file>` and `v<version>/SHA256SUMS` like GitHub.
3. Over `/ws`, as the page does: the hello names the old version and the install kind, the TNC is connected and packets came, Update now is offered;
   `update_check` finds the new version, `update_now` names it, and the topic `update` is followed until the daemon closes the socket. It must reach
   `restarting` and never `error`, and the fake server must have been asked for `SHA256SUMS` and then the file.
4. A daemon must come up by itself on the same page port and say the new version in its hello, connect to the same fake TNC (the settings came from the data
   folder) and have at least the packets the old one had. On Windows the old daemon has ended with exit code 0, the installer's log (`update/install.log` of the
   data folder) has the silent command line of Update now and `Installation process succeeded`, the installed `neoaprs.exe` and Windows' list of programs say
   the new version, and `update/` holds that installer and its log alone (an earlier installer the test put there is gone). For the AppImage the same process
   goes on as the new version, the file in the same place is the new one (its SHA-256), executable, and neither `.old` nor `.part` is left beside it.
5. After a stop, the log has the start and the end of the old version and then of the new one and ends with `NeoAPRS ended`, every setting is still there,
   and nothing else changed: on Windows the Run key, the Start menu entries, the desktop and `%LOCALAPPDATA%\NeoAPRS`, and no program of NeoAPRS or
   installer is left running; for the AppImage the home folder and the folder of the file.

On a failure the work folder (the logs, the data folder, the installer's log; not the installers and AppImages) is an artifact of the run,
`update-e2e-windows-logs` or `update-e2e-appimage-logs`.

### The desktop app's tests

The logic runs with no toolkit (fakes of the window and the tray; `tests/README.md`). The Windows shell is tried against stand-ins for pywebview, pystray and
Pillow, and the Qt shell headless with the real PySide6 (`QT_QPA_PLATFORM=offscreen`, skipped without the extra). A real tray, real Wayland or X11 windows and a
real WebView2 are what only a desktop can try. The icon is `neoaprs/desktop/icon.png` (the tray) and `icon.ico` (the Windows programs), made by
`scripts/make-icon.py`. The app picks Qt on Linux and macOS and pywebview with pystray on Windows because pywebview's Qt backend would need the tray from a
library that does not share Qt's event loop on Linux, while Qt has both.

### The project page

`site/` is the project page, <https://neo.oh2gba.eu/> (uploaded there by `server/deploy.sh --site`, with `server/neo/`: the host's `.htaccess`, the page-view endpoint, Send logs and the sked board's endpoint), (the old address <https://oh2gba.github.io/neoaprs/> redirects there; `site/frequencies.json` is the list of suggested frequencies the HF radio's box shows, edited by hand and uploaded with the site, no release: at most four entries `{"band": "40 m", "dial": "7.0541 MHz USB"}`): plain files (`index.html`, `style.css`, `site.js`, the icons and `shots/`), a system font
stack, no external file, tracker or framework, and a Content-Security-Policy that lets it load its own files only. `.github/workflows/pages.yml` publishes the
redirect of the old address (`packaging/pages-redirect/`), by hand. `robots.txt` and `sitemap.xml` are the site's own, and every picture has a `.webp` beside its `.png` (made with the thumbnails), which the page offers first. To look
at it: `python -m http.server --directory site`.

The screenshots are made by `scripts/screenshots.py`. It starts a daemon of its own on a temporary data folder, plays a day on the air into it
(`scripts/demoscene.py`: made-up calls round Helsinki, a car, a hiker and a boat moving, two weather stations, messages that are acked, retried or fail,
bulletins, email, the beacon, and objects, items and bulletins of your own) through a KISS TNC on a TCP port of the loopback, and takes the shots with Chromium
at 1440 x 900 and 390 x 844, each in the light and the dark scheme (`NAME-dark.png`).

- They go to `site/shots/`, with `thumbs/` for the gallery and `og.png` for the link preview. `map`, `weather`, `messages`, `beacon`, `objects`, `bulletins` and
  `setup` are copied to `docs/screenshots/` for the README.
- The close-ups of the delivery chain (`chain.png`, `chain-failed.png`) are taken at twice the pixels.
- The "NeoAPRS `<version>`" beside Check now is hidden in every shot (an inline style sheet the script adds to the page; the space stays, so nothing moves), so that a release by itself makes no shot old: the shots are retaken when the page changes in a way they show. The one shot that names versions is `update.png`: the made-up newer one, which the script makes from `VERSION` (the patch number plus one) and not from a constant kept by hand, and the installed one in the dialog's "You have NeoAPRS ...".
- `update.png` is taken from a second daemon of its own on a copy of the data folder: a version page on the loopback says that newer version is out and `NEOAPRS_INSTALL_KIND` plays a Windows install, so that **Update now** is offered (and would only rehearse). `beacon-de.png` is the My station tab of a browser that speaks German. `beacon-rx.png` and `phone-beacon-rx.png` are taken from another daemon of its own on a copy of the data folder with `station/transmit` set to `false` and `beacon/interval_min` set to `0` (receive only, with its badge in the header, and the beacon off: the beacon status reads Beacon off and what belongs to the beacon is grey). `nearby.png` is the Nearby tab with the digipeater OH2RCH-2 selected, its range circle fitted on the map. `beacon-gps.png` is the My station tab of a moving station: a daemon of its own on a copy of the data folder with `gps/source` `gpsd`, `gps/host` the address of a `neoaprs gps-replay` that the script starts on the loopback (gpsd's port 2947 when it is free, else any free one) and `beacon/interval_min` 30 (On, SmartBeaconing), taken about 80 seconds after the start, when the car has made its first turn. `settings-hf.png` and `stations-hf.png` are taken from a daemon of its own on a copy of the data folder with the HF radio on as the Dummy HF radio (`hf/enabled`, `hf/profile`), started with no player on its PATH so that its frames are not played through the machine's speakers: the Radio group with the HF box opened by its arrow, and the Stations table over a map zoomed out to Warsaw once the six made-up stations have beaconed (within two minutes of the start). `station-details.png` is the card of a station that runs a Kenwood TH-D74 (the destination call `APK004` of the made-up day) with Details open, and `settings-tnc.png` the TNC group of the Settings tab opened by its arrow. Every daemon of the shots is given a search pattern that matches nothing (`NEOAPRS_SERIAL_PATTERN`), so that no serial port of the machine is ever opened.
- The three Settings shots (`settings.png`, `settings-tnc.png`, `settings-web.png`) end on a whole group of the tab, so that no row is cut at the edge of the panel: the script scrolls the group they are about to the top of the panel (the tab gets room at its end for that) and does not draw the first group that would not end in the view (the panel's own colour shows below the last whole one). The crops of `site/style.css` that show them (`.crop.pane.tnc`, `.crop.pane.web`) end in the gap after a group too; they are looked at again when the tab gets a group or a row.
- The 760 px panel of the shots holds all nine tabs, also with the badges of the made-up day; the tab bars of the narrower panels (560 and 640 px) have the More button, and a phone's has the Map button, the tabs that fit and More.
- The network access is on in the demo folder with a key made at random for the run, and the Settings shot shows a made-up key and made-up addresses instead of
  the daemon's own. Nothing touches a radio.
- The street map is copied from `data/basemap.pmtiles` (or `--basemap`), which is only read.

```bash
uv run --with playwright --with pillow python scripts/screenshots.py                    # all of them
uv run --with playwright --with pillow python scripts/screenshots.py --only map messages
uv run --with playwright --with pillow python scripts/screenshots.py --chromium PATH --no-sandbox   # a browser Playwright did not install
```

## The support bundle

A user with a problem sends one zip ([the log and the support bundle](daemon.md#the-log-and-the-support-bundle) says what is in it; the manual's [support.md](manual/support.md) is for the user). The parts, all in the delivery layer except the SQL:

| module | what it is |
|---|---|
| `neoaprs/cli/supportbundle.py` | the zip as a file: the name, the deflate writing under a temporary name, the secrets taken out of every member, the log files and their budget |
| `neoaprs/cli/supportgather.py` | the gatherers, each a function that returns the text of a member: settings, logs, the doctor, the database, the packets, the journal |
| `neoaprs/cli/supportsummary.py` | `summary.txt`: `Facts` (what was found; any part may be missing) and its layout, and the warnings and errors of a log in groups of the same message |
| `neoaprs/cli/supportreadme.py` | `README.txt`, with the one line for each file (`FILE_HELP`) and what is left out |
| `neoaprs/cli/supportmake.py` | `make_bundle` runs the gatherers (a failed one is `<name>.error.txt`), finds the Desktop and starts the file manager; the daemon, the command and the tray all call it |
| `neoaprs/cli/supportcmd.py` | `neoaprs support` |
| `neoaprs/cli/systemdescription.py` | the system's name for `summary.txt` and for the daemon's second line of the log, apart so that the daemon does not load the modules above to say it |
| `neoaprs/supportsql.py` | the statements, read-only (a home of SQL in `tests/test_architecture.py`) |
| `neoaprs/web/supporthandler.py`, `supportstate.py` | `POST /support/bundle`, and `state.json` from the running parts |
| `neoaprs/web/supportsend.py`, `neoaprs/updatefetch.py` (`post_form`) | `POST /support/send`: the same bundle posted with the note to the project's server (`SUPPORT_URL` of `neoaprs/versions.py`) |
| `neoaprs/web/pageerrors.py`, `supportwire.py`, `browser.py` | `page_error`: the log line, the rate limit and the ring of 100; the command's model; the browser's name from its `User-Agent` |
| `neoaprs/cli/uncaught.py` | what escapes a thread, the main thread and the event loop is logged |

To make a bundle while developing: `.venv/bin/python -m neoaprs support --data ./data --out /tmp` (no daemon needed, none harmed; add `--show` to open the folder). From a running daemon, with the state of its parts:
`curl -s -X POST -H 'Content-Type: application/json' -d '{"page": {}}' http://127.0.0.1:7303/support/bundle -o support.zip`. `tests/support/supportdata.py` makes a data folder for a test (a migrated database with settings and packets, logs). A new part of the bundle is a gatherer
in `supportgather.py`, a step in `collect` of `supportmake.py` and a line in `FILE_HELP`; one that can fail must be a step, so that its failure is a file and not the end of the bundle. The tests are `tests/test_support_bundle.py` (the builder), `tests/test_support_web.py`
(the endpoint and `page_error`) and `tests/test_support_cli.py` (the command, the tray, the log lines, what escapes); the Start menu entry is held by `tests/test_release.py` and checked on Windows by the release workflow.

**Send feedback / logs and its server.** The page's Send feedback / logs ([daemon.md](daemon.md#the-log-and-the-support-bundle)) posts the bundle to `server/neo/support/send.php` on the project's web host (`https://neo.oh2gba.eu/support/send.php`, uploaded with the rest of `server/neo/` by `server/deploy.sh --site`). `tests/test_support_send.py` tests the daemon's side against a fake server of the loopback (`tests/support/fakesupportserver.py`, which reads the multipart form; `NEOAPRS_SUPPORT_URL` points the daemon at it), and `tests/test_support_php.py` the endpoint under `php -S` with the mail stubbed (a function `support_send_mail` defined before the page runs; skipped without `php`). The endpoint:

- takes a POST of multipart/form-data (`bundle`, `note`, `call`, `version`, `platform`) and answers JSON, `{"ok": true, "ref": ...}` or `{"ok": false, "reason": ...}`: `405 method`, `413 too_large` (a body over 10 MB is refused from its Content-Length, before anything is read, and so is a file over 10 MB; `server/neo/support/.user.ini` sets PHP's `upload_max_filesize` and `post_max_size` for the folder to 10 and 11 MB: the logs of a bundle are cut to 12 MB of text, which weigh 1 to 2 MB zipped for a real log and 7 MB for the least compressible one), `429 rate` (also when the folder is full), `400 bad_request` or `not_a_bundle`, `500 storage`;
- takes the file for a bundle when it starts with the zip's magic bytes and its list of members, read from the central directory without any zip extension, has `summary.txt` and only names a bundle has (`FILE_HELP` of `neoaprs/cli/supportreadme.py`: the files by name, `logs/NAME`, `NAME.error.txt`);
- cleans what the person's page said: the call to letters, digits and dashes (12), the version and the platform to plain characters, the note to valid text without control characters, 2000 characters at most;
- keeps `REF.zip` and `REF.json` (time, call, version, platform, size, note; written last, so that its presence says the pair is whole) in `private/support/` of the site (`SUPPORT_DIR` moves it), a folder Apache never serves (`server/neo/private/.htaccess` and a rule of `server/neo/.htaccess`; the endpoint writes a `.htaccess` into the folder too); the reference is `NEO-YYYYmmdd-HHMM-XXXX`, four random hex digits;
- holds a sender to 5 stored files an hour (60 in all) by a hash of its address (an IPv6 address by its first 64 bits) under a salt kept in the folder; only a request that stores a file counts against that shared limit, a request refused as no bundle counts only against its own address (20 an hour, `429 rate`); `rate.json` holds only hashes and the times of the last hour (what is older is written out at the next request, whatever it is), and the address is written nowhere;
- bounds the folder: 200 MB and 300 bundles (a file that would pass either is answered `429 rate`, and `private/logs/support.log` says the folder is full; one mail tells the project the first time, and a `full.flag` in the folder keeps it from being mailed again until a file is stored; counting the folder and storing the file are one step under a lock, `store.lock`, so that uploads at the same moment cannot pass the cap together), and at each accepted upload it removes the `NEO-` files that are older than 30 days, so that `server/support-fetch.sh` has 30 days to bring a file;
- sends one plain mail to neoaprs@oh2gba.eu with `mail()` as the status application does (`From: NeoAPRS <noreply@oh2gba.eu>`): the subject has the reference and the cleaned call, the body the reference, call, version, platform, size, time and the note; the call and the note cannot reach a header, and the zip is not attached. A mail that fails is a line in `private/logs/support.log` (where the host's rules put an application's log, capped at 256 KB) and the upload still succeeds.

`server/support-fetch.sh` brings the files that are new to `server/support/` (not in git) over SFTP with the account of `deploy.sh`, and prints each with its note; `--list` shows what the server holds. Nothing is deleted on the server by it: the endpoint removes a file after 30 days.

**The sked board and its server.** The Skeds tab posts to `server/neo/api/v1/skeds.php` (`https://neo.oh2gba.eu/api/v1/skeds.php`, uploaded with the rest of `server/neo/`), and every reader takes the board from the static file the endpoint writes, `https://neo.oh2gba.eu/skeds.json`, beside `frequencies.json` in the root of the site but never in `site/` (a deploy would upload it over the live board, so `server/deploy.sh` refuses to start while `site/skeds.json` exists; `robots.txt` leaves it out). `tests/test_skeds_php.py` tests the endpoint under `php -S` in a folder laid out as the site is (skipped without `php`). The endpoint:

- takes a POST of `application/json` (415 for any other type), at most 2048 bytes (413 `too_large` from the Content-Length before anything is read, and a body without one is read only to the limit): `{"action": "add", "token", "call", "from", "to", "dial", "note"}` answers `{"ok": true, "id": ..., "board": ...}`; `{"action": "remove", "token", "id"}` and `{"action": "refresh"}` answer `{"ok": true, "board": ...}`; the board is the body of `skeds.json`, `{"v": 1, "written", "closed", "skeds": [{"id", "call", "from", "to", "dial", "note"}]}`, sorted by `from`, at most 100 rows, no token and no hash of one;
- refuses with `{"ok": false, "reason": ...}` and the status that says it: `405 method`, `400 bad_request` (a call that is not an amateur call with its SSID, a dial not of the form `7.0541 MHz USB`, a time not of the form `2026-11-14T18:00:00Z` or one that does not exist, `to` not after `from`, a token not of 32 hex digits, an id not of 12), `429 rate`, `403 closed` (the board is closed, or the call is blocked), `403 not_yours`, `409 full` (five skeds to come for one token, ten for one call whatever its SSID, a hundred in all), `422 past`, `422 too_long` (over 24 hours), `422 too_far` (a start over 30 days ahead), `500 storage`; only the server's clock decides;
- cleans the note to one line of letters, marks, digits, punctuation, printable ASCII and plain spaces, 80 characters at most (control and invisible characters, bidirectional overrides and symbols beyond ASCII removed); the same sked posted again under the same token is answered with its id;
- keeps each sked as `ID.json` (with the SHA-256 of its token and the time it was posted) in `private/skeds/` of the site, written to a `.part` and renamed, and every change under the one lock (`private/skeds/lock`); at every write the ended skeds, the skeds of a blocked call and any file that is not a sked of ours are removed and the board written again (`skeds.json.part`, renamed; `server/neo/.htaccess` refuses a `.part`);
- holds an address to 10 adds an hour (60 in all) by the hash of the address under a salt of the folder, as Send logs does; an add counts once it is well formed and within the times, a remove with a wrong token and a remove of an id that is gone count as an add, a remove with the right token and a refresh do not (a flood cannot keep the moderator from making the board again), and a refresh writes `skeds.json` only when its rows or `closed` have changed.

`server/skeds.sh` moderates it over SFTP with the account of `deploy.sh`: `--list` (every stored sked with the first digits of its token's hash, so the skeds of one installation are seen together), `rm ID...` and `rm --since TIME`, `close` and `open` (the file `closed`: every add answers `closed` and the board says `"closed": true`), `blocked`, `block CALL` and `unblock CALL` (`blocked.txt`, one call on each line; a call without an SSID blocks every SSID of it); every change ends with a refresh, so the board says it at once.

## What is in the folder

- `neoaprs/`: the daemon, in the layers of [`docs/ARCHITECTURE.md`](ARCHITECTURE.md). `neoaprs/web/` is the page's server and the wire models; `neoaprs/cli/`
  the `neoaprs` command; `neoaprs/desktop/` the desktop app; `neoaprs/services/` the stateful parts; `neoaprs/page/` the committed build of the page, package
  data of the wheel; `neoaprs/samples/` the sample capture.
- `ui/`: the Vue 3 source of the page; `ui/src/protocol/` is generated.
- `tests/`: the suite (`tests/README.md`). `tests/support/` is what the tests are built from, `tests/safety/` the tests of the database actor, `tests/fixtures/`
  the captured frames and streams of the radio and the parser's cases.
- `scripts/`: the tools (the table above).
- `docs/`: the documents (`docs/README.md` is the index): `docs/manual/` the manual for the person who runs NeoAPRS, `docs/RADIOS.md` the radio guide, this
  file, `docs/daemon.md`, `docs/ARCHITECTURE.md`, `docs/MAINTAINING.md`, `docs/mercury.md` (where every number NeoAPRS fixes for the Mercury modem comes from), and `docs/screenshots/` the pictures of the front page.
- `.github/`: the workflows `ci.yml`, `release.yml` and `pages.yml`.
- `site/`: the project page.
- `server/`: the version page that the update check asks, on the project's web host: `version.php`, `latest.php` (the latest release), `log/.htaccess` (the logs and the cache are not served),
  `deploy.sh` (uploads those files and nothing else, and of the folders only what git tracks), `usage-report.sh` (fetches the logs and counts the starts per day, version and system, and the installations by their id; requests with id 0, which a run from the source tree or a test machine sends, and the numbers of the owner's ignore list are left out and said in a line each; see below), `support-fetch.sh` (fetches the support files that Send logs stored, `neo/support/send.php`), `skeds.sh` (moderates the sked board of `neo/api/v1/skeds.php`) and `psalm.xml` (the settings of Psalm for the stage `security`; not uploaded).
  **Your own runs are not counted.** A run from the source tree and a run on a database with `neoaprs db set update/not_counted true` send `id=0`; `usage-report.sh` leaves them out of every count and says how many they were. The numbers sent before that existed are taken out with an ignore list: a plain file of ids, one to a line, `#` starting a comment, blank lines, CRLF line ends and a byte-order mark allowed, read when it is there from `--ignore FILE`, else from `usage-ignore` in the folder of the `.secrets` file. It is the owner's own file outside the repository: git does not track it and `deploy.sh` does not upload it. The number of an installation is its row `update/install_id`: on that machine `neoaprs db get update/install_id` prints it. `usage-report.sh --local` reports on the logs already fetched and needs no `.secrets` file. `version.php` logs `0` as it is and does not hand it to the status application, so the status page does not count it either. Until that `version.php` is deployed the server writes `-` for it and hands the status application an empty key: the report counts such a request as one without an id.
- `packaging/`: what the release is made from besides the package: `windows/`, `appimage/`, `macos/` (the launcher, `Info.plist.in`, the icon maker, the list of what is signed by itself and the microphone sentence in eight languages), `deb/`, `mercury/` (the one C file of the Mercury build) and `ci/` (the Dockerfile of the container `scripts/check-in-container` runs the suite in).
- `systemd/`: the notes on the unit (`systemd/README.md`); the unit itself is the template `neoaprs/cli/neoaprs.service`.
- `.gitattributes`: LF line ends in every checkout (a Windows checkout would otherwise break the tests), the binary files marked.
- `.gitleaks.toml` and `osv-scanner.toml`: what the security checks set aside, each entry with its reason: the made-up values the secret scan meets in the commits, and the advisories that cannot reach NeoAPRS with the day each entry ends ([`docs/security-checks.md`](security-checks.md)).
- `LICENSE`: the GNU General Public License, version 3 (`pyproject.toml` says `GPL-3.0-or-later`).
- `CONVENTIONS.md`, `PROTOCOL.md`, `ROADMAP.md` and `CHANGELOG.md`: how the code is written, the wire protocol (generated), what is planned, and what each
  release changed. `pyproject.toml` and `uv.lock` are the only list of dependencies.
- `data/` (not in git): the live data folder of a run from this folder.

## Tests and real devices

The tests never open a serial device: `tests/conftest.py` points the search at a path that matches nothing (`NEOAPRS_SERIAL_PATTERN`), and the guards of
`tests/support/guards.py` refuse any device of a serial driver. A daemon started by hand for a test, outside the suite, gets `--port socket://...` (a fake TNC,
`neoaprs replay`) or a `serial/pattern` that matches nothing: a fresh data folder otherwise searches every serial port of the machine, and some boards reset
when their port is opened. Everything about the suite is in [`tests/README.md`](../tests/README.md).
