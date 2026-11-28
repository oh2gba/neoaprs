"""Tests for `server/deploy.sh`, which uploads only what git tracks: a made-up repository with
stand-in secrets manager and curl first on the PATH. The real server is never contacted."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.support.ptyline import posix_only

pytestmark = posix_only

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "server" / "deploy.sh"
MADE_UP = "made-up-for-this-test"
BWS = """#!/usr/bin/env bash
echo '[{"key":"ftp_server","value":"host.invalid"},{"key":"ftp_login","value":"user-made-up"},{"key":"ftp_pw","value":"made-up-for-this-test"}]'
"""
CURL = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "$CURL_ARGS"
"""
TRACKED = [
    "server/version.php",
    "server/latest.php",
    "server/log/.htaccess",
    "server/neo/.htaccess",
    "server/neo/support/send.php",
    "server/neo/private/.htaccess",
    "site/index.html",
    "site/shots/a.png",
    "site/signals/a.wav",
    "site/gone.html",
]
LEFT_OUT = [
    "site/draft.html",
    "server/neo/private/leaked.txt",
    "site/notes/ignored.txt",
    "server/neo/support/send.php.orig",
]


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={"PATH": os.environ["PATH"], "HOME": str(repo.parent)},
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository of its own with the script in server/, the tracked files, a deleted tracked one,
    an untracked and an ignored one."""
    made = tmp_path / "repo"
    made.mkdir()
    for name in TRACKED + LEFT_OUT:
        path = made / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{name}\n", encoding="utf-8")
    shutil.copy(SCRIPT, made / "server" / "deploy.sh")
    (made / ".gitignore").write_text("site/notes/\n", encoding="utf-8")
    git(made, "init", "-q")
    git(made, "add", "--", *TRACKED, "server/deploy.sh", ".gitignore")
    (made / "site" / "gone.html").unlink()
    return made


@pytest.fixture
def tools(tmp_path: Path) -> Path:
    folder = tmp_path / "tools"
    folder.mkdir()
    for name, text in (("bws", BWS), ("curl", CURL)):
        (folder / name).write_text(text, encoding="utf-8")
        (folder / name).chmod(0o755)
    (tmp_path / "token.txt").write_text(f"{MADE_UP}\n", encoding="utf-8")
    return folder


def run(repo: Path, tools: Path, *args: str) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    sent = repo.parent / "curl-args.txt"
    env = {
        "PATH": f"{tools}:{os.environ['PATH']}",
        "HOME": str(repo.parent),
        "SECRETS_FILE": str(repo.parent / "token.txt"),
        "CURL_ARGS": str(sent),
        "BWS": str(tools / "bws"),
        # (a folder whose .git is gone is no checkout, even inside one: --basetemp under work/
        # puts it in this tree)
        "GIT_CEILING_DIRECTORIES": str(repo.parent),
    }
    done = subprocess.run(
        ["bash", str(repo / "server" / "deploy.sh"), *args], capture_output=True, text=True, env=env, timeout=60
    )
    return done, sent.read_text(encoding="utf-8").splitlines() if sent.exists() else []


def test_the_site_upload_has_the_tracked_files_and_not_an_untracked_ignored_or_deleted_one(
    repo: Path, tools: Path
) -> None:
    done, args = run(repo, tools, "--site")
    assert done.returncode == 0, done.stderr
    sent = [Path(a).relative_to(repo).as_posix() for flag, a in zip(args, args[1:], strict=False) if flag == "-T"]
    expected = {
        "server/version.php",
        "server/latest.php",
        "server/log/.htaccess",
        "site/index.html",
        "site/shots/a.png",
        "site/signals/a.wav",
        "server/neo/.htaccess",
        "server/neo/support/send.php",
        "server/neo/private/.htaccess",
    }
    assert set(sent) == expected
    for name in LEFT_OUT + ["site/gone.html"]:
        assert name not in sent and not any(name in a for a in args if not a.startswith("-")), name


def test_the_files_it_leaves_out_are_named_and_the_tracked_ones_are_not(repo: Path, tools: Path) -> None:
    done, _ = run(repo, tools, "--site")
    said = done.stderr.splitlines()
    for name in (
        "site/draft.html",
        "server/neo/private/leaked.txt",
        "site/notes/ignored.txt",
        "server/neo/support/send.php.orig",
    ):
        assert f"skipped, not tracked by git: {repo}/{name}" in said, name
    assert len([line for line in said if line.startswith("skipped")]) == 4, "each is named once"


def test_the_list_shows_the_same_without_asking_the_network(repo: Path, tools: Path) -> None:
    done, args = run(repo, tools, "--list")
    assert done.returncode == 0 and args == [], "curl was never started"
    listed = done.stdout
    assert (
        "/public_html/neo/index.html" in listed
        and "/public_html/neo/private/.htaccess" in listed
        and "/public_html/neo/support/send.php" in listed
    )
    assert not any(word in listed for word in ("draft.html", "leaked.txt", "ignored.txt", "send.php.orig", "gone.html"))
    assert "skipped, not tracked by git" in done.stderr and "draft.html" in done.stderr


def test_the_version_page_alone_is_uploaded_without_the_site_and_says_nothing_of_the_folders(
    repo: Path, tools: Path
) -> None:
    done, args = run(repo, tools)
    assert done.returncode == 0, done.stderr
    sent = {Path(a).relative_to(repo).as_posix() for flag, a in zip(args, args[1:], strict=False) if flag == "-T"}
    assert sent == {"server/version.php", "server/latest.php", "server/log/.htaccess"}
    assert "skipped" not in done.stderr


def test_a_folder_that_is_no_checkout_is_refused_before_the_network_is_asked(repo: Path, tools: Path) -> None:
    shutil.rmtree(repo / ".git")
    done, args = run(repo, tools, "--site")
    assert done.returncode == 2 and "no git checkout" in done.stderr and args == []
    done, args = run(repo, tools, "--list")
    assert done.returncode == 2 and args == []


def test_a_file_of_the_version_page_that_is_not_tracked_stops_the_upload(repo: Path, tools: Path) -> None:
    git(repo, "rm", "-q", "--cached", "--", "server/latest.php")
    done, args = run(repo, tools)
    assert done.returncode == 2 and "server/latest.php is not tracked by git" in done.stderr and args == []


def test_the_script_of_the_repository_has_no_find_over_the_folders_it_sends() -> None:
    """The way a file is listed is git's: a `find` over a folder would send what git does not know."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "git -C" in text and "ls-files" in text and "find ." not in text


