"""scripts/release makes a release in one command and can be run again after any failure. It is run here for real, on a clone of a made-up repository whose origin is a bare repository in a temporary folder, with a fake `gh`
(a program that keeps the state of the runs and of the release in a file and logs every call), fake `scripts/check`, `scripts/build-page` and `server/deploy.sh`, and a loopback server for the download links: the
order of the steps, the dry run, the resume after a failure at each step, and the cases it refuses. Nothing here touches GitHub."""
import http.server
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.support.ptyline import posix_only

pytestmark = posix_only      # (bash scripts and a script with a shebang: a development tool, not the product)

ROOT = Path(__file__).resolve().parent.parent
VERSION = "0.9.1"
TAG = f"v{VERSION}"
ASSETS = sorted([f"neoaprs-{VERSION}-py3-none-any.whl", f"neoaprs-{VERSION}.tar.gz", f"NeoAPRS-Setup-{VERSION}.exe", f"NeoAPRS-{VERSION}-x86_64.AppImage", f"neoaprs_{VERSION}_amd64.deb", f"neoaprs_{VERSION}_arm64.deb", "install.sh", "NeoAPRS-Setup.exe", "NeoAPRS-x86_64.AppImage", "SHA256SUMS"])

FAKE_GH = '''#!{python}
"""A gh that keeps the state of the runs and of the release in {state} and logs every call to {log}."""
import json, sys
STATE, LOG = "{state}", "{log}"
args = sys.argv[1:]
open(LOG, "a").write("gh " + " ".join(args) + "\\n")
s = json.load(open(STATE))
def save(): json.dump(s, open(STATE, "w"))
def flag(name):
    return args[args.index(name) + 1] if name in args else None
def fail(text, code=1):
    sys.stderr.write(text + "\\n"); sys.exit(code)
if s.get("rate_limited", 0) > 0 and args[:1] == ["run"]:
    s["rate_limited"] -= 1; save(); fail("HTTP 403: API rate limit exceeded for 203.0.113.1.")
if args[:2] == ["auth", "status"]:
    sys.exit(0 if s["auth"] else fail("You are not logged into any GitHub hosts.", 1))
def outcome(workflow, attempt):
    plan = s[workflow]["plan"]
    return plan[min(attempt, len(plan)) - 1]
def runs_of(workflow):
    return [r for r in s["runs"] if r["workflow"] == workflow]
if args[:2] == ["run", "list"]:
    workflow, sha, branch = flag("--workflow"), flag("--commit"), flag("--branch")
    key = workflow + (sha or branch)
    s["looks"][key] = s["looks"].get(key, 0) + 1
    found = [r for r in runs_of(workflow) if r["headSha"] == sha or (branch and r["headBranch"] == branch)]
    if not found and s["looks"][key] > s["appear_after"] and s[workflow]["plan"]:
        run = {{"workflow": workflow, "databaseId": 100 + len(s["runs"]), "status": "queued", "conclusion": "", "attempt": 1, "headSha": sha or "", "headBranch": branch or "",
               "url": "https://github.invalid/runs/" + str(100 + len(s["runs"]))}}
        s["runs"].append(run); found = [run]
    save(); print(json.dumps(found)); sys.exit(0)
def find(run_id):
    return next(r for r in s["runs"] if str(r["databaseId"]) == run_id)
if args[:2] == ["run", "watch"]:
    run = find(args[2]); run["status"] = "completed"; run["conclusion"] = outcome(run["workflow"], run["attempt"])
    if run["workflow"] == "release.yml" and run["conclusion"] == "success":
        s["release"]["made"] = True
    save(); print("watching run", run["databaseId"]); sys.exit(0 if run["conclusion"] == "success" else 1)
if args[:2] == ["run", "view"] and "--log-failed" in args:
    print(s["log"]); sys.exit(0)
if args[:2] == ["run", "view"]:
    run = dict(find(args[2]))
    run["jobs"] = [{{"name": "python (ubuntu-latest)", "conclusion": "failure", "steps": [{{"name": "pytest", "conclusion": "failure"}}]}}, {{"name": "page", "conclusion": "success", "steps": []}}] if run["conclusion"] == "failure" else []
    print(json.dumps(run)); sys.exit(0)
if args[:2] == ["run", "rerun"]:
    run = find(args[2]); run["attempt"] += 1; run["status"] = "queued"; run["conclusion"] = ""; save(); sys.exit(0)
if args[:2] == ["release", "view"]:
    if not s["release"]["made"]:
        fail("release not found")
    names = s["release"]["assets"]
    print(json.dumps({{"tagName": args[2], "isDraft": s["release"]["draft"], "isPrerelease": False, "url": "https://github.invalid/releases/" + args[2],
                      "assets": [{{"name": n, "url": s["base"] + "/download/" + n}} for n in names]}})); sys.exit(0)
fail("fake gh: no such command: " + " ".join(args), 2)
'''

