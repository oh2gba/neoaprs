"""The Send logs endpoint of the project's server (server/neo/support/send.php) under PHP's own web server on the loopback, with the mail stubbed (a function `support_send_mail` defined before the page runs, which writes the mail to a file): a good bundle
is stored with its json and answered with a reference and one mail goes; what is not a bundle, a body over the limit, a method other than POST and a sender over the rate limit are refused; the call, the version, the platform and the note are cleaned,
and neither the call nor the note can reach a header of the mail or the name of a file; the address of the sender is written nowhere. Skipped without `php`."""
import json
import os
import re
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from neoaprs.cli.supportmake import make_bundle
from neoaprs.updatefetch import multipart
from tests.support.clock import FixedClock
from tests.support.ptyline import posix_only
from tests.support.supportdata import fake_folder

pytestmark = posix_only

ROOT = Path(__file__).resolve().parent.parent
PHP = shutil.which("php")
REF = re.compile(r"^NEO-\d{8}-\d{4}-[0-9A-F]{4}$")
STUB = """<?php
// stands in for mail(): the subject and the body, with the headers the real one adds, go to a file
function support_send_mail(string $subject, string $body): bool
{
    if (getenv('MAIL_FAILS')) return false;
    if (preg_match('/[\\r\\n]/', $subject)) return false;
    file_put_contents(getenv('MAIL_OUT'), json_encode(['subject' => $subject, 'body' => $body]) . "\\n", FILE_APPEND);
    return true;
}
"""


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class Endpoint:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.site = folder / "site"
        self.stored = folder / "private" / "support"
        self.mails = folder / "mails.jsonl"
        self.process: subprocess.Popen[bytes] | None = None
        self.port = free_port()

    def start(self, **env: str) -> None:
        shutil.copytree(ROOT / "server" / "neo" / "support", self.site / "support")
        (self.folder / "stub.php").write_text(STUB, encoding="utf-8")
        environment = {"PATH": os.environ["PATH"], "SUPPORT_DIR": str(self.stored), "MAIL_OUT": str(self.mails), **env}
        assert PHP is not None
        for _ in range(3):
            self.process = subprocess.Popen([PHP, "-S", f"127.0.0.1:{self.port}", "-t", str(self.site), "-d", f"auto_prepend_file={self.folder / 'stub.php'}", "-d", "upload_max_filesize=22M", "-d", "post_max_size=24M"],
                                            env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and self.process.poll() is None:
                try:
                    socket.create_connection(("127.0.0.1", self.port), timeout=0.2).close()
                    return
                except OSError:
                    time.sleep(0.05)
            if self.process.poll() is None:
                break
            self.port = free_port()
        raise AssertionError("php did not start")

    def stop(self) -> None:
        if self.process is not None:
            self.process.terminate()
            self.process.wait(10)

    def post(self, fields: dict[str, str] | None = None, files: dict[str, tuple[str, bytes]] | None = None, method: str = "POST", raw: bytes | None = None) -> tuple[int, dict[str, object]]:
        kind, body = multipart(fields or {}, files or {})
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}/support/send.php", data=body if raw is None else raw, method=method, headers={"Content-Type": kind})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                assert response.headers["Content-Type"] == "application/json; charset=utf-8" and response.headers["Cache-Control"] == "no-store"
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def mail_sent(self) -> list[dict[str, str]]:
        return [json.loads(line) for line in self.mails.read_text(encoding="utf-8").splitlines()] if self.mails.exists() else []


@pytest.fixture
def endpoint(tmp_path: Path) -> Iterator[Endpoint]:
    if PHP is None:
        pytest.skip("needs php")
    served = Endpoint(tmp_path / "server")
    served.folder.mkdir()
    yield served
    served.stop()


