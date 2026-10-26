# Maintaining

NeoAPRS is described in several places, and they drift apart unless each change that a user would notice goes through this list. How it is built, checked and
packaged is in [`docs/development.md`](development.md).

## After a change a user would notice

| what | where | how |
|---|---|---|
| the front page | `README.md` | the pointer to the project page, the downloads, a short feature list, the radios in a line, two screenshots |
| the release notes | `CHANGELOG.md` | a line under `## Unreleased`; the release workflow reads the section of the version (`scripts/release-notes.py`) and makes it the notes of the GitHub release, so the section reads as release notes, and they are short and to the point: one sentence that sums the release up, then one line per change that says what the user gets (under about 20 words; no how, no internal names, no setting keys unless the user types them), as the section of 0.9.1 does. Before a release the section is tidied: overlapping bullets merged, and only the final behaviour kept (no bullet for a state that a later change took away) |
| the manual and the radio guide | `docs/manual/`, `docs/RADIOS.md` | the file of the manual that the change touches, in plain words and short paragraphs; the description of a tab follows the tab |
| the table of settings | `docs/manual/settings.md` | generated: `scripts/doc-settings --write`; a new setting also needs its words in `tests/support/settingsdoc.py` |
| how the daemon behaves | `docs/daemon.md` | the technical details behind the manual, with the names the code uses |
| how it is built and released | `docs/development.md` | the stages, the scripts table, the workflows |
| the roadmap | `ROADMAP.md` | take out what is done |
| the wire protocol | `PROTOCOL.md`, `ui/src/protocol/` | generated: `scripts/gen-protocol.py` |
| the architecture tables | `docs/ARCHITECTURE.md` | generated: `scripts/doc-arch --write` |
| the page | `neoaprs/page/` | built: `scripts/build-page` |
| the screenshots | `docs/screenshots/`, `site/shots/` | `scripts/screenshots.py` (a made-up day from `scripts/demoscene.py`; nothing reaches a real radio) when the page changed in a way a shot shows; the version beside Check now is hidden in the shots and the update shot's newer number is made from `VERSION`, so a new version by itself makes no shot old |
| the project page | `site/` | <https://oh2gba.github.io/neoaprs/>, deployed by `.github/workflows/pages.yml` on a push to master; the features, the shots, the download names |
| the version page | `server/` | <https://oh2gba.eu/neoaprs/version.php>: the update check of every installed copy asks it and it names the latest GitHub release by itself, so a release needs nothing done there; the project page's download buttons go straight to GitHub (`releases/latest/download/NeoAPRS-Setup.exe` and `NeoAPRS-x86_64.AppImage`, the copies under fixed names that every release carries); `server/usage-report.sh` counts the starts and, by the id in the log, the installations |
| the announcement | the NeoAPRS post on <https://oh2gba.eu/> | everything it says must stay true; a large release gets a post of its own |

The manual's files name the version only as `<version>`, so a release changes none of them. `tests/test_docs.py` holds that, the length of the manual's
paragraphs, and the paths and names the documents put in backticks.

## The download names

The README, the project page, the announcement and `packaging/install.sh.in` name the files of a release: `NeoAPRS-Setup-<version>.exe`,
`NeoAPRS-<version>-x86_64.AppImage`, `neoaprs_<version>_arm64.deb` and `neoaprs_<version>_amd64.deb` (also in `ui/src/lib/update.ts`, which links them in the
update panel), `install.sh` (always under `releases/latest/download/`), the wheel and `SHA256SUMS`. A new name is changed in all of them and in
`.github/workflows/release.yml`. A pre-release (`0.10.0-rc1`) keeps its version as written in all of them but two: the build names the wheel and the sdist in PEP 440, `neoaprs-0.10.0rc1-py3-none-any.whl` and
`neoaprs-0.10.0rc1.tar.gz`, which `wheel_version` of `neoaprs/updateasset.py` (and `wheelVersion` of `ui/src/lib/update.ts`) gives, and the workflow asks it for the name. The .deb's own version is `0.10.0~rc1`, so that it sorts before
`0.10.0` for apt, while its file name has the version as written. The installer and the AppImage are also attached as `NeoAPRS-Setup.exe` and `NeoAPRS-x86_64.AppImage`, which the project page's buttons link to.

## A release

**Before the notes:** a control that was taken off the page since the last release has a migration that reset its stored value to the default, or a control on the page still. Never leave a user with a state the page cannot change (`CONVENTIONS.md`, "Removing a control from the page"; `tests/test_settings_reachable.py` holds the list of what the page leaves out).


**The way** is one command, on `master` with a clean tree that is up to date with origin and has the notes of the release under `## Unreleased` in `CHANGELOG.md` (a one-sentence summary line first, then the groups;
`scripts/release-notes.py` prints it as GitHub will show it; overlapping bullets merged and only the final behaviour kept):

    scripts/release 0.9.2 [--dry-run] [--rerun] [--deploy]