SCRIPT = '#!/usr/bin/env bash\necho "{name}" >> "{log}"\n{body}\n'


def make_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class Downloads(http.server.BaseHTTPRequestHandler):
    missing: set[str] = set()

    def do_HEAD(self) -> None:
        self.send_response(404 if self.path.rsplit("/", 1)[-1] in self.missing else 200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        pass


class Rig:
    """A made-up repository at 0.9.0 with notes under `## Unreleased`, its bare origin, the fakes, and `release(...)` which runs the copy of scripts/release in the clone."""

    def __init__(self, tmp: Path, base: str) -> None:
        self.tmp = tmp
        self.log = tmp / "calls.log"
        self.state_file = tmp / "gh.json"
        self.remote = tmp / "origin.git"
        self.work = tmp / "work"
        self.bin = tmp / "bin"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}", HOME=str(tmp / "home"), GIT_AUTHOR_NAME="John", GIT_AUTHOR_EMAIL="john@example.invalid", GIT_COMMITTER_NAME="John", GIT_COMMITTER_EMAIL="john@example.invalid",
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, LC_ALL="C.UTF-8")
        (tmp / "home").mkdir()
        self.state: dict[str, Any] = {"auth": True, "appear_after": 1, "looks": {}, "runs": [], "rate_limited": 0, "base": base, "log": "python (ubuntu-latest)\tpytest\t2026-10-26T08:00:00Z FAILED tests/test_flaky.py::test_it - assert 1 == 2\n"
                                      "python (ubuntu-latest)\tpytest\t2026-10-26T08:00:01Z 1 failed, 3000 passed\npython (ubuntu-latest)\tpytest\t2026-10-26T08:00:02Z uploading cache",
                                      "ci.yml": {"plan": ["success"]}, "release.yml": {"plan": ["success"]}, "release": {"made": False, "draft": False, "assets": ASSETS}}
        self.save_state()
        make_executable(self.bin / "gh", FAKE_GH.format(python=sys.executable, state=self.state_file, log=self.log))
        subprocess.run(["git", "init", "-q", "--bare", "-b", "master", str(self.remote)], check=True, env=self.env)
        hook = f'#!/usr/bin/env bash\nwhile read old new ref; do\n  echo "push $ref" >> "{self.log}"\n  case "$ref" in\n    refs/tags/*) [ -e "{tmp}/reject-tags" ] && {{ echo "tag refused" >&2; exit 1; }} ;;\n    *) [ -e "{tmp}/reject-heads" ] && {{ echo "push refused" >&2; exit 1; }} ;;\n  esac\ndone\nexit 0\n'
        make_executable(self.remote / "hooks" / "pre-receive", hook)
        subprocess.run(["git", "clone", "-q", str(self.remote), str(self.work)], check=True, env=self.env, capture_output=True)
        self.git("symbolic-ref", "HEAD", "refs/heads/master")
        (self.work / "scripts").mkdir(exist_ok=True)
        shutil.copy(ROOT / "scripts" / "release", self.work / "scripts" / "release")
        for module in ("updateasset.py", "versions.py"):               # (the script names the wheel as the package does)
            (self.work / "neoaprs").mkdir(exist_ok=True)
            shutil.copy(ROOT / "neoaprs" / module, self.work / "neoaprs" / module)
        make_executable(self.work / "scripts" / "check", SCRIPT.format(name="check", log=self.log, body=f'[ -e "{tmp}/check-fails" ] && {{ echo "check: pytest failed"; exit 1; }}\nexit 0'))
        make_executable(self.work / "scripts" / "build-page", SCRIPT.format(name="build-page", log=self.log, body=f'[ -e "{tmp}/page-differs" ] && echo "built differently" > neoaprs/page/index.html\nexit 0'))
        make_executable(self.work / "server" / "deploy.sh", SCRIPT.format(name="deploy", log=self.log, body=f'[ -e "{tmp}/deploy-fails" ] && exit 1\nexit 0'))
        (self.work / "neoaprs" / "page").mkdir(parents=True)
        (self.work / "neoaprs" / "__init__.py").write_text('"""A made-up NeoAPRS."""\n\nVERSION = "0.9.0"\nTOCALL = "APZNEO"\n', encoding="utf-8")
        (self.work / "neoaprs" / "page" / "index.html").write_text("page", encoding="utf-8")
        (self.work / "ui").mkdir()
        (self.work / "ui" / "main.ts").write_text("1", encoding="utf-8")
        (self.work / "CHANGELOG.md").write_text("# Changelog\n\n## Unreleased\n\n## 0.9.0\n\nThe first.\n", encoding="utf-8")
        self.commit("0.9.0: the changelog section and the version")
        self.git("tag", "v0.9.0")
        self.git("push", "-q", "origin", "master", "v0.9.0")
        self.write("CHANGELOG.md", "# Changelog\n\n## Unreleased\n\nA new thing the release brings.\n\n## 0.9.0\n\nThe first.\n")
        self.commit("A new thing")
        self.git("push", "-q", "origin", "master")
        self.log.write_text("", encoding="utf-8")

    # ---- the made-up world
    def git(self, *args: str, cwd: Path | None = None, check: bool = True) -> str:
        done = subprocess.run(["git", *args], cwd=cwd or self.work, env=self.env, capture_output=True, text=True)
        if check and done.returncode != 0:
            raise AssertionError(f"git {' '.join(args)}: {done.stderr}")
        return done.stdout.strip()

    def write(self, name: str, text: str) -> None:
        (self.work / name).parent.mkdir(parents=True, exist_ok=True)
        (self.work / name).write_text(text, encoding="utf-8")

    def commit(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def publish(self, message: str) -> None:
        """A commit that is on origin before the release starts (the log of calls starts empty again)."""
        self.commit(message)
        self.git("push", "-q", "origin", "master")
        self.log.write_text("", encoding="utf-8")

    def save_state(self) -> None:
        self.state_file.write_text(json.dumps(self.state), encoding="utf-8")

    def load_state(self) -> dict[str, Any]:
        return json.loads(self.state_file.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    def flag(self, name: str, on: bool = True) -> None:
        (self.tmp / name).touch() if on else (self.tmp / name).unlink(missing_ok=True)

    def another_clone_pushes(self) -> None:
        other = self.tmp / "other"
        subprocess.run(["git", "clone", "-q", str(self.remote), str(other)], check=True, env=self.env, capture_output=True)
        (other / "elsewhere.txt").write_text("a commit from another computer", encoding="utf-8")
        self.git("add", "-A", cwd=other)
        self.git("commit", "-q", "-m", "elsewhere", cwd=other)
        self.git("push", "-q", "origin", "master", cwd=other)
        self.log.write_text(self.log.read_text(encoding="utf-8").replace("push refs/heads/master\n", ""), encoding="utf-8")

    # ---- running and reading
    def release(self, *args: str, version: str = VERSION) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(self.work / "scripts" / "release"), version, "--interval", "0", *args], cwd=self.work, env=self.env, capture_output=True, text=True, timeout=120)

    def calls(self) -> list[str]:
        return [line for line in self.log.read_text(encoding="utf-8").splitlines() if line]

    def kinds(self) -> list[str]:
        """The calls of the run by what they were, in the order they came: check, push of a ref, gh run list/watch/rerun of a workflow, release view, deploy."""
        out = []
        for line in self.calls():
            if line.startswith("gh run list"):
                out.append("list " + line.split("--workflow ")[1].split()[0])
            elif line.startswith("gh run watch"):
                run = next(r for r in self.load_state()["runs"] if str(r["databaseId"]) == line.split()[3])
                out.append(f"watch {run['workflow']}")
            elif line.startswith("gh run rerun"):
                out.append("rerun")
            elif line.startswith("gh release view"):
                out.append("release view")
            elif not line.startswith("gh "):
                out.append(line.replace("push refs/heads/", "push ").replace("push refs/tags/", "push tag "))
        return out

    def changed(self) -> dict[str, str]:
        return {"head": self.git("rev-parse", "HEAD"), "origin": self.git("rev-parse", "master", cwd=self.remote), "tags": self.git("tag", "--list"), "status": self.git("status", "--porcelain"), "calls": "\n".join(self.calls())}

    def commit_of_release(self) -> str:
        return self.git("log", "-1", "--format=%H", "-S" + f'VERSION = "{VERSION}"', "--", "neoaprs/__init__.py")