def test_a_tracked_link_stops_the_upload_before_anything_is_asked(repo: Path, tools: Path) -> None:
    """curl would send what the link points at: a link to a file outside the folders is a leak."""
    outside = repo.parent / "secret.txt"
    outside.write_text("made-up\n", encoding="utf-8")
    (repo / "site" / "leak.txt").symlink_to(outside)
    git(repo, "add", "--", "site/leak.txt")
    for option in ("--site", "--list"):
        done, args = run(repo, tools, option)
        assert done.returncode == 2 and "site/leak.txt" in done.stderr and "link" in done.stderr and args == [], option
        assert "leak.txt" not in done.stdout


@pytest.mark.parametrize("name", ["x\n.env", "a\tb.html"])
def test_a_tracked_name_with_a_line_end_or_a_tab_stops_the_upload(repo: Path, tools: Path, name: str) -> None:
    (repo / "site" / name).write_text("made-up\n", encoding="utf-8")
    git(repo, "add", "--", f"site/{name}")
    for option in ("--site", "--list"):
        done, args = run(repo, tools, option)
        assert done.returncode == 2 and "control character" in done.stderr and args == [], option
        assert "/public_html/neo/.env" not in done.stdout


@pytest.mark.parametrize(
    ("script", "args"),
    [("deploy.sh", []), ("skeds.sh", ["rm", "0123456789ab"]), ("support-fetch.sh", []), ("usage-report.sh", [])],
)
def test_a_token_file_that_was_named_and_is_missing_is_never_replaced_by_the_one_beside_the_checkout(
    repo: Path, tmp_path: Path, script: str, args: list[str]
) -> None:
    """The scripts fall back to ../../oh2gba/.secrets only when no file was named: with SECRETS_FILE
    naming a missing one (as a test does), the developer's real token stays unread and nothing is
    asked."""
    shutil.copy(ROOT / "server" / script, repo / "server" / script)
    beside = tmp_path / "oh2gba"
    beside.mkdir()
    (beside / ".secrets").write_text(f"{MADE_UP}\n", encoding="utf-8")
    asked = tmp_path / "bws-was-asked"
    bws = tmp_path / "bws"
    bws.write_text(f"#!/usr/bin/env bash\necho \"$BWS_ACCESS_TOKEN\" > {asked}\necho '[]'\n", encoding="utf-8")
    bws.chmod(0o755)
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "SECRETS_FILE": str(tmp_path / "none"), "BWS": str(bws)}
    done = subprocess.run(
        ["bash", str(repo / "server" / script), *args], capture_output=True, text=True, env=env, timeout=60
    )
    assert done.returncode == 1 and "no .secrets file" in done.stderr, (done.returncode, done.stderr)
    assert not asked.exists(), "the token of the file beside the checkout went to the secrets program"
    assert MADE_UP not in done.stdout + done.stderr