It uses your own `gh` (`gh auth login` once): the anonymous API of a sandbox hit GitHub's rate limit, so the script refuses to start without a login and waits and asks again when GitHub answers with 403 and its rate limit.
Each step says in one line what it does, and every one is skipped when it is done already, so after any failure the same command goes on where it stopped:

1. **checks**: on `master`, the tree clean (only the files of an earlier stop of this same release may be changed), up to date with origin, notes under `## Unreleased`, the version new and greater than the newest release,
   and no tag `v<version>` on another commit.
2. **version**, **changelog**: `VERSION` in `neoaprs/__init__.py` (the one place it is written), and `## Unreleased` renamed to `## <version>` (the notes of the release are that section) with a fresh empty one above.
3. **page**: only when `ui/` changed since the last tag, the page is built and must be what is committed. A version bump changes nothing in `neoaprs/page/` (the page has no version in it, `ui/` is what it is built from),
   so the release commit holds no page; a committed page that is not what `ui/` builds stops the release, with the tree as it was: run `scripts/build-page`, commit `neoaprs/page/`, run the command again.
4. **check**: `scripts/check`.
5. **commit** `<version>: the changelog section and the version`, **push** `master`.
6. **ci**: waits for the CI run of that commit (`gh run watch`). A failure prints the failed jobs and the lines of the failed tests and stops; `--rerun` runs the failed jobs of that run again once, for a flaky test.
7. **tag** `v<version>` on that commit and **push the tag**. A tag is never moved: one that names another commit stops the script, and a failure of the release run is never answered with a new tag of the same number.
8. **release**: waits for the release run the same way (`--rerun` for its failed jobs). `.github/workflows/release.yml` builds, smoke-tests and publishes; its first job, `verify`, stops in seconds a tag whose number is not `VERSION`,
   a changelog with notes still under `## Unreleased`, a committed page that is not what `ui/` builds, a commit that is not on `master`, and a commit whose CI run is red or missing. The release is made as a draft and published
   when every file is on it.
9. **verify**: the release is published, not a draft, has its 10 files (the wheel, the sdist, the Windows installer, the AppImage, the two packages, `install.sh`, the installer and the AppImage again under the names `NeoAPRS-Setup.exe` and `NeoAPRS-x86_64.AppImage`, and `SHA256SUMS`) and every download link answers.
10. **deploy**: with `--deploy`, `server/deploy.sh` uploads the version page (it needs the operator's Bitwarden session; without the flag the command is printed). The version page names the new release by itself within
    ten minutes (`curl 'https://oh2gba.eu/neoaprs/version.php?v=0.0.1&os=linux'` says the new version), and a copy of the new version does not offer itself.

`--dry-run` prints the steps and what is done already, names what a real run would refuse, and changes nothing (it does not ask GitHub). `scripts/release` has tests with a fake `gh` and a fake origin
(`tests/test_release_script.py`): the order of the steps, the dry run, the resume after a failure at each step and the refusals.

Around the script, by hand: the project page and the screenshots brought up to date (above), the screenshots retaken only when the page changed since they were last taken (they show no version: `update.png` alone names
one, the made-up next version and the installed one in its dialog, so a release with no change to the page leaves them as they are), the download links of the README, the project page and the announcement tried once, and
the announcement post.

**The manual way**, when the script cannot be used (the same steps by hand):

1. The version in `neoaprs/__init__.py` (the one place it is written). Read `## Unreleased` of `CHANGELOG.md` as release notes (a one-sentence summary line first; `scripts/release-notes.py` prints it as GitHub will show it),
   rename it to `## <version>` (the notes of the release are that section) and add a fresh `## Unreleased` above it. The page has no version in it, so nothing is rebuilt for the number; if `ui/` changed since the last tag,
   `scripts/build-page` must leave `neoaprs/page/` as it is committed (`tests/test_page_build.py` fails otherwise).
2. `scripts/check` green, commit, push `master` (the tag's workflow waits for this commit's CI run, so the tag may follow at once).
3. A tag `v<version>` on that commit, pushed. Watch the run with `gh run watch`, then open the release and read the notes. A run that failed for a reason outside the code (a runner, a download, a flaky test) is run
   again with *Re-run failed jobs* (`gh run rerun RUN_ID --failed`); one that needs a change in the code gets the change and a tag of the next number. **A tag is never moved.**
   `gh workflow run release.yml --ref v<version>` runs the tag's workflow again by hand, which publishes the release (or writes its files over) without a new tag.
4. Every download link of the README, the project page and the announcement tried once.
5. `server/deploy.sh` if `server/version.php` changed; the version page names the new release (curl as above).

The jobs of the release workflow are in [`docs/development.md`](development.md#packaging-and-releases).
