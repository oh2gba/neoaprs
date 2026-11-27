"""The satellites endpoint of the project's server (server/neo/api/v1/satellites.php) under PHP's web
server on the loopback, with a stand-in for CelesTrak: one compressed download a day, none after a
refusal for two hours, the old file served meanwhile, and the list merged with the elements.
"""

import gzip
import http.server
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.support.files import fixture_bytes
from tests.support.httpthread import serve
from tests.support.ptyline import posix_only

pytestmark = posix_only

ROOT = Path(__file__).resolve().parent.parent
PHP = shutil.which("php")
DAY = 86400


class Celestrak(http.server.ThreadingHTTPServer):
    """Answers every GET with `status` and the fixture's CSV, gzipped; keeps each request's headers."""

    def __init__(self) -> None:
        self.status = 200
        self.body = fixture_bytes("satellites/amateur.csv")
        self.asked: list[tuple[str, dict[str, str]]] = []
        super().__init__(("127.0.0.1", 0), _Handler)


class _Handler(http.server.BaseHTTPRequestHandler):
    server: Celestrak

    def do_GET(self) -> None:
        self.server.asked.append((self.path, {k.lower(): v for k, v in self.headers.items()}))
        body = gzip.compress(self.server.body) if self.server.status == 200 else b"no"
        self.send_response(self.server.status)
        if self.server.status == 200:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        pass


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class Site:
    def __init__(self, folder: Path, upstream: str) -> None:
        self.site = folder
        self.store = folder / "private" / "satellites"
        (folder / "api" / "v1").mkdir(parents=True)
        (folder / "private").mkdir()
        shutil.copy(ROOT / "server/neo/api/v1/satellites.php", folder / "api/v1/satellites.php")
        shutil.copy(ROOT / "server/neo/private/satellites-list.json", folder / "private/satellites-list.json")
        self.port = free_port()
        assert PHP is not None
        self.process = subprocess.Popen(
            [PHP, "-S", f"127.0.0.1:{self.port}", "-t", str(folder)],
            env={"PATH": os.environ["PATH"], "CELESTRAK_URL": upstream},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 10
        while True:
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.2).close()
                break
            except OSError:
                assert time.monotonic() < deadline and self.process.poll() is None, "php did not start"
                time.sleep(0.05)

    def get(self, method: str = "GET") -> tuple[int, dict[str, Any]]:
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/v1/satellites.php", method=method)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                assert response.headers["Content-Type"] == "application/json; charset=utf-8"
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def age(self, name: str, sec: int) -> None:
        """Make a stored file as old as `sec` seconds."""
        when = time.time() - sec
        os.utime(self.store / name, (when, when))

    def stop(self) -> None:
        self.process.terminate()
        self.process.wait(10)


@pytest.fixture
def upstream() -> Iterator[Celestrak]:
    server = Celestrak()
    serve(server)
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def site(tmp_path: Path, upstream: Celestrak) -> Iterator[Site]:
    if PHP is None:
        pytest.skip("needs php")
    made = Site(tmp_path / "neo", f"http://127.0.0.1:{upstream.server_address[1]}/gp.php?GROUP=amateur&FORMAT=csv")
    yield made
    made.stop()


def test_the_first_request_downloads_the_elements_once_compressed_and_merges_them_with_the_list(
    site: Site, upstream: Celestrak
) -> None:
    code, answer = site.get()
    assert code == 200 and answer["v"] == 1 and answer["elements_at"] is not None
    assert len(upstream.asked) == 1 and upstream.asked[0][1]["accept-encoding"] == "gzip"
    by_id = {one["id"]: one for one in answer["satellites"]}
    iss = by_id[25544]
    assert iss["name"] == "ISS" and iss["elements"]["EPOCH"] == "2026-11-27T03:17:57.838272"
    assert iss["downlink"] == [{"mhz": 437.825, "sure": True}, {"mhz": 145.825, "sure": False}]
    assert iss["path"] == {"value": "ARISS", "sure": False} and iss["mode"] == {"value": "afsk1200", "sure": True}
    # a catalogue number above 99999, which TLE lines cannot hold
    assert by_id[101098]["elements"]["NORAD_CAT_ID"] == "101098"
    assert "source" not in iss and len(answer["satellites"]) == 10
    assert all(one["elements"] is not None for one in answer["satellites"])


