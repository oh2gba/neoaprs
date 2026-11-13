"""`scripts/site-check` against a web server of this computer that stands for the project's host: the page as committed in a made-up repository passes; a changed file, a missing one and a moved one are findings; so is
every private place that does not answer 403 (the stored support files, PHP's settings, the version page's logs, a hidden file and a helper that git tracks under `server/neo/`), while a public endpoint is not asked; a file that
is on the server and not committed is not asked for; only GET is sent; and an address that is not https (but this computer's), has a path, or does not answer ends with exit code 2 and no finding. Never the real site."""
import http.server
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest

from tests.support.ptyline import posix_only

pytestmark = posix_only

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "site-check"
SITE = {"index.html": b"<html>home</html>", "faq.html": b"<html>faq</html>", "shots/a.png": b"\x89PNG made up", "frequencies.json": b"[]"}
NEO = {".htaccess": b"Options -Indexes\n", "private/.htaccess": b"Require all denied\n", "support/send.php": b"<?php // endpoint\n", "api/v1/view.php": b"<?php // endpoint\n", "support/.user.ini": b"x\n"}


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Made Up", "-c", "user.email=made-up@example.invalid", *args], check=True, capture_output=True, env={"PATH": os.environ["PATH"], "HOME": str(repo.parent)})


def commit(repo: Path) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "made up")


class Host:
    """What the live site answers: `files` by path (an absolute path with a leading slash), `status` to say another status for a path, `moved` for a redirect; everything else under the private places is 403, anything unknown 404."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.status: dict[str, int] = {}
        self.moved: set[str] = set()
        self.methods: list[str] = []
        self.asked: list[str] = []
        self.server: http.server.ThreadingHTTPServer | None = None

    def start(self) -> str:
        host = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                host.methods.append("GET")
                host.asked.append(self.path)
                answer(self, self.path)

            def do_POST(self) -> None:
                host.methods.append("POST")
                self.send_error(405)

            def log_message(self, *args: object) -> None:
                return

        def answer(handler: Handler, path: str) -> None:
            if path in host.moved:
                handler.send_response(301)
                handler.send_header("Location", "https://elsewhere.invalid" + path)
                handler.send_header("Content-Length", "0")
                handler.end_headers()
                return
            code = host.status.get(path)
            if code is None:
                private = path.startswith(("/private", "/log/")) or path in ("/.htaccess", "/.user.ini", "/support/.user.ini")
                code = 200 if path in host.files else 403 if private else 404
            body = host.files.get(path, b"") if code == 200 else b""
            handler.send_response(code)
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    made = tmp_path / "repo"
    for name, body in SITE.items():
        (made / "site" / name).parent.mkdir(parents=True, exist_ok=True)
        (made / "site" / name).write_bytes(body)
    for name, body in NEO.items():
        (made / "server" / "neo" / name).parent.mkdir(parents=True, exist_ok=True)
        (made / "server" / "neo" / name).write_bytes(body)
    git(made, "init", "-q")
    commit(made)
    return made


@pytest.fixture
def host(repo: Path) -> Iterator[tuple[Host, str]]:
    """The live site as it should be: the site's files at their paths and `/` the index."""
    served = Host()
    served.files = {f"/{name}": body for name, body in SITE.items()} | {"/": SITE["index.html"]}
    yield served, served.start()
    served.stop()


