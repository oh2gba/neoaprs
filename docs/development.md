# Development

How NeoAPRS is built, checked, packaged and released. The rules the code is written by are in [`CONVENTIONS.md`](../CONVENTIONS.md), the layers in
[`docs/ARCHITECTURE.md`](ARCHITECTURE.md), the tests in [`tests/README.md`](../tests/README.md), the daemon's behaviour in [`docs/daemon.md`](daemon.md), and
what to keep up to date after a change in [`docs/MAINTAINING.md`](MAINTAINING.md).

NeoAPRS is one process with one asyncio loop: the standard library first, pyserial for the serial port, Tornado for the page, pydantic for the wire only,
cryptography for the secure connection's certificates, a database actor, a systemd user unit, and `scripts/check` as the one gate.

## Set up and run

```bash
uv sync --frozen            # the venv in .venv, from uv.lock
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

`scripts/check` runs the stages in this order and stops at the first failure.

### The stages of scripts/check

| stage | what it checks |
|---|---|
| `lock` | `uv.lock` is current with `pyproject.toml` |
| `ruff` | `ruff check` over the tree |
| `mypy` | `mypy --strict` over `neoaprs/` and `tests/support/`, for Linux and again for `--platform win32` |
| `architecture` | the layers and the size limits (`tests/test_architecture.py`, `tests/test_size_ratchet.py`) |
| `pytest` | the rest of the suite, side by side on the cores of the machine |
| `ui-types` | `vue-tsc --noEmit` over `ui/`: TypeScript strict, the types of the protocol from `ui/src/protocol/` only |
| `ui-lint` | eslint with no warnings, prettier `--check`, knip (nothing unused) over `ui/`, and `scripts/css-unused.py` (no rule in `ui/src/styles/` of a class that no source file writes) |
| `ui-tests` | vitest: the logic of `ui/src/lib`, the composables, the components |
| `ui-build` | `vite build` into `ui/dist` (the build works) |
| `page` | `neoaprs/page/`, what the daemon serves, is what `ui/` builds, and lives under the daemon's Content-Security-Policy (`tests/test_page_build.py`) |
| `dup` | jscpd over `ui/src`: duplicated code over the threshold of `ui/.jscpd.json` fails |
| `dup-py` | `scripts/dup-check`: the duplication ratchet of the Python half, jscpd over `neoaprs/` and `tests/support/` against `scripts/dup-baseline.json` (`docs/ARCHITECTURE.md`) |

The stages from `ui-types` on need node 22.12 or newer (on the `PATH`, else the newest in `~/.nvm`) and `ui/node_modules`.

### Local and CI

`.github/workflows/ci.yml` runs on every push to `master` and to a `ci/**` branch, and on every pull request. It does not call `scripts/check`; it runs the same commands.

| job | where | what |
|---|---|---|
| `python` | Linux and Windows, Python 3.13 | the system libraries of the Qt web engine (Linux), `uv sync --frozen --extra app`, `uv lock --check`, `ruff`, `pytest -n auto`; on Linux also `mypy` and `mypy --platform win32`, so that one tree type-checks for both systems |
| `smoke` | Linux and Windows | `uv build --wheel`, the wheel installed into a fresh venv, then `scripts/smoke.py --command <venv>/bin/neoaprs` (`Scripts\neoaprs.exe`) |
| `page` | Linux | type check, lint, prettier, knip and the page's tests, the two duplication stages (`scripts/check --stage dup` and `dup-py`), and the committed `neoaprs/page/` is what `ui/` builds |

What only `scripts/check` runs: the `css-unused` check of `ui-lint`, and the order of the stages. What only CI runs: the Windows halves of `python` and `smoke`.

What only makes sense on a POSIX system is marked `posix_only` (`tests/support/ptyline.py`) and skipped on Windows: pseudo-terminals and device files, `/proc`,
file modes, shell scripts and the stand-ins that are shell scripts (the fake `systemctl`, the fake `pmtiles`), the checks of the repository itself (documents,
scripts, the unit files) and the ones that need `git` and `bash`. Everything else runs on both systems; `tests/README.md` has the details.

The daemon, when a test starts it as a process, is stopped on Windows with Ctrl+Break in a process group of its own (`tests/support/proc.py`): `terminate()` there is a kill.

`NEOAPRS_TEST_WORKERS` and `NEOAPRS_TEST_WORKERS_MAX` set how many tests the `pytest` stage runs side by side; 0 runs them one after the other, which is what to
do to read the output of one failing test in order. The table "Environment variables" of `CONVENTIONS.md` lists every variable.

### The smoke test

`scripts/smoke.py` is the check an installer or a package must pass.

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
  object and bulletin text rules. Python makes it, and `tests/test_vectors.py` and `ui/src/protocol/vectors.test.ts` hold the daemon and the page to it. The
  page keeps its instant preview, and a drift between the two is a test failure.
- **Errors.** An `error` message carries `cmd` (the command it answers; empty for a frame that was no command), `key` (the setting it is about, or null), `code`
  (a stable word such as `setting.range`, `call.ssid` or `message.too_long`; `other` for one without a code yet), `params` (the values the sentence is made of,
  by name) and `text` (the English sentence, for a log and for a code the page has no sentence for). The page goes by `cmd`, `key` and `code`, never by the
  words of `text`. `neoaprs/coded.py` has `CodedError`, and `neoaprs/config.py` a `SettingError` that adds the key.
- **Directed queries.** `query` (`call`, `kind`: `position`, `status`, `heard` or `trace`) sends `?APRSP`, `?APRSS`, `?APRSD` or `?APRST` to a station as a message through `Asking.ask` (`neoaprs/services/asking.py`): the normal path of
  a message (the interlock, the radio's state, the pacing, the station's path), but once, with no message id and one attempt, so that no ack is waited for and none is retried (the specification's queries are not
  numbered); the row is kept as `unconfirmed`, an `out` message with no `msg_id` whose text is one of the four, which the page shows as a note and not a bubble. One query of a kind to a station in 60 seconds
  (`QUERY_EVERY_SEC`), else `query.too_soon` with `call` and `seconds`; a call that is not in the station book is `station.unknown`, one that takes no messages (an object, an item, ourselves, a station whose
  position says it takes none) `query.not_capable`. The answers are the packets and messages the stations send, which the daemon treats as it treats any.
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
service worker `sw.js`. `vite.config.ts` writes it from `ui/sw/sw.js` with the version of the package in it. The daemon serves them with
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
- **An id** is `area.thing.detail` in lower case (`footer.radio.silent`, `error.setting.range`); the area is the part of the page, not the file. A message is a string with `{value}`s; a plural `{ one: "{n} message", other:
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
| `scripts/check` | the one gate: every stage in order, stopping at the first failure; `--stage NAME`, `--list` |
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
| `scripts/screenshots.py` | takes the screenshots of the README and of the project page with Playwright, on a daemon of its own and a made-up day on the air ([the project page](#the-project-page)); the footer's version is hidden in them, so they are retaken when the page changes, not at each release |
| `scripts/demoscene.py` | the day on the air that `screenshots.py` plays: a KISS TNC on a TCP port of the loopback and a daemon on a clock moved back in time, with stations on the move, weather, messages, email, bulletins and objects, items and bulletins of our own |
| `scripts/smoke.py` | the smoke test of an installed NeoAPRS, on any system: a fake KISS TNC on a TCP port plays the capture, the daemon runs on a temporary data folder, the page, its script and `/ws` are checked, the daemon is stopped as its system stops a program and must end with exit code 0, `NeoAPRS ended` and a database that passes `integrity_check`; `--command` names the installed `neoaprs` |
| `scripts/build-appimage` | builds `dist-appimage/NeoAPRS-<version>-x86_64.AppImage` from the wheel (`--wheel FILE`, else it builds one; `--out DIR`), or with `--retag FILE VERSION` the same file saying another version (for the update test); the tools it fetches are pinned by version and SHA-256 in the script and cached in `~/.cache/neoaprs-build` ([the AppImage](#the-appimage)) |
| `scripts/build-deb` | builds `dist-deb/neoaprs_<version>_<arch>.deb` for `--arch amd64` or `arm64` (this machine's by default; either can be made on either) from the wheel (`--wheel FILE`, else it builds one; `--out DIR`); the CPython it fetches is pinned by version and SHA-256 per architecture in the script and cached in `~/.cache/neoaprs-build` ([the .deb](#the-deb)) |
| `scripts/update-e2e.py` | the end-to-end test of Update now with the real files of a release (`windows OLD.exe NEW.exe`, `appimage OLD NEW [--extract-and-run]`): installs the old version, updates it from a fake release on the loopback over the page's socket and checks the new daemon, the data and the machine ([Update now end to end](#update-now-end-to-end)); on a CI runner only |
| `scripts/smoke-appimage` | the smoke test of such a file: `--version`, `smoke.py`, the daemon with no radio, the unit `service install` writes, the app on the offscreen platform; without FUSE it extracts the file and runs its `AppRun` |
| `scripts/release-notes.py` | prints the section of `CHANGELOG.md` for a version (the newest section without one): the notes of the GitHub release, which the release workflow gives to `gh release create`; exit 1 when there is none |
| `scripts/replay` | a clone's wrapper of `neoaprs replay`: plays a capture as a KISS TNC on a TCP port (`--pty`: a pseudo-terminal), so that the daemon runs without the radio |
| `scripts/gps-replay` | a clone's wrapper of `neoaprs gps-replay`: plays a synthetic drive as a gpsd on a TCP port (2948 by default), so that the daemon beacons as a moving station without a car or a GPS ([Trying mobile operation without a vehicle](#trying-mobile-operation-without-a-vehicle)) |
| `scripts/gen-devices.py` | refreshes `neoaprs/devicedata.py`, the snapshot of the APRS device identification list (`tocalls.yaml` of aprsorg/aprs-deviceid, CC BY-SA 2.0) that names a station's device on its card: fetches the list (or reads `--from FILE`) and writes the module with the credit in its head; the only thing that fetches it, the daemon never does; `--check FILE` exits 1 when the module is not what that file makes |
| `scripts/gen-protocol.py` | writes `PROTOCOL.md` and the files of `ui/src/protocol/` (`schema.json`, `protocol.ts`, `lists.ts`, `errors.json`, `vectors.json`, and `ui/src/i18n/en/symbols.ts`) from `neoaprs/web/protocol.py` and the program's constants; run it after a change to a wire model or a limit (`tests/test_protocol.py` fails when they are stale) |
| `scripts/build-page` | builds the page from `ui/` (type check, Vite) into a temporary folder and swaps it in as `neoaprs/page/` with a rename: what the daemon serves and the wheel carries; run it after a change to `ui/` and commit `neoaprs/page/`. `--clean` forces `npm ci` |
| `scripts/node-modules-current.mjs` | the question `build-page` and `worktree-setup` ask: is `ui/node_modules` what `ui/package-lock.json` says (exit 0), or not (exit 1) |
| `scripts/fetch-basemap` | a clone's wrapper of `neoaprs map` with `--data` set to `./data` unless given: makes the base map as the page's Download button does |
| `scripts/capture` | a clone's wrapper of `neoaprs capture`: records the radio's serial port into a file byte for byte, to make test fixtures from a real radio |

In a clone, `scripts/replay`, `scripts/gps-replay`, `scripts/neoaprs-db`, `scripts/capture` and `scripts/fetch-basemap` are the commands of the same name (`gps-replay` is `neoaprs gps-replay`) with the clone's `.venv` and
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

The same two settings are on the page's Beacon tab (the GPS source alone makes the beacon a moving station's; the car preset, `beacon/moving_as`, is the default). The daemon then reads the fixes as it would a gpsd's, shows them in the topic `gps`, moves its own row on the map, and beacons by SmartBeaconing: the first fix at once, a turn at
each corner, then by time (about every two minutes at 50 km/h), nothing while the car stands. With the replay stopped the fix is stale after two minutes and nothing is sent. Nothing is transmitted unless a TNC takes the
frames: use `scripts/replay` as the radio (it takes what the daemon writes) or switch `station/transmit` off to see only the page. `tests/test_gpsreplay.py` runs the same drive through the daemon's feed, the GPS service and the beacon.

## Packaging and releases

What a release holds, on <https://github.com/oh2gba/neoaprs/releases>: `NeoAPRS-Setup-<version>.exe` (the Windows installer),
`NeoAPRS-<version>-x86_64.AppImage`, `neoaprs_<version>_arm64.deb` and `neoaprs_<version>_amd64.deb`, `neoaprs-<version>-py3-none-any.whl` and
`neoaprs-<version>.tar.gz` (the wheel and the sdist), `install.sh` and `SHA256SUMS`, with build provenance attached to each file
(`gh attestation verify FILE --repo oh2gba/neoaprs`). `.github/workflows/release.yml` makes all of it when a tag `v*` is pushed, and nothing is built by hand.
The steps to take around it are in [`docs/MAINTAINING.md`](MAINTAINING.md#a-release).

| job | where | what |
|---|---|---|
| `verify` | Linux, tags only | in seconds, before anything is built: the tag without the `v` is `VERSION` in `neoaprs/__init__.py`; `CHANGELOG.md` has a section for that version and nothing left under `## Unreleased`; `neoaprs/page/sw.js` is built with that version; the commit is on `master`; and `ci.yml` has a successful run for it (a run still going is waited for, 30 seconds at a time, 20 minutes at most; none, or a red one, fails) |
| `wheel` | Linux | `uv build` (the sdist, and the wheel built from it); the wheel is installed into a fresh environment and `scripts/smoke.py` runs against it |
| `windows` | Windows | the wheel and the locked dependencies (`uv export --frozen --no-dev`, with the extra `app`) go into a build environment with PyInstaller (pinned there, not a dependency of the project). `packaging/windows/neoaprs.spec` freezes them into `dist\NeoAPRS` with three programs, `neoaprs.exe` (console), `neoaprsw.exe` (no console: the daemon) and `neoaprs-app.exe` (no console, with the icon: the desktop app), and the page, the icon and the sample capture as data. `bundle_pmtiles.py` puts the pinned `pmtiles.exe` (`neoaprs/pmtilestool.py`: version and SHA-256) in `bin\`, where `pmtilestool.find` looks first. The folder is smoke tested. Inno Setup (`choco install innosetup`) makes the installer from `packaging/windows/neoaprs.iss`; it is run silently (`/VERYSILENT /SUPPRESSMSGBOXES /CURRENTUSER`), and the files, the Start menu entries and the Run key (`neoaprs-app.exe --tray`) are checked. `scripts/smoke.py` runs against `%LOCALAPPDATA%\Programs\NeoAPRS\neoaprs.exe`, `open` and `stop` are tried on a data folder of their own, and `neoaprs-app.exe --tray` is started silently and must start a daemon whose page answers, refuse a second app and end together with its daemon at `neoaprs stop` (started over a daemon that was running, it attaches and leaves it running at `--quit`). The silent uninstall, with the app running, must take the Run key, the files, the app and the daemon away and leave `%LOCALAPPDATA%\NeoAPRS`. Last, [Update now end to end](#update-now-end-to-end): a second installer of the next version is built from the same environment with only `VERSION` changed, and the installed version updates itself to it |
| `appimage` | Linux (`ubuntu-22.04`: glibc 2.35, the oldest the Qt wheels run on) | `scripts/build-appimage --wheel` on the wheel of the `wheel` job; then `scripts/smoke-appimage` on the file |
| `appimage-update` | Linux (`ubuntu-latest`) | [Update now end to end](#update-now-end-to-end) of the file of the `appimage` job, to a copy of it with only `VERSION` changed (`scripts/build-appimage --retag`): once mounted with FUSE, once with `--appimage-extract-and-run` |
| `deb` | Linux, a runner for each architecture (`ubuntu-latest` for amd64, `ubuntu-24.04-arm` for arm64) | `scripts/build-deb --arch ARCH --wheel` on the wheel of the `wheel` job; then, on that runner, `sudo apt install ./neoaprs_<version>_<arch>.deb`, `neoaprs --version`, the kind the package detects (`deb`, with the right architecture), `scripts/smoke.py` against `/usr/bin/neoaprs` run by the package's own Python, `service install` with a `HOME` and a `systemctl` of the test's own (the unit must start `/opt/neoaprs/bin/python3`), an install over itself (the upgrade message) and `apt remove` (the files go, the data stays) |
| `install-script` | Linux | `packaging/install.sh.in` with the version and the release's wheel address put in; `shellcheck`; `packaging/test-install.sh` runs it twice (the second is an update) in a fresh `HOME`, with no `uv` on the `PATH`, a `systemctl` that only writes down its calls, and the wheel just built served from the loopback through `NEOAPRS_WHEEL_URL`, and checks `neoaprs --version`, the unit and the calls |
| `assemble` | Linux | after every job above (a failed update test stops the release here): the six artifacts of the release (by name: never the logs a failed update test left) in one folder, `SHA256SUMS`, and the release notes (`scripts/release-notes.py`: the section of `CHANGELOG.md` for the version) |
| `release` | Linux, tags only | attests the files (`actions/attest-build-provenance`) and runs `gh release create v<version> --verify-tag --draft` with the notes and the eight files, then publishes the draft (`gh release edit --draft=false`), so that no half of a release is ever seen; a version with a dash (`1.0.0-rc1`) is marked a pre-release, which GitHub never makes `latest`. When the release of the tag is there already (an earlier run got this far), the files are written over (`gh release upload --clobber`) and the notes set again. The only job with `contents: write` |

Started by hand on a branch (Actions, release, *Run workflow*, or `gh workflow run release.yml --ref BRANCH`) it is a dry run: the same builds and checks on that
branch, `verify` and `release` skipped, and the files kept for a few days as the artifacts of the run (`gh run download RUN_ID`). Started by hand on a tag
(`gh workflow run release.yml --ref v<version>`) it is the tag's run again: verified and published like a pushed tag.

A tag run that failed is run again, never retagged: *Re-run failed jobs* (`gh run rerun RUN_ID --failed`) for a runner, a download or a flaky test (every artifact
is uploaded with `overwrite`, and `assemble` picks the release's artifacts by name, so an attempt after a failed one works); a failure that needs a change in the
code gets the change on `master` and a tag of the next number. The tag of a release stays on the commit it was made for, and the same tag never names two commits.

Nothing signs the installer: Windows SmartScreen says "Windows protected your PC" for an unsigned file the first times, which the README says.

### The AppImage

`scripts/build-appimage` builds it from the wheel: the relocatable CPython of python-build-standalone, the locked dependencies of the extra `app` (`uv export`),
the wheel, and appimagetool with its static runtime, each tool pinned by version and SHA-256 at the top of the script. `packaging/appimage/prune.py` takes out
what is not run (tests and Tk of CPython, Qt but the web engine and the modules the app imports); `AppRun` and `neoaprs.desktop` are beside it. `$APPIMAGE`
counts only for an interpreter inside `$APPDIR`, and the unit, `neoaprs open` and the start at sign-in start the AppImage file and not the mount.

### The .deb

`scripts/build-deb` builds it from the wheel with no debhelper: the CPython of python-build-standalone for the architecture (pinned by version and SHA-256 in
the script), the locked dependencies as wheels for that platform (`uv pip install --python-platform`, so either architecture is made on either kind of machine),
the wheel, the files `packaging/deb/` holds (`control.in`, `postinst`, `postrm`, `copyright`, the `neoaprs` command),
`packaging/appimage/prune.py --python-only` for what is not run, the bytecode of everything compiled in advance, and `dpkg-deb`. The result is the same bytes
each time for the same inputs (`SOURCE_DATE_EPOCH` is the last commit's time unless set). It carries the manual (`docs/manual/`), the README and the changelog
as documents.

Python is started with `-I`, so that a user's `PYTHONPATH` and user site are not mixed in. The upgrade restarts the service of each logged-in user with
`systemctl --user --machine=UID@.host restart neoaprs`, which writes nothing in their homes.

### The Windows installer

Inno Setup, `packaging/windows/neoaprs.iss`, per user with no administrator rights and no UAC prompt. The tasks, the Start menu group and the uninstaller are
described for the user in [the manual](manual/install.md#windows). The uninstaller runs `neoaprs-app.exe --quit`, `neoaprs.exe stop` and
`neoaprs.exe service remove`, and installing over an older version runs the first two before it replaces anything. The app is `neoaprs-app.exe` and not
`NeoAPRS.exe`: Windows file names ignore case, and that would be `neoaprs.exe`, the console program.

### The install script

`packaging/install.sh.in` is the template of `install.sh`; the `install-script` job renders it with the version and the wheel's address and tests it.
`NEOAPRS_WHEEL_URL` takes another wheel address, which is how the workflow tests it.

### Update now

The update the daemon does itself, on a click of the page only (the command `update_now`), for the Windows installer and an AppImage (`neoaprs/services/selfupdate.py`,
`neoaprs/services/selfinstall.py`). The other kinds have the steps on the page (`ui/src/lib/update.ts`).

1. `update_now` names a version, which must be the one the update check announced (the `update` of `status`); the command goes over the page's socket, which only
   a page of this computer or one that has logged in with the access key has (`neoaprs/web/access.py`), like every command that changes the daemon.
2. The file for this copy (`neoaprs/updateasset.py`: `NeoAPRS-Setup-<version>.exe`, `NeoAPRS-<version>-x86_64.AppImage`) and `SHA256SUMS` are fetched from
   `https://github.com/oh2gba/neoaprs/releases/download/v<version>/`. The address is built from the version alone, which must be digits and dots with an
   optional `-rc1`; nothing else of the version page's answer is used (its `url` is never downloaded). A download is https only and may be redirected only to
   `objects.githubusercontent.com` and `release-assets.githubusercontent.com`, where GitHub keeps the files (`neoaprs/updatedownload.py`); TLS is checked by
   the system's certificates. `SHA256SUMS` comes first: a release that does not name the file installs nothing.
3. The file is written as `<name>.part` while its SHA-256 is computed, with the percent in the topic `update` and `update_cancel` seen between two pieces. A
   SHA-256 that is not the one `SHA256SUMS` gives deletes the file and installs nothing.
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

`site/` is the project page, <https://oh2gba.github.io/neoaprs/>: plain files (`index.html`, `style.css`, `site.js`, the icons and `shots/`), a system font
stack, no external file, tracker or framework, and a Content-Security-Policy that lets it load its own files only. `.github/workflows/pages.yml` publishes the
folder as it is when a push to master touches it (or by hand); Pages is switched on once, in the repository's settings (Pages, Source: GitHub Actions). To look
at it: `python -m http.server --directory site`.

The screenshots are made by `scripts/screenshots.py`. It starts a daemon of its own on a temporary data folder, plays a day on the air into it
(`scripts/demoscene.py`: made-up calls round Helsinki, a car, a hiker and a boat moving, two weather stations, messages that are acked, retried or fail,
bulletins, email, the beacon, and objects, items and bulletins of your own) through a KISS TNC on a TCP port of the loopback, and takes the shots with Chromium
at 1440 x 900 and 390 x 844, each in the light and the dark scheme (`NAME-dark.png`).

- They go to `site/shots/`, with `thumbs/` for the gallery and `og.png` for the link preview. `map`, `weather`, `messages`, `beacon`, `objects`, `bulletins` and
  `setup` are copied to `docs/screenshots/` for the README.
- The close-ups of the delivery chain (`chain.png`, `chain-failed.png`) are taken at twice the pixels.
- The footer's "NeoAPRS `<version>`" is hidden in every shot (an inline style sheet the script adds to the page; the space stays, so nothing moves), so that a release by itself makes no shot old: the shots are retaken when the page changes in a way they show. The one shot that names versions is `update.png`: the made-up newer one, which the script makes from `VERSION` (the patch number plus one) and not from a constant kept by hand, and the installed one in the dialog's "You have NeoAPRS ...".
- `update.png` is taken from a second daemon of its own on a copy of the data folder: a version page on the loopback says that newer version is out and `NEOAPRS_INSTALL_KIND` plays a Windows install, so that **Update now** is offered (and would only rehearse). `beacon-de.png` is the Beacon tab of a browser that speaks German. `beacon-rx.png` and `phone-beacon-rx.png` are taken from another daemon of its own on a copy of the data folder with `station/transmit` set to `false` (Receive only, with its badge in the header). `station-details.png` is the card of a station that runs a Kenwood TH-D74 (the destination call `APK004` of the made-up day) with Details open, and `settings-tnc.png` the TNC group of the Settings tab opened by its arrow. Every daemon of the shots is given a search pattern that matches nothing (`NEOAPRS_SERIAL_PATTERN`), so that no serial port of the machine is ever opened.
- The network access is on in the demo folder with a key made at random for the run, and the Settings shot shows a made-up key and made-up addresses instead of
  the daemon's own. Nothing touches a radio.
- The street map is copied from `data/basemap.pmtiles` (or `--basemap`), which is only read.

```bash
uv run --with playwright --with pillow python scripts/screenshots.py                    # all of them
uv run --with playwright --with pillow python scripts/screenshots.py --only map messages
uv run --with playwright --with pillow python scripts/screenshots.py --chromium PATH --no-sandbox   # a browser Playwright did not install
```

## What is in the folder

- `neoaprs/`: the daemon, in the layers of [`docs/ARCHITECTURE.md`](ARCHITECTURE.md). `neoaprs/web/` is the page's server and the wire models; `neoaprs/cli/`
  the `neoaprs` command; `neoaprs/desktop/` the desktop app; `neoaprs/services/` the stateful parts; `neoaprs/page/` the committed build of the page, package
  data of the wheel; `neoaprs/samples/` the sample capture.
- `ui/`: the Vue 3 source of the page; `ui/src/protocol/` is generated.
- `tests/`: the suite (`tests/README.md`). `tests/support/` is what the tests are built from, `tests/safety/` the tests of the database actor, `tests/fixtures/`
  the captured frames and streams of the radio and the parser's cases.
- `scripts/`: the tools (the table above).
- `docs/`: the documents (`docs/README.md` is the index): `docs/manual/` the manual for the person who runs NeoAPRS, `docs/RADIOS.md` the radio guide, this
  file, `docs/daemon.md`, `docs/ARCHITECTURE.md`, `docs/MAINTAINING.md`, and `docs/screenshots/` the pictures of the front page.
- `.github/`: the workflows `ci.yml`, `release.yml` and `pages.yml`.
- `site/`: the project page.
- `server/`: the version page that the update check asks, on the project's web host: `version.php`, `log/.htaccess` (the log and the cache are not served),
  `deploy.sh` (uploads those two files and nothing else) and `usage-report.sh` (fetches the logs and counts the starts per day, version and system).
- `packaging/`: what the release is made from besides the package: `install.sh.in` and its test `test-install.sh`, and `windows/`, `appimage/` and `deb/`.
- `systemd/`: the notes on the unit (`systemd/README.md`); the unit itself is the template `neoaprs/cli/neoaprs.service`.
- `.gitattributes`: LF line ends in every checkout (a Windows checkout would otherwise break the tests), the binary files marked.
- `LICENSE`: the GNU General Public License, version 3 (`pyproject.toml` says `GPL-3.0-or-later`).
- `CONVENTIONS.md`, `PROTOCOL.md`, `ROADMAP.md` and `CHANGELOG.md`: how the code is written, the wire protocol (generated), what is planned, and what each
  release changed. `pyproject.toml` and `uv.lock` are the only list of dependencies.
- `data/` (not in git): the live data folder of a run from this folder.

## Tests and real devices

The tests never open a serial device: `tests/conftest.py` points the search at a path that matches nothing (`NEOAPRS_SERIAL_PATTERN`), and the guards of
`tests/support/guards.py` refuse any device of a serial driver. A daemon started by hand for a test, outside the suite, gets `--port socket://...` (a fake TNC,
`neoaprs replay`) or a `serial/pattern` that matches nothing: a fresh data folder otherwise searches every serial port of the machine, and some boards reset
when their port is opened. Everything about the suite is in [`tests/README.md`](../tests/README.md).