@pytest.fixture
def downloads() -> Iterator[str]:
    Downloads.missing = set()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Downloads)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def rig(tmp_path: Path, downloads: str) -> Rig:
    return Rig(tmp_path, downloads)


FULL_RUN = ["check", "push master", "list ci.yml", "list ci.yml", "watch ci.yml", f"push tag {TAG}", "release view", "list release.yml", "list release.yml", "watch release.yml", "release view"]


def assert_released(rig: Rig) -> None:
    """The made-up repository after a release: one commit that sets the version and the changelog section, on origin; the tag on that commit, on origin; a fresh empty Unreleased."""
    commit = rig.commit_of_release()
    assert rig.git("log", "-1", "--format=%s", commit) == f"{VERSION}: the changelog section and the version"
    assert rig.git("diff", "--name-only", f"{commit}~1", commit).splitlines() == ["CHANGELOG.md", "neoaprs/__init__.py"]
    assert rig.git("rev-parse", f"{TAG}^{{commit}}") == commit == rig.git("rev-parse", f"{TAG}^{{commit}}", cwd=rig.remote) and rig.git("rev-parse", "master", cwd=rig.remote) == rig.git("rev-parse", "HEAD")
    assert 'VERSION = "0.9.1"' in (rig.work / "neoaprs" / "__init__.py").read_text(encoding="utf-8")
    assert (rig.work / "CHANGELOG.md").read_text(encoding="utf-8") == "# Changelog\n\n## Unreleased\n\n## 0.9.1\n\nA new thing the release brings.\n\n## 0.9.0\n\nThe first.\n"
    assert rig.git("status", "--porcelain") == "" and rig.git("tag", "--list", "v0.9.*").split() == ["v0.9.0", TAG]


