# The security checks

`scripts/security-check` runs the checks that need a program of their own: a scanner for secrets (and beside it the script's own look for the access token of the secrets manager and at the names git tracks), two for the PHP of the project's server, one for the shell scripts, one for the GitHub workflows, and one that asks the advisory lists about the packages the lock files name. `scripts/check` runs it as two stages:

| stage | command | when |
|---|---|---|
| `security` | `scripts/security-check` | in every run of the gate; asks nobody, nothing is fetched |
| `audit` | `scripts/security-check --audit` | by name only, before a release, and every Monday by the workflow `audit.yml`: it asks osv.dev, and a new advisory must not turn the gate red for a change that has nothing to do with it |

The checks that are tests of the code itself (the routes of the page's server, the settings that reach the system, the modules that may start a program) are in the suite and in ruff's rules, not here.

## What each check is for

| check | program | what it is for |
|---|---|---|
| `secret-files` | git | no path with a part named `.secrets`, or `.secrets` with anything after it (`.secrets-hosting`, `.secrets.old`, a folder `.secrets.d/`), is tracked, in any folder, and none lies in the tree where git does not ignore it (the next `git add` of the folder would take it). Such a file holds the access token of the secrets manager; `.gitignore` names it, so only a forced `git add` gets it in. The check reads names: no such file is opened |
| `tokens` | git | the access token of the secrets manager never gets to GitHub. The script looks for its form itself, with git and nothing else, and with no list of exceptions: in every commit of a local branch or tag that `origin` does not have yet, in the messages of the tags, in the index as it is staged, and in every tracked file as it lies in the folder ([below](#the-access-token-of-the-secrets-manager)). It names the commit and the file, never what it found |
| `gitleaks` | gitleaks | no password, token or private key of any other kind gets to GitHub: the hosting login, a GitHub token, a signing key. It reads the commits of the branch (`git log` from `HEAD`, a merge as what it changes on the branch it was made on; git is told to print plainly and to show the first commit, since with the developer's own `color.ui = always` gitleaks would find nothing), the messages of those commits, and, because the gate runs before the commit, the tracked files that are changed or added: each as it lies in the folder, and as it is staged where that is something else. What it finds is never printed: the line says the file, the line number, the rule, and the commit, `not committed yet` or `as it is staged for the next commit` |
| `php-lint` | `php -l` | every tracked `*.php` under `server/` parses: a syntax error would take the version page down for every installation at the next upload |
| `psalm` | Psalm | what a request sends (the query, the form, an uploaded file, the headers, the body) does not reach a file's path, an include, a header, a shell or the answer without being cleaned. Psalm follows the value through the code of `server/` (the settings are in `server/psalm.xml`); only these reports count, the ones whose names begin with `Tainted`. Its remarks about types are not asked for. The system's php runs it, or a php image with docker where that php lacks the extensions ([The programs](#the-programs)) |
| `shellcheck` | shellcheck | the mistakes of quoting and of lost failures in the shell scripts that hold a login or decide what is uploaded, built or installed: the tracked files of `server/`, `scripts/` and `packaging/` that begin with a `sh` or `bash` line, at the level `warning`. No settings are read (`--norc`, and `SHELLCHECK_OPTS` is not handed on); a tracked `.shellcheckrc` and a `# shellcheck disable=` comment that does not say why are findings of their own |
| `zizmor` | zizmor | the workflows of `.github/workflows`: an action named by a tag that its owner can move, a cache in the workflow that publishes, a value of the event pasted into a shell line, a trigger that runs a stranger's code with our token. Offline, from the severity `medium` up; its audits that ask GitHub are left out. No settings are read (`--no-config`, and `ZIZMOR_CONFIG` is not handed on) and no `zizmor: ignore` comment is honoured; a tracked `zizmor.yml` is a finding of its own |
| `audit` | osv-scanner | no package of `uv.lock` or `ui/package-lock.json` has a published advisory. It reads the lock files themselves, so the packages of Windows and macOS are covered from Linux. It does not see the browser engine inside Qt |

The checks read what git tracks. The developer's own folders in a checkout (scratch work, notes, a virtual machine's key) are not the script's to read, and a file there is no finding; only zizmor and Psalm are given a folder as it lies, `.github/workflows` and `server/`. A new file becomes the business of the three checks for secrets when it is added (`git add`): from then on it is in the index, which is read.

`tests/test_security_check.py` tests the script's own decisions with stand-ins for the programs, and the check `tokens` with the real git in made-up repositories.

### The access token of the secrets manager

The login of the hosting account is kept in Bitwarden Secrets Manager, and the scripts of `server/` get it with an access token, the first line of a `.secrets` file: whoever has the token has the login. Its form is `0.<the token's id, a UUID>.<about thirty letters and digits>:<a key in base64>`.

The check `tokens` is what keeps it from GitHub, and it leans on no other program. gitleaks leaves out whole kinds of files by a list of its own (a `package-lock.json`, an `.svg`, a `.pdf`, `node_modules`, its own settings file), does not read a commit's message, and does not read what a merge itself changes; a token in any of those places would pass it. So the script reads for itself, as bytes, everything a push would send:

- every commit that `origin` does not have yet (`git log HEAD --branches --tags --not --remotes=origin`): of this branch and of every other local branch and tag, since `git push` takes whichever it is told and not only the one the gate was run on. Each as git prints it: the commit as it is stored (not what `git replace` shows in its place), with its author and its message, and what it changes against each of its parents, so that the resolution of a merge is read like any other change, and a commit without a parent whole; every file as text, whatever `.gitattributes` calls it, and whatever the developer's own git settings say. A commit that takes a token out again is named too: the one before it had it
- the messages of the tags that have one
- the index, every file as it is staged: a token that was added and then taken out of the file again is still what `git commit` takes
- every tracked file as it lies in the folder, and the names of the files

It looks for the form, a little looser than the real one (twenty letters and digits or more, a key of sixteen characters or more), in UTF-8 and in the UTF-16 a Windows program writes, the key also as JSON writes it (`\/` for `/`). There is no allowlist and no way to accept a finding. What it found is never printed, by this check or under any other check's line.

The daily run does not read the commits that are on `origin` already: they are on GitHub, and reading them again changes nothing. Once, and whenever there is doubt, read them all:

```bash
scripts/security-check --only tokens --all-history    # every commit of every branch and tag
```

gitleaks has a rule for the same form too (`bitwarden-secrets-manager-access-token` in `.gitleaks.toml`, without keywords), as a second look over the whole history of the branch at every run, and every run first shows gitleaks a made-up token and fails when that rule does not find it. A made-up token is put together when it is needed (in the script and in the tests) and stands whole in no file: written out, it would be a finding.

## The programs

None of the five is installed on the system. `scripts/security-tools` fetches each at one pinned version into the build cache (`~/.cache/neoaprs-build/security-tools`, or under `NEOAPRS_BUILD_CACHE`), one folder per tool and version, and keeps a file only when its SHA-256 is the one written in the script:

```bash
scripts/security-tools           # fetch what is missing (the network: GitHub's release files)
scripts/security-tools --list    # each tool, its version, and whether it is in the cache
```

The pins are for Linux x86_64. `php` is the system's (`php-cli`). Psalm is a PHP archive that this php runs, and the pinned one asks for PHP 8.3.16, 8.4.3 or newer with the XML extensions `dom` and `simplexml`: on Debian and Ubuntu the package `php-xml`.

Where the system's php lacks those extensions and docker can be used, Psalm runs in the official `php` image of the same minor version instead, which has them: `server/` and the archive are mounted read-only, the container has no network, and the check never fetches the image. The image is pinned by its digest in `PHP_IMAGES` of `scripts/security-tools`, one entry for each minor version of php, and a version without an entry has no image: the check fails and says so. An entry is the `Digest:` that `docker pull php:8.4-cli` prints, written as `php@sha256:...`; on a machine that does not have the image yet, the check's failure line names the `docker pull` that gets it. With neither a php that has the extensions nor a docker that can be used, the check fails and says so.

A program that is not there fails its check, and the line says which and how to get it. A check that could not run is never a pass.

To move a pin, write the new version, the address of its file and the digest GitHub shows for that file into `scripts/security-tools`, fetch it, and run the check: the baseline is what the pinned version finds, and a newer one may find more. What it newly finds is fixed or accepted like any other finding.

## Reading a failure

Each check prints one line, `ok` or `FAIL`, and under a failing one what was found.

- **secret-files** names the file, also one that only lies in a folder of that name. `is tracked by git`: take it out of what git tracks and leave it where it lies, `git rm --cached FILE`. `is not ignored by git`: the lines `.secrets` and `.secrets*` are missing from `.gitignore`, or a rule further down takes them back. If a commit already has the file, every token in it is revoked where it is used before anything else, as for a finding of gitleaks. There is no way to accept this finding: a file of that name is never committed.
- **tokens** names each place: `commit 0123456789: FILE`, `commit 0123456789: its message`, `the tag NAME: its message`, `the index: FILE` (what is staged), or `FILE:LINE` (the file as it lies). Revoke the token in the secrets manager before anything else: a commit that has it keeps it whatever the file says now, and a commit that was pushed has been read. Then take it out of the file and stage the file again; a commit that is not pushed yet is made anew without it (`git commit --amend`, or a rebase for an older one) and a tag likewise, until the check is green. There is no entry that accepts this finding.
- **gitleaks** names the file and line, the rule, and the commit, `not committed yet` or `as it is staged for the next commit`; for a message, `the message of commit 0123456789`. A finding in a commit: look at it with `git show COMMIT -- FILE`. If it is a real secret, it is revoked where it is used before anything else: taking it out of the tree does not take it out of the commits, and a commit that was pushed has been read. A real secret that is not committed yet is taken out of its file and the file staged again, and nothing more is needed. A private file that was added by mistake is taken out of what git tracks (`git rm --cached FILE`) and named in `.gitignore`; it never gets an entry in the allowlist. If it is a made-up value, it gets an entry in the allowlist (below). The line `the rule bitwarden-secrets-manager-access-token ... does not find a token of that form any more` is not a finding in the tree: the rule or the allowlist of `.gitleaks.toml` was changed so that the made-up token passes.
- **php-lint** prints PHP's own message with the file and the line.
- **psalm** prints the place where the value is used, the kind (`TaintedHtml`, `TaintedFile`, `TaintedHeader` ...) and under it the way the value took from the request. The fix is to clean the value on that way, or, when it is cleaned in a way Psalm does not follow, to say so in the code: `@psalm-taint-escape` on the function that cleans, with a comment that says why it is enough.
- **shellcheck** and **zizmor** print `new:` for a kind of finding the baseline does not have and `more:` when there is one more of a kind it has, each with the places. Both tools explain their rules by number or name (`SC2086`, `unpinned-uses`) on their own pages. Two kinds are the script's own: `FILE settings of shellcheck` (or `of zizmor`) for a tracked settings file of the tool, and `FILE disable=SC... without its reason` for a comment that switches a rule off and does not say why.
- **audit** prints osv-scanner's table: the advisory, the package and its version, the version that has the fix, and the lock file. An advisory against something the installers carry is a reason for a fix release: the package is moved to the fixed version in `pyproject.toml` or `ui/package.json` and the lock made again.

A line `... is not in the cache`, `php is not installed`, `this php has no dom ... extension, ... and docker cannot be used` or `no php image is pinned` is not a finding: the program is missing.

## Accepting a finding

A finding is fixed. Where that is not possible yet, or the finding is not one, it is accepted in a file that is committed, with the reason beside it. The check refuses an entry without its reason.

**A value that is no secret**: an entry `[[allowlists]]` in `.gitleaks.toml`, with a `regexes` line that matches the value and nothing else, and a `description` that says what the value is and why no installation has it. Never a folder or a whole file: a real key pasted into a test must still be found (the suite refuses an entry that names a path). A value of the form of the secrets manager's token gets no entry: a test that needs one puts it together from its parts. A `gitleaks:allow` comment in the code and a `.gitleaksignore` file are not used, so that the allowlist is the one place to read.

**A finding of shellcheck or zizmor**: an entry in `scripts/security-baseline.json`. An entry is the file, the rule and what the finding is about (never a line number, which moves), with how many there are and the reason:

```bash
scripts/security-check --update --allow-growth    # takes today's findings in; a new entry has an empty reason
scripts/security-check --update                   # after a fix: drops what is gone, never takes anything in
```

Then write the reason into the new entry. It says why the finding may stay and what ends it ("a known fault: ... It ends when ...") or why it is none ("the word is split on purpose: it is a command with its arguments"). For a single line of a shell script that is right as it is, the comment `# shellcheck disable=SC2086   # the reason` above it is the better place: the reason after a `#` of its own on the same line, and a comment without one is a finding. A `zizmor: ignore` comment in a workflow is not honoured: for the workflows the baseline is the one place to read.

A settings file of either tool (`.shellcheckrc`, `zizmor.yml`) is not a way to accept a finding: the check does not read it, so what it switches off still fails here, and the file itself is a finding. If such a file must be in the tree for another reason (an editor), the baseline names it like any other finding, with that reason.

**An advisory that cannot reach NeoAPRS**: an entry `[[IgnoredVulns]]` in `osv-scanner.toml` with the `id` of the advisory, a `reason` that says what the advisory needs and why that is not there (a build tool that only reads our own tree; a server we do not open to the network), and `effectiveUntil`, the day the entry ends, a few months ahead. From that day the advisory fails the audit again and is looked at again. An advisory against a package the installers carry is never set aside.
