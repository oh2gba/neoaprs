"""The daemon serves the page it was started with: the files of `neoaprs/page/` are read into memory once, so a page rebuilt on disk, a branch switched or a package upgraded while the daemon runs changes nothing until it is
started again, and the page and the daemon that say their build in `hello` are always a pair."""
import hashlib
import logging
from pathlib import Path

import pytest

from neoaprs.web import server as web_server
from neoaprs.web.pagesnapshot import MAX_BYTES, PageSnapshot
from tests.support.env import Env

OLD = '<!doctype html><script type="module" crossorigin src="./assets/index-OLDOLD11.js"></script><link rel="stylesheet" href="./assets/index-OLDCSS11.css"><div id="app"></div>'
NEW = OLD.replace("OLD", "NEW")
MARK = "x"                                                                                    # (a shipped page is about 3.4 MB; the tests need only a few bytes)


def build_page(folder: Path, html: str, *, worker: str = "// worker") -> None:
    """A page folder the way Vite leaves one: the shell, the files it names, the worker, a hidden file and a source map that must not be served."""
    name = "OLDOLD11" if "OLDOLD11" in html else "NEWNEW11"
    css = "OLDCSS11" if "OLDCSS11" in html else "NEWCSS11"
    (folder / "assets").mkdir(parents=True, exist_ok=True)
    (folder / "index.html").write_text(html, encoding="utf-8")
    (folder / "assets" / f"index-{name}.js").write_text(f"console.log('{name}')", encoding="utf-8")
    (folder / "assets" / f"index-{css}.css").write_text("body{}", encoding="utf-8")
    (folder / "assets" / f"index-{name}.js.map").write_text("{}", encoding="utf-8")
    (folder / "sw.js").write_text(worker, encoding="utf-8")
    (folder / ".env").write_text("secret", encoding="utf-8")


def test_a_snapshot_has_the_files_of_the_folder_and_not_the_hidden_ones_or_the_source_maps(tmp_path: Path) -> None:
    build_page(tmp_path, OLD)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("x", encoding="utf-8")
    snapshot = PageSnapshot.take(tmp_path)
    assert sorted(snapshot.files) == ["assets/index-OLDCSS11.css", "assets/index-OLDOLD11.js", "index.html", "sw.js"]
    assert snapshot.build == "index-OLDOLD11.js" and snapshot.missing() == []
    index = snapshot.get("index.html")
    assert index is not None and index.data == OLD.encode() and index.etag == '"' + hashlib.sha256(OLD.encode()).hexdigest()[:32] + '"'
    assert snapshot.size == sum(len(f.data) for f in snapshot.files.values()) and snapshot.get("nothing") is None
    build_page(tmp_path, NEW)
    assert snapshot.get("index.html") == index, "a snapshot does not change when the folder does"


