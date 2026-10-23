# Maintaining

NeoAPRS is described in several places, and they drift apart unless each change that a user would notice goes through this list.

## After a change a user would notice

| what | where | how |
|---|---|---|
| the front page | `README.md` | the pitch, the downloads table, the radios table, the screenshots |
| the release notes | `CHANGELOG.md` | a line under `## Unreleased`; the release workflow reads the section of the version (`scripts/release-notes.py`) |
| the manual and the radio guide | `docs/MANUAL.md`, `docs/RADIOS.md` | the settings table, the sections the change touches |
| the roadmap | `ROADMAP.md` | take out what is done |
| the wire protocol | `PROTOCOL.md`, `ui/src/protocol/` | generated: `scripts/gen-protocol.py` |
| the architecture tables | `docs/ARCHITECTURE.md` | generated: `scripts/doc-arch --write` |
| the page | `neoaprs/page/` | built: `scripts/build-page` |
| the screenshots | `docs/screenshots/`, `site/shots/` | `scripts/screenshots.py` (a made-up day from `scripts/demoscene.py`; nothing reaches a real radio); the page's header shows the version, so a new version makes every shot old |
| the project page | `site/` | <https://oh2gba.github.io/neoaprs/>, deployed by `.github/workflows/pages.yml` on a push to master; the features, the shots, the download names |
| the announcement | the NeoAPRS post on <https://oh2gba.eu/> | everything it says must stay true; a large release gets a post of its own |

## The download names

The README, the project page, the announcement and `packaging/install.sh.in` name the files of a release: `NeoAPRS-Setup-<version>.exe`, `NeoAPRS-<version>-x86_64.AppImage`, `install.sh` (always under `releases/latest/download/`), the wheel and `SHA256SUMS`. A new name is changed in all of them and in `.github/workflows/release.yml`.

## A release

1. The version in `neoaprs/__init__.py` (the one place it is written) and a `## <version>` section in `CHANGELOG.md` under `## Unreleased`.
2. `scripts/check` green, CI green on master.
3. The screenshots and the project page brought up to date (above).
4. A tag `v<version>` pushed: `.github/workflows/release.yml` builds, smoke-tests and publishes the release.
5. Every download link of the README, the project page and the announcement tried once.

## Tests and real devices

The tests never open a serial device: `tests/conftest.py` points the search at a path that matches nothing (`NEOAPRS_SERIAL_PATTERN`), and the guards of `tests/support/guards.py` refuse any device of a serial driver. A daemon started by hand for a test, outside the suite, gets `--port socket://...` (a fake TNC, `neoaprs replay`) or a `serial/pattern` that matches nothing: a fresh data folder otherwise searches every serial port of the machine, and some boards reset when their port is opened.