# ---- the steps, in order ----

def test_a_release_goes_through_the_steps_in_order_and_leaves_one_commit_and_one_tag(rig: Rig) -> None:
    done = rig.release()
    assert done.returncode == 0, done.stdout + done.stderr
    assert rig.kinds() == FULL_RUN
    assert_released(rig)
    steps = re.findall(r"^\[(\d+)/12\] (\w+):", done.stdout, flags=re.M)
    assert [name for _, name in steps] == ["checks", "version", "changelog", "page", "check", "commit", "push", "ci", "tag", "release", "verify", "deploy"]
    assert "ui/ has not changed since v0.9.0" in done.stdout and "release 0.9.1 is done" in done.stdout and "the notes begin: A new thing the release brings." in done.stdout
    assert "server/deploy.sh" in done.stdout and "deploy" not in rig.kinds()


def test_the_page_is_built_only_when_ui_changed_since_the_last_tag_and_must_be_what_the_source_builds(rig: Rig) -> None:
    rig.write("ui/main.ts", "2")
    rig.publish("The page changed")
    done = rig.release()
    assert done.returncode == 0, done.stdout + done.stderr
    assert rig.kinds()[:2] == ["build-page", "check"] and "the committed page is what ui/ builds" in done.stdout
    assert rig.git("diff", "--name-only", f"{rig.commit_of_release()}~1", rig.commit_of_release()).splitlines() == ["CHANGELOG.md", "neoaprs/__init__.py"], "the release commit holds no page"