def test_an_upload_of_hundreds_of_files_ends_well_and_names_the_first_twelve(repo: Path, tools: Path) -> None:
    """The list of what was sent is cut to twelve lines; cut by `head`, a long list ended the script
    with 141 after everything was uploaded."""
    many = [f"site/shots/picture-{i:03}.png" for i in range(600)]
    for name in many:
        (repo / name).write_text(f"{name}\n", encoding="utf-8")
    git(repo, "add", "--", *many)
    done, args = run(repo, tools, "--site")
    assert done.returncode == 0, done.stderr
    sent = [a for a in args if a.startswith("sftp://")]
    assert len(sent) > 600 and done.stdout.count("  -> ") == 12
    assert f"... and {len(sent) - 12} more" in done.stdout and "done." in done.stdout


STOP_ON_LOGIN = """#!/usr/bin/env bash
printf '%s\\n' "$@" >> "$CURL_ARGS"
cat > "$CURL_STDIN"
exit "${CURL_EXIT:-0}"
"""


def run_tool(
    tmp_path: Path, script: str, args: list[str], code: int = 0
) -> tuple[subprocess.CompletedProcess[str], list[str], str]:
    tools = tmp_path / "tools"
    tools.mkdir(exist_ok=True)
    for name, text in (("bws", BWS), ("curl", STOP_ON_LOGIN)):
        (tools / name).write_text(text, encoding="utf-8")
        (tools / name).chmod(0o755)
    (tmp_path / "token.txt").write_text(f"{MADE_UP}\n", encoding="utf-8")
    sent, login = tmp_path / "args.txt", tmp_path / "stdin.txt"
    env = {
        "PATH": f"{tools}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "SECRETS_FILE": str(tmp_path / "token.txt"),
        "BWS": str(tools / "bws"),
        "CURL_ARGS": str(sent),
        "CURL_STDIN": str(login),
        "CURL_EXIT": str(code),
        "TMPDIR": str(tmp_path),
    }
    done = subprocess.run(
        ["bash", str(ROOT / "server" / script), *args], capture_output=True, text=True, env=env, timeout=60
    )
    return (
        done,
        sent.read_text(encoding="utf-8").splitlines() if sent.exists() else [],
        login.read_text(encoding="utf-8") if login.exists() else "",
    )


def test_a_blocked_list_that_could_not_be_read_is_never_replaced(tmp_path: Path) -> None:
    done, args, _ = run_tool(tmp_path, "skeds.sh", ["block", "OH2XYZ"], code=6)
    assert done.returncode == 1 and "could not be read" in done.stderr
    assert "-T" not in args, "nothing was uploaded"


def test_a_blocked_list_that_is_not_there_starts_empty(tmp_path: Path) -> None:
    done, args, _ = run_tool(tmp_path, "skeds.sh", ["block", "OH2XYZ"], code=78)
    assert "-T" in args and "could not be read" not in done.stderr


@pytest.mark.parametrize(
    ("script", "args"), [("skeds.sh", ["blocked"]), ("support-fetch.sh", ["--list"]), ("usage-report.sh", [])]
)
def test_the_login_reaches_curl_on_stdin_and_never_on_its_command_line(
    tmp_path: Path, script: str, args: list[str]
) -> None:
    done, argv, login = run_tool(tmp_path, script, args)
    assert argv, done.stderr
    assert MADE_UP not in "\n".join(argv) and "user-made-up" not in "\n".join(argv)
    assert "-K" in argv and f'user = "user-made-up:{MADE_UP}"' in login


def test_the_deploy_sends_the_login_on_stdin_too(repo: Path, tools: Path) -> None:
    done, args = run(repo, tools, "--site")
    assert done.returncode == 0 and MADE_UP not in "\n".join(args) and "-K" in args
