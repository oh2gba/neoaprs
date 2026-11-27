"""The gate's links stage (scripts/linkcheck.py): which links it collects, and each outcome against
a stand-in server on the loopback: found, found only by GET, not found, gone, refusing robots, too
slow, no such host, no network, and an allowed link."""

import http.server
import socket
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.support.httpthread import serve
from tests.test_scripts import load_script

linkcheck = load_script("linkcheck.py")
ROOT = Path(__file__).resolve().parent.parent


class Handler(http.server.BaseHTTPRequestHandler):
    release = threading.Event()

    def _answer(self, body: bool) -> None:
        path = self.path
        if path == "/no-head" and self.command == "HEAD":
            self.send_response(405)
        elif path in ("/", "/no-head"):
            self.send_response(200)
        elif path == "/gone":
            self.send_response(410)
        elif path == "/H%C3%A4meenlinna":
            self.send_response(200)
        elif path == "/loop":
            self.send_response(302)
            self.send_header("Location", "/loop")
        elif path == "/robots-no":
            self.send_response(403)
        elif path == "/slow":
            Handler.release.wait(10)
            self.send_response(200)
        else:
            self.send_response(404)
        self.send_header("Content-Length", "2" if body else "0")
        self.end_headers()
        if body:
            self.wfile.write(b"ok")

    def do_HEAD(self) -> None:  # noqa: N802 (the name the library calls)
        self._answer(False)

    def do_GET(self) -> None:  # noqa: N802
        self._answer(True)

    def log_message(self, *_args: object) -> None:
        pass


@pytest.fixture
def site() -> Iterator[str]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    serve(server)
    yield f"http://127.0.0.1:{server.server_address[1]}"
    Handler.release.set()
    server.shutdown()
    server.server_close()
    Handler.release.clear()


def test_a_link_that_answers_is_ok_and_one_found_only_by_get_too(site: str) -> None:
    assert linkcheck.check(f"{site}/", 5).word == "ok"
    assert linkcheck.check(f"{site}/no-head", 5).word == "ok"


def test_not_found_and_gone_fail(site: str) -> None:
    for path, status in (("/missing", 404), ("/gone", 410)):
        outcome = linkcheck.check(f"{site}{path}", 5)
        assert (outcome.fails, outcome.word) == (True, f"not found ({status})")


def test_refusing_robots_and_slowness_are_reported_and_do_not_fail(site: str) -> None:
    refused = linkcheck.check(f"{site}/robots-no", 5)
    assert (refused.fails, refused.reported, refused.word) == (False, True, "answered 403 (refuses robots)")
    slow = linkcheck.check(f"{site}/slow", 0.5)
    assert (slow.fails, slow.reported) == (False, True) and "no answer" in slow.word


def test_a_host_that_does_not_exist_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_such_name(host: object, *_args: object, **_kwargs: object) -> object:
        raise socket.gaierror(socket.EAI_NONAME, f"{host}: no such name")

    monkeypatch.setattr(socket, "getaddrinfo", no_such_name)  # (as the name server answers)
    outcome = linkcheck.check("https://no-such-host.neoaprs-test.org/", 5)
    assert (outcome.fails, outcome.word) == (True, "no such host")


def test_the_run_fails_only_for_a_failing_link_that_is_not_allowed(site: str) -> None:
    said: list[str] = []
    links = {f"{site}/": ["README.md"], f"{site}/missing": ["site/index.html"], f"{site}/robots-no": ["a.md"]}
    assert linkcheck.run(links, {}, lambda url: linkcheck.check(url, 5), lambda: True, said.append) == 1
    assert any(line.startswith("FAIL") and "/missing" in line and "site/index.html" in line for line in said)
    assert any(line.startswith("reported") and "/robots-no" in line for line in said)
    assert said[-1] == "linkcheck: 3 links, 1 ok, 1 failed"
    said.clear()
    allow = {f"{site}/missing": "answers 404 to robots, opens in a browser"}
    assert linkcheck.run(links, allow, lambda url: linkcheck.check(url, 5), lambda: True, said.append) == 0
    assert any(line.startswith("allowed") and "opens in a browser" in line for line in said)


