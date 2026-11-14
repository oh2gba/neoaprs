# Maintaining

NeoAPRS is described in several places, and they drift apart unless each change that a user would notice goes through this list. How it is built, checked and
packaged is in [`docs/development.md`](development.md).

## After a change a user would notice

| what | where | how |
|---|---|---|
| the front page | `README.md` | the pointer to the project page, the downloads, a short feature list, the radios in a line, two screenshots |
| the release notes | `CHANGELOG.md` | a line under `## Unreleased`, written by the rule of `CONVENTIONS.md` ("Documents, scripts, units"): one short line for a thing a user can see or do, and none for a change nobody can notice (`tests/test_changelog_brief.py` holds the form, here and again under the version at the release; what is worth a line is the writer's care). The release workflow reads the section of the version (`scripts/release-notes.py`) and makes it the notes of the GitHub release. Before a release the section is tidied: the sentence that sums the release up written first, overlapping lines merged, and only the final behaviour kept (no line for a state that a later change took away) |
| the manual and the radio guide | `docs/manual/`, `docs/RADIOS.md` | the file of the manual that the change touches, in plain words and short paragraphs; the description of a tab follows the tab |
| the table of settings | `docs/manual/settings.md` | generated: `scripts/doc-settings --write`; a new setting also needs its words in `tests/support/settingsdoc.py` |
| how the daemon behaves | `docs/daemon.md` | the technical details behind the manual, with the names the code uses |
| how it is built and released | `docs/development.md` | the stages, the scripts table, the workflows |
| the roadmap | `ROADMAP.md` | take out what is done |
| the wire protocol | `PROTOCOL.md`, `ui/src/protocol/` | generated: `scripts/gen-protocol.py` |
| the architecture tables | `docs/ARCHITECTURE.md` | generated: `scripts/doc-arch --write` |
| the page | `neoaprs/page/` | built: `scripts/build-page` |
| the screenshots | `docs/screenshots/`, `site/shots/` | `scripts/screenshots.py` (a made-up day from `scripts/demoscene.py`; nothing reaches a real radio) when the page changed in a way a shot shows; the version beside Check now is hidden in the shots and the update shot's newer number is made from `VERSION`, so a new version by itself makes no shot old |
| the project page | `site/` | <https://neo.oh2gba.eu/>, uploaded by `server/deploy.sh --site` (the old address <https://oh2gba.github.io/neoaprs/> redirects there: `.github/workflows/pages.yml`, by hand); the features, the shots, the download names |
| the version page | `server/` | <https://neo.oh2gba.eu/version.php> (and the same file at <https://oh2gba.eu/neoaprs/version.php> for the copies before 0.16): the update check of every installed copy asks it and it names the latest GitHub release by itself, so a release needs nothing done there; the project page's download buttons go straight to GitHub (`releases/latest/download/NeoAPRS-Setup.exe` and `NeoAPRS-x86_64.AppImage`, the copies under fixed names that every release carries); `server/usage-report.sh` counts the starts and, by the id in the log, the installations; the same host takes the support files that Send logs posts (`neo/support/send.php`, stored in `private/support/`, one mail to the project for each), which `server/support-fetch.sh` fetches; and the sked board (`neo/api/v1/skeds.php`, each sked stored in `private/skeds/`, the board written to `skeds.json` in the root of the site and never uploaded), which `server/skeds.sh` moderates over SFTP: `--list`, `rm`, `close` and `open`, `block` and `unblock` |
| the announcement | the NeoAPRS post on <https://oh2gba.eu/> | everything it says must stay true; a large release gets a post of its own |

The manual's files name the version only as `<version>`, so a release changes none of them. `tests/test_docs.py` holds that, the length of the manual's
paragraphs, and the paths and names the documents put in backticks.

## The download names

The README, the project page and the announcement name the files of a release: `NeoAPRS-Setup-<version>.exe`, `NeoAPRS-<version>-x86_64.AppImage`, `NeoAPRS-<version>-arm64.dmg`,
`neoaprs_<version>_arm64.deb` and `neoaprs_<version>_amd64.deb` (also in `ui/src/lib/update.ts`, which links them in the update panel) and `SHA256SUMS`; the source tarball
`neoaprs-<version>.tar.gz` is on the release page too, unadvertised, for packagers. These are the supported installs since 0.16, the ones that carry Mercury: the install line and the wheel
of the earlier releases are gone (a copy installed that way is sent to the release page by the update window; the kinds `uv-tool` and `pip` stay recognised). A new name is changed in all of
them and in `.github/workflows/release.yml`. A pre-release (`0.10.0-rc1`) keeps its version as written in all of them but one: the build names the sdist (and the wheel it builds the
AppImage and the packages from) in PEP 440, `neoaprs-0.10.0rc1.tar.gz`, which `wheel_version` of `neoaprs/updateasset.py` gives, and the workflow asks it for the name. The .deb's own
version is `0.10.0~rc1`, so that it sorts before `0.10.0` for apt, while its file name has the version as written. The installer, the AppImage and the macOS app are also attached as `NeoAPRS-Setup.exe`,
`NeoAPRS-x86_64.AppImage` and `NeoAPRS-arm64.dmg`, which the project page's buttons link to.

## What the update trusts

Update now (`neoaprs/updatefetch.py`, `neoaprs/services/selfinstall.py`) trusts GitHub over TLS: it downloads the file of exactly the announced version from the release page of the project (the host
is checked again at every redirect, the size is capped) and compares its SHA-256 with `SHA256SUMS` of the same release. That list is not signed, so whoever can replace a release's files can replace
the list too; the check finds a damaged or cut download, not a release that was tampered with at the source. The workflow makes build attestations that the daemon does not check, and the Windows
installer is not code-signed. A signature over `SHA256SUMS` under a key built into the program would close this; until then the trust is the account that publishes the releases, and the account's
protection (two-factor sign-in, no token with write access to releases outside the workflow) is the control.

## A build for testing

Every file of a release can be built on GitHub without releasing anything: start the release workflow by hand on `master` or any branch (Actions, release, *Run workflow*, choose the branch; or
`gh workflow run release.yml --ref master`). The run is named "build for testing" in the list of runs. It builds the Windows installer, the AppImage, the macOS app, the two .deb packages with Mercury inside, the source
tarball and `SHA256SUMS` (and the wheel they are built from, which is not a file of the release), and runs every smoke and update test on them, exactly as a tag's run does; what it skips is the `verify` job (the tag's checks) and the `release` job, so no
release, no tag and nothing on the version page come of it. About twenty minutes. The files are the artifacts of the run, kept for a few days: `gh run list --workflow release.yml` names the run,
`gh run download RUN_ID -n release-files` fetches the folder with every file and the notes (`-n windows-installer`, `-n appimage`, `-n macos-app`, `-n deb-amd64`, `-n deb-arm64` or `-n dist` for one of them), and the
Actions page of the run lists them under *Artifacts*. A tag started by hand (`--ref v<version>`) is not a build for testing but the tag's release run again.

