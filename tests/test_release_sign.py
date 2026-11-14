"""The step sign of scripts/release and its --verify, on the made-up repository of tests/test_release_script.py (a fake `gh`, a fake `bws` that hands out a key the test made, whose public half the clone's
neoaprs/updateasset.py carries): the release stays a draft until SHA256SUMS is signed; the key is read by bws into memory and is never printed, logged or written to a file; a key that is not the program's, a
bws that cannot read it and a list that is not one sign nothing; a draft signed already is only published; a published release is never signed after the fact; --verify checks a published release and changes
nothing."""
import base64
import hashlib
import http.server
import secrets
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from neoaprs.updateasset import signed_message, sign
from tests.support.ptyline import posix_only
from tests.test_release_script import ASSETS, SIGNED, SUMS, TAG, VERSION, Downloads, Rig, assert_released, make_executable
from tests.support.httpthread import serve

pytestmark = posix_only

@pytest.fixture
def rig(tmp_path: Path, downloads: str) -> Rig:
    return Rig(tmp_path, downloads)


@pytest.fixture
def downloads() -> Iterator[str]:
    Downloads.missing = set()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Downloads)
    serve(server)
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def state(rig: Rig) -> dict[str, object]:
    return rig.load_state()["release"]  # type: ignore[no-any-return]


def files_holding(folder: Path, text: bytes) -> list[str]:
    return [str(p) for p in folder.rglob("*") if p.is_file() and text in p.read_bytes()]


def test_the_signature_is_made_with_the_key_bws_reads_and_the_secret_is_never_shown_or_written(rig: Rig) -> None:
    done = rig.release()
    assert done.returncode == 0, done.stdout + done.stderr
    secret = base64.b64encode(rig.seed)
    assert secret.decode() not in done.stdout + done.stderr and secret.decode() not in rig.log.read_text(encoding="utf-8")
    assert files_holding(rig.work, secret) == [] and files_holding(rig.tmp / "home", secret) == []
    assert files_holding(rig.tmp, secret) == [str(rig.seed_file)], "only the fake bws's own store holds it"
    bws = [c for c in rig.calls() if c.startswith("bws ")]
    assert bws == [f"bws secret get {rig.env['NEOAPRS_SIGNING_SECRET_ID']} --output json --server-url https://vault.bitwarden.invalid"]
    release = state(rig)
    assert release["draft"] is False and release["assets"] == SIGNED
    signature = base64.b64decode(release["files"]["SHA256SUMS.sig"])  # type: ignore[index]
    Ed25519PrivateKey.from_private_bytes(rig.seed).public_key().verify(signature, signed_message(SUMS.encode(), VERSION))
    assert "SHA256SUMS of v0.9.1 is signed" in done.stdout and "SHA256SUMS.sig holds with the program's public key" in done.stdout
    calls = rig.kinds()
    assert calls.index("bws") < calls.index("upload") < calls.index("edit"), "published only once signed"
    assert_released(rig)


def test_bws_alone_is_given_the_access_token_and_the_secret_id(rig: Rig) -> None:
    """git (and scripts/check, the hooks and deploy.sh the script starts the same way), gh and bws each write down whether they see the two; a git or gh that saw them could read the key with bws."""
    seen = rig.tmp / "seen.log"
    for program in ("git", "gh", "bws"):
        real = rig.bin / f"real-{program}"
        if (rig.bin / program).exists():
            (rig.bin / program).rename(real)
        else:
            real = Path(str(shutil.which(program)))
        make_executable(rig.bin / program, f'#!/usr/bin/env bash\necho "{program} ${{BWS_ACCESS_TOKEN:-none}} ${{NEOAPRS_SIGNING_SECRET_ID:-none}}" >> "{seen}"\nexec "{real}" "$@"\n')
    token = secrets.token_hex(16)
    rig.env["BWS_ACCESS_TOKEN"] = token
    done = rig.release()
    assert done.returncode == 0, done.stdout + done.stderr
    lines = seen.read_text(encoding="utf-8").splitlines()
    assert {line.split()[0] for line in lines} == {"git", "gh", "bws"}
    assert [line for line in lines if line.split()[1:] != ["none", "none"]] == [f"bws {token} {rig.env['NEOAPRS_SIGNING_SECRET_ID']}"]
    assert "push refs/heads/master" in rig.calls() and "check" in rig.calls(), "git push and scripts/check ran"


def test_a_key_that_is_not_the_programs_signs_nothing_and_the_release_stays_a_draft(rig: Rig) -> None:
    rig.seed_file.write_text(base64.b64encode(bytes(32)).decode(), encoding="ascii")
    done = rig.release()
    assert done.returncode == 1 and "is not the one whose public half the program carries" in done.stdout and "nothing is signed" in done.stdout
    assert state(rig)["draft"] is True and "upload" not in rig.kinds() and state(rig)["assets"] == ASSETS


@pytest.mark.parametrize(("value", "why"), [("not base64!", "is not the base64 of the signing key's seed"), (base64.b64encode(bytes(31)).decode(), "is not the base64 of a 32-byte seed")])
def test_a_secret_that_is_not_a_seed_is_refused_without_its_value(rig: Rig, value: str, why: str) -> None:
    rig.seed_file.write_text(value, encoding="ascii")
    done = rig.release()
    assert done.returncode == 1 and why in done.stdout and value not in done.stdout and state(rig)["draft"] is True


