"""The security checks (scripts/security-check) and the fetching of their programs (scripts/security-tools), with stand-ins: a made-up tree holds copies of the two scripts, and small fake programs stand where
the script looks for the real ones (the tools in a build cache of the test's own, php first on the PATH). What is tested is our logic: a finding fails and is printed under its line, the baseline lets a
known finding pass and nothing beside it, an entry needs its reason, a program that is not there fails with the sentence that says how to get it, and the advisory check runs only when asked; a file or
folder of access tokens that git tracks fails; the check `tokens`, which is the script's own reading with the real git, finds a made-up access token of the secrets manager in every place a push would
carry it (a lock file, a picture, a binary file, a commit's message, a merge's resolution, the index) and never prints it; gitleaks is shown the messages and what is changed or staged, and no file git
does not track; Psalm runs in the pinned php image where php lacks its extensions; a settings file of shellcheck or zizmor is a finding. The real programs are run by `scripts/check --stage security`;
no test here reaches the network (the downloads go to a fake server on the loopback) or a real docker (a stand-in is first on the PATH), and the git commands name the made-up tree (`git -C`), which no
folder above it can stand in for."""
import asyncio
import base64
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from tests.support.fakehttp import http_server
from tests.support.ptyline import posix_only

pytestmark = posix_only      # (stand-ins with a shebang for a development check, not the product)

ROOT = Path(__file__).resolve().parent.parent
OFFLINE = ["secret-files", "tokens", "gitleaks", "php-lint", "psalm", "shellcheck", "zizmor"]
TOKEN_RULE = "bitwarden-secrets-manager-access-token"

# A stand-in for any program of the checks: it writes down how it was called, prints what the test laid down for it and ends with the code the test chose. php is four programs in one: its list of
# extensions, its version, its lint, and Psalm (the phar it is given to run). gitleaks is three: over the commits (its own name), over what it is given to read (it keeps that in the file `stdin`) and
# over a folder (it keeps the names of what lies there in the file `shown`, and what the messages and the staged copies say in the files `messages` and `staged`; `@FOLDER@` in what it is to print stands for that folder).
# Over the commits it asks the real git what it was told, as the git that the real gitleaks starts would be, and keeps the answers in the file `git-told`.
# docker is two: whether it can be used, and the container it runs. A program that is handed settings through the environment says so in the file `handed`.
STAND_IN = """#!/bin/sh
name="$(basename "$0")"
for last; do :; done
case "$name ${{1:-}}" in
    "gitleaks stdin") name=gitleaks-stdin; cat > "{fakes}/stdin" ;;
    "gitleaks git") {{ git config color.ui; git config color.diff; git config log.showRoot; echo "${{GIT_NO_REPLACE_OBJECTS:-}}"; }} > "{fakes}/git-told" 2>&1 ;;
    "gitleaks dir") name=gitleaks-dir; (cd "$last" && find . ! -type d | sort > "{fakes}/shown"
        for kind in messages staged; do [ -d "$kind" ] && find "$kind" -type f -exec cat {{}} + > "{fakes}/$kind"; done) ;;
    "php -m") name=php-m ;;
    "php -r") name=php-r ;;
    "php -l") name=php-l ;;
    php\\ *) name=psalm ;;
    "docker info") name=docker-info ;;
    "docker run") name=docker-run ;;
esac
[ -n "${{SHELLCHECK_OPTS:-}}${{ZIZMOR_CONFIG:-}}${{GITLEAKS_CONFIG:-}}" ] && echo "$name" >> "{fakes}/handed"
echo "$name $*" >> "{fakes}/calls"
[ -f "{fakes}/$name.out" ] && sed "s|@FOLDER@|$last|g" "{fakes}/$name.out"
[ -f "{fakes}/$name.code" ] && exit "$(cat "{fakes}/$name.code")"
exit 0
"""