## Moving the Mercury pin

The Mercury that every release carries is the four constants at the head of `neoaprs/mercury.py`: `VERSION`, `SOURCE_COMMIT`, `SOURCE_URL` and `SOURCE_SHA256`. The address is made from the commit, so three are typed. The same source is built for Linux, macOS and Windows, so there is no other pin. A new Mercury is a change of them in one commit, with these steps:

1. `VERSION` is Rhizomatica's tag, `SOURCE_COMMIT` the commit that tag points at, `SOURCE_SHA256` the SHA-256 of the archive at `SOURCE_URL`.
2. Look for the old version and the old commit in the whole tree (`grep -rn`) and change what names them: `packaging/deb/copyright` (the source address), `docs/RADIOS.md`, the profile's description and comments in `neoaprs/tncprofile.py` and `neoaprs/mercury.py`, the fake in `tests/support/fakemercury.py` and the file names of the tarballs in `tests/test_mercury_build.py`, `tests/test_deb.py`, `tests/test_appimage.py` and `tests/test_release.py`.
3. `scripts/build-mercury --install` builds the new source into the venv and stops when the archive is not the one with the SHA-256 given. If it fails to link, `packaging/mercury/pulse_stub.c` no longer covers what Mercury asks of PulseAudio. Every flag that `command()` of `neoaprs/mercury.py` starts the program with has to be in the new `mercury -h`.
4. Run the suite, then the real thing: `scripts/mercury-bench` and `scripts/check --stage sim`.
5. Measure again what [`docs/mercury.md`](mercury.md) quotes (`scripts/mercury-measure`: the time of a frame, the delivery time, the level of the audio, the size of the beacon pause, the frames a VOX radio loses to its attack time with and without the lead-in) and move the constants of `neoaprs/mercury.py` and `neoaprs/radiorules.py` and the table of the document when a figure has moved.
6. The five patches (`packaging/mercury/loopback.patch`, `packaging/mercury/leadin.patch`, `packaging/mercury/dsound.patch`, `packaging/mercury/flush.patch`, `packaging/mercury/ffcpu.patch`) must still apply, and the Windows build must still link: `scripts/build-mercury --windows` needs the MinGW-w64 cross compiler (`gcc-mingw-w64-x86-64 mingw-w64-x86-64-dev mingw-w64-common` on Debian), and a build for testing (above) runs it as the job `mercury-windows`, together with the Linux build for both architectures; the `windows` job then starts the program and checks that it listens on 127.0.0.1 only.

