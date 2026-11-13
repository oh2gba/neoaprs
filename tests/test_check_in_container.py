"""The container the size of GitHub's runner (scripts/check-in-container and packaging/ci/Dockerfile) as far as it can be held without docker: the threads a run takes, from made-up lists of siblings; the
files that go in, from a made-up repository; the tar and what unpacks it, run here with bash, tar and git as they run inside; the command line for docker; the script from end to end against a stand-in
for docker that writes down what it was asked; and that the Dockerfile and the default commands are the CI's Linux job's. The image itself and a run in it are tried by hand (docs/development.md)."""
import contextlib
import importlib.machinery
import importlib.util
import io
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType

import pytest
from tests.support.ptyline import SIGKILL, is_root, posix_only

pytestmark = posix_only      # (a script of the repository that locks a file and runs docker: a development check, not the product)

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check-in-container"
DOCKERFILE = (ROOT / "packaging" / "ci" / "Dockerfile").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
PATIENCE_SEC = 60.0          # for a wait that includes the start of a program
linux_only = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the script reads the cores from /sys, which is Linux's")
MADE_UP = "made-up-for-this-test"      # what every file that must stay on the machine holds here: the packed tree is searched for it


@pytest.fixture(scope="module", autouse=True)
def scratch_outside_the_repository() -> None:
    """Every scratch folder of this file is in the temporary folder, the system's or, where that one cannot be written, the one TMPDIR names. With neither, Python's last resort is the current
    folder, which is the repository: then nothing here is run."""
    scratch = Path(tempfile.gettempdir()).resolve()
    if scratch == ROOT or ROOT in scratch.parents:
        pytest.fail(f"the temporary folder is {scratch}, inside the repository (the system's cannot be written): set TMPDIR to a folder outside it", pytrace=False)