def test_a_committed_page_that_is_not_what_ui_builds_stops_the_release_and_leaves_the_tree_as_it_was(rig: Rig) -> None:
    rig.write("ui/main.ts", "2")
    rig.publish("The page changed, the build not committed")
    rig.flag("page-differs")
    before = rig.changed()
    done = rig.release()
    assert done.returncode == 1 and "the committed page is not what ui/ builds" in done.stdout and "scripts/build-page" in done.stdout
    after = rig.changed()
    assert after["origin"] == before["origin"] and after["head"] == before["head"] and after["tags"] == before["tags"]
    assert "neoaprs/page" not in after["status"] and (rig.work / "neoaprs" / "page" / "index.html").read_text(encoding="utf-8") == "page"
    assert "check" not in rig.kinds() and not [c for c in rig.calls() if c.startswith("gh run")]
    rig.flag("page-differs", False)
    assert rig.release().returncode == 0, "and with the page committed, the same command goes on from the version it wrote"
    assert_released(rig)


def test_a_dry_run_prints_the_steps_and_changes_nothing(rig: Rig) -> None:
    before = rig.changed()
    done = rig.release("--dry-run")
    assert done.returncode == 0, done.stdout + done.stderr
    assert rig.changed() == before and rig.calls() == [], "no commit, no push, no gh, no check"
    for word in ("would write VERSION", "would rename", "would run scripts/check", "would commit", "would push master", "would wait for the ci.yml run", "would tag v0.9.1", "would wait for the release.yml run", "would check that v0.9.1 is published", "dry run: nothing was changed"):
        assert word in done.stdout, word
    assert (rig.work / "CHANGELOG.md").read_text(encoding="utf-8").count("## 0.9.1") == 0


def test_a_dry_run_says_what_a_finished_release_has_done_already(rig: Rig) -> None:
    assert rig.release().returncode == 0
    done = rig.release("--dry-run")
    assert done.returncode == 0, done.stdout
    assert "skipped: VERSION is written already" in done.stdout and "skipped" in done.stdout.split("[7/12]")[1] and "is on origin/master" in done.stdout and f"{TAG} is on" in done.stdout


def test_deploy_runs_the_deploy_script_at_the_end_only_when_asked(rig: Rig) -> None:
    done = rig.release("--deploy")
    assert done.returncode == 0, done.stdout + done.stderr
    assert rig.kinds() == [*FULL_RUN, "deploy"] and "curl 'https://oh2gba.eu/neoaprs/version.php" in done.stdout


def test_a_deploy_that_fails_is_told_and_the_release_stays_done(rig: Rig) -> None:
    rig.flag("deploy-fails")
    done = rig.release("--deploy")
    assert done.returncode == 1 and "server/deploy.sh failed" in done.stdout
    assert_released(rig)
    rig.flag("deploy-fails", False)
    again = rig.release("--deploy")
    assert again.returncode == 0 and rig.kinds().count("check") == 1 and rig.kinds().count("deploy") == 2


# ---- what it refuses, before it changes anything ----

def refusal(rig: Rig, why: str, *args: str, version: str = VERSION) -> None:
    before = rig.changed()
    done = rig.release(*args, version=version)
    assert done.returncode == 1 and "stopped:" in done.stdout and why in done.stdout, done.stdout + done.stderr
    after = rig.changed()
    assert after["head"] == before["head"] and after["origin"] == before["origin"] and after["tags"] == before["tags"], "a refusal changes no commit, no branch of origin and no tag"
    assert (rig.work / "CHANGELOG.md").read_text(encoding="utf-8").count("## 0.9.1") == 0 and 'VERSION = "0.9.0"' in (rig.work / "neoaprs" / "__init__.py").read_text(encoding="utf-8")
    assert not any(k in rig.kinds() for k in ("check", "push master", "build-page"))


def test_it_refuses_to_release_from_a_branch_other_than_master(rig: Rig) -> None:
    rig.git("switch", "-q", "-c", "feature")
    refusal(rig, "not on master (on feature)")


def test_it_refuses_a_tree_that_is_not_clean(rig: Rig) -> None:
    rig.write("neoaprs/__init__.py", '"""A made-up NeoAPRS."""\n\nVERSION = "0.9.0"\nTOCALL = "APZXXX"\n')
    refusal(rig, "the tree is not clean: neoaprs/__init__.py")