@pytest.fixture(scope="module")
def bundle(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    """A real bundle of a fake data folder, as the daemon makes it."""
    base = tmp_path_factory.mktemp("bundle")
    made = make_bundle(fake_folder(base), base / "out", now=FixedClock(), journal=lambda: None)
    return made.path.read_bytes()


def good(bundle: bytes, **over: str) -> dict[str, str]:
    return {"note": "It stopped beaconing.", "call": "OH2GBA", "version": "0.16.1", "platform": "linux", **over}


def zipped(names: list[str]) -> bytes:
    import io
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name in names:
            z.writestr(name, "x")
    return buffer.getvalue()


def test_a_good_bundle_is_stored_with_its_json_answered_with_a_reference_and_mailed_once_without_the_file(endpoint: Endpoint, bundle: bytes) -> None:
    endpoint.start()
    code, answer = endpoint.post(good(bundle), {"bundle": ("neoaprs-support-OH2GBA.zip", bundle)})
    ref = str(answer["ref"])
    assert code == 200 and answer == {"ok": True, "ref": ref} and REF.match(ref)
    assert (endpoint.stored / f"{ref}.zip").read_bytes() == bundle
    meta = json.loads((endpoint.stored / f"{ref}.json").read_text(encoding="utf-8"))
    assert meta["ref"] == ref and meta["call"] == "OH2GBA" and meta["version"] == "0.16.1" and meta["platform"] == "linux" and meta["note"] == "It stopped beaconing."
    assert meta["size"] == len(bundle) and re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$", meta["time"])
    assert sorted(p.name for p in endpoint.stored.iterdir() if p.name.startswith("NEO-")) == [f"{ref}.json", f"{ref}.zip"], "no half-written file is left"
    (mail,) = endpoint.mail_sent()
    assert mail["subject"] == f"NeoAPRS logs {ref} from OH2GBA"
    for line in (f"Reference: {ref}", "Call:      OH2GBA", "Version:   0.16.1", "Platform:  linux", f"Size:      {len(bundle) // 1024} KB", "It stopped beaconing."):
        assert line in mail["body"]
    assert "PK" not in mail["body"], "the zip stays on the server"
    assert (endpoint.stored / ".htaccess").read_text(encoding="utf-8") == "Require all denied\n"


def test_two_files_have_two_references(endpoint: Endpoint, bundle: bytes) -> None:
    endpoint.start()
    refs = {str(endpoint.post(good(bundle), {"bundle": ("a.zip", bundle)})[1]["ref"]) for _ in range(3)}
    assert len(refs) == 3 and len(list(endpoint.stored.glob("NEO-*.zip"))) == 3 and len(endpoint.mail_sent()) == 3


@pytest.mark.parametrize("content", [b"", b"just text, no zip", b"PK\x03\x04" + b"\x00" * 100, b"PK\x03\x04" + b"junk" * 5000 + b"PK\x05\x06" + b"\x00" * 18])
def test_what_is_not_a_zip_is_refused_and_nothing_is_kept_or_mailed(endpoint: Endpoint, content: bytes) -> None:
    endpoint.start()
    code, answer = endpoint.post({"note": "x"}, {"bundle": ("a.zip", content)})
    assert code == 400 and answer["ok"] is False and answer["reason"] in ("not_a_bundle", "bad_request")
    assert not list(endpoint.stored.glob("NEO-*")) and endpoint.mail_sent() == []


@pytest.mark.parametrize("names", [["notes.txt"], ["summary.txt", "../evil.php"], ["summary.txt", "evil.php"], ["summary.txt", "logs/../x.txt"], ["summary.txt", "/etc/passwd"], ["README.txt", "settings.json"], ["summary.txt", "logs/a/b.txt"]])
def test_a_zip_whose_members_are_not_those_of_a_bundle_is_refused(endpoint: Endpoint, names: list[str]) -> None:
    endpoint.start()
    code, answer = endpoint.post(good(b""), {"bundle": ("a.zip", zipped(names))})
    assert (code, answer) == (400, {"ok": False, "reason": "not_a_bundle"})
    assert not list(endpoint.stored.glob("NEO-*"))


def test_the_members_of_every_part_of_a_bundle_are_accepted(endpoint: Endpoint) -> None:
    endpoint.start()
    names = ["README.txt", "summary.txt", "settings.json", "state.json", "doctor.txt", "database.txt", "packets.txt", "page.json", "page-errors.json", "logs/neoaprs.log", "logs/neoaprs.log.1", "logs/neoaprs-app.log", "logs/journal.txt", "packets.error.txt"]
    assert endpoint.post(good(b""), {"bundle": ("a.zip", zipped(names))})[0] == 200


def test_no_file_in_the_form_is_a_bad_request(endpoint: Endpoint) -> None:
    endpoint.start()
    assert endpoint.post({"note": "x"}) == (400, {"ok": False, "reason": "bad_request"})
    assert endpoint.post({"bundle": "a text, not a file"}) == (400, {"ok": False, "reason": "bad_request"})


def test_only_a_post_is_answered(endpoint: Endpoint) -> None:
    endpoint.start()
    for method in ("GET", "PUT", "DELETE"):
        assert endpoint.post(method=method, raw=b"x") == (405, {"ok": False, "reason": "method"}), method
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(f"http://127.0.0.1:{endpoint.port}/support/send.php", timeout=10)
    assert e.value.code == 405 and e.value.headers["Allow"] == "POST"


def test_a_body_over_20_megabytes_is_refused_before_it_is_read_and_one_under_it_is_taken(endpoint: Endpoint, bundle: bytes) -> None:
    endpoint.start()
    big = zipped(["summary.txt"]) + b"\x00" * (21 * 1024 * 1024)
    assert endpoint.post(good(bundle), {"bundle": ("a.zip", big)}) == (413, {"ok": False, "reason": "too_large"})
    assert not list(endpoint.stored.glob("NEO-*")) and endpoint.mail_sent() == []
    fits = zipped(["summary.txt"]) + b"\x00" * (19 * 1024 * 1024)       # (a zip with a long tail before its end record is the end record's business, not the size's)
    code, answer = endpoint.post(good(bundle), {"bundle": ("a.zip", fits)})
    assert code in (200, 400), "not refused for its size"
    assert answer.get("reason") != "too_large"


def test_a_sender_is_held_to_five_files_an_hour_and_the_hash_of_the_address_is_all_that_is_kept(endpoint: Endpoint, bundle: bytes) -> None:
    endpoint.start()
    answers = [endpoint.post(good(bundle), {"bundle": ("a.zip", bundle)}) for _ in range(7)]
    assert [code for code, _ in answers] == [200] * 5 + [429] * 2 and answers[5][1] == {"ok": False, "reason": "rate"}
    assert len(list(endpoint.stored.glob("NEO-*.zip"))) == 5 and len(endpoint.mail_sent()) == 5
    kept = "".join(p.read_text(encoding="utf-8", errors="replace") for p in endpoint.stored.iterdir() if p.is_file())
    assert "127.0.0.1" not in kept, "the address is written nowhere"
    rates = json.loads((endpoint.stored / "rate.json").read_text(encoding="utf-8"))
    assert len(rates) == 1 and all(re.fullmatch(r"[0-9a-f]{16}", key) for key in rates)


def test_the_hour_gives_the_share_back(endpoint: Endpoint, bundle: bytes) -> None:
    endpoint.start()
    for _ in range(5):
        assert endpoint.post(good(bundle), {"bundle": ("a.zip", bundle)})[0] == 200
    assert endpoint.post(good(bundle), {"bundle": ("a.zip", bundle)})[0] == 429
    path = endpoint.stored / "rate.json"
    old = int(time.time()) - 3700
    path.write_text(json.dumps({key: [old] * 5 for key in json.loads(path.read_text(encoding="utf-8"))}), encoding="utf-8")
    assert endpoint.post(good(bundle), {"bundle": ("a.zip", bundle)})[0] == 200


def test_the_call_the_version_and_the_platform_are_cleaned_and_cannot_make_a_header_or_a_name(endpoint: Endpoint, bundle: bytes) -> None:
    endpoint.start()
    code, answer = endpoint.post(good(bundle, call="OH2GBA\r\nBcc: evil@example.org\r\nSubject: x", version="1.0\r\nBcc: a@b.c" + "9" * 40, platform="linux/../../etc/passwd\nTo: x"),
                                 {"bundle": ("../../evil.php", bundle)})
    ref = str(answer["ref"])
    assert code == 200
    meta = json.loads((endpoint.stored / f"{ref}.json").read_text(encoding="utf-8"))
    assert meta["call"] == "OH2GBABccevi"
    assert re.fullmatch(r"[0-9A-Za-z._+-]{0,20}", meta["version"]) and len(meta["version"]) == 20
    assert re.fullmatch(r"[0-9A-Za-z._-]{0,40}", meta["platform"])
    (mail,) = endpoint.mail_sent()
    assert "\n" not in mail["subject"] and "\r" not in mail["subject"] and mail["subject"] == f"NeoAPRS logs {ref} from {meta['call']}"
    assert sorted(p.name for p in endpoint.stored.rglob("*") if p.is_file() and p.name.startswith("NEO-")) == [f"{ref}.json", f"{ref}.zip"]
    assert not list(endpoint.folder.rglob("evil.php"))
    assert endpoint.post(good(bundle, call="\r\n!!"), {"bundle": ("a.zip", bundle)})[0] == 200
    assert re.fullmatch(r"NeoAPRS logs NEO-\d{8}-\d{4}-[0-9A-F]{4}", endpoint.mail_sent()[-1]["subject"]), "no call is no 'from'"


def test_the_note_is_text_cut_to_2000_characters_and_stays_in_the_body_of_the_mail(endpoint: Endpoint, bundle: bytes) -> None:
    endpoint.start()
    note = "Subject: hijack\r\nBcc: evil@example.org\r\n\r\nline two \u00e4\u3042\U0001f4fb\x00\x07\x1b[31m red\n" + "y" * 3000
    code, answer = endpoint.post(good(bundle, note=note), {"bundle": ("a.zip", bundle)})
    assert code == 200
    kept = json.loads((endpoint.stored / f"{answer['ref']}.json").read_text(encoding="utf-8"))["note"]
    assert len(kept) == 2000 and kept.startswith("Subject: hijack\nBcc: evil@example.org\n\nline two \u00e4\u3042\U0001f4fb[31m red\n") and not re.search(r"[\x00-\x08\x0b-\x1f\x7f]", kept)
    (mail,) = endpoint.mail_sent()
    assert mail["subject"].startswith("NeoAPRS logs NEO-") and "hijack" not in mail["subject"] and "evil" not in mail["subject"]
    assert kept in mail["body"]


def test_a_note_that_is_not_utf8_keeps_its_ascii_and_a_missing_one_is_empty(endpoint: Endpoint, bundle: bytes) -> None:
    endpoint.start()
    boundary = "xxboundaryxx"
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="note"\r\n\r\n'.encode() + b"plain \xff\xfe text\r\n"
            + f'--{boundary}\r\nContent-Disposition: form-data; name="bundle"; filename="a.zip"\r\n\r\n'.encode() + bundle + f"\r\n--{boundary}--\r\n".encode())
    request = urllib.request.Request(f"http://127.0.0.1:{endpoint.port}/support/send.php", data=body, method="POST", headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        ref = json.loads(response.read())["ref"]
    assert json.loads((endpoint.stored / f"{ref}.json").read_text(encoding="utf-8"))["note"] == "plain  text"
    ref2 = str(endpoint.post({"call": "OH2GBA"}, {"bundle": ("a.zip", bundle)})[1]["ref"])
    assert json.loads((endpoint.stored / f"{ref2}.json").read_text(encoding="utf-8"))["note"] == ""
    assert "(none)" in endpoint.mail_sent()[-1]["body"]


def test_a_failed_mail_is_logged_and_the_upload_still_succeeds(endpoint: Endpoint, bundle: bytes) -> None:
    endpoint.start(MAIL_FAILS="1")
    code, answer = endpoint.post(good(bundle), {"bundle": ("a.zip", bundle)})
    assert code == 200 and answer["ok"] is True and (endpoint.stored / f"{answer['ref']}.zip").is_file()
    assert endpoint.mail_sent() == []
    line = (endpoint.stored.parent / "logs" / "support.log").read_text(encoding="utf-8")
    assert f"the mail for {answer['ref']} was not sent" in line and "127.0.0.1" not in line and "stopped" not in line


def test_the_files_are_kept_where_the_web_is_refused_them(endpoint: Endpoint) -> None:
    deny = "Require all denied"
    assert deny in (ROOT / "server" / "neo" / "private" / ".htaccess").read_text(encoding="utf-8")
    site = (ROOT / "server" / "neo" / ".htaccess").read_text(encoding="utf-8")
    assert r"RewriteRule ^private(/|$) - [F,L]" in site and r'<FilesMatch "^\.user\.ini$">' in site
    ini = (ROOT / "server" / "neo" / "support" / ".user.ini").read_text(encoding="utf-8")
    assert "upload_max_filesize = 20M" in ini and "post_max_size = 21M" in ini
    default = "private/support"
    assert default in (ROOT / "server" / "neo" / "support" / "send.php").read_text(encoding="utf-8")