def check(url: str, repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-I", str(SCRIPT), url, "--root", str(repo)], capture_output=True, text=True, timeout=120, env={"PATH": os.environ["PATH"], "HOME": str(repo.parent)})


def test_a_page_as_committed_with_every_private_place_forbidden_passes(repo: Path, host: tuple[Host, str]) -> None:
    served, url = host
    done = check(url, repo)
    places = module().private_places(repo, datetime.now(UTC))
    assert done.returncode == 0 and done.stdout == f"site-check: 4 files compared, {len(places)} private places asked, 0 findings\n", done.stdout
    assert all(place in served.asked for place in places)
    assert set(served.methods) == {"GET"}, "nothing but GET is sent"
    assert "/private/support/salt" in served.asked and "/support/.user.ini" in served.asked and "/private/.htaccess" in served.asked


def test_a_changed_a_missing_and_a_moved_file_are_findings(repo: Path, host: tuple[Host, str]) -> None:
    served, url = host
    served.files["/faq.html"] = b"<html>faq</html><script src=//evil.invalid></script>"
    del served.files["/frequencies.json"]
    served.moved.add("/shots/a.png")
    done = check(url, repo)
    assert done.returncode == 1
    assert done.stdout.splitlines()[:3] == ["changed: /faq.html", "missing: /frequencies.json (status 404)", "not served: /shots/a.png (status 301)"]


def test_the_index_is_compared_at_the_address_of_the_root_too(repo: Path, host: tuple[Host, str]) -> None:
    served, url = host
    served.files["/"] = b"<html>defaced</html>"
    assert check(url, repo).stdout.splitlines()[0] == "changed: /"


def test_a_private_place_that_is_not_403_is_a_finding_whatever_it_answers(repo: Path, host: tuple[Host, str]) -> None:
    served, url = host
    served.files["/private/support/rate.json"] = b"{}"
    served.status["/log/latest.json"] = 404
    served.status["/support/.user.ini"] = 301
    done = check(url, repo)
    assert done.returncode == 1
    lines = done.stdout.splitlines()
    assert "not forbidden: /private/support/rate.json (status 200, it must be 403)" in lines
    assert "not forbidden: /log/latest.json (status 404, it must be 403)" in lines
    assert "not forbidden: /support/.user.ini (status 301, it must be 403)" in lines
    assert lines[-1].endswith("3 findings")


def test_the_logs_of_the_version_page_of_this_month_and_the_last_are_asked(repo: Path, host: tuple[Host, str]) -> None:
    served, url = host
    now = datetime.now(UTC)
    served.status[f"/log/starts-{now:%Y-%m}.log"] = 200
    assert f"not forbidden: /log/starts-{now:%Y-%m}.log (status 200, it must be 403)" in check(url, repo).stdout
    loaded = module()
    assert loaded.private_places(repo, datetime(2026, 1, 15, tzinfo=UTC)).count("/log/starts-2025-12.log") == 1, "the last month of the year before"


def test_a_tracked_helper_and_a_tracked_hidden_file_must_be_forbidden_and_an_endpoint_is_not_asked(repo: Path, host: tuple[Host, str]) -> None:
    served, url = host
    helper = repo / "server" / "neo" / "lib" / "skeds-store.php"
    helper.parent.mkdir()
    helper.write_bytes(b"<?php // a helper\n")
    hidden = repo / "server" / "neo" / "skeds" / ".htaccess"
    hidden.parent.mkdir()
    hidden.write_bytes(b"Require all denied\n")
    commit(repo)
    served.files["/lib/skeds-store.php"] = b"<?php // a helper\n"
    done = check(url, repo)
    assert done.stdout.splitlines()[0] == "not forbidden: /lib/skeds-store.php (status 200, it must be 403)"
    assert "/skeds/.htaccess" in served.asked and "/support/send.php" not in served.asked and "/api/v1/view.php" not in served.asked


def test_a_file_that_is_on_the_server_and_not_committed_is_not_asked_for_and_an_untracked_local_one_is_not_expected(repo: Path, host: tuple[Host, str]) -> None:
    served, url = host
    (repo / "site" / "draft.html").write_text("not committed", encoding="utf-8")
    served.files["/planted.php"] = b"<?php system($_GET['c']);"
    done = check(url, repo)
    assert done.returncode == 0, done.stdout
    assert "/draft.html" not in served.asked and "/planted.php" not in served.asked


def test_a_file_that_is_deleted_from_the_disk_is_still_what_is_committed(repo: Path, host: tuple[Host, str]) -> None:
    served, url = host
    (repo / "site" / "faq.html").unlink()
    assert check(url, repo).returncode == 0, "the live page has the committed file"
    del served.files["/faq.html"]
    assert check(url, repo).stdout.splitlines()[0] == "missing: /faq.html (status 404)"


def test_the_live_file_is_compared_with_the_committed_one_and_not_with_the_one_edited_on_the_disk(repo: Path, host: tuple[Host, str]) -> None:
    served, url = host
    (repo / "site" / "frequencies.json").write_bytes(b'["a value pasted for a test"]')
    assert check(url, repo).returncode == 0, "the live page is what is committed"
    served.files["/frequencies.json"] = b'["a value pasted for a test"]'
    done = check(url, repo)
    assert done.returncode == 1 and done.stdout.splitlines()[0] == "changed: /frequencies.json", "the deployed disk file is not the committed one"


def test_a_link_in_the_tree_is_no_file_to_compare(repo: Path, host: tuple[Host, str]) -> None:
    _, url = host
    (repo / "site" / "leak.txt").symlink_to(repo / "site" / "index.html")
    commit(repo)
    assert "leak.txt" not in module().tracked(repo, "site")
    assert check(url, repo).returncode == 0


def test_a_checkout_without_a_commit_is_exit_code_2(tmp_path: Path, host: tuple[Host, str]) -> None:
    _, url = host
    bare = tmp_path / "bare"
    (bare / "site").mkdir(parents=True)
    git(bare, "init", "-q")
    done = check(url, bare)
    assert done.returncode == 2 and done.stdout == "" and "could not be read" in done.stderr


@pytest.mark.parametrize("address", ["http://example.invalid", "https://neo.example.invalid/path", "ftp://127.0.0.1", "https://user@neo.example.invalid", "127.0.0.1:80", "https://neo.example.invalid?x=1"])
def test_an_address_that_is_not_the_page_s_own_https_one_is_refused_before_anything_is_asked(repo: Path, address: str) -> None:
    done = check(address, repo)
    assert done.returncode == 2 and done.stdout == "" and done.stderr.startswith("site-check: ")


def test_a_host_that_does_not_answer_is_one_line_and_exit_code_2(repo: Path) -> None:
    done = check("http://127.0.0.1:9", repo)       # (the discard port: nothing listens)
    assert done.returncode == 2 and done.stdout == "" and len(done.stderr.splitlines()) == 1 and "no answer from http://127.0.0.1:9" in done.stderr


def module() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("site_check", str(SCRIPT))
    spec = importlib.util.spec_from_loader("site_check", loader)
    assert spec is not None
    loaded = importlib.util.module_from_spec(spec)
    loader.exec_module(loaded)
    return loaded


def test_every_endpoint_it_leaves_alone_is_a_php_file_the_repository_tracks() -> None:
    """`PUBLIC_PHP` names the endpoints under `server/neo/`; every other PHP file the repository tracks there is checked for 403, so a renamed endpoint (and a new one, which has to be added) shows here or on the live page."""
    loaded = module()
    assert set(loaded.PUBLIC_PHP) <= {name for name in loaded.tracked(ROOT, "server/neo") if name.endswith(".php")}