## A release

**Before the notes:** a control that was taken off the page since the last release has a migration that reset its stored value to the default, or a control on the page still. Never leave a user with a state the page cannot change (`CONVENTIONS.md`, "Removing a control from the page"; `tests/test_settings_reachable.py` holds the list of what the page leaves out).


**The way** is one command, on `master` with a clean tree that is up to date with origin and has the notes of the release under `## Unreleased` in `CHANGELOG.md` (a one-sentence summary line first, then one short line for each thing a user can see or do;
`scripts/release-notes.py` prints it as GitHub will show it; overlapping lines merged and only the final behaviour kept):

    scripts/release 0.9.2 [--dry-run] [--rerun] [--deploy]
    scripts/release 0.9.2 --verify

It uses your own `gh` (`gh auth login` once): the anonymous API of a sandbox hit GitHub's rate limit, so the script refuses to start without a login and waits and asks again when GitHub answers with 403 and its rate limit.
Each step says in one line what it does, and every one is skipped when it is done already, so after any failure the same command goes on where it stopped:

1. **checks**: on `master`, the tree clean (only the files of an earlier stop of this same release may be changed), up to date with origin, notes under `## Unreleased`, the version new and greater than the newest release,
   and no tag `v<version>` on another commit.
2. **version**, **changelog**: `VERSION` in `neoaprs/__init__.py` (the one place it is written), and `## Unreleased` renamed to `## <version>` (the notes of the release are that section) with a fresh empty one above.
3. **page**: only when `ui/` changed since the last tag, the page is built and must be what is committed. A version bump changes nothing in `neoaprs/page/` (the page has no version in it, `ui/` is what it is built from),
   so the release commit holds no page; a committed page that is not what `ui/` builds stops the release, with the tree as it was: run `scripts/build-page`, commit `neoaprs/page/`, run the command again.