def test_it_refuses_a_file_that_would_belong_in_the_build_but_lets_a_stray_one_be(rig: Rig) -> None:
    rig.write("ui/new.ts", "1")
    refusal(rig, "the tree is not clean: ui/new.ts")
    (rig.work / "ui" / "new.ts").unlink()
    rig.write(".mcp.json", "{}")
    done = rig.release()
    assert done.returncode == 0, done.stdout + done.stderr
    assert ".mcp.json" not in rig.git("show", "--stat", rig.commit_of_release())


def test_it_refuses_when_origin_has_commits_the_tree_has_not(rig: Rig) -> None:
    rig.another_clone_pushes()
    refusal(rig, "behind origin/master: git pull")


def test_it_refuses_commits_not_pushed_that_are_not_the_release_commit(rig: Rig) -> None:
    rig.write("README.md", "x")
    rig.commit("Not pushed")
    refusal(rig, "commit(s) that origin/master has not")


def test_it_refuses_a_changelog_without_notes_under_unreleased(rig: Rig) -> None:
    rig.write("CHANGELOG.md", "# Changelog\n\n## Unreleased\n\n## 0.9.0\n\nThe first.\n")
    rig.publish("The notes are gone")
    refusal(rig, "`## Unreleased` of CHANGELOG.md has no notes")


@pytest.mark.parametrize(("version", "why"), [("0.9.0", "tag v0.9.0 exists"), ("0.8.9", "is not greater than 0.9.0"), ("1.0", "is not a version"), ("v0.9.1", "is not a version")])
def test_it_refuses_a_version_that_is_not_new_and_greater(rig: Rig, version: str, why: str) -> None:
    if version == "0.9.0":
        rig.git("tag", "-d", "v0.9.0")
        rig.git("tag", "v0.9.0", "HEAD")                              # (the tag of a version names another commit than the one that wrote it: a tag is never moved)
        rig.git("push", "-q", "-f", "origin", "v0.9.0")
    done = rig.release(version=version)
    assert done.returncode == 1 and "stopped:" in done.stdout and (why in done.stdout or version == "0.9.0" and "tag v0.9.0 exists" in done.stdout), done.stdout
    assert "check" not in rig.kinds() and rig.git("status", "--porcelain") == ""


def test_it_refuses_a_tag_that_names_another_commit_and_never_moves_it(rig: Rig) -> None:
    other = rig.git("rev-parse", "HEAD")
    rig.git("tag", TAG, other)
    refusal(rig, f"the tag {TAG} exists here at")


def test_it_refuses_when_gh_is_not_logged_in(rig: Rig) -> None:
    rig.state["auth"] = False
    rig.save_state()
    refusal(rig, "gh is not logged in")


def test_a_dry_run_names_what_a_real_run_would_refuse_and_goes_on_with_the_steps(rig: Rig) -> None:
    rig.git("switch", "-q", "-c", "feature")
    rig.write("README.md", "dirty")
    done = rig.release("--dry-run")
    assert done.returncode == 1 and "WOULD REFUSE: not on master (on feature)" in done.stdout and "[12/12] deploy" in done.stdout and "the dry run found" in done.stdout


# ---- run again after a failure at each step ----

def test_scripts_check_that_fails_leaves_the_version_written_and_nothing_committed_and_the_same_command_goes_on(rig: Rig) -> None:
    rig.flag("check-fails")
    first = rig.release()
    assert first.returncode == 1 and "scripts/check failed: nothing is committed" in first.stdout
    assert rig.git("diff", "--name-only").splitlines() == ["CHANGELOG.md", "neoaprs/__init__.py"] and rig.git("log", "-1", "--format=%s") == "A new thing"
    assert rig.kinds() == ["check"]
    rig.flag("check-fails", False)
    again = rig.release()
    assert again.returncode == 0, again.stdout + again.stderr
    assert "skipped: VERSION is written already" in again.stdout and "skipped: the section 0.9.1 is written already" in again.stdout
    assert rig.kinds() == ["check", *FULL_RUN]
    assert_released(rig)