def load_tools() -> ModuleType:
    """scripts/security-tools as a module (it has no .py: the loader is named)."""
    loader = importlib.machinery.SourceFileLoader("security_tools_under_test", str(ROOT / "scripts" / "security-tools"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


tools = load_tools()


class Tree:
    """The made-up tree, its stand-ins and `check(...)`, which runs the copy of scripts/security-check in it."""

    def __init__(self, tmp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root, self.fakes, self.bin = tmp / "tree", tmp / "fakes", tmp / "bin"
        monkeypatch.setenv("NEOAPRS_BUILD_CACHE", str(tmp / "cache"))
        monkeypatch.setenv("PATH", f"{self.bin}{os.pathsep}{os.environ['PATH']}")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")} | {"HOME": str(tmp / "home"), "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "LC_ALL": "C.UTF-8",
                                                                                         "GIT_CEILING_DIRECTORIES": str(tmp)}      # (git never looks for a repository above the made-up tree)
        for folder in (self.fakes, self.bin, tmp / "home"):
            folder.mkdir()
        self.write("scripts/deploy", "#!/usr/bin/env bash\necho deploy\n")
        self.write("scripts/tool.py", "#!/usr/bin/env python3\nprint('no shell')\n")
        self.write("packaging/postinst", "#!/bin/sh\nexit 0\n")
        self.write("server/version.php", "<?php echo 1;\n")
        self.write("server/psalm.xml", "<psalm/>\n")
        self.write(".github/workflows/ci.yml", "on: push\n")
        self.write(".gitleaks.toml", '[extend]\nuseDefault = true\n\n[[allowlists]]\ndescription = "the made-up key of the tests"\nregexes = [\'\'\'^made-up$\'\'\']\n')
        self.write("osv-scanner.toml", '[[IgnoredVulns]]\nid = "GHSA-aaaa-bbbb-cccc"\neffectiveUntil = 2027-01-31\nreason = "a build tool: the pattern is ours"\n')
        self.write("uv.lock", "version = 1\n")
        self.write("ui/package-lock.json", "{}\n")
        for name in ("security-check", "security-tools"):
            shutil.copy2(ROOT / "scripts" / name, self.root / "scripts" / name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, env=self.env)
        assert (self.root / ".git").is_dir()
        self.git("add", "-A")
        for name in tools.TOOLS:
            self.install(tools.tool_path(name))
        self.install(self.bin / "php")
        self.install(self.bin / "docker")
        self.say("gitleaks-stdin", json.dumps([{"RuleID": TOKEN_RULE, "Secret": "REDACTED"}]), code=1)
        self.say("php-m", "[PHP Modules]\nCore\ndom\nSimpleXML\n")
        self.say("php-r", "8.4")
        self.say("docker-info", "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?", code=1)
        self.say("psalm", "[]")
        self.say("shellcheck", '{"comments": []}')
        self.say("zizmor", "[]")

    def git(self, *args: str) -> str:
        """A git command in the made-up tree, which is named to it: where the test happens to stand decides nothing. What it printed."""
        done = subprocess.run(["git", "-C", str(self.root), "-c", "user.name=A Test", "-c", "user.email=test@example.invalid", *args], check=True, env=self.env, capture_output=True, text=True)
        return done.stdout.strip()

    def commit(self, message: str = "the tree") -> str:
        """Everything of the folder committed; the commit's name as the checks print it."""
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")[:10]

    def write(self, name: str, text: str | bytes) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text if isinstance(text, bytes) else text.encode())

    def laid(self, name: str) -> str:
        """What the stand-ins kept in their file of that name; nothing when there is none."""
        kept = self.fakes / name
        return kept.read_text(encoding="utf-8") if kept.exists() else ""

    def install(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(STAND_IN.format(fakes=self.fakes), encoding="utf-8")
        path.chmod(0o755)

    def say(self, name: str, text: str, code: int = 0) -> None:
        """What the stand-in of that name prints from now on, and how it ends."""
        (self.fakes / f"{name}.out").write_text(text, encoding="utf-8")
        (self.fakes / f"{name}.code").write_text(str(code), encoding="utf-8")

    def calls(self, name: str = "") -> list[str]:
        """How the stand-ins were called so far (only the one of that name, if given)."""
        log = self.fakes / "calls"
        return [line for line in (log.read_text(encoding="utf-8").splitlines() if log.exists() else []) if not name or line.split(" ", 1)[0] == name]

    def check(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(self.root / "scripts" / "security-check"), *args], cwd=self.root.parent, env=self.env, capture_output=True, text=True, timeout=120)

    def baseline(self, **entries: dict[str, dict[str, object]]) -> None:
        self.write("scripts/security-baseline.json", json.dumps(entries))

    def saved(self) -> dict[str, dict[str, dict[str, Any]]]:
        loaded: dict[str, dict[str, dict[str, Any]]] = json.loads((self.root / "scripts" / "security-baseline.json").read_text(encoding="utf-8"))
        return loaded


@pytest.fixture
def tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Tree:
    return Tree(tmp_path, monkeypatch)


def lines(done: subprocess.CompletedProcess[str]) -> dict[str, str]:
    """The line of each check: its name and `ok` or `FAIL`."""
    return {words[1]: words[0] for words in (line.split() for line in done.stdout.splitlines()) if len(words) >= 3 and words[0] in ("ok", "FAIL")}


def shell_finding(file: str = "scripts/deploy", code: int = 2086, line: int = 7) -> dict[str, object]:
    return {"file": file, "line": line, "endLine": line, "column": 3, "endColumn": 9, "level": "warning", "code": code, "message": "Double quote to prevent globbing and word splitting.", "fix": None}


def workflow_finding(action: str = "actions/checkout@v7", rule: str = "unpinned-uses", row: int = 31, path: str = ".github/workflows/ci.yml") -> dict[str, object]:
    """A finding as zizmor's JSON has it: the step it is in, then the primary place with the text it points at."""
    def place(kind: str, feature: str, annotation: str) -> dict[str, object]:
        return {"symbolic": {"key": {"Local": {"verbatim_path": path}}, "annotation": annotation, "kind": kind}, "concrete": {"location": {"start_point": {"row": row, "column": 14}}, "feature": feature}}
    return {"ident": rule, "desc": "unpinned action reference", "determinations": {"confidence": "High", "severity": "High", "persona": "Regular"},
            "locations": [place("Hidden", f"uses: {action}", "this step"), place("Primary", action, "action is not pinned to a hash")], "ignored": False}


# ---- every check, and what it asks of its program

def test_a_tree_in_which_no_program_finds_anything_is_green_and_each_program_was_asked_the_agreed_way(tree: Tree) -> None:
    tree.write("scripts/scratch.sh", "#!/bin/sh\nexit 0\n")
    done = tree.check()
    assert done.returncode == 0, done.stdout + done.stderr
    assert lines(done) == dict.fromkeys(OFFLINE, "ok") and list(lines(done)) == OFFLINE
    gitleaks = tree.calls("gitleaks")[0]
    assert gitleaks.startswith("gitleaks git ") and gitleaks.endswith(" --log-opts=--diff-merges=first-parent HEAD ."), "the commits of this branch, a merge as what it changes"
    assert all(word in gitleaks.split() for word in ("--redact", "--ignore-gitleaks-allow", "--config=.gitleaks.toml")), "nothing it finds shown, our allowlist alone"
    assert len(tree.calls("gitleaks")) == 1 and len(tree.calls("gitleaks-stdin")) == 1 and len(tree.calls("gitleaks-dir")) == 1
    assert tree.calls("php-l") == ["php-l -l server/version.php"]
    psalm = tree.calls("psalm")[0].split()
    assert psalm[1].endswith("/psalm.phar") and "--config=server/psalm.xml" in psalm and "--taint-analysis" in psalm and "--no-cache" in psalm
    assert tree.calls("shellcheck") == ["shellcheck --norc --severity=warning --format=json1 packaging/postinst scripts/deploy"], "the shell scripts git tracks: not the Python ones, not a file that is not tracked"
    zizmor = tree.calls("zizmor")[0].split()
    assert "--offline" in zizmor and "--no-config" in zizmor and "--no-ignores" in zizmor and "--min-severity=medium" in zizmor and zizmor[-1] == ".github/workflows"
    assert tree.calls("docker") == tree.calls("docker-info") == tree.calls("docker-run") == [], "a php that has what Psalm needs runs it itself"


def test_the_advisory_check_runs_only_with_its_flag_and_then_alone(tree: Tree) -> None:
    assert tree.check().returncode == 0
    assert tree.calls("osv-scanner") == [], "the check that asks the network is never part of the plain run"
    tree.say("osv-scanner", "Scanned uv.lock file and found 57 packages\nNo issues found")
    done = tree.check("--audit")
    assert done.returncode == 0 and lines(done) == {"audit": "ok"}
    assert "found 57 packages" in done.stdout, "the audit prints what it found, green too"
    assert tree.calls("osv-scanner") == ["osv-scanner scan source --no-resolve --config=osv-scanner.toml --lockfile=uv.lock --lockfile=ui/package-lock.json"]
    assert len(tree.calls("gitleaks")) == 1 and len(tree.calls("zizmor")) == 1, "and none of the other programs a second time"


def test_an_advisory_fails_the_audit_and_an_entry_set_aside_needs_its_reason_and_its_end(tree: Tree) -> None:
    tree.say("osv-scanner", "| https://osv.dev/GHSA-pcg2-g6cj-q92c | 5.3 | PyPI | tornado | 6.5.10 | 6.6 | uv.lock |", code=1)
    done = tree.check("--audit")
    assert done.returncode == 1 and lines(done) == {"audit": "FAIL"} and "GHSA-pcg2-g6cj-q92c" in done.stdout
    tree.say("osv-scanner", "No issues found")
    for entry in ('[[IgnoredVulns]]\nid = "GHSA-x"\neffectiveUntil = 2027-01-31\n', '[[IgnoredVulns]]\nid = "GHSA-x"\nreason = "a build tool"\n', '[[PackageOverrides]]\nname = "vite"\nignore = true\nreason = " "\neffectiveUntil = 2027-01-31\n'):
        tree.write("osv-scanner.toml", entry)
        asked = len(tree.calls("osv-scanner"))
        done = tree.check("--audit")
        assert done.returncode == 1 and "needs its reason and the day it ends" in done.stdout
        assert len(tree.calls("osv-scanner")) == asked, "the lists are not asked while the file is wrong"


# ---- a finding fails, and says where

def test_a_secret_in_the_commits_fails_with_the_place_and_never_with_the_value(tree: Tree) -> None:
    leak = {"RuleID": "github-pat", "File": "tests/test_x.py", "StartLine": 12, "Commit": "0123456789abcdef0123", "Date": "2026-11-13T08:00:00Z", "Secret": "REDACTED", "Match": "REDACTED", "Email": "someone@example.invalid"}
    tree.say("gitleaks", json.dumps([leak, leak]), code=1)
    done = tree.check()
    assert done.returncode == 1 and lines(done) == dict.fromkeys(OFFLINE, "ok") | {"gitleaks": "FAIL"}, "the other checks are still made"
    assert done.stdout.count("tests/test_x.py:12: github-pat, in commit 0123456789 of 2026-11-13") == 1
    assert "example.invalid" not in done.stdout and ".gitleaks.toml" in done.stdout


def made_up_token() -> str:
    """A value of the form of the secrets manager's access token that opens nothing: 0.<a UUID>.<thirty letters and digits>:<sixteen bytes in base64>. Put together from its parts, so that it stands whole in
    no file (the scan of the commits would find it in this one)."""
    return ".".join(["0", str(uuid.UUID(int=0x1234567890ABCDEF1234567890ABCDEF)), "Zx9" * 10]) + ":" + base64.b64encode(b"made up, no key!").decode()


def token_rule() -> dict[str, Any]:
    """The rule for the access token of the secrets manager, out of the .gitleaks.toml the gate uses."""
    config = tomllib.loads((ROOT / ".gitleaks.toml").read_text(encoding="utf-8"))
    found: dict[str, Any] = next(rule for rule in config["rules"] if rule["id"] == TOKEN_RULE)
    return found


def test_gitleaks_rule_for_the_secrets_managers_token_matches_a_made_up_one_whatever_the_line_calls_it_and_no_allowlist_entry_lets_it_pass() -> None:
    rule, token = token_rule(), made_up_token()
    assert "keywords" not in rule and "path" not in rule, "no word on the line and no path of ours narrows it (gitleaks' own list of files it leaves out is why the check `tokens` reads for itself)"
    pattern = re.compile(rule["regex"])
    for line in (token, f"BWS_ACCESS_TOKEN={token}", f'export BWS_ACCESS_TOKEN="{token}"', f"  token: '{token}'", f"bws run --access-token {token} -- deploy", f"<code>{token}</code>"):
        found = pattern.search(line)
        assert found is not None and found.group() == token, line
    number, secret, key = token.split(".", 2)[1], "Zx9" * 10, token.rsplit(":", 1)[1]
    for other in ("0.18.2", number, f"0.{number}", f"0.{number}.{secret}", f"0.{number}.{secret}:", f"{number}.{secret}:{key}", f"0.{number[:-1]}.{secret}:{key}", f"0.{number}.short:{key}"):
        assert pattern.search(other) is None, other
    config = tomllib.loads((ROOT / ".gitleaks.toml").read_text(encoding="utf-8"))
    for entry in config["allowlists"]:
        assert "paths" not in entry, "an entry is a value or its form, never a file or a folder: a token in that file would pass"
        assert not any(re.search(regex, token) for regex in entry["regexes"]), entry["description"]


def test_every_run_shows_the_scan_a_made_up_token_and_fails_when_our_rule_does_not_find_it(tree: Tree) -> None:
    assert tree.check("--only", "gitleaks").returncode == 0
    shown = (tree.fakes / "stdin").read_text(encoding="utf-8").strip()
    assert re.fullmatch(token_rule()["regex"], shown), "what the scan is shown is of the form the rule of the real file is written for"
    asked = tree.calls("gitleaks-stdin")[0].split()
    assert asked[1] == "stdin" and "--config=.gitleaks.toml" in asked and "--redact" in asked and "--ignore-gitleaks-allow" in asked
    for report, code in (("", 0), (json.dumps([{"RuleID": "generic-api-key"}]), 1)):
        tree.say("gitleaks-stdin", report, code)
        done = tree.check("--only", "gitleaks")
        assert done.returncode == 1 and f"the rule {TOKEN_RULE} of .gitleaks.toml does not find a token of that form any more" in done.stdout, "a rule that is gone, or an allowlist that swallows the token, is no pass"
        assert shown not in done.stdout


def test_gitleaks_is_shown_the_messages_and_what_is_changed_or_staged_and_no_file_git_does_not_track(tree: Tree) -> None:
    tree.write(".gitignore", "ignored.txt\n")
    commit = tree.commit("The first commit.\n\nIts message has a second paragraph.")
    assert tree.check("--only", "gitleaks").returncode == 0
    assert tree.laid("shown").split() == [f"./messages/{tree.git('rev-parse', 'HEAD')}"], "a folder that is as its last commit has only what its commits say to show"
    assert "The first commit.\n\nIts message has a second paragraph." in tree.laid("messages")

    tree.write("scripts/deploy", "#!/usr/bin/env bash\necho changed\n")
    tree.write("notes/new.txt", "a new file that git does not track is not this check's to open\n")
    tree.write("work/vmkey", "nor is the developer's own folder\n")
    tree.write("server/added.php", "<?php echo 'as it was added';\n")
    tree.write("ignored.txt", "what git ignores is not what a commit takes\n")
    tree.git("add", "server/added.php")
    tree.write("server/added.php", "<?php echo 'as it was changed after that';\n")
    tree.write("packaging/postinst", "#!/bin/sh\nexit 1\n")
    tree.git("add", "packaging/postinst")
    assert tree.check("--only", "gitleaks").returncode == 0
    asked = tree.calls("gitleaks-dir")[-1].split()
    assert asked[1] == "dir" and "--follow-symlinks" in asked and "--redact" in asked and "--config=.gitleaks.toml" in asked and "--ignore-gitleaks-allow" in asked
    shown = [name for name in tree.laid("shown").split() if not name.startswith("./messages/")]
    assert shown == ["./changed/packaging/postinst", "./changed/scripts/deploy", "./changed/server/added.php", "./staged/server/added.php"], "the changed and the added file as they lie, and what is staged where the file says something else by now"
    assert tree.laid("staged") == "<?php echo 'as it was added';\n", "the copy is what `git commit` would take"
    assert not Path(asked[-1]).exists(), "the folder is gone again"

    found = {"RuleID": "github-pat", "StartLine": 2, "Secret": "REDACTED", "Match": "REDACTED", "Commit": ""}
    leaks = [found | {"File": str(tree.root / "scripts" / "deploy"), "SymlinkFile": "@FOLDER@/changed/scripts/deploy"}, found | {"File": "@FOLDER@/staged/server/added.php", "SymlinkFile": ""},
             found | {"File": f"@FOLDER@/messages/{'0123456789abcdef' * 2}01234567", "SymlinkFile": ""}]
    tree.say("gitleaks-dir", json.dumps(leaks), code=1)
    done = tree.check()
    assert done.returncode == 1 and lines(done) == dict.fromkeys(OFFLINE, "ok") | {"gitleaks": "FAIL"}
    assert "scripts/deploy:2: github-pat, not committed yet" in done.stdout and "server/added.php:2: github-pat, as it is staged for the next commit" in done.stdout
    assert "the message of commit 0123456789: github-pat" in done.stdout and str(tree.root) not in done.stdout and asked[-1] not in done.stdout and commit not in done.stdout
    tree.say("gitleaks-dir", "FTL could not walk the folder", code=126)
    assert tree.check("--only", "gitleaks").returncode == 1, "a scan that broke is no pass"


def test_a_file_or_folder_of_access_tokens_that_git_tracks_fails_wherever_it_lies_and_is_not_shown(tree: Tree) -> None:
    for name in (".secrets", "server/.secrets-hosting", "server/.secrets.old", "notes/.secrets/token", "server/.secrets.d/hosting", "docs/secrets.md", "notes/x.secrets"):
        tree.write(name, "TOKEN=made-up-and-never-printed\n")
    done = tree.check("--only", "secret-files")
    assert done.returncode == 1 and lines(done) == {"secret-files": "FAIL"}, "in a tree whose .gitignore does not name it, the next `git add -A` would take it"
    assert ".secrets is not ignored by git" in done.stdout.splitlines()[1] and "server/.secrets-hosting is not ignored by git" in done.stdout and "is tracked" not in done.stdout
    tree.write(".gitignore", ".secrets\n.secrets*\n")
    done = tree.check("--only", "secret-files")
    assert done.returncode == 0 and lines(done) == {"secret-files": "ok"}, "in the folder, ignored and not tracked: that is where such a file belongs"
    tree.git("add", "-A", "--force")
    done = tree.check()
    assert done.returncode == 1 and lines(done) == dict.fromkeys(OFFLINE, "ok") | {"secret-files": "FAIL"}
    assert ".secrets is tracked by git" in done.stdout.splitlines()[1] and "git rm --cached" in done.stdout
    for name in ("server/.secrets-hosting", "server/.secrets.old", "notes/.secrets/token", "server/.secrets.d/hosting"):
        assert f"{name} is tracked by git" in done.stdout, "a part of the path named so is enough: the file, or a folder it lies in"
    assert "secrets.md" not in done.stdout and "x.secrets" not in done.stdout and "never-printed" not in done.stdout
    shown = tree.laid("shown").split()
    assert "./changed/notes/x.secrets" in shown and not any(part.startswith(".secrets") for name in shown for part in Path(name).parts), "no program is shown one either"
    tree.git("rm", "-q", "-r", "--cached", ".secrets", "server/.secrets-hosting", "server/.secrets.old", "notes/.secrets", "server/.secrets.d")
    assert tree.check("--only", "secret-files").returncode == 0


# ---- tokens: the script's own reading, with the real git

def only_tokens(tree: Tree, *args: str) -> tuple[int, list[str]]:
    """The check `tokens` alone: how it ended, and the lines under its own, without the advice."""
    done = tree.check("--only", "tokens", *args)
    assert made_up_token() not in done.stdout + done.stderr and "Zx9Zx9" not in done.stdout, "what was found is never printed"
    return done.returncode, [line.split("| ", 1)[1] for line in done.stdout.splitlines()[1:] if "| " in line and "it is not shown. Revoke" not in line]


def test_a_token_in_a_commit_is_found_whatever_the_file_is_and_also_after_it_was_taken_out_again(tree: Tree) -> None:
    token = made_up_token()
    tree.write(".gitattributes", "*.pdf binary\n*.bin -diff\n")
    tree.commit()
    places = {"ui/package-lock.json": f'{{"integrity": "{token}"}}\n'.encode(), "art/icon.svg": f"<svg><desc>{token}</desc></svg>\n".encode(), ".gitleaks.toml": f"# {token}\n".encode(),
              "docs/paper.pdf": b"%PDF-1.7\n\x00\xff\xfe stream " + token.encode() + b"\x00 endstream\n", "data/blob.bin": bytes(range(256)) + token.encode() + bytes(range(256)),
              "node_modules/x/a.js": f"const t = '{token}'\n".encode(), "notes/from windows.txt": f"BWS_ACCESS_TOKEN={token}\r\n".encode("utf-16"), "go.sum": f"x {token}\n".encode()}
    for name, content in places.items():
        tree.write(name, content)
    first = tree.commit("the files")
    code, found = only_tokens(tree)
    assert code == 1
    for name in places:
        assert f"commit {first}: {name}" in found and f"the index: {name} (as it is staged for the next commit)" in found and any(line.startswith(f"{name}:") for line in found), name

    for name in places:
        tree.write(name, b"taken out again\n")
    second = tree.commit("taken out")
    code, found = only_tokens(tree)
    assert code == 1 and sorted(found) == sorted(f"commit {first}: {name}" for name in places), "the commit that had it keeps it: nothing in the folder or the index says so any more, and the one that took it out has none"
    code, found = only_tokens(tree, "--all-history")
    assert code == 1 and sorted(found) == sorted(f"commit {commit}: {name}" for commit in (first, second) for name in places), "with every commit read, a line that takes it out is named too"


def test_a_token_in_a_commits_message_in_a_merges_resolution_or_in_a_tags_message_is_found(tree: Tree) -> None:
    token = made_up_token()
    tree.write("notes.txt", "one\n")
    tree.commit()
    tree.git("commit", "-q", "--allow-empty", "-m", f"The upload works again.\n\nTried by hand with {token} first.")
    said = tree.git("rev-parse", "HEAD")[:10]
    assert only_tokens(tree) == (1, [f"commit {said}: its message"])
    tree.git("reset", "-q", "--hard", "HEAD~1")
    assert only_tokens(tree)[0] == 0

    tree.git("checkout", "-q", "-b", "side")
    tree.write("side.txt", "from the side\n")
    tree.commit("the side")
    tree.git("checkout", "-q", "-")
    tree.write("main.txt", "from the main line\n")
    tree.commit("the main line")
    tree.git("merge", "-q", "--no-ff", "--no-commit", "side")
    tree.write("notes.txt", f"one\nthe resolution brought {token}\n")
    merge = tree.commit("the two lines joined")
    assert len(tree.git("rev-list", "--parents", "-1", "HEAD").split()) == 3, "a commit with two parents"
    code, found = only_tokens(tree)
    assert code == 1 and f"commit {merge}: notes.txt" in found and "notes.txt:2" in found, "what a merge itself changes is read like any other change"
    tree.git("reset", "-q", "--hard", "HEAD~1")
    assert only_tokens(tree)[0] == 0

    tree.git("tag", "v0.0.1")
    tree.git("tag", "-a", "v0.0.2", "-m", f"the release, signed off with {token}")
    assert only_tokens(tree) == (1, ["the tag v0.0.2: its message"])


def test_the_developers_own_git_settings_and_a_replaced_commit_hide_nothing_of_the_commits(tree: Tree) -> None:
    token = made_up_token()
    for setting, value in (("color.ui", "always"), ("color.diff", "always"), ("log.showRoot", "false"), ("log.diffMerges", "off"), ("diff.noprefix", "true"), ("diff.srcPrefix", "x/"), ("diff.dstPrefix", "longer/")):
        tree.git("config", setting, value)
    tree.write("notes.txt", f"{token}\n")
    first = tree.commit("the first commit of the repository has it")
    tree.write("notes.txt", "one\n")
    second = tree.commit("taken out")
    both = [f"commit {second}: notes.txt", f"commit {first}: notes.txt"]
    assert only_tokens(tree, "--all-history") == (1, both), "the commit without a parent is read whole, and the file is named as it is"

    tree.git("checkout", "-q", "-b", "side")
    tree.write("side.txt", "from the side\n")
    tree.commit("the side")
    tree.git("checkout", "-q", "-")
    tree.write("main.txt", "from the main line\n")
    tree.commit("the main line")
    tree.git("merge", "-q", "--no-ff", "--no-commit", "side")
    tree.write("more.txt", f"the resolution brought {token}\n")
    merge = tree.commit("the two lines joined")
    tree.git("rm", "-q", "more.txt")
    third = tree.commit("taken out again")
    assert only_tokens(tree, "--all-history") == (1, [f"commit {third}: more.txt", f"commit {merge}: more.txt", *both]), "a merge is read as what it changes, whatever the setting for the short flag says"

    tree.git("replace", "--graft", "HEAD")
    assert only_tokens(tree, "--all-history") == (1, [f"commit {third}: more.txt", f"commit {merge}: more.txt", *both]), "a commit is read as it is stored, with its parents: that is what a push sends, not what stands in its place here"
    assert tree.check("--only", "gitleaks").returncode == 0
    assert tree.laid("git-told").split() == ["false", "false", "true", "1"], "and the git that gitleaks starts is told the same: with colours in what it prints, gitleaks finds nothing in the commits"


def test_what_is_staged_is_read_as_it_is_staged_and_a_tracked_file_as_it_lies_but_no_file_git_does_not_track(tree: Tree) -> None:
    token = made_up_token()
    tree.write("notes.txt", "one\n")
    tree.commit()
    tree.write("notes.txt", f"one\ntwo\nBWS_ACCESS_TOKEN={token}\n")
    assert only_tokens(tree) == (1, ["notes.txt:3"]), "a tracked file that was changed and not added yet"
    tree.git("add", "notes.txt")
    tree.write("notes.txt", "one\n")
    assert only_tokens(tree) == (1, ["the index: notes.txt (as it is staged for the next commit)"]), "taken out of the file again, and still what `git commit` takes"
    tree.git("add", "notes.txt")
    assert only_tokens(tree)[0] == 0

    tree.write("work/scratch.txt", f"{token}\n")
    tree.write("new.txt", f"{token}\n")
    done = tree.check()
    assert done.returncode == 0 and lines(done) == dict.fromkeys(OFFLINE, "ok"), "a file git does not track is opened by no check"
    assert "scratch.txt" not in tree.laid("shown") and "new.txt" not in tree.laid("shown")
    tree.git("add", "new.txt")
    assert only_tokens(tree) == (1, ["the index: new.txt (as it is staged for the next commit)", "new.txt:1"]), "once it is added it is"
    tree.git("rm", "-q", "--cached", "new.txt")

    tree.write(f"notes/{token}.txt", "the token as a file's name\n")
    tree.git("add", "notes")
    code, found = only_tokens(tree)
    assert code == 1 and found == ["the index: notes/(a token, not shown).txt (as it is staged for the next commit)"]


def test_by_default_only_the_commits_the_remote_does_not_have_are_read_and_all_of_them_when_asked(tree: Tree) -> None:
    token = made_up_token()
    tree.write("notes.txt", f"{token}\n")
    first = tree.commit("with it")
    tree.write("notes.txt", "one\n")
    second = tree.commit("without it")
    assert only_tokens(tree)[0] == 1
    tree.git("update-ref", "refs/remotes/origin/master", "HEAD")
    done = tree.check("--only", "tokens")
    assert done.returncode == 0 and "that origin does not have yet (0)" in done.stdout, "what is pushed is on GitHub already: the daily run does not read it again"
    assert only_tokens(tree, "--all-history") == (1, [f"commit {second}: notes.txt", f"commit {first}: notes.txt"])
    tree.write("more.txt", "more\n")
    tree.commit("one more")
    done = tree.check("--only", "tokens")
    assert done.returncode == 0 and "that origin does not have yet (1)" in done.stdout
    tree.git("update-ref", "refs/remotes/elsewhere/master", "HEAD")
    assert "does not have yet (1)" in tree.check("--only", "tokens").stdout, "a remote of another name is not GitHub"

    tree.git("checkout", "-q", "-b", "side")
    tree.write("side.txt", f"{token}\n")
    side = tree.commit("the side has it")
    tree.git("checkout", "-q", "-")
    assert only_tokens(tree) == (1, [f"commit {side}: side.txt"]), "a branch that is not checked out is pushed as easily as this one"
    tree.git("tag", "kept", "side")
    tree.git("branch", "-q", "-D", "side")
    assert only_tokens(tree) == (1, [f"commit {side}: side.txt"]), "and so is a tag, also one without a message"
    tree.git("tag", "-d", "kept")
    assert only_tokens(tree)[0] == 0


def test_a_commit_that_takes_out_a_token_the_remote_already_has_is_not_one_that_carries_it(tree: Tree) -> None:
    tree.write("notes.txt", f"{made_up_token()}\n")
    first = tree.commit("with it")
    tree.git("update-ref", "refs/remotes/origin/master", "HEAD")
    tree.write("notes.txt", "gone\n")
    second = tree.commit("without it")
    assert only_tokens(tree)[0] == 0, "the token is on a line the commit takes out; the commit that had it is on GitHub"
    assert only_tokens(tree, "--all-history") == (1, [f"commit {second}: notes.txt", f"commit {first}: notes.txt"])
    tree.write("notes.txt", f"{made_up_token()}\n")
    third = tree.commit("with it again")
    assert f"commit {third}: notes.txt" in only_tokens(tree)[1], "a line that puts one in is read"


def test_what_only_looks_like_a_token_is_none(tree: Tree) -> None:
    number, secret, key = made_up_token().split(".", 2)[1], "Zq7" * 10, made_up_token().rsplit(":", 1)[1]
    others = ("0.18.2", number, f"0.{number}", f"0.{number}.{secret}", f"0.{number}.{secret}:", f"{number}.{secret}:{key}", f"0.{number[:-1]}.{secret}:{key}", f"0.{number}.short:{key}", f"0.{number}.{secret}:short")
    tree.write("notes.txt", "\n".join(others) + "\n")
    tree.commit("\n\n".join(others))
    done = tree.check("--only", "tokens")
    assert done.returncode == 0, done.stdout
    tree.write("notes.txt", f"0.{number}.{'a' * 20}:{'b' * 16}\n")
    assert tree.check("--only", "tokens").returncode == 1, "twenty letters and digits and sixteen of the key are enough: looser than a real one"
    slashes = base64.b64encode(b"\xff" * 16).decode().replace("/", "\\/")
    tree.write("notes.txt", f'{{"token": "0.{number}.{secret}:{slashes}"}}\n')
    assert tree.check("--only", "tokens").returncode == 1, "the key as JSON writes it, a backslash before each `/`"


def test_gitleaks_that_breaks_and_an_allowlist_without_reasons_are_failures(tree: Tree) -> None:
    tree.say("gitleaks", "FTL could not read the repository", code=126)
    done = tree.check("--only", "gitleaks")
    assert done.returncode == 1 and "could not read the repository" in done.stdout
    tree.say("gitleaks", "", code=1)
    assert tree.check("--only", "gitleaks").returncode == 1, "the code for leaks without a report of them is no pass either"
    tree.say("gitleaks", "")
    tree.write(".gitleaks.toml", '[[allowlists]]\nregexes = [\'\'\'^x$\'\'\']\n')
    done = tree.check("--only", "gitleaks")
    assert done.returncode == 1 and "has no description" in done.stdout
    tree.write(".gitleaks.toml", "")
    tree.write(".gitleaksignore", "0123:tests/test_x.py:github-pat:12\n")
    done = tree.check("--only", "gitleaks")
    assert done.returncode == 1 and ".gitleaksignore is not used here" in done.stdout


def test_a_php_file_that_does_not_parse_fails(tree: Tree) -> None:
    tree.say("php-l", "PHP Parse error:  syntax error, unexpected end of file in server/version.php on line 3", code=255)
    done = tree.check()
    assert done.returncode == 1 and lines(done)["php-lint"] == "FAIL" and "unexpected end of file in server/version.php on line 3" in done.stdout


def test_of_what_psalm_reports_only_request_data_reaching_a_sink_counts(tree: Tree) -> None:
    other = {"type": "UndefinedFunction", "severity": "error", "file_name": "server/version.php", "line_from": 52, "message": "Function status_db does not exist", "is_security": False, "taint_trace": None}
    tree.say("psalm", json.dumps([other]), code=2)
    assert tree.check("--only", "psalm").returncode == 0, "the types of the PHP are not this check's question"
    tainted = {"type": "TaintedHtml", "severity": "error", "file_name": "server/version.php", "line_from": 66, "message": "Detected tainted HTML", "is_security": True,
               "taint_trace": [{"file_name": "server/version.php", "line_from": 33, "label": "$_GET['v']"}, {"file_name": "server/version.php", "line_from": 66, "label": "call to echo"}]}
    tree.say("psalm", "a remark of the program before its report\n" + json.dumps([other, tainted]), code=2)
    done = tree.check("--only", "psalm")
    assert done.returncode == 1 and "server/version.php:66: TaintedHtml: Detected tainted HTML" in done.stdout and "server/version.php:33: $_GET['v']" in done.stdout
    assert "UndefinedFunction" not in done.stdout


def test_psalm_that_cannot_run_is_never_a_pass(tree: Tree) -> None:
    tree.say("psalm", "Problem parsing server/psalm.xml", code=1)
    done = tree.check("--only", "psalm")
    assert done.returncode == 1 and "Problem parsing server/psalm.xml" in done.stdout
    tree.say("psalm", "", code=0)
    assert tree.check("--only", "psalm").returncode == 1, "no report is not an empty report"
    tree.say("php-m", "[PHP Modules]\nCore\njson\n")
    asked = len(tree.calls("psalm"))
    done = tree.check("--only", "psalm")
    assert done.returncode == 1 and "this php has no dom and no simplexml extension, which Psalm needs, and docker cannot be used: Cannot connect to the Docker daemon" in done.stdout
    assert "apt install php-xml" in done.stdout and tree.calls("docker-run") == [] and len(tree.calls("psalm")) == asked, "neither way is there: that is a failure, and nothing was run"


def pin_php_image(tree: Tree, minor: str) -> str:
    """Pins a made-up image for that php in the tree's copy of scripts/security-tools; its name."""
    image = "php@sha256:" + "ab" * 32
    with (tree.root / "scripts" / "security-tools").open("a", encoding="utf-8") as script:
        script.write(f'\nPHP_IMAGES["{minor}"] = "{image}"\n')
    return image


def test_where_php_lacks_the_extensions_psalm_runs_in_the_pinned_php_image_read_only_and_without_network(tree: Tree) -> None:
    tree.say("php-m", "[PHP Modules]\nCore\njson\n")
    tree.say("docker-info", "29.9.3")
    tree.say("docker-run", "[]")
    tree.say("php-r", "8.5")
    done = tree.check("--only", "psalm")
    assert done.returncode == 1 and "no php image is pinned for PHP 8.5 (PHP_IMAGES in scripts/security-tools)" in done.stdout and tree.calls("docker-run") == [], "an image that is not pinned is not run"

    tree.say("php-r", "8.4")
    image = pin_php_image(tree, "8.4")
    done = tree.check("--only", "psalm")
    assert done.returncode == 0 and lines(done) == {"psalm": "ok"}, done.stdout
    asked = tree.calls("docker-run")[0].split()
    assert asked[1:5] == ["run", "--rm", "--pull=never", "--network=none"], "never fetched by the check, and no network inside"
    mounts = [asked[at + 1] for at, word in enumerate(asked) if word == "--volume"]
    assert mounts == [f"{tree.root}/server:/neoaprs/server:ro", f"{tools.tool_path('psalm')}:/psalm.phar:ro"], "server/ and the archive, both read-only, and nothing else of the machine"
    assert asked[asked.index(image) - 2:] == ["--workdir", "/neoaprs", image, "php", "/psalm.phar", "--config=server/psalm.xml", "--taint-analysis", "--output-format=json", "--no-cache", "--no-progress", "--threads=1"]
    assert tree.calls("psalm") == [], "the php that lacks the extensions is not asked to run it"

    tainted = {"type": "TaintedHtml", "file_name": "server/version.php", "line_from": 66, "message": "Detected tainted HTML", "is_security": True, "taint_trace": None}
    tree.say("docker-run", json.dumps([tainted]), code=2)
    done = tree.check("--only", "psalm")
    assert done.returncode == 1 and "server/version.php:66: TaintedHtml: Detected tainted HTML" in done.stdout, "what it reports counts as it does outside the container"

    tree.say("docker-run", f"Unable to find image '{image}' locally\ndocker: Error response from daemon: No such image: {image}", code=125)
    done = tree.check("--only", "psalm")
    assert done.returncode == 1 and f"when it is not on this machine yet: docker pull {image}" in done.stdout
    tree.say("docker-run", "", code=0)
    assert tree.check("--only", "psalm").returncode == 1, "no report is not an empty report, here neither"

    tree.say("php-r", "8.5")
    asked_before = len(tree.calls("docker-run"))
    done = tree.check("--only", "psalm")
    assert done.returncode == 1 and "no php image is pinned for PHP 8.5" in done.stdout and len(tree.calls("docker-run")) == asked_before, "the image of another php is not taken for it"


def test_the_pinned_php_images_are_named_by_their_digest() -> None:
    for minor, image in tools.PHP_IMAGES.items():
        assert re.fullmatch(r"\d+\.\d+", minor) and re.fullmatch(r"php@sha256:[0-9a-f]{64}", image), f"{minor}: the official image by its digest, never by a tag that can move"


# ---- the baseline of shellcheck and zizmor

def test_a_finding_fails_a_baseline_entry_lets_it_pass_and_a_new_one_beside_it_fails(tree: Tree) -> None:
    tree.say("zizmor", json.dumps([workflow_finding(), workflow_finding(row=65)]), code=14)
    done = tree.check("--only", "zizmor")
    assert done.returncode == 1 and "new: .github/workflows/ci.yml unpinned-uses actions/checkout@v7" in done.stdout
    assert ".github/workflows/ci.yml:32: unpinned-uses (high): unpinned action reference: action is not pinned to a hash" in done.stdout and ".github/workflows/ci.yml:66:" in done.stdout

    tree.baseline(zizmor={".github/workflows/ci.yml unpinned-uses actions/checkout@v7": {"count": 2, "reason": "known: pinned by commit soon"}})
    done = tree.check("--only", "zizmor")
    assert done.returncode == 0 and lines(done) == {"zizmor": "ok"}, done.stdout
    tree.say("zizmor", json.dumps([workflow_finding(row=40), workflow_finding(row=90)]), code=14)
    assert tree.check("--only", "zizmor").returncode == 0, "the lines of a finding may move"

    tree.say("zizmor", json.dumps([workflow_finding(), workflow_finding(row=65), workflow_finding("someone/else@v1", row=70)]), code=14)
    done = tree.check("--only", "zizmor")
    assert done.returncode == 1 and "new: .github/workflows/ci.yml unpinned-uses someone/else@v1" in done.stdout and "actions/checkout@v7" not in done.stdout

    tree.say("zizmor", json.dumps([workflow_finding(), workflow_finding(row=65), workflow_finding(row=99)]), code=14)
    done = tree.check("--only", "zizmor")
    assert done.returncode == 1 and "more: .github/workflows/ci.yml unpinned-uses actions/checkout@v7: 3 now, the baseline has 2" in done.stdout


def test_a_baseline_entry_needs_its_reason_and_one_that_holds_more_than_is_found_says_so(tree: Tree) -> None:
    tree.say("shellcheck", json.dumps({"comments": [shell_finding()]}), code=1)
    tree.baseline(shellcheck={"scripts/deploy SC2086": {"count": 1, "reason": "  "}})
    done = tree.check("--only", "shellcheck")
    assert done.returncode == 1 and "no reason: the baseline entry 'scripts/deploy SC2086' needs one" in done.stdout
    tree.baseline(shellcheck={"scripts/deploy SC2086": {"count": 2, "reason": "the word is split on purpose"}})
    done = tree.check("--only", "shellcheck")
    assert done.returncode == 0 and "the baseline can be tightened: scripts/security-check --update" in done.stdout
    tree.say("shellcheck", json.dumps({"comments": [shell_finding(), shell_finding("packaging/postinst", 2155)]}), code=1)
    done = tree.check("--only", "shellcheck")
    assert done.returncode == 1 and "new: packaging/postinst SC2155" in done.stdout and "packaging/postinst:7: SC2155 (warning)" in done.stdout


def test_a_program_of_the_baseline_that_breaks_is_a_failure(tree: Tree) -> None:
    tree.say("shellcheck", "shellcheck: scripts/deploy: openBinaryFile: does not exist", code=2)
    tree.say("zizmor", "fatal: no audit was performed", code=1)
    done = tree.check()
    assert done.returncode == 1 and lines(done)["shellcheck"] == "FAIL" and lines(done)["zizmor"] == "FAIL"
    assert "openBinaryFile" in done.stdout and "no audit was performed" in done.stdout
    tree.say("zizmor", "not a report", code=14)
    assert tree.check("--only", "zizmor").returncode == 1


def test_update_never_makes_the_baseline_larger_unless_told_and_a_new_entry_then_waits_for_its_reason(tree: Tree) -> None:
    tree.say("shellcheck", json.dumps({"comments": [shell_finding()]}), code=1)
    tree.say("zizmor", json.dumps([workflow_finding(), workflow_finding(row=65)]), code=14)
    refused = tree.check("--update")
    assert refused.returncode == 1 and "the baseline is not made larger" in refused.stdout and not (tree.root / "scripts" / "security-baseline.json").exists()

    written = tree.check("--update", "--allow-growth")
    assert written.returncode == 0 and "wait for their reason" in written.stdout
    assert tree.saved() == {"shellcheck": {"scripts/deploy SC2086": {"count": 1, "reason": ""}}, "zizmor": {".github/workflows/ci.yml unpinned-uses actions/checkout@v7": {"count": 2, "reason": ""}}}
    assert tree.check().returncode == 1, "an entry without its reason does not pass"

    tree.baseline(shellcheck={"scripts/deploy SC2086": {"count": 1, "reason": "split on purpose"}}, zizmor={".github/workflows/ci.yml unpinned-uses actions/checkout@v7": {"count": 2, "reason": "pinned by commit soon"}})
    assert tree.check().returncode == 0

    tree.say("shellcheck", '{"comments": []}')
    tree.say("zizmor", json.dumps([workflow_finding()]), code=14)
    tightened = tree.check("--update")
    assert tightened.returncode == 0 and "wait for their reason" not in tightened.stdout
    assert tree.saved() == {"shellcheck": {}, "zizmor": {".github/workflows/ci.yml unpinned-uses actions/checkout@v7": {"count": 1, "reason": "pinned by commit soon"}}}, "what is gone leaves the baseline, the reasons stay"


def test_a_settings_file_and_a_disable_comment_without_its_reason_are_findings_and_no_program_is_handed_settings(tree: Tree) -> None:
    tree.write(".shellcheckrc", "disable=SC2086\n")
    tree.write(".github/zizmor.yml", "rules:\n  unpinned-uses:\n    disable: true\n")
    tree.write("scripts/deploy", "#!/usr/bin/env bash\n# shellcheck disable=SC2086\necho $1\n  # shellcheck disable=SC2155   # the name is one word: nothing to lose\nlocal x=\"$(date)\"\n# shellcheck source=/dev/null\n"
                                 "# shellcheck shell=bash disable=SC2034,SC2154 #\n")
    tree.write("untracked/.shellcheckrc", "a file git does not track is not looked at\n")
    tree.git("add", ".shellcheckrc", ".github", "scripts")
    tree.env |= {"SHELLCHECK_OPTS": "--exclude=SC2086", "ZIZMOR_CONFIG": str(tree.root / ".github" / "zizmor.yml"), "GITLEAKS_CONFIG": os.devnull}
    done = tree.check()
    assert done.returncode == 1 and lines(done) == dict.fromkeys(OFFLINE, "ok") | {"shellcheck": "FAIL", "zizmor": "FAIL"}
    assert "new: .shellcheckrc settings of shellcheck" in done.stdout and "new: .github/zizmor.yml settings of zizmor" in done.stdout and "untracked" not in done.stdout
    assert "new: scripts/deploy disable=SC2086 without its reason" in done.stdout and "    scripts/deploy:2: " in done.stdout
    assert "new: scripts/deploy disable=SC2034,SC2154 without its reason" in done.stdout and "    scripts/deploy:7: " in done.stdout and "SC2155" not in done.stdout, "a comment that says why is what the guide asks for"
    assert "--norc" in tree.calls("shellcheck")[0].split() and "--no-config" in tree.calls("zizmor")[0].split(), "and neither program reads the file"
    assert tree.laid("handed") == "", "nor the settings of the environment"

    tree.baseline(shellcheck={".shellcheckrc settings of shellcheck": {"count": 1, "reason": "for the editor: it sets the shell, nothing is switched off"},
                              "scripts/deploy disable=SC2086 without its reason": {"count": 1, "reason": "generated: the line is written by the packaging"},
                              "scripts/deploy disable=SC2034,SC2154 without its reason": {"count": 1, "reason": "generated too"}},
                  zizmor={".github/zizmor.yml settings of zizmor": {"count": 1, "reason": "for the editor's plugin: it switches nothing off"}})
    done = tree.check()
    assert done.returncode == 0, "the baseline may name each, with the reason it is there: " + done.stdout


# ---- a program that is not there

@pytest.mark.parametrize("name", ["gitleaks", "psalm", "shellcheck", "zizmor"])
def test_a_tool_that_is_not_in_the_cache_fails_its_check_with_the_sentence_that_says_how_to_get_it(tree: Tree, name: str) -> None:
    tools.tool_path(name).unlink()
    done = tree.check()
    assert done.returncode == 1
    assert lines(done) == dict.fromkeys(OFFLINE, "ok") | {name: "FAIL"}, "only its own check fails"
    assert f"{name} {tools.TOOLS[name].version} is not in the cache ({os.environ['NEOAPRS_BUILD_CACHE']}/security-tools): scripts/security-tools fetches it" in done.stdout


def test_a_missing_tool_fails_the_audit_and_the_update_too(tree: Tree) -> None:
    tools.tool_path("osv-scanner").unlink()
    done = tree.check("--audit")
    assert done.returncode == 1 and "osv-scanner" in done.stdout and "scripts/security-tools fetches it" in done.stdout
    tools.tool_path("zizmor").unlink()
    done = tree.check("--update", "--allow-growth")
    assert done.returncode == 1 and "the baseline was not written" in done.stderr and not (tree.root / "scripts" / "security-baseline.json").exists()


def test_without_php_the_two_checks_of_the_server_fail_and_say_what_to_install(tree: Tree, tmp_path: Path) -> None:
    (tree.bin / "php").unlink()
    for program in ("git", "basename", "cat", "find", "sed", "sort"):             # a PATH that holds what the script and the stand-ins need, and no php
        found = shutil.which(program)
        assert found is not None
        os.symlink(found, tree.bin / program)
    done = subprocess.run([sys.executable, str(tree.root / "scripts" / "security-check")], cwd=tmp_path, env={**tree.env, "PATH": str(tree.bin)}, capture_output=True, text=True, timeout=120)
    assert done.returncode == 1 and lines(done) == dict.fromkeys(OFFLINE, "ok") | {"php-lint": "FAIL", "psalm": "FAIL"}
    assert done.stdout.count("php is not installed") == 2 and "apt install php-cli php-xml" in done.stdout


def test_the_flags_that_exclude_each_other_are_refused(tree: Tree) -> None:
    for args in (["--audit", "--update"], ["--audit", "--only", "zizmor"], ["--allow-growth"], ["--only", "audit"], ["--all-history", "--audit"], ["--all-history", "--update"], ["--bogus"]):
        assert tree.check(*args).returncode == 2, args
    assert tree.calls() == []


# ---- scripts/security-tools: the pins, the hosts, the cache

def test_every_pin_is_a_version_a_file_of_its_github_release_and_a_digest() -> None:
    assert set(tools.TOOLS) == {"gitleaks", "shellcheck", "zizmor", "osv-scanner", "psalm"}
    for name, tool in tools.TOOLS.items():
        assert tools.allowed(tool.url) and tool.url.startswith("https://github.com/") and "/releases/download/" in tool.url, name
        assert tool.version in tool.url and len(tool.sha256) == 64 and int(tool.sha256, 16) >= 0, name
        assert tools.tool_path(name).parent.name == f"{name}-{tool.version}", "a new pin is a new folder: the program of the old one is never taken for it"


def test_only_githubs_hosts_of_release_files_are_asked() -> None:
    assert tools.allowed("https://release-assets.githubusercontent.com/github-production-release-asset/1/2?sig=x")
    for url in ("http://github.com/gitleaks/gitleaks/releases/download/v1/x", "https://github.com.example.org/x", "https://example.org/gitleaks", "https://user@github.com/x", "https://github.com:8443/x", "file:///etc/passwd"):
        assert not tools.allowed(url), url
    with pytest.raises(tools.FetchError, match="not one of GitHub's addresses"):
        tools.download("https://example.org/gitleaks.tar.gz", Path(os.devnull), "0" * 64)


def archive_of(member: str, body: bytes) -> bytes:
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as tar:
        info = tarfile.TarInfo(member)
        info.size = len(body)
        tar.addfile(info, io.BytesIO(body))
    return data.getvalue()


async def test_a_tool_is_fetched_checked_and_unpacked_into_the_cache_and_another_file_is_thrown_away(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server = await http_server()
    program = b"#!/bin/sh\necho the tool\n"
    archive = archive_of("tool-1.2.3/tool", program)
    server.route("/tool.tar.gz", body=archive)
    server.route("/plain", body=program)
    monkeypatch.setenv("NEOAPRS_BUILD_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(tools, "allowed", lambda url: url.startswith(server.url("")))
    monkeypatch.setattr(tools, "available_here", lambda: True)
    monkeypatch.setitem(tools.TOOLS, "packed", tools.Tool("1.2.3", server.url("/tool.tar.gz"), hashlib.sha256(archive).hexdigest(), "tool", "tool-1.2.3/tool"))
    monkeypatch.setitem(tools.TOOLS, "plain", tools.Tool("4.5", server.url("/plain"), hashlib.sha256(program).hexdigest(), "plain.phar"))
    monkeypatch.setitem(tools.TOOLS, "other", tools.Tool("6", server.url("/plain"), "0" * 64, "other"))

    assert ["packed", "1.2.3", "not", "in", "the", "cache"] in [line.split() for line in tools.listing().splitlines()]
    packed = await asyncio.to_thread(tools.fetch, "packed")
    assert packed == tmp_path / "cache" / "security-tools" / "packed-1.2.3" / "tool" and packed.read_bytes() == program and os.access(packed, os.X_OK)
    plain = await asyncio.to_thread(tools.fetch, "plain")
    assert plain.name == "plain.phar" and plain.read_bytes() == program
    assert ["packed", "1.2.3", "in", "the", "cache:", str(packed)] in [line.split() for line in tools.listing().splitlines()]
    assert await asyncio.to_thread(tools.fetch, "packed") == packed and server.requests.count("/tool.tar.gz") == 1, "what is in the cache is not fetched again"

    with pytest.raises(tools.FetchError, match="is not the file that was expected"):
        await asyncio.to_thread(tools.fetch, "other")
    assert sorted(p.name for p in (tmp_path / "cache" / "security-tools").iterdir()) == ["packed-1.2.3", "plain-4.5"], "nothing of a file with another digest is kept"


async def test_a_transfer_that_breaks_off_is_tried_again_and_a_refusal_or_a_redirect_elsewhere_is_final(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server = await http_server()
    server.route("/cut", body=b"x" * 10, announce=100)
    server.route("/gone", status=404)
    server.route("/away", status=302, headers={"Location": "https://example.org/tool"})
    monkeypatch.setattr(tools, "allowed", lambda url: url.startswith(server.url("")))
    target = tmp_path / "file"
    with pytest.raises(tools.FetchError, match="could not be fetched"):
        await asyncio.to_thread(tools.download, server.url("/cut"), target, "0" * 64, 0.0)
    assert server.requests.count("/cut") == 3
    with pytest.raises(tools.FetchError, match="the server answered 404"):
        await asyncio.to_thread(tools.download, server.url("/gone"), target, "0" * 64, 0.0)
    assert server.requests.count("/gone") == 1
    with pytest.raises(tools.FetchError, match="sent on to https://example.org/tool"):
        await asyncio.to_thread(tools.download, server.url("/away"), target, "0" * 64, 0.0)


def test_on_another_system_no_tool_is_available_and_nothing_is_asked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEOAPRS_BUILD_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(tools, "available_here", lambda: False)
    assert all(line.endswith("not available here") for line in tools.listing().splitlines()) and len(tools.listing().splitlines()) == len(tools.TOOLS)
    with pytest.raises(tools.FetchError, match="gitleaks is not available here"):
        tools.fetch("gitleaks")
    assert not (tmp_path / "cache").exists()


def test_the_list_of_the_script_names_each_tool_with_its_version_and_fetches_nothing(tree: Tree) -> None:
    done = subprocess.run([sys.executable, str(tree.root / "scripts" / "security-tools"), "--list"], cwd=tree.root.parent, env=tree.env, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0 and len(done.stdout.splitlines()) == len(tools.TOOLS)
    for name, tool in tools.TOOLS.items():
        assert any(line.split()[:2] == [name, tool.version] and "in the cache" in line for line in done.stdout.splitlines()), name
    assert subprocess.run([sys.executable, str(tree.root / "scripts" / "security-tools"), "nothing"], cwd=tree.root.parent, env=tree.env, capture_output=True, text=True, timeout=60).returncode == 2