def test_a_folder_that_is_not_there_is_an_empty_snapshot_with_no_build(tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("neoaprs.web.pagesnapshot.RETRY_SEC", 0.0)
    with caplog.at_level(logging.ERROR, logger="neoaprs.web"):
        snapshot = PageSnapshot.take(tmp_path / "nothing")
    assert snapshot.files == {} and snapshot.build == "" and snapshot.size == 0
    assert "is not whole (no files)" in caplog.text


def test_a_folder_swapped_in_the_middle_of_a_read_is_read_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A build swaps the folder with two renames: index.html of the new build that names a file the read did not get is a page of two builds, and it is read again."""
    (tmp_path / "index.html").write_text(OLD, encoding="utf-8")
    (tmp_path / "assets").mkdir()
    slept: list[float] = []

    def finish_the_build(seconds: float) -> None:
        slept.append(seconds)
        build_page(tmp_path, OLD)

    monkeypatch.setattr("neoaprs.web.pagesnapshot.time.sleep", finish_the_build)
    snapshot = PageSnapshot.take(tmp_path)
    assert len(slept) == 1 and snapshot.missing() == [] and "assets/index-OLDOLD11.js" in snapshot.files


def test_a_page_that_stays_incomplete_is_served_as_it_is_and_the_log_says_so(tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("neoaprs.web.pagesnapshot.RETRY_SEC", 0.0)
    (tmp_path / "index.html").write_text(OLD, encoding="utf-8")
    with caplog.at_level(logging.ERROR, logger="neoaprs.web"):
        snapshot = PageSnapshot.take(tmp_path)
    assert snapshot.missing() == ["assets/index-OLDCSS11.css", "assets/index-OLDOLD11.js"] and "is not whole" in caplog.text


def test_a_folder_bigger_than_a_page_can_be_is_refused(tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("neoaprs.web.pagesnapshot.MAX_BYTES", 10)
    monkeypatch.setattr("neoaprs.web.pagesnapshot.RETRY_SEC", 0.0)
    (tmp_path / "index.html").write_text("0123456789abcdef", encoding="utf-8")
    assert PageSnapshot.take(tmp_path).files == {}


def test_the_built_page_is_small_enough_to_keep_in_memory_and_is_all_there() -> None:
    """The page is read into memory when the daemon starts, so its size is a decision: the shipped one is about 3.4 MB. When it grows past this, serve it from a folder named by the build instead (and say so in docs/daemon.md)."""
    folder = web_server.PAGE_DIR
    snapshot = PageSnapshot.take(folder)
    assert snapshot.size < 16 * 1024 * 1024 < MAX_BYTES, f"the page is {snapshot.size / 1048576:.1f} MB"
    served = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file() and not p.name.endswith(".map")}
    assert set(snapshot.files) == served and snapshot.missing() == [] and snapshot.build.startswith("index-")


async def test_a_page_rebuilt_while_the_daemon_runs_changes_nothing_until_it_is_started_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    page = tmp_path / "page"
    build_page(page, OLD, worker="// old worker")
    monkeypatch.setattr(web_server, "PAGE_DIR", page)
    e = Env(tmp_path / "data", web=True)
    await e.start()
    before = await e.fetch("/")
    old_js = await e.fetch("/assets/index-OLDOLD11.js")
    assert before.code == 200 and before.body == OLD.encode() and old_js.code == 200
    tab = await e.ws()
    assert (await tab.expect("hello"))["page"] == "index-OLDOLD11.js"

    for path in page.rglob("*"):                                                                  # the page is rebuilt (a branch was switched): every file is another
        if path.is_file():
            path.unlink()
    build_page(page, NEW, worker="// new worker")

    assert (await e.fetch("/")).body == OLD.encode() and (await e.fetch("/index.html")).body == OLD.encode()
    assert (await e.fetch("/assets/index-OLDOLD11.js")).body == old_js.body
    assert (await e.fetch("/assets/index-NEWNEW11.js")).code == 404, "a file of the new build is not the daemon's"
    assert (await e.fetch("/sw.js")).body == b"// old worker"
    assert (await e.fetch("/.env")).code == 404 and (await e.fetch("/assets/index-NEWNEW11.js.map")).code == 404
    assert (await (await e.ws()).expect("hello"))["page"] == "index-OLDOLD11.js"
    await e.stop()

    again = Env(tmp_path / "data", web=True)                                                      # started again, it takes the page as it is
    await again.start()
    assert (await again.fetch("/")).body == NEW.encode() and (await again.fetch("/assets/index-NEWNEW11.js")).code == 200
    assert (await again.fetch("/assets/index-OLDOLD11.js")).code == 404
    assert (await (await again.ws()).expect("hello"))["page"] == "index-NEWNEW11.js"


async def test_the_snapshot_is_served_with_the_headers_of_a_file_from_the_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    page = tmp_path / "page"
    build_page(page, OLD)
    monkeypatch.setattr(web_server, "PAGE_DIR", page)
    e = Env(tmp_path / "data", web=True)
    await e.start()
    shell = await e.fetch("/")
    assert shell.headers["Etag"] == '"' + hashlib.sha256(OLD.encode()).hexdigest()[:32] + '"'
    assert shell.headers["Cache-Control"] == "no-cache" and shell.headers["Accept-Ranges"] == "bytes" and shell.headers["Last-Modified"]
    assert shell.headers["Content-Type"].startswith("text/html") and shell.headers["X-Content-Type-Options"] == "nosniff"
    assert (await e.fetch("/", headers={"If-None-Match": shell.headers["Etag"]})).code == 304
    assert (await e.fetch("/", headers={"If-None-Match": '"another"'})).code == 200
    head = await e.fetch("/", method="HEAD")
    assert head.code == 200 and head.body == b"" and head.headers["Content-Length"] == str(len(OLD)) and head.headers["Etag"] == shell.headers["Etag"]
    asset = await e.fetch("/assets/index-OLDOLD11.js")
    assert asset.headers["Cache-Control"] == "public, max-age=31536000, immutable" and asset.headers["Content-Type"].startswith("text/javascript")
    part = await e.fetch("/assets/index-OLDOLD11.js", headers={"Range": "bytes=8-10"})
    assert part.code == 206 and part.body == b"log" and part.headers["Content-Range"] == f"bytes 8-10/{len(asset.body)}"
    assert (await e.fetch("/assets/index-OLDOLD11.js", headers={"Range": "bytes=999-"})).code == 416
    for path in ("/assets/", "/assets", "/nothing", "/../neoaprs/__init__.py", "/%2e%2e/neoaprs/__init__.py"):
        assert (await e.fetch(path)).code in (403, 404), path
    assert (await e.fetch("/", headers={"Host": "evil.example"})).code == 403