def test_a_tree_changed_by_hand_after_a_stop_is_still_refused(rig: Rig) -> None:
    rig.flag("check-fails")
    rig.release()
    rig.write("ui/main.ts", "changed by hand")
    done = rig.release()
    assert done.returncode == 1 and "the tree is not clean: ui/main.ts" in done.stdout


def test_a_push_that_fails_leaves_the_commit_and_the_command_pushes_it_without_a_second_commit(rig: Rig) -> None:
    rig.flag("reject-heads")
    first = rig.release()
    assert first.returncode == 1 and "push refused" in first.stdout + first.stderr
    commit = rig.commit_of_release()
    assert rig.git("rev-parse", "HEAD") == commit and rig.git("rev-parse", "master", cwd=rig.remote) != commit and rig.git("tag", "--list", TAG) == ""
    rig.flag("reject-heads", False)
    assert rig.release().returncode == 0
    assert rig.commit_of_release() == commit and rig.git("rev-list", "--count", f"v0.9.0..{TAG}") == "2"
    assert rig.kinds().count("check") == 1
    assert_released(rig)


def test_a_failed_ci_run_is_shown_with_its_failed_jobs_and_tests_and_no_tag_is_made(rig: Rig) -> None:
    rig.state["ci.yml"]["plan"] = ["failure", "success"]
    rig.save_state()
    first = rig.release()
    assert first.returncode == 1
    for text in ("FAILED: run 100", "job python (ubuntu-latest): failure (step: pytest)", "FAILED tests/test_flaky.py::test_it - assert 1 == 2", "1 failed, 3000 passed", "--rerun"):
        assert text in first.stdout, text
    assert "uploading cache" not in first.stdout and "job page" not in first.stdout, "only the failed jobs and the lines of the failed tests"
    assert rig.git("tag", "--list", TAG) == "" and "rerun" not in rig.kinds() and rig.kinds()[-1] == "watch ci.yml"
    again = rig.release()
    assert again.returncode == 1 and "rerun" not in rig.kinds() and rig.git("tag", "--list", TAG) == "", "without --rerun a failed run stays failed"


def test_rerun_runs_the_failed_jobs_of_ci_once_and_the_release_goes_on(rig: Rig) -> None:
    rig.state["ci.yml"]["plan"] = ["failure", "success"]
    rig.save_state()
    assert rig.release().returncode == 1
    done = rig.release("--rerun")
    assert done.returncode == 0, done.stdout + done.stderr
    assert rig.kinds().count("rerun") == 1 and rig.kinds().count("check") == 1
    assert_released(rig)


def test_rerun_runs_the_failed_jobs_only_once_per_run(rig: Rig) -> None:
    rig.state["ci.yml"]["plan"] = ["failure"]
    rig.save_state()
    done = rig.release("--rerun")
    assert done.returncode == 1 and "has been run again already" in done.stdout and rig.kinds().count("rerun") == 1
    assert rig.git("tag", "--list", TAG) == ""
    assert rig.release("--rerun").returncode == 1 and rig.kinds().count("rerun") == 1, "a run that was run again does not get a third go from the script"


def test_a_tag_push_that_fails_keeps_the_local_tag_and_the_command_pushes_it(rig: Rig) -> None:
    rig.flag("reject-tags")
    first = rig.release()
    assert first.returncode == 1 and "tag refused" in first.stdout + first.stderr
    commit = rig.commit_of_release()
    assert rig.git("rev-parse", f"{TAG}^{{commit}}") == commit and rig.git("tag", "--list", TAG, cwd=rig.remote) == ""
    rig.flag("reject-tags", False)
    assert rig.release().returncode == 0
    assert rig.kinds().count("check") == 1 and rig.kinds().count("push master") == 1
    assert_released(rig)