def test_a_secret_bws_cannot_read_or_none_named_signs_nothing(rig: Rig) -> None:
    rig.env["NEOAPRS_SIGNING_SECRET_ID"] = "00000000-0000-0000-0000-000000000000"
    done = rig.release()
    assert done.returncode == 1 and "bws could not read the secret 00000000-0000-0000-0000-000000000000 (exit code 1): Error: 404 Resource not found" in done.stdout
    del rig.env["NEOAPRS_SIGNING_SECRET_ID"]
    unnamed = rig.release()
    assert unnamed.returncode == 1 and "NEOAPRS_SIGNING_SECRET_ID names no secret" in unnamed.stdout
    assert state(rig)["draft"] is True and "upload" not in rig.kinds()
    rig.env["NEOAPRS_SIGNING_SECRET_ID"] = "00000000-0000-4000-8000-000000000001"
    assert rig.release().returncode == 0, "and with the secret named, the same command signs and publishes"
    assert_released(rig)


def test_a_list_that_names_a_file_twice_is_not_signed(rig: Rig) -> None:
    rig.state["release"]["files"]["SHA256SUMS"] = SUMS + SUMS.splitlines(keepends=True)[0]
    rig.save_state()
    done = rig.release()
    assert done.returncode == 1 and "the draft's SHA256SUMS is not signed" in done.stdout and "twice" in done.stdout and "bws" not in rig.kinds()


def test_a_draft_signed_already_is_only_published(rig: Rig) -> None:
    rig.state["release"].update(assets=SIGNED, files={"SHA256SUMS": SUMS, "SHA256SUMS.sig": sign(SUMS.encode(), VERSION, rig.seed)})
    rig.save_state()
    done = rig.release()
    assert done.returncode == 0, done.stdout + done.stderr
    assert "skipped: SHA256SUMS.sig holds already; the release is published" in done.stdout and "bws" not in rig.kinds() and "upload" not in rig.kinds() and rig.kinds().count("edit") == 1
    assert_released(rig)


@pytest.mark.parametrize("signature", [None, "another-version", "another-key"])
def test_a_draft_whose_signature_does_not_hold_is_signed_again(rig: Rig, signature: str | None) -> None:
    files = {"SHA256SUMS": SUMS}
    if signature == "another-version":
        files["SHA256SUMS.sig"] = sign(SUMS.encode(), "0.9.0", rig.seed)
    elif signature == "another-key":
        files["SHA256SUMS.sig"] = sign(SUMS.encode(), VERSION, bytes(32))
    rig.state["release"].update(assets=SIGNED if signature else ASSETS, files=files)
    rig.save_state()
    done = rig.release()
    assert done.returncode == 0, done.stdout + done.stderr
    assert rig.kinds().count("bws") == 1 and state(rig)["files"]["SHA256SUMS.sig"] == sign(SUMS.encode(), VERSION, rig.seed)  # type: ignore[index]


def test_a_published_release_is_never_signed_after_the_fact(rig: Rig) -> None:
    rig.state["release"]["draft"] = False
    rig.save_state()
    done = rig.release()
    assert done.returncode == 1 and "is published and its SHA256SUMS.sig does not hold" in done.stdout and "bws" not in rig.kinds()


def test_verify_checks_the_published_release_and_changes_nothing(rig: Rig) -> None:
    assert rig.release().returncode == 0
    before = rig.load_state()
    marker = len(rig.calls())
    done = rig.release("--verify")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "SHA256SUMS.sig holds with the program's public key" in done.stdout and "[1/" not in done.stdout
    new = rig.calls()[marker:]
    assert all(c.startswith(("gh release view", "gh release download")) for c in new), new
    assert rig.load_state() == before


@pytest.mark.parametrize(("change", "why"), [
    ("another-list", "is not the project's signature"),
    ("another-version", "as the list of v0.9.1"),
    ("truncated", "not the 64 of a signature"),
    ("draft", "still a draft"),
    ("file-missing", "SHA256SUMS does not name the files of the release: missing ['install.sh']"),
])
def test_verify_refuses_a_release_whose_signature_does_not_hold(rig: Rig, change: str, why: str) -> None:
    assert rig.release().returncode == 0
    rig.state = rig.load_state()
    files = rig.state["release"]["files"]
    other = SUMS.replace(hashlib.sha256(b"install.sh").hexdigest(), hashlib.sha256(b"changed").hexdigest())
    if change == "another-list":
        files["SHA256SUMS"] = other
    elif change == "another-version":
        files["SHA256SUMS.sig"] = sign(SUMS.encode(), "0.9.0", rig.seed)
    elif change == "truncated":
        files["SHA256SUMS.sig"] = base64.b64encode(base64.b64decode(files["SHA256SUMS.sig"])[:60]).decode()
    elif change == "draft":
        rig.state["release"]["draft"] = True
    else:
        files["SHA256SUMS"] = "".join(line for line in SUMS.splitlines(keepends=True) if not line.endswith(" install.sh\n"))
        files["SHA256SUMS.sig"] = sign(files["SHA256SUMS"].encode(), VERSION, rig.seed)
    rig.save_state()
    done = rig.release("--verify")
    assert done.returncode == 1 and why in done.stdout, done.stdout
    assert TAG in done.stdout