4. **check**: `scripts/check`, which includes the stages `security` and `smoke`: run it outside a sandbox that keeps uv from its cache, and run `scripts/security-tools` once before (it fetches the programs of `security`). It reads the notes once more, now under `## <version>` (`tests/test_changelog_brief.py`): notes that are not brief stop the release here; correct them in that section and run the command again. The simulation of the HF net (`scripts/check --stage sim`, about six minutes) is not in it; the CI job `sim` runs it on every push to master, so a green CI run of the release commit covers it.
5. **commit** `<version>: the changelog section and the version`, **push** `master`.
6. **ci**: waits for the CI run of that commit (`gh run watch`). A failure prints the failed jobs and the lines of the failed tests and stops; `--rerun` runs the failed jobs of that run again once, for a flaky test.
7. **tag** `v<version>` on that commit and **push the tag**. A tag is never moved: one that names another commit stops the script, and a failure of the release run is never answered with a new tag of the same number.
   **A fix after the release commit** (its CI run failed, the fix is on `master` and pushed, no tag yet): run the same command; when `HEAD` has the same `VERSION` and the same section of the changelog (nothing under `Unreleased`), `HEAD` is the release, and steps 6 and 7 are about it (the output says "the release is HEAD"; `--dry-run` shows it). A `HEAD` that changed either is refused, and a tag that exists is never moved.
8. **release**: waits for the release run the same way (`--rerun` for its failed jobs). `.github/workflows/release.yml` builds, smoke-tests and publishes; its first job, `verify`, stops in seconds a tag whose number is not `VERSION`,
   a changelog with notes still under `## Unreleased`, a committed page that is not what `ui/` builds, a commit that is not on `master`, and a commit whose CI run is red or missing. The release is made as a draft and stays one:
   it is not published by the workflow.
9. **sign**: the draft must have its 14 files and a `SHA256SUMS` that names each of them once. The signing key is read at that moment from Bitwarden Secrets Manager by `bws secret get`, into memory only: the secret
   whose id `NEOAPRS_SIGNING_SECRET_ID` names, with bws's token in `BWS_ACCESS_TOKEN` and the server in `BWS_SERVER_URL` (`https://vault.bitwarden.eu` for the project's account). A key whose public half is not
   `PUBLIC_KEY` of `neoaprs/updateasset.py` signs nothing. bws is the only program the script hands those two variables to: `scripts/check`, git and its hooks, gh and `server/deploy.sh` run without them. `SHA256SUMS.sig` is uploaded, checked with the program's public key, and then the release is published. A draft signed already is only published; a
   published release is never signed after the fact. Run it outside a sandbox: bws needs the network ([Update now](development.md#update-now) has what is signed).
10. **verify**: the release is published, not a draft, has its 15 files (the Windows installer, the AppImage, the macOS app, the two packages, the five again under the names `NeoAPRS-Setup.exe`, `NeoAPRS-x86_64.AppImage`, `NeoAPRS-arm64.dmg`, `neoaprs_amd64.deb` and `neoaprs_arm64.deb`, the source tarball, the wheel and `install.sh` for the copies installed with the install line before 0.16, `SHA256SUMS` and `SHA256SUMS.sig`), the signature holds with the program's public key and every download link answers.
    `scripts/release <version> --verify` does this step alone, for a release published earlier, and changes nothing.
11. **deploy**: with `--deploy`, `server/deploy.sh` uploads the version page (it needs the operator's Bitwarden session; without the flag the command is printed). The version page names the new release by itself within
    ten minutes (`curl 'https://neo.oh2gba.eu/version.php?v=0.0.1&os=linux'` says the new version), and a copy of the new version does not offer itself.

`--dry-run` prints the steps and what is done already, names what a real run would refuse, and changes nothing (it does not ask GitHub). `scripts/release` has tests with a fake `gh` and a fake origin
(`tests/test_release_script.py`): the order of the steps, the dry run, the resume after a failure at each step and the refusals; the step sign and `--verify` with a fake `bws` and a key the test makes
(`tests/test_release_sign.py`).

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
   `gh workflow run release.yml --ref v<version>` runs the tag's workflow again by hand, which makes the draft (or writes its files over) without a new tag.
   The draft is signed and published by `scripts/release <version>` (the steps before sign are skipped as done); by hand there is no signing, since the key is read into memory by the script alone.
4. Every download link of the README, the project page and the announcement tried once.
5. `server/deploy.sh` if `server/version.php` changed; the version page names the new release (curl as above).

The jobs of the release workflow are in [`docs/development.md`](development.md#packaging-and-releases).