def test_a_failed_release_run_is_shown_and_run_again_with_rerun_and_the_tag_is_never_made_again(rig: Rig) -> None:
    rig.state["release.yml"]["plan"] = ["failure", "success"]
    rig.save_state()
    first = rig.release()
    assert first.returncode == 1 and "FAILED: run 101" in first.stdout and "release.yml run 101 failed" in first.stdout and "the next version (a tag is never moved)" in first.stdout
    tagged = rig.git("rev-parse", TAG, cwd=rig.remote)
    done = rig.release("--rerun")
    assert done.returncode == 0, done.stdout + done.stderr
    assert rig.git("rev-parse", TAG, cwd=rig.remote) == tagged
    assert rig.kinds().count(f"push tag {TAG}") == 1 and rig.kinds().count("rerun") == 1 and rig.kinds().count("check") == 1 and rig.kinds().count("watch ci.yml") == 1
    assert_released(rig)


def test_a_release_that_is_a_draft_or_short_of_files_or_has_a_dead_link_stops_the_run_and_nothing_before_is_done_again(rig: Rig, downloads: str) -> None:
    rig.state["release"]["draft"] = True
    rig.save_state()
    assert "still a draft" in rig.release().stdout
    rig.state = rig.load_state()
    rig.state["release"].update(draft=False, assets=[a for a in ASSETS if a != "SHA256SUMS"])
    rig.save_state()
    short = rig.release()
    assert short.returncode == 1 and "missing ['SHA256SUMS']" in short.stdout
    rig.state = rig.load_state()
    rig.state["release"]["assets"] = [a for a in ASSETS if a != "NeoAPRS-Setup.exe"]
    rig.save_state()
    unnamed = rig.release()
    assert unnamed.returncode == 1 and "missing ['NeoAPRS-Setup.exe']" in unnamed.stdout
    rig.state = rig.load_state()
    rig.state["release"]["assets"] = ASSETS
    rig.save_state()
    Downloads.missing = {f"NeoAPRS-Setup-{VERSION}.exe"}
    dead = rig.release()
    assert dead.returncode == 1 and f"the download link of NeoAPRS-Setup-{VERSION}.exe does not answer" in dead.stdout and "status 404" in dead.stdout
    Downloads.missing = set()
    done = rig.release()
    assert done.returncode == 0, done.stdout
    assert rig.kinds().count("check") == 1 and rig.kinds().count("push master") == 1 and rig.kinds().count(f"push tag {TAG}") == 1 and rig.kinds().count("watch ci.yml") == 1 and rig.kinds().count("watch release.yml") == 1
    assert_released(rig)


def test_a_release_run_that_ends_without_success_stops_the_script(rig: Rig) -> None:
    rig.state["release.yml"]["plan"] = ["cancelled"]
    rig.save_state()
    stopped = rig.release()
    assert stopped.returncode == 1 and "release.yml run 101 failed" in stopped.stdout and "--rerun" in stopped.stdout
    assert rig.git("tag", "--list", TAG, cwd=rig.remote) == TAG, "the tag stays: the run is run again, the tag is not made again"


def test_a_finished_release_run_again_does_nothing_and_says_what_it_skipped(rig: Rig) -> None:
    assert rig.release().returncode == 0
    marker = len(rig.calls())
    again = rig.release()
    assert again.returncode == 0, again.stdout + again.stderr
    new = rig.calls()[marker:]
    assert not any(c in ("check", "push refs/heads/master") or c.startswith(("push ", "gh run watch", "gh run rerun")) for c in new), new
    assert "skipped" in again.stdout and "release 0.9.1 is done" in again.stdout
    assert_released(rig)


def test_gh_that_hits_the_rate_limit_is_asked_again_after_a_wait(rig: Rig) -> None:
    rig.state["rate_limited"] = 2
    rig.save_state()
    done = rig.release()
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.count("GitHub's rate limit; waiting") == 2
    assert_released(rig)


def test_gh_that_stays_rate_limited_is_given_up_with_a_hint(rig: Rig) -> None:
    rig.state["rate_limited"] = 100
    rig.save_state()
    done = rig.release()
    assert done.returncode == 1 and "gh auth status" in done.stdout and done.stdout.count("GitHub's rate limit; waiting") == 5
    assert rig.git("tag", "--list", TAG) == ""


def test_the_script_answers_help_and_names_its_flags() -> None:
    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "release"), "--help"], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0
    for flag in ("--dry-run", "--rerun", "--deploy", "--interval"):
        assert flag in done.stdout