@pytest.fixture(scope="module")
def script() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("check_in_container", str(SCRIPT))
    spec = importlib.util.spec_from_loader("check_in_container", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


# ---- the threads ----

TWO_THREAD_CORES = [(0, 16), (1, 17), (2, 18), (3, 19)]
SINGLE_THREAD_CORES = [(0,), (1,), (2,), (3,), (4,), (5,)]


def test_a_runner_is_two_cores_with_their_siblings_and_a_starved_one_is_one_core(script: ModuleType) -> None:
    assert script.RUNNER.threads == 4 and script.STARVED.threads == 2
    assert script.choose_cpus(TWO_THREAD_CORES, script.RUNNER.threads) == [0, 16, 1, 17]
    assert script.choose_cpus(TWO_THREAD_CORES, script.STARVED.threads) == [0, 16]


def test_on_a_machine_without_siblings_the_threads_are_as_many_cores(script: ModuleType) -> None:
    assert script.choose_cpus(SINGLE_THREAD_CORES, 4) == [0, 1, 2, 3]
    assert script.choose_cpus(SINGLE_THREAD_CORES, 2) == [0, 1]


def test_a_machine_with_fewer_cores_than_asked_gives_all_it_has(script: ModuleType) -> None:
    assert script.choose_cpus([(0, 1)], 4) == [0, 1]
    assert script.choose_cpus([(0,), (1,), (2,)], 4) == [0, 1, 2]
    assert script.choose_cpus([], 4) == []


def test_cores_of_different_sizes_fill_up_to_the_number_and_not_beyond(script: ModuleType) -> None:
    assert script.choose_cpus([(0, 1), (2,), (3,), (4,)], 4) == [0, 1, 2, 3]
    assert script.choose_cpus([(0,), (1, 2), (3, 4)], 4) == [0, 1, 2, 3], "the last core gives only the thread that is still missing"


def test_a_run_takes_the_cores_no_other_run_holds_and_the_least_held_when_all_are(script: ModuleType) -> None:
    assert script.choose_cpus(TWO_THREAD_CORES, 4, taken=[0, 16, 1, 17]) == [2, 18, 3, 19]
    assert script.choose_cpus(TWO_THREAD_CORES, 2, taken=[0, 16, 1, 17, 2, 18]) == [3, 19]
    assert script.choose_cpus(TWO_THREAD_CORES, 4, taken=[0, 16, 1, 17, 2, 18]) == [3, 19, 0, 16], "the free core, then the first of the held ones"
    assert script.choose_cpus(TWO_THREAD_CORES, 2, taken=[0, 16, 1, 17, 2, 18, 3, 19, 0, 16]) == [1, 17], "every core is held: one that is held once, not the one held twice"


def test_the_kernels_lists_of_threads_are_read(script: ModuleType) -> None:
    assert script.parse_cpu_list("0,16\n") == (0, 16)
    assert script.parse_cpu_list("0-3") == (0, 1, 2, 3)
    assert script.parse_cpu_list("0-1,8-9") == (0, 1, 8, 9)
    assert script.parse_cpu_list("5") == (5,)
    assert script.parse_cpu_list("\n") == ()


def test_the_cores_are_read_from_the_sibling_files_of_the_threads_that_are_on(script: ModuleType, tmp_path: Path) -> None:
    for thread, siblings in {0: "0,2", 1: "1,3", 2: "0,2", 3: "1,3", 10: "10"}.items():
        folder = tmp_path / f"cpu{thread}" / "topology"
        folder.mkdir(parents=True)
        (folder / "thread_siblings_list").write_text(siblings + "\n")
    (tmp_path / "cpu4").mkdir()                          # a thread that is switched off has no topology
    for other in ("cpufreq", "cpuidle"):                 # (folders of /sys/devices/system/cpu that are no threads)
        (tmp_path / other / "topology").mkdir(parents=True)
        (tmp_path / other / "topology" / "thread_siblings_list").write_text("99\n")
    assert script.read_cores(tmp_path) == [(0, 2), (1, 3), (10,)]
    assert script.read_cores(tmp_path / "nothing-here") == []


# ---- the tree that goes in ----

def asked(folder: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """git in a repository of the test's own, named in the command. Nothing of the caller's environment can point it at another (a GIT_DIR of a hook the suite is run from, the user's configuration), and
    it looks for no repository above that folder: a made-up repository that failed to be made is an error, never the repository the suite is run in."""
    env = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    env |= {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_CEILING_DIRECTORIES": str(folder.parent)}
    return subprocess.run(["git", "-C", str(folder), *args], env=env, capture_output=True, text=True)


def git(folder: Path, *args: str) -> str:
    done = asked(folder, *args)
    assert done.returncode == 0, f"git {' '.join(args)} in {folder}: {done.stderr}"
    return done.stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A made-up repository: tracked files (a program, a link, a name with a space, one changed since it was added, one deleted from the disk and one that an ignore rule names), an untracked file,
    ignored ones, and a repository of its own inside it."""
    if shutil.which("git") is None:
        pytest.skip("needs git")
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / ".gitignore").write_text("*.log\n.venv/\n")
    (root / "src" / "kept.py").write_text("kept = 1\n")
    (root / "src" / "a name.txt").write_text("a name the shell would split\n")
    (root / "tool").write_text("#!/bin/sh\necho tool\n")
    (root / "tool").chmod(0o755)
    (root / "link").symlink_to("src/kept.py")
    (root / "gone.txt").write_text("deleted after it was added\n")
    (root / "kept.log").write_text("tracked, though the rule for logs names it\n")
    git(root, "init", "-q", "-b", "master")
    assert Path(git(root, "rev-parse", "--show-toplevel").strip()).resolve() == root.resolve()
    git(root, "add", ".")
    git(root, "add", "--force", "kept.log")
    (root / "gone.txt").unlink()
    (root / "src" / "kept.py").write_text("kept = 2\n")
    (root / "new.txt").write_text("not added yet\n")
    (root / "debug.log").write_text("ignored\n")
    (root / ".venv").mkdir()
    (root / ".venv" / "pyvenv.cfg").write_text("ignored\n")
    inner = root / "inner"
    inner.mkdir()
    git(inner, "init", "-q", "-b", "master")
    (inner / "file.txt").write_text("another repository\n")
    git(inner, "add", ".")
    git(inner, "-c", "user.name=test", "-c", "user.email=test@localhost", "commit", "-q", "-m", "its own history")
    return root


TRACKED = [".gitignore", "kept.log", "link", "src/a name.txt", "src/kept.py", "tool"]
PACKED = sorted([*TRACKED, "new.txt"])


def test_what_goes_in_is_the_tracked_and_the_untracked_files_on_disk_and_nothing_ignored(script: ModuleType, repo: Path) -> None:
    assert script.packed_files(repo) == PACKED, "no gone.txt (deleted), no debug.log and no .venv (ignored), no inner/ (a repository of its own)"
    assert script.tracked_files(repo) == TRACKED


def test_a_tracked_file_in_a_folder_that_is_a_link_now_is_gone_for_git_and_is_not_read_through_the_link(script: ModuleType, repo: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "kept.py").write_text(f"outside = {MADE_UP}\n")
    shutil.rmtree(repo / "src")
    (repo / "src").symlink_to(outside)
    packed_names = script.packed_files(repo)
    assert "src" in packed_names and not [name for name in packed_names if name.startswith("src/")]
    assert not [name for name in script.tracked_files(repo) if name.startswith("src/")]
    assert MADE_UP.encode() not in packed(script, repo)


def test_a_file_of_access_tokens_never_goes_in_whatever_git_says_of_it(script: ModuleType, repo: Path) -> None:
    assert ".secrets" not in (repo / ".gitignore").read_text(), "no ignore rule names the files below"
    tokens = (".secrets", ".secrets-deploy", ".secrets-committed", "src/.secrets.bak", ".secrets.d/github", "src/.secrets-old/deep/file.txt")
    for name in tokens:
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(f"MADE_UP_TOKEN={MADE_UP}\n")
    (repo / "secrets.md").write_text("a document about them is no such file\n")
    (repo / "tokens-link").symlink_to(".secrets")
    git(repo, "add", "--force", ".secrets-deploy", ".secrets-committed", "src/.secrets-old")
    git(repo, "-c", "user.name=test", "-c", "user.email=test@localhost", "commit", "-q", "-m", "tokens that were committed by mistake", "--", ".secrets-committed")
    listing = git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard").split("\0")
    assert set(tokens) <= set(listing), "git itself lists every one of them: tracked, committed, or untracked with no rule that names it"
    assert script.packed_files(repo) == sorted([*PACKED, "secrets.md", "tokens-link"]) and script.tracked_files(repo) == TRACKED
    tar = packed(script, repo)
    assert MADE_UP.encode() not in tar, "the text of no such file is anywhere in what goes in"
    with tarfile.open(fileobj=io.BytesIO(tar)) as archive:
        assert not [name for name in archive.getnames() if ".secrets" in name]
        assert b".secrets" not in content(archive, "tracked")
        assert archive.getmember("neoaprs/tokens-link").issym(), "a link to one goes in as a link, which points at nothing inside"


def test_what_an_ignore_rule_names_never_goes_in_a_private_key_among_it(script: ModuleType, repo: Path) -> None:
    (repo / ".gitignore").write_text("*.log\n.venv/\n/work/\n/.mcp.json\n")
    for name in ("work/vmtest/vmkey", "work/notes.txt", ".mcp.json", "src/trace.log"):
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(f"-----BEGIN MADE-UP PRIVATE KEY-----\n{MADE_UP}\n")
    (repo / "work" / "vmtest" / "vmkey").chmod(0o600)
    assert script.packed_files(repo) == PACKED and script.tracked_files(repo) == TRACKED
    tar = packed(script, repo)
    assert MADE_UP.encode() not in tar, "the text of no ignored file is anywhere in what goes in"
    with tarfile.open(fileobj=io.BytesIO(tar)) as archive:
        assert sorted(archive.getnames()) == sorted([*(f"neoaprs/{name}" for name in PACKED), "tracked"])


def test_the_list_is_this_trees_own_whatever_repository_the_environment_names(script: ModuleType, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    other = tmp_path / "other"
    other.mkdir()
    git(other, "init", "-q", "-b", "master")
    (other / "theirs.txt").write_text("a file of another repository\n")
    git(other, "add", ".")
    for name, value in {"GIT_DIR": other / ".git", "GIT_WORK_TREE": other, "GIT_INDEX_FILE": other / ".git" / "index"}.items():
        monkeypatch.setenv(name, str(value))
    assert script.packed_files(repo) == PACKED and script.tracked_files(repo) == TRACKED


def test_a_folder_that_is_no_repository_or_lies_inside_one_is_not_packed(script: ModuleType, repo: Path, tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "file.txt").write_text("unpacked from an archive\n")
    for folder in (plain, repo / "src"):
        out = io.BytesIO()
        with pytest.raises(script.NotPacked, match="is not the working tree of a git repository"):
            script.pack(folder, out)
        assert out.getvalue() == b"", folder


def test_a_file_that_cannot_be_read_is_named_and_one_that_went_away_is_left_out(script: ModuleType, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(script, "packed_files", lambda root: [*PACKED, "went-away.txt"])
    with tarfile.open(fileobj=io.BytesIO(packed(script, repo))) as archive:
        assert sorted(archive.getnames()) == sorted([*(f"neoaprs/{name}" for name in PACKED), "tracked"])
    monkeypatch.undo()
    if is_root():
        pytest.skip("root reads every file")
    (repo / "new.txt").chmod(0)
    with pytest.raises(script.NotPacked, match=r"^new\.txt could not be packed \(Permission denied\)$"):
        script.pack(repo, io.BytesIO())


@contextlib.contextmanager
def closed(folder: Path, mode: int = 0) -> Iterator[None]:
    """`folder` with these rights for a while, and open again after: pytest takes the test's folders away itself."""
    folder.chmod(mode)
    try:
        yield
    finally:
        folder.chmod(0o755)


def test_a_folder_that_cannot_be_entered_or_listed_is_said_and_never_passed_over(script: ModuleType, repo: Path) -> None:
    if is_root():
        pytest.skip("root enters every folder")
    with closed(repo / "src"):
        with pytest.raises(script.NotPacked, match=r"^src/a name\.txt could not be packed \(Permission denied\)$"):
            script.tracked_files(repo)                   # (the tracked files are in git's index: git lists them without a look at the folder)
        with pytest.raises(script.NotPacked, match=rf"^git could not list the files of {re.escape(str(repo))} \(.*src/.*\)$"):
            script.pack(repo, io.BytesIO())
    (repo / "kept-out").mkdir()
    (repo / "kept-out" / "file.txt").write_text("in a folder nobody may open\n")
    assert "kept-out/file.txt" in script.packed_files(repo)
    with closed(repo / "kept-out"), pytest.raises(script.NotPacked, match=r"^git could not list the files of .* \(.*kept-out/.*\)$"):
        script.pack(repo, io.BytesIO())                  # (git leaves the folder out with a warning and exit code 0: the tree would go in with files missing)


def packed(script: ModuleType, repo: Path) -> bytes:
    out = io.BytesIO()
    script.pack(repo, out)
    return out.getvalue()


def content(archive: tarfile.TarFile, name: str) -> bytes:
    file = archive.extractfile(name)
    assert file is not None, name
    return file.read()


def test_the_tar_holds_the_tree_as_it_is_on_disk_and_the_list_of_its_tracked_files(script: ModuleType, repo: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(packed(script, repo))) as archive:
        members = {member.name: member for member in archive.getmembers()}
        assert sorted(members) == sorted([*(f"neoaprs/{name}" for name in PACKED), "tracked"])
        assert content(archive, "neoaprs/src/kept.py") == b"kept = 2\n", "the text on disk, not the text that was added"
        assert content(archive, "tracked") == b"".join(name.encode() + b"\0" for name in TRACKED)
        assert members["neoaprs/tool"].mode & stat.S_IXUSR and not members["neoaprs/src/kept.py"].mode & stat.S_IXUSR
        assert members["neoaprs/link"].issym() and members["neoaprs/link"].linkname == "src/kept.py"
        assert {(member.uid, member.gid, member.uname, member.gname) for member in members.values()} == {(0, 0, "", "")}, "nobody's name or number from this machine goes in"


def inside(script: ModuleType, repo: Path, work: Path, *commands: str, **environment: str) -> subprocess.CompletedProcess[bytes]:
    """What the container runs, run here: the script's own shell text in an empty folder, the tar on its input and the commands as its arguments, with a home of its own (no configuration of the
    user's git) and no variable of the suite's environment but the PATH."""
    for tool in ("bash", "tar"):
        if shutil.which(tool) is None:
            pytest.skip(f"needs {tool}")
    home = work.parent / f"{work.name}-home"
    for folder in (work, home):
        folder.mkdir()
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "LC_ALL": "C.UTF-8", **environment}
    return subprocess.run(["bash", "-c", script.INSIDE, "check-in-container", *commands], cwd=work, env=env, input=packed(script, repo), capture_output=True, timeout=PATIENCE_SEC)


def test_inside_the_tree_is_a_repository_whose_tracked_files_are_the_ones_tracked_here(script: ModuleType, repo: Path, tmp_path: Path) -> None:
    done = inside(script, repo, tmp_path / "work")
    assert done.returncode == 0, done.stderr.decode()
    tree = tmp_path / "work" / "neoaprs"
    assert sorted(p.name for p in (tmp_path / "work").iterdir()) == ["neoaprs"], "the list of tracked files is gone once the repository is made"
    assert git(tree, "ls-files", "-z").split("\0")[:-1] == TRACKED
    assert git(tree, "status", "--porcelain") == "?? new.txt\n", "what was changed here and not added is no change inside: the commit is the disk"
    assert git(tree, "log", "--format=%s") == "The tree as it was on disk\n"
    assert (tree / "src" / "kept.py").read_text() == "kept = 2\n" and os.access(tree / "tool", os.X_OK) and (tree / "link").is_symlink()
    assert asked(tree, "check-ignore", "-q", ".venv/x").returncode == 0, "the environment a run makes in the tree is ignored there as here"


def test_inside_a_repository_named_by_the_environment_is_left_alone(script: ModuleType, repo: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    git(other, "init", "-q", "-b", "master")
    done = inside(script, repo, tmp_path / "work", "git rev-parse --show-toplevel > ../where", GIT_DIR=str(other / ".git"), GIT_WORK_TREE=str(other), GIT_INDEX_FILE=str(other / ".git" / "index"))
    assert done.returncode == 0, done.stderr.decode()
    tree = tmp_path / "work" / "neoaprs"
    assert git(tree, "ls-files", "-z").split("\0")[:-1] == TRACKED and git(tree, "log", "--format=%s") == "The tree as it was on disk\n"
    assert asked(other, "rev-parse", "--verify", "HEAD").returncode != 0 and git(other, "ls-files") == "", "no commit and no file was added to the repository the environment named"
    assert Path((tmp_path / "work" / "where").read_text().strip()).resolve() == tree.resolve(), "nor does a command of the run see it"


def test_inside_the_commands_run_in_the_tree_in_order_with_nothing_to_read_and_stop_at_the_first_failure(script: ModuleType, repo: Path, tmp_path: Path) -> None:
    done = inside(script, repo, tmp_path / "work", "pwd > ../where", "cat > ../input; echo first >> ../order", "echo second >> ../order; exit 7", "echo third >> ../order")
    assert done.returncode == 7
    work = tmp_path / "work"
    assert Path((work / "where").read_text().strip()).resolve() == (work / "neoaprs").resolve()
    assert (work / "input").read_bytes() == b"" and (work / "order").read_text() == "first\nsecond\n"
    lines = [line for line in done.stderr.decode().splitlines() if line.startswith("check-in-container: ")]
    assert lines[0] == "check-in-container: pwd > ../where" and re.fullmatch(r"check-in-container: exit 0 after \d+ s: pwd > \.\./where", lines[1])
    assert re.fullmatch(r"check-in-container: exit 7 after \d+ s: echo second >> \.\./order; exit 7", lines[-1])


# ---- the command line for docker ----

def options(line: list[str], name: str) -> list[str]:
    return [line[i + 1] for i, word in enumerate(line) if word == name]


def test_the_command_line_of_a_run_is_a_runner_four_threads_as_a_cpu_set_16_gb_and_no_swap(script: ModuleType) -> None:
    line = script.docker_run("neoaprs-ci:abc", script.RUNNER, [0, 16, 1, 17], ["uv lock --check", "uv run pytest -n auto"], Path("/scratch/container-id"))
    assert line[:2] == ["docker", "run"]
    before, after = line[: line.index("neoaprs-ci:abc")], line[line.index("neoaprs-ci:abc") + 1:]
    assert options(before, "--cpuset-cpus") == ["0,16,1,17"] and "--cpus" not in before, "a CPU set: a quota would leave pytest counting every thread of the machine"
    assert options(before, "--memory") == ["16g"] and options(before, "--memory-swap") == ["16g"], "the same number: no swap beyond the memory"
    assert "--init" in before and "--rm" in before and "--interactive" in before and options(before, "--shm-size") == ["1g"]
    assert options(before, "--pull") == ["never"], "an image that is not here is an error, never a question to a registry"
    assert options(before, "--cidfile") == ["/scratch/container-id"] and options(before, "--label") == ["eu.oh2gba.neoaprs.check-cpus=0,16,1,17"]
    assert after == ["bash", "-c", script.INSIDE, "check-in-container", "uv lock --check", "uv run pytest -n auto"]


def test_a_starved_run_is_two_threads_and_7_gb(script: ModuleType) -> None:
    line = script.docker_run("neoaprs-ci:abc", script.STARVED, [0, 16], ["true"], Path("/scratch/container-id"))
    assert options(line, "--cpuset-cpus") == ["0,16"] and options(line, "--memory") == ["7g"] and options(line, "--memory-swap") == ["7g"]


def test_the_environment_inside_has_the_switches_and_no_display(script: ModuleType) -> None:
    line = script.docker_run("neoaprs-ci:abc", script.RUNNER, [0, 1, 2, 3], ["true"], Path("/scratch/container-id"))
    environment = dict(value.split("=", 1) for value in options(line, "--env"))
    assert environment == {"NEOAPRS_UPDATE_CHECK": "0", "UV_FROZEN": "1", "NEOAPRS_NO_DEVICES": "1", "UV_LINK_MODE": "copy"}
    workflow = dict(re.findall(r'^  (\w+): "([^"]*)"', WORKFLOW.split("\nenv:\n", 1)[1].split("\n\n", 1)[0], re.M))
    assert workflow and workflow.items() <= environment.items(), "what the workflow sets for every job is set inside"
    assert all("=" in value for value in options(line, "--env")), "a name without a value would take this machine's variable in, a token among them"
    assert not any(word in ("--tty", "-t", "-it", "--env-file") for word in line), "no terminal, and nothing of this machine's environment"


def test_nothing_in_the_command_line_can_meet_another_run_and_the_working_tree_is_not_mounted(script: ModuleType) -> None:
    line = script.docker_run("neoaprs-ci:abc", script.RUNNER, [0, 1, 2, 3], ["true"], Path("/scratch/container-id"))
    before = line[: line.index("neoaprs-ci:abc")]
    for option in ("--name", "--publish", "-p", "--publish-all", "-P", "--network", "--hostname", "--mount", "--privileged"):
        assert option not in before, option
    volumes = dict(value.split(":", 1) for value in options(before, "--volume"))
    assert volumes == {"neoaprs-ci-uv": "/home/runner/.cache/uv", "neoaprs-ci-npm": "/home/runner/.npm"}
    assert not any("/" in name for name in volumes), "named volumes only: no folder of this machine is mounted"
    assert options(before, "--workdir") == ["/home/runner/work"]


def test_the_image_is_named_by_its_dockerfile_and_built_with_no_context(script: ModuleType, tmp_path: Path) -> None:
    one, other = tmp_path / "one", tmp_path / "other"
    one.write_text("FROM ubuntu:24.04\n")
    other.write_text("FROM ubuntu:24.04\nRUN true\n")
    assert re.fullmatch(r"neoaprs-ci:[0-9a-f]{12}", script.image_tag(one))
    assert script.image_tag(one) != script.image_tag(other) and script.image_tag(one) == script.image_tag(one)
    assert script.docker_build("neoaprs-ci:abc") == ["docker", "build", "--tag", "neoaprs-ci:abc", "-"], "the Dockerfile on the input and no folder: no file of the project can be copied in"


# ---- the Dockerfile and the default commands are the CI's Linux job's ----

def python_job() -> str:
    found = re.search(r"^  python:\n(.*?)(?=^  [\w-]+:\n|\Z)", WORKFLOW, re.S | re.M)
    assert found is not None
    return found.group(1)


def test_the_default_commands_are_the_commands_of_the_ci_job_on_linux_in_its_order(script: ModuleType) -> None:
    install = re.findall(r"^      - run: (uv sync .+)$", python_job(), re.M)
    commands = [*install, *re.findall(r"^      - run: (.+)\n        if: runner\.os == 'Linux'$", python_job(), re.M)]
    assert len(commands) >= 5 and commands[0].startswith("uv sync ") and all(command.startswith("scripts/check --stage ") for command in commands[1:])
    assert list(script.CI_COMMANDS) == commands, "the job `python` of .github/workflows/ci.yml has changed: CI_COMMANDS of scripts/check-in-container follows it"


def test_the_image_has_the_libraries_the_ci_job_installs_word_for_word() -> None:
    found = re.search(r"apt-get install -y --no-install-recommends (.+)", python_job())
    assert found is not None and len(found.group(1).split()) >= 5
    assert f"      {found.group(1).strip()} \\\n" in DOCKERFILE, "the list of libraries of the job `python` of ci.yml is a line of packaging/ci/Dockerfile"


def test_the_image_is_ubuntu_with_the_tools_a_runner_has_and_the_user_runner() -> None:
    assert re.search(r"^FROM ubuntu:24\.04$", DOCKERFILE, re.M)
    installed = re.search(r"apt-get install -y --no-install-recommends \\\n(.*?)\n && ", DOCKERFILE, re.S)
    assert installed is not None
    for tool in ("ca-certificates", "curl", "git", "php-cli", "build-essential"):
        assert tool in installed.group(1).split(), tool
    assert "groupadd --gid 1001 runner" in DOCKERFILE and "useradd --uid 1001 --gid 1001" in DOCKERFILE
    assert re.search(r"^USER runner$", DOCKERFILE, re.M) and re.search(r"^WORKDIR /home/runner/work$", DOCKERFILE, re.M)
    after_user = DOCKERFILE.split("\nUSER runner\n", 1)[1]
    assert "USER " not in after_user and "mkdir -p /home/runner/work /home/runner/.cache/uv /home/runner/.npm" in after_user, "the folders of the volumes are made as the runner, whose they then are"


def test_uv_and_node_are_pinned_by_version_and_digest_and_no_file_of_the_project_is_copied_in() -> None:
    assert re.search(r"^ARG UV_VERSION=\d+\.\d+\.\d+$", DOCKERFILE, re.M) and re.search(r"^ARG UV_SHA256=[0-9a-f]{64}$", DOCKERFILE, re.M)
    node = re.search(r"^ARG NODE_VERSION=22\.(\d+)\.\d+$", DOCKERFILE, re.M)
    assert node is not None and int(node.group(1)) >= 12 and re.search(r"^ARG NODE_SHA256=[0-9a-f]{64}$", DOCKERFILE, re.M), "node 22.12 or newer, as scripts/check asks"
    fetched = re.findall(r"curl -fsSL -o (\S+) \"(https://[^\"]+)\"", DOCKERFILE)
    assert len(fetched) == 2 and "${UV_VERSION}" in fetched[0][1] and "${NODE_VERSION}" in fetched[1][1]
    for file, digest in zip((file for file, _ in fetched), ("UV_SHA256", "NODE_SHA256")):
        assert f'echo "${{{digest}}}  {file}" | sha256sum --check --strict -' in DOCKERFILE, f"{file} is checked against its pin before it is unpacked"
    instructions = "\n".join(line for line in DOCKERFILE.splitlines() if not line.startswith("#"))
    assert re.findall(r"https://[^\s\"]+", instructions) == [address for _, address in fetched], "every address the build names is one whose file is checked"
    assert not re.search(r"^\s*(COPY|ADD)\b", DOCKERFILE, re.M)


def test_the_python_of_the_image_is_the_one_the_workflows_name() -> None:
    named = set(re.findall(r'python-version: "([\d.]+)"', WORKFLOW))
    assert len(named) == 1
    assert f"ARG PYTHON_VERSION={named.pop()}\n" in DOCKERFILE and "UV_PYTHON=${PYTHON_VERSION}" in DOCKERFILE and 'uv python install "${PYTHON_VERSION}"' in DOCKERFILE


# ---- the script from end to end, on a stand-in for docker ----

FAKE_DOCKER = r"""#!/bin/sh
# Stands in for docker: writes down the first two words of each call, keeps what `build` and `run` were given, and answers as the files of $FAKE_DOCKER say.
echo "$1 $2" >> "$FAKE_DOCKER/calls"
case "$1" in
    image) [ -e "$FAKE_DOCKER/has-image" ] ;;
    build) cat > "$FAKE_DOCKER/build.input"; echo "$*" > "$FAKE_DOCKER/build.args"; [ ! -e "$FAKE_DOCKER/build-fails" ] ;;
    ps) cat "$FAKE_DOCKER/ps" 2>/dev/null; exit 0 ;;
    run)
        printf '%s\0' "$@" > "$FAKE_DOCKER/run.args"
        echo $$ > "$FAKE_DOCKER/run.pid"
        while [ $# -gt 1 ]; do [ "$1" = --cidfile ] && echo c0ffee > "$2"; shift; done
        cat > "$FAKE_DOCKER/run.tar.part" && mv "$FAKE_DOCKER/run.tar.part" "$FAKE_DOCKER/run.tar"
        [ -e "$FAKE_DOCKER/hangs" ] && exec sleep 600
        exit "$(cat "$FAKE_DOCKER/exit" 2>/dev/null || echo 0)" ;;
    rm) echo "$*" >> "$FAKE_DOCKER/removed"; kill "$(cat "$FAKE_DOCKER/run.pid")" 2>/dev/null; exit 0 ;;
esac
"""


class Rig:
    """The script in a made-up folder of its own (it packs the repository it lies in), with the stand-in for docker first on the PATH. Its home, its temporary folder and the folder it is started
    in are the rig's too, each empty: nothing of the user's configuration reaches it, and whatever it left behind would lie there and not in the repository the suite is run in."""

    def __init__(self, folder: Path, tmp_path: Path) -> None:
        self.repo, self.state, self.runtime, self.temp, self.started_in = folder, tmp_path / "docker", tmp_path / "runtime", tmp_path / "temp", tmp_path / "started-in"
        (folder / "scripts").mkdir(parents=True)
        (folder / "packaging" / "ci").mkdir(parents=True)
        shutil.copy(SCRIPT, folder / "scripts" / "check-in-container")
        shutil.copy(ROOT / "packaging" / "ci" / "Dockerfile", folder / "packaging" / "ci" / "Dockerfile")
        home, bin_folder = tmp_path / "home", tmp_path / "bin"
        for made in (self.state, self.runtime, self.temp, self.started_in, home, bin_folder):
            made.mkdir()
        (bin_folder / "docker").write_text(FAKE_DOCKER)
        (bin_folder / "docker").chmod(0o755)
        self.env = {"PATH": f"{bin_folder}{os.pathsep}{os.environ['PATH']}", "HOME": str(home), "TMPDIR": str(self.temp), "FAKE_DOCKER": str(self.state), "XDG_RUNTIME_DIR": str(self.runtime),
                    "LC_ALL": "C.UTF-8"}
        self.command = [sys.executable, str(folder / "scripts" / "check-in-container")]

    def has(self, name: str, text: str = "") -> None:
        (self.state / name).write_text(text)

    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([*self.command, *args], cwd=self.started_in, env=self.env, capture_output=True, text=True, timeout=PATIENCE_SEC)

    def left_behind(self) -> list[str]:
        """What lies in the script's temporary folder and in the folder it was started in."""
        return sorted(str(file) for folder in (self.temp, self.started_in) for file in folder.iterdir())

    def calls(self) -> list[str]:
        file = self.state / "calls"
        return file.read_text().splitlines() if file.exists() else []

    def run_line(self) -> list[str]:
        return (self.state / "run.args").read_text().split("\0")[:-1]


@pytest.fixture
def rig(repo: Path, tmp_path: Path) -> Iterator[Rig]:
    made = Rig(repo, tmp_path)
    git(repo, "add", "scripts", "packaging")
    yield made
    with contextlib.suppress(OSError, ValueError):       # (a stand-in that was left hanging by a test that failed; the number of one that has ended may be another program's by now)
        pid = int((made.state / "run.pid").read_text())
        if Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")[:2] == [b"sleep", b"600"]:
            os.kill(pid, SIGKILL)


@linux_only
def test_a_run_builds_the_image_that_is_missing_feeds_the_tree_and_ends_with_the_commands_exit_code(script: ModuleType, rig: Rig) -> None:
    rig.has("exit", "3")
    done = rig.run()
    assert done.returncode == 3, done.stderr
    assert rig.calls() == ["image inspect", "build --tag", "ps --all", "run --rm"]
    tag = script.image_tag(rig.repo / "packaging" / "ci" / "Dockerfile")
    assert (rig.state / "build.args").read_text() == f"build --tag {tag} -\n" and (rig.state / "build.input").read_text() == DOCKERFILE
    line = rig.run_line()
    assert line[line.index(tag) + 1:] == ["bash", "-c", script.INSIDE, "check-in-container", *script.CI_COMMANDS], "with no command, the CI job's own"
    cpus = options(line, "--cpuset-cpus")[0].split(",")
    assert 1 <= len(cpus) <= 4 and len(set(cpus)) == len(cpus) and options(line, "--memory") == ["16g"]
    with tarfile.open(rig.state / "run.tar") as archive:
        names = archive.getnames()
    assert "neoaprs/scripts/check-in-container" in names and "neoaprs/new.txt" in names and "tracked" in names and "neoaprs/debug.log" not in names
    assert f"check-in-container: building {tag} from packaging/ci/Dockerfile" in done.stderr and f"check-in-container: {tag} on threads {','.join(cpus)} with 16 GB" in done.stderr
    assert done.stdout == "" and [file.name for file in rig.runtime.iterdir()] == ["neoaprs-check-in-container.lock"], "the lock of the start is in the user's runtime folder"
    scratch = Path(options(line, "--cidfile")[0]).parent
    assert scratch.parent == rig.temp and scratch.name.startswith("check-in-container-"), "the folder of the container's id is made in the temporary folder"
    assert rig.left_behind() == [], "and is taken away, as is the packed tree; nothing is written where the script was started"


@linux_only
def test_an_image_that_is_there_is_not_built_again_and_a_command_of_ones_own_goes_in_as_one_shell_line(script: ModuleType, rig: Rig) -> None:
    rig.has("has-image")
    done = rig.run("--starved", "--", "uv", "run", "pytest", "-k", "a name", "tests/test_x.py")
    assert done.returncode == 0, done.stderr
    assert rig.calls() == ["image inspect", "ps --all", "run --rm"]
    line = rig.run_line()
    assert line[line.index("check-in-container") + 1:] == ["uv run pytest -k 'a name' tests/test_x.py"]
    assert len(options(line, "--cpuset-cpus")[0].split(",")) <= 2 and options(line, "--memory") == ["7g"]


@linux_only
def test_a_run_started_beside_others_takes_cores_they_do_not_hold(script: ModuleType, rig: Rig) -> None:
    cores = script.read_cores()
    if len(cores) < 2:
        pytest.skip("a machine of one core has no other core to take")
    first = script.choose_cpus(cores, 2)
    rig.has("has-image")
    rig.has("ps", ",".join(str(cpu) for cpu in first) + "\n")
    assert rig.run("--starved", "--", "true").returncode == 0
    mine = [int(cpu) for cpu in options(rig.run_line(), "--cpuset-cpus")[0].split(",")]
    assert mine and not set(mine) & set(first)


def test_image_only_builds_prints_the_name_and_runs_nothing(script: ModuleType, rig: Rig) -> None:
    done = rig.run("--image-only")
    assert done.returncode == 0, done.stderr
    assert done.stdout == script.image_tag(rig.repo / "packaging" / "ci" / "Dockerfile") + "\n"
    assert rig.calls() == ["image inspect", "build --tag"]


def test_a_build_that_fails_ends_with_dockers_own_code_and_runs_nothing(rig: Rig) -> None:
    rig.has("build-fails")
    done = rig.run()
    assert done.returncode == 125 and "check-in-container: the image could not be built" in done.stderr
    assert rig.calls() == ["image inspect", "build --tag"]


def test_help_and_a_wrong_argument_ask_docker_nothing(rig: Rig) -> None:
    done = rig.run("--help")
    assert done.returncode == 0 and "scripts/check-in-container [--starved] [--image-only] [-- COMMAND...]" in done.stdout and "--cpuset" not in done.stderr
    assert rig.run("pytest").returncode == 2 and rig.run("--starved", "pytest").returncode == 2, "a command comes after `--`"
    assert rig.calls() == []


def test_without_docker_the_script_says_so(rig: Rig, tmp_path: Path) -> None:
    empty = tmp_path / "no-tools"
    empty.mkdir()
    done = subprocess.run([*rig.command], cwd=rig.started_in, env={**rig.env, "PATH": str(empty)}, capture_output=True, text=True, timeout=PATIENCE_SEC)
    assert done.returncode == 2 and done.stderr == "check-in-container: docker is not installed\n"


def wait_for(condition: Callable[[], bool], what: str) -> None:
    deadline = time.monotonic() + PATIENCE_SEC
    while not condition():
        assert time.monotonic() < deadline, f"waited {PATIENCE_SEC:.0f} s for {what}"
        time.sleep(0.02)


@linux_only
@pytest.mark.parametrize("number", [signal.SIGTERM, signal.SIGINT])
def test_a_signal_that_ends_the_script_removes_its_container(rig: Rig, number: signal.Signals) -> None:
    rig.has("has-image")
    rig.has("hangs")
    process = subprocess.Popen([*rig.command, "--", "sleep", "600"], cwd=rig.started_in, env=rig.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        wait_for((rig.state / "run.tar").exists, "the container to have read the tree")
        process.send_signal(number)
        assert process.wait(timeout=PATIENCE_SEC) == 128 + number
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()
    assert (rig.state / "removed").read_text().splitlines()[0] == "rm --force c0ffee"
    assert rig.left_behind() == []


def one_line_and_nothing_started(rig: Rig, done: subprocess.CompletedProcess[str], sentence: str) -> None:
    """`sentence` is a pattern for the whole of what is said after the script's own words."""
    assert done.returncode == 2 and done.stdout == "", done.stderr
    lines = done.stderr.splitlines()
    assert len(lines) == 1 and re.fullmatch(f"check-in-container: nothing was run: {sentence}", lines[0]), f"one plain sentence, and no traceback: {done.stderr}"
    assert rig.calls() == [] and rig.left_behind() == [], "docker was asked for nothing: no image looked for or built, no container started"


def test_a_file_that_cannot_be_read_ends_in_one_sentence_before_docker_is_asked_for_anything(rig: Rig) -> None:
    if is_root():
        pytest.skip("root reads every file")
    (rig.repo / "new.txt").chmod(0)
    one_line_and_nothing_started(rig, rig.run(), r"new\.txt could not be packed \(Permission denied\)")
    one_line_and_nothing_started(rig, rig.run("--starved", "--", "true"), r"new\.txt could not be packed \(Permission denied\)")


def test_a_folder_that_cannot_be_opened_ends_in_one_sentence_before_docker_is_asked_for_anything(rig: Rig) -> None:
    if is_root():
        pytest.skip("root enters every folder")
    (rig.repo / "kept-out").mkdir()
    with closed(rig.repo / "kept-out"):
        done = rig.run()
    one_line_and_nothing_started(rig, done, rf"git could not list the files of {re.escape(str(rig.repo.resolve()))} \(.*kept-out/.*\)")      # (in the brackets, git's own words)


def test_a_folder_that_is_no_repository_ends_in_one_sentence_before_docker_is_asked_for_anything(tmp_path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("needs git")
    plain = Rig(tmp_path / "unpacked-from-an-archive", tmp_path)
    assert asked(plain.repo, "rev-parse", "--show-toplevel").returncode != 0, "the folder is in no repository"
    one_line_and_nothing_started(plain, plain.run(), re.escape(f"{plain.repo.resolve()} is not the working tree of a git repository (the tree that goes in is the one git lists)"))


def test_the_image_is_built_for_image_only_whatever_the_tree_is(script: ModuleType, tmp_path: Path) -> None:
    plain = Rig(tmp_path / "unpacked-from-an-archive", tmp_path)
    done = plain.run("--image-only")
    assert done.returncode == 0 and done.stdout == script.image_tag(plain.repo / "packaging" / "ci" / "Dockerfile") + "\n", done.stderr
    assert plain.calls() == ["image inspect", "build --tag"] and plain.left_behind() == []