def test_within_a_day_nothing_is_asked_again_and_after_it_one_download_is(site: Site, upstream: Celestrak) -> None:
    site.get()
    site.get()
    assert len(upstream.asked) == 1
    site.age("elements.csv", DAY + 60)
    code, _ = site.get()
    assert code == 200 and len(upstream.asked) == 2


def test_a_refusal_keeps_the_old_file_and_nothing_is_asked_for_two_hours(site: Site, upstream: Celestrak) -> None:
    _, first = site.get()
    site.age("elements.csv", DAY + 60)
    upstream.status = 403
    code, answer = site.get()
    assert code == 200 and answer["satellites"] == first["satellites"] and len(upstream.asked) == 2
    site.get()
    assert len(upstream.asked) == 2, "no question within two hours of a refusal"
    site.age("failed", 2 * 3600 + 60)
    upstream.status = 200
    site.get()
    assert len(upstream.asked) == 3


def test_with_no_download_yet_the_list_is_served_without_elements(site: Site, upstream: Celestrak) -> None:
    upstream.status = 503
    code, answer = site.get()
    assert code == 200 and answer["elements_at"] is None
    assert all(one["elements"] is None for one in answer["satellites"])


def test_a_changed_list_is_merged_at_once_without_asking_celestrak(site: Site, upstream: Celestrak) -> None:
    site.get()
    listed = site.site / "private" / "satellites-list.json"
    data = json.loads(listed.read_text(encoding="utf-8"))
    data["satellites"] = data["satellites"][:1]
    listed.write_text(json.dumps(data), encoding="utf-8")
    site.age("satellites.json", 60)
    _, answer = site.get()
    assert [one["id"] for one in answer["satellites"]] == [25544] and len(upstream.asked) == 1


def test_only_a_get_is_answered(site: Site, upstream: Celestrak) -> None:
    code, answer = site.get("POST")
    assert code == 405 and answer == {"ok": False, "reason": "method"} and upstream.asked == []


def _good_csv() -> bytes:
    return fixture_bytes("satellites/amateur.csv")


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"OBJECT_NAME,OBJECT_ID,EPOCH,NORAD_CAT_ID\n",
        b"\n".join(_good_csv().splitlines()[:3]) + b"\n",  # the header and two rows
        _good_csv()[: len(_good_csv()) // 2],  # cut off in a line
        b"<html>not the csv</html>",
    ],
    ids=["empty", "header-only", "two-rows", "truncated", "not-csv"],
)
def test_a_partial_empty_truncated_or_malformed_download_never_replaces_the_good_elements(
    site: Site, upstream: Celestrak, body: bytes
) -> None:
    _, first = site.get()
    site.age("elements.csv", DAY + 60)
    upstream.body = body
    code, answer = site.get()
    assert code == 200 and len(upstream.asked) == 2
    assert answer["satellites"] == first["satellites"], "the good elements are kept"
    assert (site.store / "failed").is_file()


def test_a_download_that_lost_listed_satellites_is_not_taken(site: Site, upstream: Celestrak) -> None:
    _, first = site.get()
    site.age("elements.csv", DAY + 60)
    lines = _good_csv().splitlines()
    gone = [b",25544," in line or b",101098," in line for line in lines]
    upstream.body = b"\n".join(line for line, out in zip(lines, gone, strict=True) if not out) + b"\n"
    assert sum(gone) == 2
    _, answer = site.get()
    assert answer["satellites"] == first["satellites"]


def test_failures_in_a_row_wait_two_hours_then_six_then_a_day_and_a_good_download_ends_it(
    site: Site, upstream: Celestrak
) -> None:
    site.get()
    site.age("elements.csv", DAY + 60)
    upstream.status = 404
    site.get()
    for waited in (2 * 3600 + 60, 6 * 3600 + 60):
        asked = len(upstream.asked)
        site.age("failed", waited - 3600)
        site.get()
        assert len(upstream.asked) == asked, f"not asked again within {waited - 60} s"
        site.age("failed", waited)
        site.get()
        assert len(upstream.asked) == asked + 1
    asked = len(upstream.asked)
    site.age("failed", 6 * 3600 + 60)
    site.get()
    assert len(upstream.asked) == asked, "after three failures, a day"
    site.age("failed", DAY + 60)
    upstream.status = 200
    site.get()
    assert len(upstream.asked) == asked + 1 and not (site.store / "failed").exists()