def test_with_no_network_it_says_so_and_passes() -> None:
    said: list[str] = []

    def no_lookup(_host: str) -> object:
        raise OSError("no network")

    assert (
        linkcheck.run(
            {"https://x.org/": ["README.md"]}, {}, out=said.append, is_online=lambda: linkcheck.online(no_lookup)
        )
        == 0
    )
    assert said == ["linkcheck: no network (github.com cannot be looked up): 1 links not asked"]


def test_it_collects_the_links_offered_and_not_the_addresses_named(tmp_path: Path) -> None:
    (tmp_path / "ui" / "src" / "lib").mkdir(parents=True)
    (tmp_path / "ui" / "src" / "lib" / "links.ts").write_text('export const A = "https://a.org/";\n')
    (tmp_path / "docs" / "manual").mkdir(parents=True)
    (tmp_path / "docs" / "manual" / "x.md").write_text(
        "See [b](https://b.org/x). The service asks `https://api.c.org/v1/lat/` and http://192.168.1.20:7303.\n"
        "```\ncurl https://d.org/\n```\nhttp://localhost:7303 and https://www.example.com/\n"
    )
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "index.html").write_text(
        '<a href="https://e.org/">e</a> <code>https://f.org/</code> <img src="https://g.org/i.png">'
    )
    (tmp_path / "README.md").write_text("Download: <https://h.org/file.exe>.\n")
    assert linkcheck.collect(tmp_path) == {
        "https://a.org/": ["ui/src/lib/links.ts"],
        "https://b.org/x": ["docs/manual/x.md"],
        "https://e.org/": ["site/index.html"],
        "https://g.org/i.png": ["site/index.html"],
        "https://h.org/file.exe": ["README.md"],
    }


def test_every_outside_link_of_the_page_is_collected() -> None:
    module = (ROOT / "ui" / "src" / "lib" / "links.ts").read_text(encoding="utf-8")
    collected = linkcheck.collect()
    for url in linkcheck.links_in(module):
        assert "ui/src/lib/links.ts" in collected[url]
    assert "https://aisstream.io/account" in collected


def test_the_allow_list_gives_each_link_its_reason(tmp_path: Path) -> None:
    listed = tmp_path / "allowed.txt"
    listed.write_text("# a comment\n\nhttps://x.org/ refuses robots with 403\n")
    assert linkcheck.allowed(listed) == {"https://x.org/": "refuses robots with 403"}
    listed.write_text("https://x.org/\n")
    with pytest.raises(SystemExit):
        linkcheck.allowed(listed)
    assert isinstance(linkcheck.allowed(), dict)


def test_a_link_with_letters_outside_ascii_is_asked_encoded(site: str) -> None:
    assert linkcheck.check(site + "/Hämeenlinna", 5.0).word == "ok"


def test_a_link_with_a_control_character_is_asked_encoded_and_one_that_cannot_be_asked_is_reported(site: str) -> None:
    assert linkcheck.check(site + "/a\x01b c", 5.0).word == "not found (404)"
    broken = "http://127.0.0.1:99999/x"
    outcome = linkcheck.check(broken, 5.0)
    assert outcome.reported and not outcome.fails and outcome.word.startswith("not reached")
    said: list[str] = []
    assert linkcheck.run({broken: ["x.md"], site + "/": ["y.md"]}, {}, is_online=lambda: True, out=said.append) == 0


def test_a_redirect_loop_is_not_ok(site: str) -> None:
    outcome = linkcheck.check(site + "/loop", 5.0)
    assert outcome.reported and outcome.word.startswith("redirects in a loop")


def test_every_address_the_site_offers_is_collected_meta_tags_and_structured_data_too(tmp_path: Path) -> None:
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "index.html").write_text(
        '<meta property="og:image" content="https://a.org/og.png">'
        '<script type="application/ld+json">{"url": "https://b.org/", "logo": "https://c.org/l.png"}</script>'
        '<pre>https://d.org/</pre><!-- https://e.org/ --><svg xmlns="http://www.w3.org/2000/svg"></svg>'
    )
    (tmp_path / "site" / "sitemap.xml").write_text(
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://f.org/</loc></url></urlset>'
    )
    (tmp_path / "site" / "site.js").write_text('fetch("https://g.org/api");\n')
    assert sorted(linkcheck.collect(tmp_path)) == [
        "https://a.org/og.png",
        "https://b.org/",
        "https://c.org/l.png",
        "https://f.org/",
        "https://g.org/api",
    ]
