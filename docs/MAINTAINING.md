# Maintaining

NeoAPRS is described in several places, and they drift apart unless each change that a user would notice goes through this list. How it is built, checked and
packaged is in [`docs/development.md`](development.md).

## After a change a user would notice

| what | where | how |
|---|---|---|
| the front page | `README.md` | the pitch, the downloads table, the radios table, the screenshots |
| the release notes | `CHANGELOG.md` | a line under `## Unreleased`; the release workflow reads the section of the version (`scripts/release-notes.py`) and makes it the notes of the GitHub release, so the section reads as release notes, and they are short and to the point: one sentence that sums the release up, then one line per change that says what the user gets (under about 20 words; no how, no internal names, no setting keys unless the user types them), as the section of 0.9.1 does. Before a release the section is tidied: overlapping bullets merged, and only the final behaviour kept (no bullet for a state that a later change took away) |
| the manual and the radio guide | `docs/manual/`, `docs/RADIOS.md` | the file of the manual that the change touches, in plain words and short paragraphs; the description of a tab follows the tab |
| the table of settings | `docs/manual/settings.md` | generated: `scripts/doc-settings --write`; a new setting also needs its words in `tests/support/settingsdoc.py` |
| how the daemon behaves | `docs/daemon.md` | the technical details behind the manual, with the names the code uses |
| how it is built and released | `docs/development.md` | the stages, the scripts table, the workflows |
| the roadmap | `ROADMAP.md` | take out what is done |
| the wire protocol | `PROTOCOL.md`, `ui/src/protocol/` | generated: `scripts/gen-protocol.py` |
| the architecture tables | `docs/ARCHITECTURE.md` | generated: `scripts/doc-arch --write` |
| the page | `neoaprs/page/` | built: `scripts/build-page` |
| the screenshots | `docs/screenshots/`, `site/shots/` | `scripts/screenshots.py` (a made-up day from `scripts/demoscene.py`; nothing reaches a real radio) when the page changed in a way a shot shows; the footer's version is hidden in the shots and the update shot's newer number is made from `VERSION`, so a new version by itself makes no shot old |
| the project page | `site/` | <https://oh2gba.github.io/neoaprs/>, deployed by `.github/workflows/pages.yml` on a push to master; the features, the shots, the download names |
| the version page and the download page | `server/` | <https://oh2gba.eu/neoaprs/version.php>: the update check of every installed copy asks it and it names the latest GitHub release by itself, so a release needs nothing done there; <https://oh2gba.eu/neoaprs/download.php?f=windows> (also `appimage`, `deb-amd64`, `deb-arm64`, `wheel`) is what the download buttons of the project page link to: a 302 to that file of the latest release, found from the same cache (`server/latest.php`), and to the release page for anything else; its calls are counted in `log/downloads-YYYY-MM.log` on the server (time, f, version). A change to a file of `server/` is uploaded with `server/deploy.sh`, and `server/usage-report.sh` counts the starts and, by the id in the log, the installations. A note for every user: a line in `message.txt` beside `version.php` on the server, removed again to clear it |
| the announcement | the NeoAPRS post on <https://oh2gba.eu/> | everything it says must stay true; a large release gets a post of its own |

The manual's files name the version only as `<version>`, so a release changes none of them. `tests/test_docs.py` holds that, the length of the manual's
paragraphs, and the paths and names the documents put in backticks.

## The download names

The README, the project page, the announcement and `packaging/install.sh.in` name the files of a release: `NeoAPRS-Setup-<version>.exe`,
`NeoAPRS-<version>-x86_64.AppImage`, `neoaprs_<version>_arm64.deb` and `neoaprs_<version>_amd64.deb` (also in `ui/src/lib/update.ts`, which links them in the
update panel), `install.sh` (always under `releases/latest/download/`), the wheel and `SHA256SUMS`. A new name is changed in all of them and in
`.github/workflows/release.yml`, and in the table of `server/download.php`, which the download buttons of the project page go through.

## A release

1. The version in `neoaprs/__init__.py` (the one place it is written). Read `## Unreleased` of `CHANGELOG.md` as release notes (a one-sentence summary line first; `scripts/release-notes.py` prints it as GitHub will show it), rename it to `## <version>` (the notes of the release
   are that section) and add a fresh `## Unreleased` above it. The page has the version built in (open pages load themselves again when the daemon's differs): run
   `scripts/build-page` after the change and commit `neoaprs/page/`; `tests/test_page_build.py` fails until you do.
2. `scripts/check` green, commit, push `master` (the tag's workflow waits for this commit's CI run, so the tag may follow at once).
3. The project page brought up to date (above), and the screenshots retaken only when the page changed since they were last taken: they show no version
   (`update.png` alone names one, the made-up next version and the installed one in its dialog), so a release with no change to the page leaves them as
   they are.
4. A tag `v<version>` pushed: `.github/workflows/release.yml` builds, smoke-tests and publishes the release. Its first job, `verify`, stops in seconds a tag
   whose number is not `VERSION`, a changelog with notes still under `## Unreleased`, a page not built with the version (`neoaprs/page/sw.js`), a commit that
   is not on `master`, and a commit whose CI run is red or missing (one still running is waited for, 20 minutes at most). A failed job leaves no release (a
   draft at most, which the next attempt finishes). The release is made as a draft and published when every file is on it. Watch the run with `gh run watch`, then open the release and read the notes. A run that failed for a
   reason outside the code (a runner, a download, a flaky test) is run again with *Re-run failed jobs* (`gh run rerun RUN_ID --failed`); one that needs a
   change in the code gets the change and a tag of the next number. **A tag is never moved.** `gh workflow run release.yml --ref v<version>` runs the tag's
   workflow again by hand, which publishes the release (or writes its files over) without a new tag.
5. Every download link of the README, the project page and the announcement tried once.
6. The download page too: `curl -sI 'https://oh2gba.eu/neoaprs/download.php?f=windows'` has a `Location:` with the new version (within the same ten minutes). The version page names the new release: `curl 'https://oh2gba.eu/neoaprs/version.php?v=0.0.1&os=linux'` says the new version (it believes GitHub's answer
   for ten minutes, so it notices within that long), and a copy of the new version does not offer itself.

The jobs of the release workflow are in [`docs/development.md`](development.md#packaging-and-releases).
