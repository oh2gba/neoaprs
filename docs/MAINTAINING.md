# Maintaining

NeoAPRS is described in several places, and they drift apart unless each change that a user would notice goes through this list. How it is built, checked and
packaged is in [`docs/development.md`](development.md).

## After a change a user would notice

| what | where | how |
|---|---|---|
| the front page | `README.md` | the pitch, the downloads table, the radios table, the screenshots |
| the release notes | `CHANGELOG.md` | a line under `## Unreleased`; the release workflow reads the section of the version (`scripts/release-notes.py`) |
| the manual and the radio guide | `docs/manual/`, `docs/RADIOS.md` | the file of the manual that the change touches, in plain words and short paragraphs; the description of a tab follows the tab |
| the table of settings | `docs/manual/settings.md` | generated: `scripts/doc-settings --write`; a new setting also needs its words in `tests/support/settingsdoc.py` |
| how the daemon behaves | `docs/daemon.md` | the technical details behind the manual, with the names the code uses |
| how it is built and released | `docs/development.md` | the stages, the scripts table, the workflows |
| the roadmap | `ROADMAP.md` | take out what is done |
| the wire protocol | `PROTOCOL.md`, `ui/src/protocol/` | generated: `scripts/gen-protocol.py` |
| the architecture tables | `docs/ARCHITECTURE.md` | generated: `scripts/doc-arch --write` |
| the page | `neoaprs/page/` | built: `scripts/build-page` |
| the screenshots | `docs/screenshots/`, `site/shots/` | `scripts/screenshots.py` (a made-up day from `scripts/demoscene.py`; nothing reaches a real radio); the page's footer shows the version, so a new version makes every shot old |
| the project page | `site/` | <https://oh2gba.github.io/neoaprs/>, deployed by `.github/workflows/pages.yml` on a push to master; the features, the shots, the download names |
| the version page | `server/` | <https://oh2gba.eu/neoaprs/version.php>: the update check of every installed copy asks it and it names the latest GitHub release by itself, so a release needs nothing done there; a change to `server/version.php` is uploaded with `server/deploy.sh`, and `server/usage-report.sh` counts the starts. A note for every user: a line in `message.txt` beside `version.php` on the server, removed again to clear it |
| the announcement | the NeoAPRS post on <https://oh2gba.eu/> | everything it says must stay true; a large release gets a post of its own |

The manual's files name the version only as `<version>`, so a release changes none of them. `tests/test_docs.py` holds that, the length of the manual's
paragraphs, and the paths and names the documents put in backticks.

## The download names

The README, the project page, the announcement and `packaging/install.sh.in` name the files of a release: `NeoAPRS-Setup-<version>.exe`,
`NeoAPRS-<version>-x86_64.AppImage`, `neoaprs_<version>_arm64.deb` and `neoaprs_<version>_amd64.deb` (also in `ui/src/lib/update.ts`, which links them in the
update panel), `install.sh` (always under `releases/latest/download/`), the wheel and `SHA256SUMS`. A new name is changed in all of them and in
`.github/workflows/release.yml`.

## A release

1. The version in `neoaprs/__init__.py` (the one place it is written). Rename `## Unreleased` of `CHANGELOG.md` to `## <version>` (the notes of the release are
   that section) and add a fresh `## Unreleased` above it. The page has the version built in (open pages load themselves again when the daemon's differs): run
   `scripts/build-page` after the change and commit `neoaprs/page/`; `tests/test_page_build.py` fails until you do.
2. `scripts/check` green, commit, push `master`, CI green.
3. The screenshots and the project page brought up to date (above).
4. A tag `v<version>` pushed: `.github/workflows/release.yml` builds, smoke-tests and publishes the release. A tag whose number is not `VERSION` stops at the
   job `verify`, and a failed job leaves no release. Watch the run with `gh run watch`, then open the release and read the notes.
5. Every download link of the README, the project page and the announcement tried once.
6. The version page names the new release: `curl 'https://oh2gba.eu/neoaprs/version.php?v=0.0.1&os=linux'` says the new version (GitHub is asked once an hour,
   so it may take that long), and a copy of the new version does not offer itself.

The jobs of the release workflow are in [`docs/development.md`](development.md#packaging-and-releases).
